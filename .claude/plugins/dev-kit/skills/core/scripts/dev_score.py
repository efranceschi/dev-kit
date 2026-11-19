#!/usr/bin/env python3
"""dev_score.py - deterministic quality score from auditor findings.

Standard library only. Usage:
  python3 -I dev_score.py score --scope M1 [--kind gate|review] [--out FILE] [--root DIR] [--previous FINDINGS_JSON] [--round N] AUDITOR_JSON [AUDITOR_JSON ...]

Each input file is one auditor result following shared/prompts/auditor-output-contract.md.

Scoring rule (reproducible, no judgement involved)
  dimension score = 100 - sum(penalty per finding)         penalties: critical 40, high 20, medium 8, low 2
  a finding with "confidence": "low" counts half
  caps: any critical finding -> dimension score <= 40; any high finding -> <= 69
  low cap: the low penalties of one dimension add up to at most autonomy.quality.low_cap (default 10)
  dedupe: findings of several auditors in one dimension with the same (file, line), or the same
          normalised title and file, count once (highest severity kept)
  delta (--previous, rounds >= 2): previous findings stay scored unless an auditor of their dimension
          marks them "closed" in its "previous" list (omitted = still open); new critical/high/medium
          findings score; new low findings are recorded as deferred and do not score
  overall = weighted average of the dimensions that ran (weights from .dev/state.json autonomy.quality.weights)

Verdict = pass only when ALL hold
  1. no open finding with severity in block_on (default critical, high)
  2. every dimension >= its minimum (autonomy.quality.dimension_min[dim], else min_dimension)
  3. overall >= min_overall (gate) or review_min_overall (review)
  4. every auditor that ran returned a parsable result (missing/invalid input => fail)

Exit codes: 0 pass · 1 fail · 2 usage/input error
Output: table on stdout, JSON in --out (default: next to the first input, scores.json).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir; dev_telemetry lives next to us
import dev_telemetry as tel  # noqa: E402

AUDITOR_DIMENSION = {
    "code-reviewer": "code",
    "security-auditor": "security",
    "test-auditor": "tests",
    "spec-tracer": "spec",
    "usability-auditor": "ux",
    "a11y-auditor": "a11y",
    "visual-reviewer": "visual",
    "copy-reviewer": "copy",
    "performance-auditor": "performance",
    "data-reviewer": "data",
    "ops-reviewer": "operations",
    "deps-auditor": "dependencies",
    "docs-reviewer": "docs",
    "design-reviewer": "design",
    "requirements-reviewer": "requirements",
}
PENALTY = {"critical": 40, "high": 20, "medium": 8, "low": 2}
DEFAULT_QUALITY = {
    "min_overall": 85,
    "min_dimension": 70,
    "dimension_min": {"security": 90, "tests": 80, "spec": 85, "a11y": 80},
    "review_min_overall": 80,
    "block_on": ["critical", "high"],
    "low_cap": 10,
    "weights": {
        "code": 15, "security": 15, "tests": 15, "spec": 15, "ux": 8, "a11y": 8,
        "visual": 6, "copy": 3, "performance": 6, "data": 4, "operations": 3,
        "dependencies": 2, "docs": 5, "design": 10, "requirements": 10,
    },
}


def load_quality(root: Path) -> dict:
    q = json.loads(json.dumps(DEFAULT_QUALITY))
    for p in [root, *root.parents]:
        sp = p / ".dev" / "state.json"
        if sp.exists():
            try:
                cur = json.loads(sp.read_text(encoding="utf-8")).get("autonomy", {}).get("quality", {})
            except (json.JSONDecodeError, OSError):
                cur = {}
            for k, v in cur.items():
                if isinstance(v, dict) and isinstance(q.get(k), dict):
                    q[k].update(v)
                else:
                    q[k] = v
            break
    return q


def severity(f: dict) -> str:
    sev = str(f.get("severity", "low")).lower()
    return sev if sev in PENALTY else "low"


def dimension_score(findings: list[dict], low_cap: float | None = None) -> tuple[int, dict]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    penalty = 0.0
    low_penalty = 0.0
    for f in findings:
        sev = severity(f)
        counts[sev] += 1
        w = 0.5 if str(f.get("confidence", "high")).lower() == "low" else 1.0
        if sev == "low":
            low_penalty += PENALTY[sev] * w
        else:
            penalty += PENALTY[sev] * w
    if low_cap is not None:
        low_penalty = min(low_penalty, float(low_cap))
    penalty += low_penalty
    score = max(0, round(100 - penalty))
    if counts["critical"]:
        score = min(score, 40)
    elif counts["high"]:
        score = min(score, 69)
    return score, counts


def _norm(s: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(s or "").lower()))


def dedupe_key(f: dict) -> tuple:
    file = str(f.get("file") or "").strip().lower()
    if file and f.get("line") not in (None, ""):
        return ("loc", file, str(f.get("line")))
    return ("title", _norm(f.get("title")), file)


def merge_findings(findings: list[dict]) -> list[dict]:
    """Collapse findings reported by *different* audits (input files) with the same key; keep the
    highest severity and the list of auditors. Findings of one audit are never merged with each other:
    the auditor already merged its own duplicates (output contract)."""
    order = ["low", "medium", "high", "critical"]
    merged: dict[tuple, dict] = {}
    for f in findings:
        k = dedupe_key(f)
        src = f.get("_src")
        n = 0
        while (k + (n,)) in merged and src in merged[k + (n,)]["_srcs"]:
            n += 1
        key = k + (n,)
        if key not in merged:
            merged[key] = dict(f)
            merged[key]["_srcs"] = [src]
            merged[key]["auditors"] = [f.get("_auditor")] if f.get("_auditor") else []
            continue
        m = merged[key]
        m["_srcs"].append(src)
        if f.get("_auditor") and f["_auditor"] not in m["auditors"]:
            m["auditors"].append(f["_auditor"])
        if order.index(severity(f)) > order.index(severity(m)):
            m["severity"] = severity(f)
        if str(m.get("confidence", "high")).lower() == "low" and str(f.get("confidence", "high")).lower() != "low":
            m["confidence"] = f.get("confidence", "high")
    return list(merged.values())


def finding_dimension(f: dict) -> str | None:
    if f.get("dimension") in AUDITOR_DIMENSION.values():
        return f["dimension"]
    aud = f.get("auditor") or f.get("auditors")
    for a in ([aud] if isinstance(aud, str) else (aud or [])):
        if a in AUDITOR_DIMENSION:
            return AUDITOR_DIMENSION[a]
    return None


def load_previous(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("findings", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("previous findings must be a list or {\"findings\": [...]}")
    return [f for f in items if isinstance(f, dict)]


def evaluate(inputs: list[Path], quality: dict, kind: str, scope: str, previous: list[dict] | None = None) -> dict:
    dims: dict[str, dict] = {}
    problems: list[str] = []
    marks: dict[str, dict[str, str]] = {}  # dimension -> previous id -> closed|open
    for path in inputs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{path.name}: unreadable or invalid JSON ({e})")
            continue
        auditor = data.get("auditor", "")
        dim = AUDITOR_DIMENSION.get(auditor)
        if dim is None:
            problems.append(f"{path.name}: unknown auditor '{auditor}'")
            continue
        findings = data.get("findings")
        if not isinstance(findings, list):
            problems.append(f"{path.name}: missing 'findings' list")
            continue
        entry = dims.setdefault(dim, {"auditors": [], "findings": [], "score": 100})
        if auditor not in entry["auditors"]:
            entry["auditors"].append(auditor)
        entry["findings"] += [{**f, "_auditor": auditor, "_src": str(path)} for f in findings if isinstance(f, dict)]
        entry["stats"] = data.get("stats", {})
        for pv in data.get("previous") or []:
            if isinstance(pv, dict) and pv.get("id"):
                state = str(pv.get("state", "open")).lower()
                cur = marks.setdefault(dim, {}).get(pv["id"])
                # "open" from any auditor wins over "closed"
                marks[dim][pv["id"]] = "open" if "open" in (state, cur) else "closed"
    low_cap = quality.get("low_cap")
    delta = None
    if previous is not None:
        delta = {"closed": 0, "still_open": 0, "new_scored": 0, "new_deferred": 0}
        prev_by_dim: dict[str, list[dict]] = {}
        for f in previous:
            d = finding_dimension(f)
            if d is not None:
                prev_by_dim.setdefault(d, []).append(f)
        for d, entry in dims.items():
            prev = prev_by_dim.get(d, [])
            prev_keys = {dedupe_key(f) for f in prev}
            kept = []
            for f in prev:
                if marks.get(d, {}).get(f.get("id")) == "closed":
                    delta["closed"] += 1
                else:
                    delta["still_open"] += 1
                    kept.append({**f, "_previous": True})
            deferred = []
            for f in merge_findings(entry["findings"]):
                if dedupe_key(f) in prev_keys:
                    continue  # same as a previous finding: already counted (or closed)
                if severity(f) == "low":
                    deferred.append(f)
                    delta["new_deferred"] += 1
                else:
                    kept.append(f)
                    delta["new_scored"] += 1
            entry["findings"] = kept
            entry["deferred"] = len(deferred)
    for entry in dims.values():
        entry["findings"] = merge_findings(entry["findings"]) if previous is None else entry["findings"]
        entry["score"], entry["counts"] = dimension_score(entry["findings"], low_cap)
    weights = quality["weights"]
    total_w = sum(weights.get(d, 5) for d in dims)
    overall = round(sum(weights.get(d, 5) * v["score"] for d, v in dims.items()) / total_w) if total_w else 0

    block_on = set(quality.get("block_on", ["critical", "high"]))
    blockers = []
    reasons = []
    for d, v in sorted(dims.items()):
        for f in v["findings"]:
            if str(f.get("severity", "")).lower() in block_on:
                blockers.append({"dimension": d, "id": f.get("id"), "severity": f.get("severity"), "title": f.get("title"), "file": f.get("file"), "line": f.get("line")})
        minimum = quality["dimension_min"].get(d, quality["min_dimension"])
        v["min"] = minimum
        v["ok"] = v["score"] >= minimum
        if not v["ok"]:
            reasons.append(f"{d} score {v['score']} < {minimum}")
    if blockers:
        reasons.insert(0, f"{len(blockers)} blocking finding(s) ({'/'.join(sorted(block_on))})")
    cut = quality["review_min_overall"] if kind == "review" else quality["min_overall"]
    if overall < cut:
        reasons.append(f"overall {overall} < {cut}")
    reasons += problems
    if not dims:
        reasons.append("no valid auditor results")
    for v in dims.values():
        v.pop("findings", None)
    return {
        "scope": scope, "kind": kind, "overall": overall, "cutoff": cut,
        "dimensions": dims, "blockers": blockers, "problems": problems,
        "verdict": "pass" if not reasons else "fail", "reasons": reasons,
        **({"delta": delta} if delta is not None else {}),
    }


def render(res: dict) -> str:
    lines = [f"Quality score for {res['scope']} ({res['kind']})", "",
             f"{'dimension':<14}{'score':>6}{'min':>6}  {'crit':>4}{'high':>5}{'med':>5}{'low':>5}  auditors"]
    for d, v in sorted(res["dimensions"].items()):
        c = v["counts"]
        mark = "" if v["ok"] else "  <-- below minimum"
        lines.append(f"{d:<14}{v['score']:>6}{v['min']:>6}  {c['critical']:>4}{c['high']:>5}{c['medium']:>5}{c['low']:>5}  {', '.join(v['auditors'])}{mark}")
    lines += ["", f"overall {res['overall']} (cut-off {res['cutoff']}) -> {res['verdict'].upper()}"]
    if res.get("delta"):
        dl = res["delta"]
        lines.append(f"delta: {dl['closed']} closed · {dl['still_open']} still open · {dl['new_scored']} new scored · {dl['new_deferred']} new low deferred")
    for r in res["reasons"]:
        lines.append(f"  - {r}")
    for b in res["blockers"][:15]:
        lines.append(f"  * [{b['severity']}] {b['dimension']} {b['id']}: {b['title']} ({b['file']}:{b['line']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--scope", required=True)
    s.add_argument("--kind", choices=["gate", "review"], default="gate")
    s.add_argument("--out")
    s.add_argument("--root", default=".")
    s.add_argument("--json", action="store_true", help="print JSON instead of the table")
    s.add_argument("--previous", help="consolidated findings of the previous round (delta mode)")
    s.add_argument("--round", type=int, help="round number, for the session log")
    s.add_argument("inputs", nargs="+")
    a = p.parse_args(argv)
    paths = [Path(x) for x in a.inputs]
    missing = [str(x) for x in paths if not x.exists()]
    if missing:
        print("dev_score: input not found: " + ", ".join(missing), file=sys.stderr)
        return 2
    quality = load_quality(Path(a.root).resolve())
    previous = None
    if a.previous:
        try:
            previous = load_previous(Path(a.previous))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"dev_score: cannot read --previous: {e}", file=sys.stderr)
            return 2
    res = evaluate(paths, quality, a.kind, a.scope, previous)
    out = Path(a.out) if a.out else paths[0].parent / "scores.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False) if a.json else render(res))
    root = Path(a.root).resolve()
    dev = next((d / ".dev" for d in [root, *root.parents] if (d / ".dev" / "state.json").exists()), None)
    if dev is not None:
        tel.safe_emit(dev, "score", {
            "scope": tel.scope_token(a.scope), "kind": a.kind, "round": a.round, "overall": res["overall"],
            "cutoff": res["cutoff"], "verdict": res["verdict"], "blockers": len(res["blockers"]),
            "auditors": sum(len(v["auditors"]) for v in res["dimensions"].values()),
            "dimensions": {d: v["score"] for d, v in res["dimensions"].items()},
            "delta": res.get("delta")})
    return 0 if res["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
