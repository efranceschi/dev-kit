#!/usr/bin/env python3
"""dev_cost.py - token usage and estimated cost (US$, API-equivalent) per dev-kit stage.

Standard library only. Usage:
  python3 -I dev_cost.py --root DIR ingest [--transcripts DIR]
  python3 -I dev_cost.py --root DIR report [--by stage|agent|model|session|milestone] [--all | --since YYYY-MM-DD] [--json] [--no-ingest]
  python3 -I dev_cost.py --root DIR report --time [--all | --since D] [--json]   time per agent and skill, ledger reuse
  python3 -I dev_cost.py --root DIR export [--stamp YYYYMMDD-HHMMSS] [--all | --since D] [--no-ingest]

Source: Claude Code's local transcripts (~/.claude/projects/<project>/<session>.jsonl and
<session>/subagents/agent-*.jsonl). Only usage numbers, model, agent type and ids are read and stored, in
.dev/costs/usage.jsonl; never message content. Requests are deduplicated by requestId (one transcript line per
content block shares it). Each request is attributed to a stage using the skill windows of the session log
(.dev/telemetry.jsonl, conventions.md §13); requests outside any window go to "orchestration".

Prices: .dev/costs/prices.json (created from the defaults below; edit it freely). Values are US$ per million
tokens and an ESTIMATE of the API-equivalent cost: on subscription plans nothing is billed per token.

Exit codes: 0 ok · 1 usage error · 2 no state
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir
import dev_telemetry as tel  # noqa: E402

DEFAULT_PRICES = {
    "currency": "USD",
    "unit": "per million tokens",
    "as_of": "2026-11-03",
    "note": "Estimate of the API-equivalent cost; check the current pricing page and edit this file if needed.",
    "rules": {"cache_write_5m": 1.25, "cache_write_1h": 2.0, "cache_read": 0.1},
    "models": {
        "claude-fable-5-2": {"input": 8, "output": 40, "cache_read": 0.20, "fast": 2},
        "claude-mythos-5-2": {"input": 8, "output": 40, "cache_read": 0.20, "fast": 2},
        "claude-fable-5-1": {"input": 10, "output": 50},
        "claude-mythos-5-1": {"input": 10, "output": 50},
        "claude-fable-5": {"input": 10, "output": 50},
        "claude-opus-5-5": {"input": 4, "output": 20, "cache_read": 0.20, "fast": 2},
        "claude-opus-5": {"input": 5, "output": 25, "fast": 2},
        "claude-opus-4-8": {"input": 5, "output": 25, "fast": 2},
        "claude-opus-4-7": {"input": 5, "output": 25},
        "claude-opus-4-6": {"input": 5, "output": 25},
        "claude-sonnet-5-5": {"input": 2, "output": 10, "cache_read": 0.10},
        "claude-sonnet-5": {"input": 2, "output": 10},
        "claude-sonnet-4-6": {"input": 3, "output": 15},
        "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
        "claude-haiku-4-5": {"input": 1, "output": 5},
    },
}
TOKEN_FIELDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
AGENT_STAGE_HINT = {"implementer": "implement", "architect": "architecture"}


def fail(msg: str, code: int = 1) -> None:
    print(f"dev_cost: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_ts(s: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_token(s: object, default: str = "other") -> str:
    v = str(s or "").strip().lower()
    return v if re.fullmatch(r"[a-z0-9][a-z0-9_.:<>-]{0,59}", v) else default


MISSING_IDS = {"", "unknown", "none", "null", "undefined", "n/a", "-"}
FAMILIES = ("fable", "mythos", "opus", "sonnet", "haiku")


def id_token(*candidates: object) -> str:
    """First usable id among the candidates. Placeholders ("unknown", "null"...) count as missing; an id the
    store cannot keep as is (too long, unusual characters) is kept as a short hash, so distinct requests stay
    distinct instead of collapsing into one "unknown" record."""
    for c in candidates:
        v = str(c or "").strip()
        if v.lower() in MISSING_IDS:
            continue
        tok = safe_token(v, "")
        return tok or "h" + hashlib.sha1(v.encode("utf-8", "replace")).hexdigest()[:16]
    return ""


def clean_model(model: object) -> str:
    """Model id without gateway or provider decoration: `system.ai.claude-opus-5-5`, `us.anthropic.claude-…-v1:0`,
    `anthropic/claude-…`, `claude-…@20261001` and `claude-…[1m]` all become `claude-…`."""
    v = str(model or "").strip().lower()
    v = re.sub(r"\[[^\]]*\]$", "", v)
    i = v.find("claude-")
    if i > 0:
        v = v[i:]
    else:
        v = v.rsplit("/", 1)[-1]
    v = re.sub(r"@.*$", "", v)
    v = re.sub(r"-v\d+(:\d+)?$", "", v)
    return safe_token(v, "unknown")


# ------------------------------------------------------------------ ingest

def transcripts_dir(root: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))


def parse_file(path: Path, agent: str, agent_id: str | None) -> list[dict]:
    """One record per requestId (last line wins: it carries the final usage). Content is never read into the record."""
    by_req: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"assistant"' not in line or '"usage"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") != "assistant":
                continue
            m = r.get("message") or {}
            model = str(m.get("model") or "")
            u = m.get("usage") or {}
            if not model or model.startswith("<") or not u:
                continue
            rid = id_token(r.get("requestId"), m.get("id"), r.get("uuid"))
            if not rid:
                continue
            cc = u.get("cache_creation") or {}
            w5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
            w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
            total_w = int(u.get("cache_creation_input_tokens") or 0)
            if not cc and total_w:
                w5 = total_w
            by_req[rid] = {
                "ts": r.get("timestamp"), "session": safe_token(r.get("sessionId"), "unknown"),
                "agent": agent, "agent_id": safe_token(agent_id or r.get("agentId"), "main") if agent != "main" else "main",
                "model": clean_model(model), "request": rid,
                "input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
                "cache_write_5m": w5, "cache_write_1h": w1, "cache_read": int(u.get("cache_read_input_tokens") or 0),
                "speed": "fast" if u.get("speed") == "fast" else "standard",
            }
    return list(by_req.values())


def ingest(dev: Path, root: Path, override: str | None = None) -> dict:
    tdir = transcripts_dir(root, override)
    costs = dev / "costs"
    costs.mkdir(parents=True, exist_ok=True)
    prices_path = costs / "prices.json"
    if not prices_path.exists():
        prices_path.write_text(json.dumps(DEFAULT_PRICES, indent=2) + "\n", encoding="utf-8")
    if not tdir.exists():
        return {"transcripts": False, "files": 0, "changed": 0, "requests": count_usage(costs)}
    index_path = costs / "ingested.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {}
    groups: dict[str, list[dict]] = {}
    up = costs / "usage.jsonl"
    if up.exists():
        for line in up.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            groups.setdefault(rec.get("src", "?"), []).append(rec)
    files: list[tuple[Path, str, str | None]] = []
    for p in sorted(tdir.glob("*.jsonl")):
        files.append((p, "main", None))
    for p in sorted(tdir.glob("*/subagents/agent-*.jsonl")):
        meta = p.with_suffix(".meta.json")
        try:
            agent = safe_token(json.loads(meta.read_text(encoding="utf-8")).get("agentType"), "subagent")
        except (OSError, json.JSONDecodeError):
            agent = "subagent"
        files.append((p, agent, p.stem.replace("agent-", "")))
    changed = 0
    for p, agent, aid in files:
        src = safe_token(p.stem, "src") + ("@" + safe_token(p.parent.parent.name, "s") if agent != "main" else "")
        st = p.stat()
        sig = [st.st_size, int(st.st_mtime)]
        stale = any(r.get("request") == "unknown" for r in groups.get(src, []))  # stores written before 1.15.0
        if index.get(src) == sig and src in groups and not stale:
            continue
        groups[src] = [{**r, "src": src} for r in parse_file(p, agent, aid)]
        index[src] = sig
        changed += 1
    seen: set[str] = set()
    out = []
    for src in sorted(groups):
        for r in groups[src]:
            key = f"{r.get('session')}:{r.get('request')}"
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: str(r.get("ts")))
    tmp = up.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    os.replace(tmp, up)
    index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    return {"transcripts": True, "files": len(files), "changed": changed, "requests": len(out)}


def count_usage(costs: Path) -> int:
    up = costs / "usage.jsonl"
    return len(up.read_text(encoding="utf-8").splitlines()) if up.exists() else 0


def load_usage(dev: Path) -> list[dict]:
    up = dev / "costs" / "usage.jsonl"
    out = []
    if up.exists():
        for line in up.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# ------------------------------------------------------------------ attribution

def stage_windows(events: list[dict]) -> list[tuple[datetime, datetime, str]]:
    """(start, end, stage) for every skill run in the session log; unclosed runs end at +inf."""
    far = datetime.max.replace(tzinfo=timezone.utc)
    open_runs: list[tuple[str, datetime]] = []
    wins: list[tuple[datetime, datetime, str]] = []
    reviews = [(parse_ts(e["ts"]), tel.scope_stage(e.get("scope"))) for e in events if e["event"] == "review"]
    for e in events:
        ts = parse_ts(e.get("ts"))
        if ts is None or e["event"] not in ("skill_start", "skill_end"):
            continue
        skill = e.get("skill", "other")
        if e["event"] == "skill_start":
            open_runs.append((skill, ts))
            continue
        for i in range(len(open_runs) - 1, -1, -1):
            if open_runs[i][0] == skill:
                wins.append((open_runs[i][1], ts, skill))
                open_runs.pop(i)
                break
    wins += [(start, far, skill) for skill, start in open_runs]
    out = []
    for start, end, skill in wins:
        stage = tel.SKILL_STAGE.get(skill)
        if skill == "review":
            inside = [s for t, s in reviews if t and start <= t <= end and s]
            stage = inside[0] if inside else "plan"
        out.append((start, end, stage or "orchestration"))
    return out


def attribute(usage: list[dict], events: list[dict]) -> list[dict]:
    wins = stage_windows(events)
    first_seen: dict[str, datetime] = {}
    for r in usage:
        if r.get("agent") != "main":
            ts = parse_ts(r.get("ts"))
            k = r.get("agent_id", "")
            if ts and (k not in first_seen or ts < first_seen[k]):
                first_seen[k] = ts

    def window_stage(ts: datetime | None) -> str:
        if ts is None:
            return "orchestration"
        inside = [w for w in wins if w[0] <= ts <= w[1]]
        return max(inside, key=lambda w: w[0])[2] if inside else "orchestration"

    # the hooks log which skill each subagent ran under (agent_spawn with agent_id, conventions.md §13): exact,
    # so it wins over the time window; the window stays for agents logged before 3.0 or without hooks
    by_agent: dict[str, str] = {}
    for e in events:
        if e["event"] == "agent_spawn" and e.get("agent_id") and e.get("skill"):
            st = tel.SKILL_STAGE.get(str(e["skill"]))
            if e["skill"] == "review":
                st = tel.scope_stage(e.get("scope")) or "plan"
            if st:
                by_agent[str(e["agent_id"])] = st
    out = []
    for r in usage:
        if r.get("agent") == "main":
            stage = window_stage(parse_ts(r.get("ts")))
        else:
            hint = next((v for k, v in AGENT_STAGE_HINT.items() if str(r.get("agent", "")).endswith(k)), None)
            stage = hint or by_agent.get(str(r.get("agent_id", "")).lower()) or window_stage(first_seen.get(r.get("agent_id", "")))
        out.append({**r, "stage": stage})
    return out


# ------------------------------------------------------------------ milestones (the board's velocity)

def milestone_windows(dev: Path) -> tuple[list[tuple], list[tuple]]:
    """From state.json: (start, end, milestone) of every task that ran (end = done_at, or now while in progress), and
    the QA window of every milestone (its last task done -> passed_at)."""
    try:
        st = json.loads((dev / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    now = datetime.now(timezone.utc)
    tasks, last_done = [], {}
    for t in (st.get("tasks") or {}).values():
        s, e, m = parse_ts(t.get("started_at")), parse_ts(t.get("done_at")), t.get("milestone")
        if m and e and (m not in last_done or e > last_done[m]):
            last_done[m] = e
        if m and s and t.get("status") != "dropped":
            tasks.append((s, e or now, m))
    qa = []
    for m, info in (st.get("milestones") or {}).items():
        p = parse_ts(info.get("passed_at"))
        if m in last_done:
            qa.append((last_done[m], p or now, m))
    return tasks, qa


def tag_milestones(usage: list[dict], dev: Path) -> list[dict]:
    """Each usage row gets the milestone it was spent on: the milestone of a task in progress at that moment (the
    lowest-numbered one if several run), otherwise the milestone whose QA window holds it, otherwise none."""
    tasks, qa = milestone_windows(dev)
    num = lambda m: (lambda g: (int(g[1]), int(g[2] or 0)) if g else (10 ** 6, 0))(re.fullmatch(r"M(\d+)(?:\.(\d+))?", str(m)))  # noqa: E731
    out = []
    for r in usage:
        ts = parse_ts(r.get("ts"))
        m = None
        if ts:
            running = [w[2] for w in tasks if w[0] <= ts <= w[1]]
            m = min(running, key=num) if running else next((w[2] for w in sorted(qa, key=lambda w: w[0]) if w[0] <= ts <= w[1]), None)
        out.append({**r, "milestone": m})
    return out


def milestone_costs(dev: Path) -> dict:
    """Cost and tokens per milestone over all of the project's usage, written to .dev/costs/milestones.json for the
    board. Without transcripts, the tokens the skills reported per scope (agent_end), flagged partial."""
    events, _ = tel.read_events(dev)
    usage, _ = period_filter(attribute(load_usage(dev), events), events, "all", None, dev)
    prices = load_prices(dev)
    rows: dict[str, dict] = {}
    for r in tag_milestones(usage, dev):
        m = r.get("milestone")
        if not m:
            continue
        row = rows.setdefault(m, {"usd": 0.0, "usd_complete": True, "tokens": 0, "requests": 0, "partial": False})
        row["requests"] += 1
        row["tokens"] += sum(int(r.get(f, 0)) for f in TOKEN_FIELDS)
        c = cost_of(r, prices)
        if c is None:
            row["usd_complete"] = False
        else:
            row["usd"] += c
    if not usage:
        try:
            st = json.loads((dev / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            st = {}
        ts = st.get("tasks") or {}
        for e in events:
            if e["event"] != "agent_end" or not e.get("tokens"):
                continue
            sc = str(e.get("scope") or "")
            m = sc if re.fullmatch(r"M\d+(?:\.\d+)?", sc) else (ts.get(sc) or {}).get("milestone")
            if m:
                row = rows.setdefault(m, {"usd": 0.0, "usd_complete": False, "tokens": 0, "requests": 0, "partial": True})
                row["requests"] += 1
                row["tokens"] += int(e["tokens"])
    for row in rows.values():
        row["usd"] = round(row["usd"], 4)
    out = {"at": tel.now(), "milestones": rows}
    (dev / "costs").mkdir(parents=True, exist_ok=True)
    (dev / "costs" / "milestones.json").write_text(json.dumps(out) + "\n", encoding="utf-8")
    return out


def milestone_split(dev: Path, m: str) -> dict:
    """Cost and tokens of one milestone over all usage, split between the main session (orchestration) and agents."""
    events, _ = tel.read_events(dev)
    usage, _ = period_filter(attribute(load_usage(dev), events), events, "all", None, dev)
    prices = load_prices(dev)
    out = {"usd": 0.0, "tokens": 0, "orchestration_usd": 0.0, "agents_usd": 0.0, "complete": True, "requests": 0}
    for r in tag_milestones(usage, dev):
        if r.get("milestone") != m:
            continue
        out["requests"] += 1
        out["tokens"] += sum(int(r.get(f, 0)) for f in TOKEN_FIELDS)
        c = cost_of(r, prices)
        if c is None:
            out["complete"] = False
            continue
        out["usd"] += c
        out["orchestration_usd" if r.get("agent") == "main" else "agents_usd"] += c
    for k in ("usd", "orchestration_usd", "agents_usd"):
        out[k] = round(out[k], 4)
    return out


def stage_tokens(dev: Path, mode: str = "session", since: str | None = None) -> dict:
    """Tokens and cost per stage from the transcripts: the same numbers the cost report shows (one source)."""
    events, _ = tel.read_events(dev)
    usage, _ = period_filter(attribute(load_usage(dev), events), events, mode, since, dev)
    prices = load_prices(dev)
    out: dict[str, dict] = {}
    for r in usage:
        row = out.setdefault(r.get("stage") or "orchestration", {"tokens": 0, "usd": 0.0})
        row["tokens"] += sum(int(r.get(f, 0)) for f in TOKEN_FIELDS)
        row["usd"] = round(row["usd"] + (cost_of(r, prices) or 0.0), 4)
    return out


# ------------------------------------------------------------------ pricing and report

def load_prices(dev: Path) -> dict:
    p = dev / "costs" / "prices.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("models"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_PRICES


def price_key(model: str, prices: dict) -> tuple[str | None, bool]:
    """(price table key, exact). Exact: the model or its longest listed prefix. Otherwise the first listed model of
    the same family (fable, opus, sonnet, haiku), reported as "priced as" so the estimate is never silent."""
    models = prices.get("models", {})
    for cand in dict.fromkeys([model, clean_model(model)]):
        if cand in models:
            return cand, True
        keys = [k for k in models if cand.startswith(k)]
        if keys:
            return max(keys, key=len), True
    fam = next((f for f in FAMILIES if f in model.lower()), None)
    if fam:
        same = [k for k in models if fam in k]
        if same:
            return same[0], False
    return None, False


def price_for(model: str, prices: dict) -> dict | None:
    key, _ = price_key(model, prices)
    return prices.get("models", {}).get(key) if key else None


def cost_of(r: dict, prices: dict) -> float | None:
    p = price_for(str(r.get("model", "")), prices)
    if not p:
        return None
    rules = {**DEFAULT_PRICES["rules"], **prices.get("rules", {})}
    inp = float(p["input"])
    cr = float(p["cache_read"]) if "cache_read" in p else inp * rules["cache_read"]
    usd = (r.get("input", 0) * inp + r.get("output", 0) * float(p["output"]) +
           r.get("cache_write_5m", 0) * inp * rules["cache_write_5m"] +
           r.get("cache_write_1h", 0) * inp * rules["cache_write_1h"] + r.get("cache_read", 0) * cr) / 1e6
    if r.get("speed") == "fast":
        usd *= float(p.get("fast", 1))
    return usd


def adoption_start(dev: Path):
    """Existing projects only: when dev-kit was adopted (state created_at). Claude Code sessions in the project
    before that were not dev-kit work and stay out of `--all`."""
    try:
        st = json.loads((dev / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parse_ts(st.get("created_at")) if st.get("brownfield") else None


def period_filter(usage: list[dict], events: list[dict], mode: str, since: str | None,
                  dev: Path | None = None) -> tuple[list[dict], dict]:
    if mode == "all":
        start = adoption_start(dev) if dev is not None else None
        if start is not None:  # existing project: sessions before dev-kit was adopted are not dev-kit work
            return [r for r in usage if (parse_ts(r.get("ts")) or start) >= start], {"mode": "all", "from": start.isoformat()}
        return usage, {"mode": "all"}
    if mode == "since":
        start = parse_ts(f"{since}T00:00:00+00:00")
        if start is None:
            fail("--since must be YYYY-MM-DD")
        return [r for r in usage if (parse_ts(r.get("ts")) or start) >= start], {"mode": "since", "since": since}
    sess = tel.filter_period(events, "session")
    start = parse_ts(sess[0]["ts"]) if sess else None
    if start is None:
        return usage, {"mode": "all", "note": "no dev-kit session in the log; showing everything"}
    return [r for r in usage if (parse_ts(r.get("ts")) or start) >= start], {"mode": "session", "from": sess[0]["ts"]}


def build_report(dev: Path, by: str, mode: str, since: str | None) -> dict:
    events, _ = tel.read_events(dev)
    usage = attribute(load_usage(dev), events)
    usage, period = period_filter(usage, events, mode, since, dev)
    if by == "milestone":
        usage = tag_milestones(usage, dev)
    prices = load_prices(dev)
    rows: dict[str, dict] = {}
    unknown: set[str] = set()
    approx: dict[str, str] = {}
    for r in usage:
        key_, exact = price_key(str(r.get("model", "")), prices)
        if key_ and not exact:
            approx[str(r.get("model"))] = key_
        key = {"stage": r["stage"], "agent": r.get("agent"), "model": r.get("model"), "session": r.get("session"),
               "milestone": r.get("milestone")}[by] or "other"
        row = rows.setdefault(key, {"key": key, "requests": 0, **{f: 0 for f in TOKEN_FIELDS}, "usd": 0.0, "usd_complete": True})
        row["requests"] += 1
        for f in TOKEN_FIELDS:
            row[f] += int(r.get(f, 0))
        c = cost_of(r, prices)
        if c is None:
            row["usd_complete"] = False
            unknown.add(str(r.get("model")))
        else:
            row["usd"] += c
    warnings = []
    source = "transcripts"
    if not usage:
        partial = [e for e in tel.filter_period(events, mode if mode != "since" else "since", since) if e["event"] == "agent_end" and e.get("tokens")]
        if partial:
            source = "skills (partial)"
            warnings.append("partial: no transcripts found; only the token totals reported by the skills (no cost, no cache split)")
            for e in partial:
                key = (tel.scope_stage(e.get("scope")) or e.get("agent", "other")) if by == "stage" else e.get(by if by != "session" else "session", "other")
                row = rows.setdefault(str(key), {"key": str(key), "requests": 0, **{f: 0 for f in TOKEN_FIELDS}, "usd": 0.0, "usd_complete": False})
                row["requests"] += 1
                row["input"] += int(e["tokens"])
    if approx:
        warnings.append("no exact price for: " + ", ".join(f"{m} (priced as {k})" for m, k in sorted(approx.items()))
                        + "; add them to .dev/costs/prices.json for an exact estimate")
    if unknown:
        warnings.append("no price for: " + ", ".join(sorted(unknown)) + " (add them to .dev/costs/prices.json); their cost shows as n/d")
    as_of = parse_ts(f"{prices.get('as_of', '')}T00:00:00+00:00")
    if as_of and (datetime.now(timezone.utc) - as_of).days > 90:
        warnings.append(f"price table is from {prices.get('as_of')}; check the current prices")
    total = {"requests": sum(r["requests"] for r in rows.values()),
             **{f: sum(r[f] for r in rows.values()) for f in TOKEN_FIELDS},
             "usd": round(sum(r["usd"] for r in rows.values()), 4),
             "usd_complete": all(r["usd_complete"] for r in rows.values())}
    total["tokens"] = sum(total[f] for f in TOKEN_FIELDS)
    out_rows = sorted(rows.values(), key=lambda r: -r["usd"])
    for r in out_rows:
        r["usd"] = round(r["usd"], 4)
        r["tokens"] = sum(r[f] for f in TOKEN_FIELDS)
        r["share"] = round(100 * r["usd"] / total["usd"], 1) if total["usd"] else 0.0
    rep = {"by": by, "period": period, "source": source, "currency": "USD", "estimate": "API-equivalent",
           "prices_as_of": prices.get("as_of"), "rows": out_rows, "total": total, "warnings": warnings}
    (dev / "costs").mkdir(parents=True, exist_ok=True)
    (dev / "costs" / "summary.json").write_text(json.dumps({"at": tel.now(), "period": period, "total": total}) + "\n", encoding="utf-8")
    return rep


def build_time_report(dev: Path, mode: str, since: str | None) -> dict:
    """Where the time went: per agent type (from the subagent transcripts: first to last request of each run) and
    per skill (skill_end durations of the session log), plus the work the ledger reused (conventions.md §18).
    Shares are of the sum of all rows; a skill's time includes the agents it waits for, so they overlap."""
    events, _ = tel.read_events(dev)
    usage, period = period_filter(attribute(load_usage(dev), events), events, mode, since, dev)
    runs: dict[tuple[str, str], list[datetime]] = {}
    for r in usage:
        if r.get("agent") in (None, "main"):
            continue
        ts = parse_ts(r.get("ts"))
        if ts:
            runs.setdefault((str(r["agent"]), str(r.get("agent_id") or r.get("src"))), []).append(ts)
    rows: dict[str, dict] = {}

    def add(kind: str, name: str, minutes: float) -> None:
        row = rows.setdefault(f"{kind}:{name}", {"kind": kind, "name": name, "runs": 0, "total_min": 0.0, "max_min": 0.0})
        row["runs"] += 1
        row["total_min"] += minutes
        row["max_min"] = max(row["max_min"], minutes)

    for (agent, _), tss in runs.items():
        add("agent", agent, (max(tss) - min(tss)).total_seconds() / 60)
    evs = tel.filter_period(events, mode, since) if mode != "all" else events
    for e in evs:
        if e.get("event") == "skill_end" and isinstance(e.get("duration_s"), (int, float)):
            add("skill", str(e.get("skill") or "other"), float(e["duration_s"]) / 60)
    base = sum(r["total_min"] for r in rows.values())
    out = sorted(rows.values(), key=lambda r: -r["total_min"])
    for r in out:
        r["share"] = round(100 * r["total_min"] / base, 1) if base else 0.0
        r["avg_min"] = round(r["total_min"] / r["runs"], 1) if r["runs"] else 0.0
        r["total_min"] = round(r["total_min"], 1)
        r["max_min"] = round(r["max_min"], 1)
    reuse: dict[str, dict] = {}
    for e in evs:
        if e.get("event") == "ledger":
            x = reuse.setdefault(str(e.get("scope")), {"plans": 0, "review": 0, "reuse": 0, "spot": 0})
            x["plans"] += 1
            for k in ("review", "reuse", "spot"):
                x[k] += int(e.get(k) or 0)
    return {"period": period, "base_hours": round(base / 60, 1), "rows": out, "reuse": reuse,
            "note": "skill time includes the agents it waits for, so shares overlap"}


def render_time(rep: dict) -> str:
    lines = [f"Time by agent and skill ({rep['period']}) · base {rep['base_hours']} h of recorded activity",
             "(a skill's time includes the agents it waits for; shares overlap)", "",
             f"{'kind':<6} {'name':<24}{'share':>7}{'runs':>6}{'avg min':>9}{'max min':>9}"]
    for r in rep["rows"]:
        lines.append(f"{r['kind']:<6} {r['name']:<24}{r['share']:>6.1f}%{r['runs']:>6}{r['avg_min']:>9.1f}{r['max_min']:>9.1f}")
    if not rep["rows"]:
        lines.append("no timed activity in this period")
    if rep["reuse"]:
        lines += ["", f"{'reused by the ledger':<28}{'plans':>6}{'reviewed':>10}{'reused':>8}{'spot':>6}"]
        for k, x in sorted(rep["reuse"].items()):
            lines.append(f"{k:<28}{x['plans']:>6}{x['review']:>10}{x['reuse']:>8}{x['spot']:>6}")
    return "\n".join(lines)


def fmt_tokens(n: int) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else (f"{n / 1e3:.1f}k" if n >= 1e3 else str(n))


def render(rep: dict) -> str:
    lines = [f"Estimated cost (US$, API-equivalent) by {rep['by']} · period {rep['period'].get('mode')} · source {rep['source']}",
             f"{rep['by']:<22}{'US$':>10}{'%':>7}{'reqs':>7}{'input':>9}{'output':>9}{'c.write':>9}{'c.read':>9}"]
    for r in rep["rows"]:
        usd = f"{r['usd']:.2f}" + ("" if r["usd_complete"] else "*")
        lines.append(f"{str(r['key'])[:21]:<22}{usd:>10}{r['share']:>7}{r['requests']:>7}{fmt_tokens(r['input']):>9}"
                     f"{fmt_tokens(r['output']):>9}{fmt_tokens(r['cache_write_5m'] + r['cache_write_1h']):>9}{fmt_tokens(r['cache_read']):>9}")
    t = rep["total"]
    lines.append(f"{'total':<22}{t['usd']:>10.2f}{'':>7}{t['requests']:>7}{fmt_tokens(t['input']):>9}{fmt_tokens(t['output']):>9}"
                 f"{fmt_tokens(t['cache_write_5m'] + t['cache_write_1h']):>9}{fmt_tokens(t['cache_read']):>9}")
    for w in rep["warnings"]:
        lines.append(f"  ! {w}")
    if not t["usd_complete"]:
        lines.append("  * n/d: part of the tokens have no price")
    return "\n".join(lines)


def stamped(folder: Path, prefix: str, ext: str, stamp: str | None) -> Path:
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    path, n = folder / f"{prefix}-{stamp}.{ext}", 2
    while path.exists():
        path, n = folder / f"{prefix}-{stamp}-{n}.{ext}", n + 1
    return path


def export_csv(dev: Path, mode: str, since: str | None, stamp: str | None) -> Path:
    events, _ = tel.read_events(dev)
    usage, _ = period_filter(attribute(load_usage(dev), events), events, mode, since, dev)
    prices = load_prices(dev)
    agg: dict[tuple, dict] = {}
    for r in usage:
        k = (r["stage"], r.get("agent"), r.get("model"))
        row = agg.setdefault(k, {"requests": 0, **{f: 0 for f in TOKEN_FIELDS}, "usd": 0.0, "priced": True})
        row["requests"] += 1
        for f in TOKEN_FIELDS:
            row[f] += int(r.get(f, 0))
        c = cost_of(r, prices)
        if c is None:
            row["priced"] = False
        else:
            row["usd"] += c
    path = stamped(dev / "costs", "tokens", "csv", stamp)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "agent", "model", "requests", *TOKEN_FIELDS, "estimated_usd"])
        for (stage, agent, model), row in sorted(agg.items()):
            w.writerow([stage, agent, model, row["requests"], *[row[x] for x in TOKEN_FIELDS],
                        f"{row['usd']:.4f}" if row["priced"] else "n/d"])
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest"); s.add_argument("--transcripts")
    for name in ("report", "export"):
        s = sub.add_parser(name)
        g = s.add_mutually_exclusive_group(); g.add_argument("--all", action="store_true"); g.add_argument("--since")
        s.add_argument("--no-ingest", action="store_true"); s.add_argument("--transcripts")
        if name == "report":
            s.add_argument("--by", choices=["stage", "agent", "model", "session", "milestone"], default="stage")
            s.add_argument("--json", action="store_true")
            s.add_argument("--time", action="store_true", help="time per agent and skill instead of cost")
        else:
            s.add_argument("--stamp")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    dev = root / ".dev"
    if not (dev / "state.json").exists():
        fail(f"no dev-kit state at {dev}", 2)
    if a.cmd == "ingest":
        res = ingest(dev, root, a.transcripts)
        milestone_costs(dev)  # the board's velocity reads it
        print(json.dumps(res))
        return 0
    if not a.no_ingest:
        ingest(dev, root, a.transcripts)
        milestone_costs(dev)
    mode = "all" if a.all else ("since" if a.since else "session")
    if a.cmd == "report" and a.time:
        rep = build_time_report(dev, mode, a.since)
        print(json.dumps(rep, indent=2) if a.json else render_time(rep))
        return 0
    if a.cmd == "report":
        rep = build_report(dev, a.by, mode, a.since)
        print(json.dumps(rep, indent=2) if a.json else render(rep))
        stages = {}
        if a.by == "stage":
            stages = {str(r["key"]): r["usd"] for r in rep["rows"] if re.fullmatch(r"[a-z_]{1,40}", str(r["key"]))}
        tel.safe_emit(dev, "cost", {"usd": rep["total"]["usd"], "tokens": rep["total"]["tokens"],
                                    "requests": rep["total"]["requests"], "period": mode, "stages": stages or None})
        return 0
    path = export_csv(dev, mode, a.since, a.stamp)
    print(f"tokens written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
