#!/usr/bin/env python3
"""dev_score.py - deterministic quality score from auditor findings.

Standard library only. Usage:
  python3 -I dev_score.py score --scope M1 [--kind gate|review] [--out FILE] [--root DIR] [--previous FINDINGS_JSON] [--round N] AUDITOR_JSON [AUDITOR_JSON ...]
  python3 -I dev_score.py check [--fix] [--json] AUDITOR_JSON [AUDITOR_JSON ...]
  python3 -I dev_score.py consolidate --scope M1 --round N --out-dir DIR [--kind gate|review] [--previous F] AUDITOR_JSON ...
  python3 -I dev_score.py select --previous FINDINGS --auditors a,b,c (--since SHA | --changed-from FILE) [--json]

consolidate writes findings.json and findings-round-<N>.json (previous open findings keep their ids, new ones get
the next ids, deferred and legacy listed apart). select says which auditors a re-run needs: those with open
findings or with changed files in their dimension; the others keep their result ("carried": true).

check validates auditor files against the output contract and normalises the common drift (previous[].status ->
state, severity and state synonyms, missing or repeated ids, missing auditor taken from the file name, a JSON
block wrapped in prose). --fix writes the normalised file back. Exit 1 lists what the agent must correct.

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
          findings score; new low findings, and (document reviews only, --kind review) new findings below
          critical marked "in_change": false (text the revision did not touch), are recorded as deferred; "convergence" reports blockers and
          the medium trend against the previous round
  contradicts: a finding with "contradicts": "F-nnn" (it reverses an earlier recommendation) is capped at medium
          and listed in "conflicts" for an ADR
  legacy: findings with "legacy": true (existing projects: a problem already present at the brownfield
          baseline and not made worse by the scope) never score or block; they are listed in "legacy"
          so the orchestrator registers them as issues
  challenges (--challenges .dev/qa/<M>/challenges.json, from `dev_state.py challenge record`): a critical/high
          finding another role or model disputed with evidence does not score and gets no fix task (listed as
          "disputed"), except a critical security finding, which keeps blocking; refine rewrites the severity;
          a challenge holds only while the files it judged are unchanged
  exit_check: spec-tracer's "exit_check" {"result": "pass"|"fail", "checks": [...]} becomes "exit"; a fail fails
          the verdict (never a partial score)
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
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir; dev_telemetry lives next to us
import dev_telemetry as tel  # noqa: E402
import dev_ids as dids  # noqa: E402

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


SEVERITY_ALIASES = {
    "critical": "critical", "crit": "critical", "blocker": "critical", "blocking": "critical", "fatal": "critical",
    "high": "high", "major": "high", "error": "high", "severe": "high", "serious": "high",
    "medium": "medium", "med": "medium", "moderate": "medium", "warning": "medium", "warn": "medium", "minor": "medium",
    "low": "low", "info": "low", "informational": "low", "nit": "low", "nitpick": "low", "trivial": "low",
    "suggestion": "low", "style": "low", "cosmetic": "low",
}
STATE_ALIASES = {
    "closed": "closed", "fixed": "closed", "resolved": "closed", "done": "closed", "verified": "closed",
    "addressed": "closed", "not_reproducible": "closed",
    "open": "open", "still_open": "open", "not_fixed": "open", "unresolved": "open", "partial": "open",
    "partially_fixed": "open", "regressed": "open", "reopened": "open",
}


def _key(v: object) -> str:
    return re.sub(r"[\s-]+", "_", str(v or "").strip().lower())


def auditor_from_name(path: Path | None) -> str | None:
    if path is None:
        return None
    stem = re.sub(r"-\d+$", "", path.stem)
    return stem if stem in AUDITOR_DIMENSION else None


def normalize(data: object, path: Path | None = None) -> tuple[dict | None, list[str], list[str]]:
    """Normalise one auditor result in place. Returns (data, changes, errors); errors are contract violations the
    agent must fix (no findings list, unknown auditor or severity)."""
    changes: list[str] = []
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, changes, ["top level must be a JSON object"]
    aud = data.get("auditor")
    if aud not in AUDITOR_DIMENSION:
        guess = auditor_from_name(path)
        if guess and not aud:
            data["auditor"] = guess
            changes.append(f"auditor set to '{guess}' from the file name")
        else:
            errors.append(f"unknown auditor '{aud}' (use your exact agent name: {', '.join(sorted(AUDITOR_DIMENSION))})")
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("missing 'findings' list (use [] when there is nothing to report)")
        findings = []
    seen: set[str] = set()
    used = {str(f.get("id")) for f in findings if isinstance(f, dict) and f.get("id")}
    nxt = 1
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] is not an object")
            continue
        raw = f.get("severity")
        sev = SEVERITY_ALIASES.get(_key(raw))
        if sev is None:
            errors.append(f"findings[{i}] severity '{raw}' is not one of critical, high, medium, low")
        elif sev != raw:
            f["severity"] = sev
            changes.append(f"findings[{i}] severity '{raw}' -> '{sev}'")
        fid = str(f.get("id") or "")
        if not fid or fid in seen:
            while f"F-{nxt:03d}" in used or f"F-{nxt:03d}" in seen:
                nxt += 1
            new = f"F-{nxt:03d}"
            changes.append(f"findings[{i}] id '{fid or '-'}' -> '{new}'")
            f["id"] = fid = new
        seen.add(fid)
        if isinstance(f.get("confidence"), str) and f["confidence"].strip().lower() not in ("high", "low"):
            f["confidence"] = "low" if f["confidence"].strip().lower() in ("medium", "med", "unverified", "inferred") else "high"
            changes.append(f"findings[{i}] confidence normalised to '{f['confidence']}'")
    prev = data.get("previous")
    if prev is not None and not isinstance(prev, list):
        errors.append("'previous' must be a list")
    for i, pv in enumerate(prev if isinstance(prev, list) else []):
        if not isinstance(pv, dict):
            errors.append(f"previous[{i}] is not an object")
            continue
        if "state" not in pv and "status" in pv:
            pv["state"] = pv.pop("status")
            changes.append(f"previous[{i}] 'status' renamed to 'state'")
        raw = pv.get("state")
        st = STATE_ALIASES.get(_key(raw))
        if st is None:
            st = "open"
            changes.append(f"previous[{i}] state '{raw}' is unclear -> 'open'")
        elif st != raw:
            changes.append(f"previous[{i}] state '{raw}' -> '{st}'")
        pv["state"] = st
        if not pv.get("id"):
            errors.append(f"previous[{i}] has no id (copy the id of the previous finding)")
    return data, changes, errors


def read_result(path: Path) -> tuple[object, bool]:
    """Parse an auditor file. Accepts a pure JSON file or, as a fallback, a message whose last fenced json block
    is the result. Returns (data, wrapped)."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        blocks = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.S)
        for b in reversed(blocks):
            try:
                return json.loads(b), True
            except json.JSONDecodeError:
                continue
        raise


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
    # legacy findings (pre-existing debt in existing projects) never score, in any round (conventions §16)
    return [f for f in items if isinstance(f, dict) and not f.get("legacy") and not f.get("out_of_scope")]


def files_fp(root: Path, files: list[str]) -> str:
    """Same fingerprint as dev_state.files_fp: a challenge holds while the files it judged are unchanged."""
    h = hashlib.sha256()
    for f in sorted(set(files)):
        h.update(f.encode() + b"\0")
        try:
            h.update((root / f).read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:16]


def load_challenges(path: Path | None, root: Path) -> list[dict]:
    """Challenges recorded by `dev_state.py challenge record` whose cited files did not change since (§7)."""
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for c in (data.values() if isinstance(data, dict) else data):
        if isinstance(c, dict) and c.get("verdict") in ("agree", "dispute", "refine"):
            if c.get("files_fp") and files_fp(root, c.get("files") or []) != c["files_fp"]:
                continue  # the code changed: the finding is judged again
            out.append(c)
    return out


def apply_challenges(dims: dict, challenges: list[dict]) -> tuple[list[dict], list[dict]]:
    """agree: marked; refine: new severity; dispute: out of the score (listed as disputed), except a critical
    security finding, which keeps blocking. Returns (disputed, disputed security findings kept)."""
    disputed, kept_sec = [], []
    for d, entry in dims.items():
        keep = []
        for f in entry["findings"]:
            c = next((c for c in challenges if c.get("dimension") == d and (
                (str(c.get("original_id")) == str(f.get("id")) and c.get("auditor") == f.get("_auditor"))
                or dedupe_key(c) == dedupe_key(f))), None)
            if c is None:
                keep.append(f)
                continue
            f = {**f, "challenged": c["verdict"], "challenge_evidence": c.get("evidence"), "challenger": c.get("challenger")}
            if c["verdict"] == "refine":
                f["severity_reported"] = severity(f)
                f["severity"] = (c.get("refined") or {}).get("severity") or f["severity"]
                keep.append(f)
            elif c["verdict"] == "dispute":
                if d == "security" and severity(f) == "critical":
                    kept_sec.append(f)
                    keep.append(f)
                else:
                    disputed.append({**f, "dimension": d})
            else:
                keep.append(f)
        entry["findings"] = keep
    return disputed, kept_sec


def evaluate(inputs: list[Path], quality: dict, kind: str, scope: str, previous: list[dict] | None = None,
             keep: dict | None = None, challenges: list[dict] | None = None) -> dict:
    dims: dict[str, dict] = {}
    problems: list[str] = []
    marks: dict[str, dict[str, str]] = {}  # dimension -> previous id -> closed|open
    legacy: list[dict] = []
    exits: list[dict] = []
    for path in inputs:
        try:
            data, _ = read_result(path)
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{path.name}: unreadable or invalid JSON ({e})")
            continue
        data, _, errors = normalize(data, path)
        if errors:
            problems += [f"{path.name}: {e}" for e in errors]
            continue
        auditor = data.get("auditor", "")
        dim = AUDITOR_DIMENSION[auditor]
        findings = data["findings"]
        entry = dims.setdefault(dim, {"auditors": [], "findings": [], "score": 100})
        if auditor not in entry["auditors"]:
            entry["auditors"].append(auditor)
        if data.get("carried"):
            entry["carried"] = True  # not re-run this round: its result was kept (conventions.md §18)
        if data.get("incomplete"):
            # the auditor stalled or ran out of time (`dev_state.py qa-watch --settle`): its dimension is not judged
            # this round, the gate cannot pass, no fix task comes from it, and the next round re-runs only it
            entry["incomplete"] = str(data["incomplete"])[:160]
            problems.append(f"{auditor} did not finish ({entry['incomplete']}): the next round re-runs it")
        for f in findings:
            if not isinstance(f, dict):
                continue
            if f.get("legacy") is True or f.get("out_of_scope") is True:
                # pre-existing debt (brownfield) or a problem in shared code the scope did not touch (a global
                # component): never scored here, registered as an issue by the orchestrator
                legacy.append({"dimension": dim, "auditor": auditor, "id": f.get("id"), "severity": f.get("severity"),
                               "title": f.get("title"), "file": f.get("file"), "line": f.get("line"),
                               **({"reason": "out_of_scope"} if f.get("out_of_scope") is True and f.get("legacy") is not True else {})})
            else:
                entry["findings"].append({**f, "_auditor": auditor, "_src": str(path)})
        entry["stats"] = data.get("stats", {})
        ec = data.get("exit_check")
        if ec is not None:  # the milestone's exit check, run by spec-tracer: pass or fail, never a partial score
            if not isinstance(ec, dict) or ec.get("result") not in ("pass", "fail"):
                problems.append(f"{path.name}: exit_check must be {{\"result\": \"pass\"|\"fail\", \"checks\": [...]}}")
                exit_res = {"result": "fail", "checks": [], "invalid": True}
            else:
                checks = [c for c in ec.get("checks") or [] if isinstance(c, dict)]
                bad = ec["result"] == "fail" or any(c.get("result") != "pass" for c in checks)
                exit_res = {"result": "fail" if bad else "pass", "checks": checks}
            exits.append(exit_res)
        for pv in data.get("previous") or []:
            if isinstance(pv, dict) and pv.get("id"):
                state = str(pv.get("state", "open")).lower()
                cur = marks.setdefault(dim, {}).get(pv["id"])
                # "open" from any auditor wins over "closed"
                marks[dim][pv["id"]] = "open" if "open" in (state, cur) else "closed"
    disputed, kept_sec = apply_challenges(dims, challenges) if challenges else ([], [])
    low_cap = quality.get("low_cap")
    delta = None
    conv_prev: dict[str, int] = {}
    # a finding that contradicts a recommendation of an earlier round (ping-pong) is capped at medium and listed:
    # the orchestrator settles it with an ADR instead of applying one more reversal
    conflicts = []
    for d, entry in dims.items():
        for f in entry["findings"]:
            if f.get("contradicts"):
                if severity(f) in ("critical", "high"):
                    f["severity_reported"] = severity(f)
                    f["severity"] = "medium"
                conflicts.append({"dimension": d, "id": f.get("id"), "contradicts": f.get("contradicts"), "title": f.get("title")})
    if previous is not None:
        delta = {"closed": 0, "still_open": 0, "new_scored": 0, "new_deferred": 0, "new_outside_change": 0}
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
                # round >= 2 judges the revision: lows, and anything short of critical in text the revision did not
                # touch ("in_change": false), are recorded but do not score
                outside = kind == "review" and f.get("in_change") is False and severity(f) != "critical"
                if severity(f) == "low" or outside:
                    deferred.append(f)
                    delta["new_deferred"] += 1
                    delta["new_outside_change"] += int(outside)
                else:
                    kept.append(f)
                    delta["new_scored"] += 1
            entry["findings"] = kept
            entry["deferred"] = len(deferred)
            entry["_deferred"] = deferred
            prev_med = sum(1 for f in prev if severity(f) == "medium")
            conv_prev[d] = prev_med
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
    exit_res = None
    if exits:
        exit_res = {"result": "fail" if any(e["result"] == "fail" for e in exits) else "pass",
                    "checks": [c for e in exits for c in e["checks"]]}
        if exit_res["result"] == "fail":
            failed = [str(c.get("check")) for c in exit_res["checks"] if c.get("result") != "pass"]
            reasons.append("exit_check failed" + (f": {', '.join(failed)}" if failed else ""))
    for f in kept_sec:
        reasons.append(f"security critical {f.get('id')} disputed: it keeps blocking until the user decides (Needs you)")
    reasons += problems
    if not dims:
        reasons.append("no valid auditor results")
    convergence = None
    if previous is not None:
        mediums = sum(v["counts"]["medium"] for v in dims.values())
        mediums_prev = sum(conv_prev.values())
        trend = "falling" if mediums < mediums_prev else ("flat" if mediums == mediums_prev else "rising")
        convergence = {"blockers": len(blockers), "mediums": mediums, "mediums_prev": mediums_prev, "trend": trend,
                       "converged": not blockers and trend in ("falling", "flat")}
    kept_all, deferred_all = [], []
    for d, v in dims.items():
        kept_all += [{**f, "dimension": d} for f in v.pop("findings", None) or []]
        deferred_all += [{**f, "dimension": d} for f in v.pop("_deferred", None) or []]
    if keep is not None:
        keep["findings"], keep["deferred"] = kept_all, deferred_all
        keep["disputed"] = disputed
    return {
        "scope": scope, "kind": kind, "overall": overall, "cutoff": cut,
        "dimensions": dims, "blockers": blockers, "problems": problems,
        "verdict": "pass" if not reasons else "fail", "reasons": reasons,
        **({"exit": exit_res} if exit_res is not None else {}),
        **({"disputed": [{k: f.get(k) for k in ("id", "dimension", "severity", "title", "file", "line", "challenger")} for f in disputed]}
           if disputed else {}),
        **({"delta": delta} if delta is not None else {}),
        **({"convergence": convergence} if convergence is not None else {}),
        **({"conflicts": conflicts} if conflicts else {}),
        **({"legacy": legacy} if legacy else {}),
    }


def render(res: dict) -> str:
    lines = [f"Quality score for {res['scope']} ({res['kind']})", "",
             f"{'dimension':<14}{'score':>6}{'min':>6}  {'crit':>4}{'high':>5}{'med':>5}{'low':>5}  auditors"]
    for d, v in sorted(res["dimensions"].items()):
        c = v["counts"]
        mark = f"  <-- did not finish ({v['incomplete']})" if v.get("incomplete") else ("" if v["ok"] else "  <-- below minimum")
        lines.append(f"{d:<14}{v['score']:>6}{v['min']:>6}  {c['critical']:>4}{c['high']:>5}{c['medium']:>5}{c['low']:>5}  {', '.join(v['auditors'])}{mark}")
    lines += ["", f"overall {res['overall']} (cut-off {res['cutoff']}) -> {res['verdict'].upper()}"]
    if res.get("delta"):
        dl = res["delta"]
        lines.append(f"delta: {dl['closed']} closed · {dl['still_open']} still open · {dl['new_scored']} new scored · {dl['new_deferred']} new deferred"
                     + (f" ({dl['new_outside_change']} outside the change)" if dl.get("new_outside_change") else ""))
    if res.get("convergence"):
        cv = res["convergence"]
        lines.append(f"convergence: {cv['blockers']} blocking · mediums {cv['mediums_prev']} -> {cv['mediums']} ({cv['trend']})"
                     + (" · converged" if cv["converged"] else ""))
    for c in res.get("conflicts", []):
        lines.append(f"conflict: {c['dimension']} {c['id']} contradicts {c['contradicts']} (capped at medium; settle with an ADR)")
    for f in res.get("disputed") or []:
        lines.append(f"disputed: {f['dimension']} {f['id']} ({f['severity']}) by {f.get('challenger')}: not scored, no fix task (Contested)")
    if res.get("legacy"):
        lines.append(f"legacy: {len(res['legacy'])} pre-existing finding(s) not scored (register them as issues)")
    if res.get("exit"):
        ex = res["exit"]
        lines.append(f"exit check: {ex['result'].upper()}" + "".join(f"\n  {'ok ' if c.get('result') == 'pass' else 'FAIL'} {c.get('check')}"
                                                             + (f" ({c['detail']})" if c.get("detail") else "") for c in ex["checks"]))
    for r in res["reasons"]:
        lines.append(f"  - {r}")
    for b in res["blockers"][:15]:
        lines.append(f"  * [{b['severity']}] {b['dimension']} {b['id']}: {b['title']} ({b['file']}:{b['line']})")
    return "\n".join(lines)


PUBLIC_KEYS = ("id", "severity", "category", "title", "file", "files", "line", "evidence", "failure_scenario",
               "recommendation", "acceptance_ref", "task_ref", "effort", "confidence", "partial", "in_change",
               "contradicts", "severity_reported", "challenged", "challenge_evidence", "challenger")


def _public(f: dict) -> dict:
    out = {k: f[k] for k in PUBLIC_KEYS if k in f and f[k] is not None}
    auds = f.get("auditors") or ([f["_auditor"]] if f.get("_auditor") else []) or ([f["auditor"]] if f.get("auditor") else [])
    out["auditor"] = auds[0] if auds else None
    if len(auds) > 1:
        out["auditors"] = auds
    out["dimension"] = f.get("dimension")
    if f.get("_previous"):
        out["previous"] = True
    return out


def consolidate(inputs: list[Path], quality: dict, kind: str, scope: str, previous: list[dict] | None,
                round_n: int, challenges: list[dict] | None = None) -> dict:
    """The consolidated findings of a round (qa §3.3): previous findings still open keep their id (auditors mark
    them by id in the next round), new scored findings get the next free ids, new lows and out-of-change findings
    are listed as deferred, legacy ones are left out (they become issues)."""
    keep: dict = {}
    res = evaluate(inputs, quality, kind, scope, previous, keep, challenges)
    if previous is None:  # round 1: merge_findings already merged duplicates per dimension
        keep["deferred"] = []
    used = {str(f.get("id")) for f in keep["findings"] if f.get("_previous")}
    nums = [dids.number(x) for x in used if dids.is_id("finding", x)]
    nxt = max(nums, default=0) + 1
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings, disputed = [], []
    pool = keep["findings"] + [{**f, "_disputed": True} for f in keep.get("disputed") or []]
    for f in sorted(pool, key=lambda f: (not f.get("_previous"), order.get(severity(f), 4), str(f.get("file")), str(f.get("line")))):
        pf = _public(f)
        if not f.get("_previous"):
            pf["original_id"] = f.get("id")
            pf["id"] = f"F-{nxt:03d}"
            nxt += 1
        # disputed findings keep their place in the numbering (ids stay stable when a challenge lands)
        (disputed if f.get("_disputed") else findings).append(pf)
    deferred = []
    for f in keep["deferred"]:
        pf = _public(f)
        pf["original_id"] = f.get("id")
        pf["id"] = f"D-{len(deferred) + 1:03d}"
        deferred.append(pf)
    # the same file and line reported by several dimensions: listed once per dimension (each scores in its own),
    # linked so fix-tasks creates one task
    by_loc: dict[tuple, list[dict]] = {}
    for f in findings:
        if f.get("file") and f.get("line") not in (None, ""):
            by_loc.setdefault((str(f["file"]).lower(), str(f["line"])), []).append(f)
    for group in by_loc.values():
        if len({g["dimension"] for g in group}) > 1:
            for g in group:
                g["same_as"] = [x["id"] for x in group if x is not g]
    carried = sorted(a for d, v in res["dimensions"].items() if v.get("carried") for a in v["auditors"])
    incomplete = sorted(a for d, v in res["dimensions"].items() if v.get("incomplete") for a in v["auditors"])
    return {"scope": scope, "kind": kind, "round": round_n, "verdict": res["verdict"], "overall": res["overall"],
            "findings": findings, "deferred": deferred, "disputed": disputed, "legacy": res.get("legacy", []), "carried": carried,
            "incomplete": incomplete,
            "delta": res.get("delta"), "convergence": res.get("convergence")}


DIMENSION_FILES = {
    # what a change must touch for an auditor to have something new to look at in a re-run (conventions.md §18);
    # an auditor with open findings always re-runs
    "copy": r"\.(tsx|jsx|vue|svelte|astro|html?|hbs|ejs|erb|jinja2?|j2|liquid|twig|po|pot|xliff|arb|strings)$|(^|/)(locales?|i18n|lang|messages|translations)/",
    "a11y": r"\.(tsx|jsx|vue|svelte|astro|html?|hbs|ejs|erb|jinja2?|j2|css|scss|sass|less|styl)$|(^|/)(components?|templates|views|pages|styles|theme)/",
    "visual": r"\.(tsx|jsx|vue|svelte|astro|html?|hbs|ejs|erb|jinja2?|j2|css|scss|sass|less|styl|svg)$|(^|/)(components?|templates|views|pages|styles|theme|tokens)/",
    "ux": r"\.(tsx|jsx|vue|svelte|astro|html?|hbs|ejs|erb|jinja2?|j2|css|scss)$|(^|/)(components?|templates|views|pages|routes)/",
    "data": r"(^|/)(migrations?|alembic|prisma|db|database|models?|schema|repositor(y|ies)|entities|sql)/|\.(sql|prisma)$|schema\.",
    "dependencies": r"(^|/)(package(-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|uv\.lock|Pipfile(\.lock)?|Cargo\.(toml|lock)|go\.(mod|sum)|Gemfile(\.lock)?|composer\.(json|lock))$",
    "operations": r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*|compose\.ya?ml|Makefile|Procfile|\.env\.example|\.github/|\.gitlab-ci|deploy|infra|ops|scripts|config|k8s|helm|systemd)(/|$|\.)|\.(service|ya?ml|toml|ini|conf)$",
    "docs": r"\.(md|mdx|rst|adoc)$|(^|/)docs?/",
}
CODE_DIMENSIONS = {"code", "security", "tests", "spec", "performance"}
NON_CODE = re.compile(r"(^|/)\.dev/|\.(md|mdx|rst|txt|png|jpe?g|gif|svg|ico)$|(^|/)docs?/")


def delivered(raw_dir: Path, head: str) -> dict[str, str]:
    """Auditors whose result an earlier round (interrupted, or failed only because another auditor did not finish)
    already delivered on this exact commit: a valid file in raw/, `sha` equal to `head` (a prefix of 7 or more
    characters on either side), not carried, not incomplete. Auditing the same commit again finds the same thing, so
    they are kept as they are instead of being spawned again (`--full` re-runs them). Returns auditor -> file name."""
    out: dict[str, str] = {}
    head = (head or "").strip().lower()
    if len(head) < 7 or not raw_dir.is_dir():
        return out
    for path in sorted(raw_dir.glob("*.json")):
        try:
            data, _ = read_result(path)
            data, _, errors = normalize(data, path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if errors or not isinstance(data, dict) or data.get("carried") or data.get("incomplete"):
            continue
        sha = str(data.get("sha") or "").strip().lower()
        if len(sha) < 7 or not (sha.startswith(head) or head.startswith(sha)):
            continue
        out.setdefault(str(data.get("auditor")), path.name)
    return out


def select(auditors: list[str], previous: list[dict], changed: list[str], keep: dict[str, str] | None = None) -> dict:
    open_dims: dict[str, int] = {}
    for f in previous:
        d = finding_dimension(f)
        if d:
            open_dims[d] = open_dims.get(d, 0) + 1
    rerun, carry, kept = [], [], []
    for aud in auditors:
        d = AUDITOR_DIMENSION.get(aud)
        if d is None:
            continue
        if keep and aud in keep:
            kept.append({"auditor": aud, "file": keep[aud], "why": "already delivered on this commit"})
            continue
        if open_dims.get(d):
            rerun.append({"auditor": aud, "why": f"{open_dims[d]} open finding(s)"})
            continue
        if d in CODE_DIMENSIONS:
            hits = [c for c in changed if not NON_CODE.search(c)]
        else:
            pat = DIMENSION_FILES.get(d)
            hits = [c for c in changed if pat and re.search(pat, c)]
        if hits:
            rerun.append({"auditor": aud, "why": f"{len(hits)} changed file(s) in its dimension", "files": hits[:50]})
        else:
            carry.append(aud)
    return {"rerun": rerun, "carry": carry, "keep": kept, "changed": len(changed)}


def cmd_select(a: argparse.Namespace) -> int:
    try:
        previous = load_previous(Path(a.previous)) if a.previous else []
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"dev_score: cannot read --previous: {e}", file=sys.stderr)
        return 2
    keep = delivered(Path(a.raw_dir), a.head) if a.raw_dir and a.head else {}
    auditors = [x.strip() for x in a.auditors.split(",") if x.strip()]
    if not a.previous:  # round 1 (or a retry of it): every auditor runs, except the ones already delivered
        res = {"rerun": [{"auditor": x, "why": "first round"} for x in auditors if x not in keep],
               "carry": [], "keep": [{"auditor": x, "file": keep[x], "why": "already delivered on this commit"}
                                     for x in auditors if x in keep], "changed": None}
        return print_select(res, a.json)
    if a.changed_from:
        changed = [x.strip() for x in Path(a.changed_from).read_text(encoding="utf-8").splitlines() if x.strip()]
    else:
        r = subprocess.run(["git", "-C", a.root, "diff", "--name-only", a.since, "HEAD"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"dev_score: git diff {a.since}..HEAD failed: {r.stderr.strip()}", file=sys.stderr)
            return 2
        changed = [x for x in r.stdout.splitlines() if x.strip()]
    return print_select(select(auditors, previous, changed, keep), a.json)


def print_select(res: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(res, indent=2))
    else:
        for x in res["keep"]:
            print(f"keep {x['auditor']}: {x['why']} ({x['file']}); do not spawn it")
        for x in res["rerun"]:
            print(f"rerun {x['auditor']}: {x['why']}")
        for x in res["carry"]:
            print(f"carry {x}: nothing new in its dimension; keep its previous result with \"carried\": true")
    return 0


def cmd_consolidate(a: argparse.Namespace) -> int:
    paths = [Path(x) for x in a.inputs]
    previous = None
    if a.previous:
        try:
            previous = load_previous(Path(a.previous))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"dev_score: cannot read --previous: {e}", file=sys.stderr)
            return 2
    root = Path(a.root).resolve()
    chal = load_challenges(Path(a.challenges), root) if a.challenges else None
    res = consolidate(paths, load_quality(root), a.kind, a.scope, previous, a.round, chal)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(res, indent=2, ensure_ascii=False) + "\n"
    (out / "findings.json").write_text(text, encoding="utf-8")
    (out / f"findings-round-{a.round}.json").write_text(text, encoding="utf-8")
    print(f"{a.scope} round {a.round}: {len(res['findings'])} finding(s) ({sum(1 for f in res['findings'] if f.get('previous'))} still open from before), "
          f"{len(res['deferred'])} deferred, {len(res['disputed'])} disputed, {len(res['legacy'])} legacy, carried: {', '.join(res['carried']) or 'none'} "
          f"-> {out / 'findings.json'}, findings-round-{a.round}.json")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    report = []
    bad = 0
    for x in a.inputs:
        path = Path(x)
        item = {"file": str(path), "changes": [], "errors": []}
        try:
            data, wrapped = read_result(path)
        except OSError as e:
            item["errors"].append(f"cannot read: {e}")
            data, wrapped = None, False
        except json.JSONDecodeError as e:
            item["errors"].append(f"invalid JSON ({e}); write only the JSON object to the file")
            data, wrapped = None, False
        if data is not None:
            if wrapped:
                item["changes"].append("JSON block extracted from the surrounding prose")
            data, ch, er = normalize(data, path)
            item["changes"] += ch
            item["errors"] += er
            if a.fix and data is not None and item["changes"]:
                data.setdefault("_normalized", []).extend(item["changes"])
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                item["written"] = True
        bad += bool(item["errors"])
        report.append(item)
    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for it in report:
            state = "INVALID" if it["errors"] else ("normalised" if it["changes"] else "ok")
            print(f"{it['file']}: {state}" + (" (written)" if it.get("written") else ""))
            for e in it["errors"]:
                print(f"  ! {e}")
            for ch in it["changes"]:
                print(f"  ~ {ch}")
    return 1 if bad else 0


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
    s.add_argument("--challenges", help="challenges.json of dev_state.py challenge record (disputed findings do not score)")
    s.add_argument("inputs", nargs="+")
    c = sub.add_parser("check")
    c.add_argument("--fix", action="store_true", help="write the normalised result back to each file")
    c.add_argument("--json", action="store_true")
    c.add_argument("inputs", nargs="+")
    k = sub.add_parser("consolidate")
    k.add_argument("--scope", required=True); k.add_argument("--kind", choices=["gate", "review"], default="gate")
    k.add_argument("--round", type=int, required=True); k.add_argument("--out-dir", required=True)
    k.add_argument("--root", default="."); k.add_argument("--previous"); k.add_argument("--challenges"); k.add_argument("inputs", nargs="+")
    e = sub.add_parser("select")
    e.add_argument("--previous", help="consolidated findings of the previous round; without it, every auditor runs (round 1)")
    e.add_argument("--auditors", required=True)
    e.add_argument("--raw-dir", help="the round's raw/ folder: auditors an interrupted round delivered on --head are kept")
    e.add_argument("--head", help="the commit this round audits (git rev-parse HEAD)")
    e.add_argument("--since"); e.add_argument("--changed-from"); e.add_argument("--root", default=".")
    e.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a)
    if a.cmd == "consolidate":
        return cmd_consolidate(a)
    if a.cmd == "select":
        if a.previous and not a.since and not a.changed_from:
            print("dev_score: select --previous needs --since <sha> or --changed-from <file>", file=sys.stderr)
            return 2
        return cmd_select(a)
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
    res = evaluate(paths, quality, a.kind, a.scope, previous,
                   challenges=load_challenges(Path(a.challenges), Path(a.root).resolve()) if a.challenges else None)
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
            "delta": res.get("delta"),
            "converged": (res.get("convergence") or {}).get("converged"),
            "conflicts": len(res.get("conflicts") or []) or None})
    return 0 if res["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
