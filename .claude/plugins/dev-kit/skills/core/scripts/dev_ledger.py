#!/usr/bin/env python3
"""dev_ledger.py - the work ledger: incremental verification without lowering the bar (conventions.md §18).

Standard library only; imported by dev_state.py (`dev_state.py ledger ...`), not run on its own.

Every unit of verification work (a test run, an auditor's pass over one file, a review of one document
section, a screenshot, a dependency audit, an implementation attempt) is recorded in .dev/run/ledger.jsonl
with the fingerprint of its inputs: the content of the unit's own files, the shared context it was judged
against (checklists, specs, architecture) and salt strings (kit version, model tier). A unit is reusable only
when the fingerprint is identical AND its result was "ok". Everything else is done again.

Quality rules enforced here:
  - conservative invalidation: any change to an input, a context file or a salt invalidates the unit;
  - findings never close from the cache: a unit whose result was "findings" is always re-reviewed;
  - full coverage: a unit never recorded is always reviewed ("never" list);
  - spot checks: a seeded sample (spot_pct of the reusable units, at least one per plan when any) is reviewed
    again; a spot check that finds something new means the caller drops the prefix and redoes it all;
  - shared files: when any `shared` input changed, every unit of the plan is reviewed;
  - --no-cache (release, or by choice) reviews everything.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir
import dev_ids as dids  # noqa: E402

RESULTS = ("ok", "findings", "failed")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(dev: Path) -> Path:
    return dev / "run" / "ledger.jsonl"


def file_digest(root: Path, rel: str) -> str:
    p = (root / rel) if not Path(rel).is_absolute() else Path(rel)
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def fingerprint(root: Path, inputs: list[str], context: list[str] | None = None, salt: list[str] | None = None) -> str:
    h = hashlib.sha256()
    for group, items in (("in", inputs), ("ctx", context or [])):
        for rel in sorted(set(items)):
            h.update(f"{group}:{rel}={file_digest(root, rel)}\n".encode())
    for s in sorted(set(salt or [])):
        h.update(f"salt:{s}\n".encode())
    return h.hexdigest()[:20]


def load(dev: Path) -> dict[str, dict]:
    """Latest record per key."""
    out: dict[str, dict] = {}
    p = ledger_path(dev)
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and r.get("key"):
            out[r["key"]] = r
    return out


def append(dev: Path, recs: list[dict]) -> None:
    p = ledger_path(dev)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def put(dev: Path, key: str, fp: str, result: str, ref: str | None = None, note: str | None = None, **extra) -> dict:
    if result not in RESULTS:
        raise ValueError(f"result must be one of {', '.join(RESULTS)}")
    rec = {"key": key, "fp": fp, "result": result, "at": now(), **({"ref": ref} if ref else {}),
           **({"note": note[:300]} if note else {}), **{k: v for k, v in extra.items() if v is not None}}
    append(dev, [rec])
    return rec


def drop(dev: Path, prefix: str) -> int:
    """Invalidate every key with the prefix (appends tombstones; history is kept)."""
    keys = [k for k, r in load(dev).items() if k.startswith(prefix) and r.get("result") != "dropped"]
    append(dev, [{"key": k, "fp": "", "result": "dropped", "at": now()} for k in keys])
    return len(keys)


def reusable(rec: dict | None, fp: str) -> bool:
    return bool(rec) and rec.get("fp") == fp and rec.get("result") == "ok"


def plan(dev: Path, root: Path, prefix: str, units: dict[str, list[str]], context: list[str], salt: list[str],
         shared: list[str] | None = None, spot_pct: float = 10.0, seed: str = "", no_cache: bool = False) -> dict:
    """units: unit id -> its own input files. Returns which units to review and which to reuse, with reasons."""
    recs = load(dev)
    review: dict[str, str] = {}
    reuse: list[str] = []
    fps = {u: fingerprint(root, ins, context, salt) for u, ins in units.items()}
    shared_changed = []
    if shared:
        for s in shared:
            key = f"{prefix}:shared:{s}"
            if not reusable(recs.get(key), fingerprint(root, [s])):
                shared_changed.append(s)
    for u in sorted(units):
        rec = recs.get(f"{prefix}:{u}")
        if no_cache:
            review[u] = "no-cache"
        elif shared_changed:
            review[u] = "shared changed: " + ", ".join(shared_changed[:3])
        elif not rec or rec.get("result") == "dropped":
            review[u] = "never reviewed"
        elif rec.get("result") != "ok":
            review[u] = f"last result {rec.get('result')}"
        elif rec.get("fp") != fps[u]:
            review[u] = "inputs changed"
        else:
            reuse.append(u)
    spot: list[str] = []
    if reuse and spot_pct > 0 and not no_cache:
        n = max(1, round(len(reuse) * spot_pct / 100))
        rnd = random.Random(f"{prefix}|{seed}")
        spot = sorted(rnd.sample(sorted(reuse), min(n, len(reuse))))
        for u in spot:
            review[u] = "spot check"
        reuse = [u for u in reuse if u not in spot]
    return {"prefix": prefix, "review": [{"unit": u, "why": w} for u, w in sorted(review.items())],
            "reuse": reuse, "spot": spot, "never": [u for u, w in review.items() if w == "never reviewed"],
            "shared_changed": shared_changed, "fingerprints": fps}


def record(dev: Path, root: Path, prefix: str, units: dict[str, list[str]], context: list[str], salt: list[str],
           with_findings: set[str], ref: str | None = None, shared: list[str] | None = None) -> dict:
    """After a pass: each reviewed unit becomes ok, or findings when a finding points at it."""
    recs = []
    for u, ins in units.items():
        recs.append({"key": f"{prefix}:{u}", "fp": fingerprint(root, ins, context, salt),
                     "result": "findings" if u in with_findings else "ok", "at": now(), **({"ref": ref} if ref else {})})
    for s in shared or []:
        recs.append({"key": f"{prefix}:shared:{s}", "fp": fingerprint(root, [s]), "result": "ok", "at": now()})
    append(dev, recs)
    return {"ok": sum(r["result"] == "ok" for r in recs if ":shared:" not in r["key"]),
            "findings": sum(r["result"] == "findings" for r in recs)}


# ------------------------------------------------------------------ document sections

ID_RE = re.compile(rf"\b(?:{dids.AC}|{dids.SCREEN}|{dids.ADR}|{dids.TASK}|{dids.STORY}|{dids.JOURNEY})\b")


def sections(path: Path) -> list[dict]:
    """Split a markdown document by ## / ### headings. Each section: key (heading path), start line, text hash,
    ids it defines (in its heading or as list items) and ids it cites."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict] = []
    cur = {"key": "(preamble)", "start": 1, "lines": []}
    h2 = ""
    for i, ln in enumerate(lines, 1):
        m = re.match(r"^(#{2,3})\s+(.*\S)\s*$", ln)
        if m:
            out.append(cur)
            title = re.sub(r"\s+", " ", m.group(2))
            if len(m.group(1)) == 2:
                h2 = title
                key = title
            else:
                key = f"{h2} > {title}" if h2 else title
            cur = {"key": key, "start": i, "lines": [ln]}
        else:
            cur["lines"].append(ln)
    out.append(cur)
    res = []
    volatile = re.compile(r"^\W*(date|status|updated|last updated|revision|rev)\W*\s*[:=]", re.I)
    for s in out:
        body = [x for x in s["lines"] if not (s["start"] <= 12 and volatile.match(x))]
        text = "\n".join(x.rstrip() for x in body).strip()
        if not text and s["key"] == "(preamble)":
            continue
        defines = set(ID_RE.findall(s["lines"][0] if s["lines"] else ""))
        for ln in s["lines"]:
            m = re.match(r"^\s*(?:[-*]|\d+\.|\|)\s*\**\s*((?:AC|S|ADR|T|US|J)-\d+)\b", ln)
            if m:
                defines.add(m.group(1))
        res.append({"key": s["key"], "start": s["start"], "end": s["start"] + len(s["lines"]) - 1,
                    "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                    "defines": sorted(defines), "cites": sorted(set(ID_RE.findall(text)) - defines)})
    return res


def section_plan(dev: Path, root: Path, target: str, files: list[str], context: list[str], salt: list[str],
                 spot_pct: float = 10.0, seed: str = "", no_cache: bool = False) -> dict:
    """Sections to review in a document review round: changed or never reviewed ones, the ones that cite an id
    defined in a changed section, the ones that had findings, and a spot sample of the rest."""
    recs = load(dev)
    ctx_fp = fingerprint(root, [], context, salt)
    secs = []
    for f in files:
        p = root / f
        if p.exists():
            secs += [{**s, "file": f, "unit": f"{f}#{s['key']}"} for s in sections(p)]
    review: dict[str, str] = {}
    changed_ids: set[str] = set()
    for s in secs:
        rec = recs.get(f"review:{target}:{s['unit']}")
        fp = f"{s['hash']}:{ctx_fp}"
        if no_cache:
            review[s["unit"]] = "no-cache"
        elif not rec or rec.get("result") == "dropped":
            review[s["unit"]] = "never reviewed"
        elif rec.get("fp") != fp:
            review[s["unit"]] = "text or context changed"
            changed_ids |= set(s["defines"])
        elif rec.get("result") != "ok":
            review[s["unit"]] = f"last result {rec.get('result')}"
    for s in secs:
        if s["unit"] not in review and changed_ids & set(s["cites"]):
            review[s["unit"]] = "cites changed " + ", ".join(sorted(changed_ids & set(s["cites"]))[:4])
    reuse = [s["unit"] for s in secs if s["unit"] not in review]
    spot: list[str] = []
    if reuse and spot_pct > 0 and not no_cache:
        n = max(1, round(len(reuse) * spot_pct / 100))
        spot = sorted(random.Random(f"review:{target}|{seed}").sample(sorted(reuse), min(n, len(reuse))))
        for u in spot:
            review[u] = "spot check"
        reuse = [u for u in reuse if u not in spot]
    by_unit = {s["unit"]: s for s in secs}
    return {"target": target,
            "review": [{"unit": u, "file": by_unit[u]["file"], "section": by_unit[u]["key"], "lines": [by_unit[u]["start"], by_unit[u]["end"]], "why": w}
                       for u, w in sorted(review.items(), key=lambda kv: (by_unit[kv[0]]["file"], by_unit[kv[0]]["start"]))],
            "reuse": reuse, "spot": spot, "sections": len(secs)}


def section_record(dev: Path, root: Path, target: str, files: list[str], context: list[str], salt: list[str],
                   finding_lines: dict[str, list[int]]) -> dict:
    """After a review round: each section is ok, or findings when an open finding's line falls inside it."""
    ctx_fp = fingerprint(root, [], context, salt)
    recs = []
    for f in files:
        p = root / f
        if not p.exists():
            continue
        lines = finding_lines.get(f, [])
        for s in sections(p):
            hit = any(s["start"] <= ln <= s["end"] for ln in lines)
            recs.append({"key": f"review:{target}:{f}#{s['key']}", "fp": f"{s['hash']}:{ctx_fp}",
                         "result": "findings" if hit else "ok", "at": now()})
    append(dev, recs)
    return {"ok": sum(r["result"] == "ok" for r in recs), "findings": sum(r["result"] == "findings" for r in recs)}
