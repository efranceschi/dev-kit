"""dev_telemetry.py - structured, privacy-safe session log for dev-kit (conventions.md §13).

Standard library only; imported by dev_state.py and dev_score.py (not run directly).

Every event is one JSON line in .dev/telemetry.jsonl:
  {"v": 1, "ts": "...Z", "session": "<random id>", "kit": "<version>", "event": "<type>", ...allowed fields}

Privacy is enforced here, not only by instruction: each event type has an allowlist of keys, values must be
numbers, booleans, known ids (T-001, M1, F-003, Q-002, ADR-010) or short lowercase tokens, and free text is
accepted only in feedback notes, which are sanitised (no paths, URLs, e-mails, long numbers or hex, and no
words from the project name or the brief's entities). Anything else is rejected with ValueError.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
ID_RE = re.compile(r"^(T-\d{1,5}|M\d{1,3}|R\d{1,3}|F-\d{1,5}|Q-\d{1,5}|ADR-\d{1,5}|I-\d{1,5})$")
TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,39}$")

COUNTS = {"critical", "high", "medium", "low"}
DIMENSIONS = {"code", "security", "tests", "spec", "ux", "a11y", "visual", "copy", "performance", "data",
              "operations", "dependencies", "docs", "design", "requirements"}
FEEDBACK_AREAS = {"start", "interview", "prd", "architecture", "design", "plan", "implement", "test", "qa", "usability",
                  "review", "deploy", "docs", "release", "issue", "board", "scoring", "isolation", "scripts", "prompts",
                  "cost", "autopilot", "other"}
FEEDBACK_LISTS = ("worked", "failed", "improve")

# key -> kind: "num", "bool", "tok" (token or id), "counts", "dims", "delta", "mtok" ({"model","effort"}), "feedback"
COMMON = {"duration_s": "num", "round": "num", "feedback": "feedback"}
SCHEMA: dict[str, dict[str, str]] = {
    "session_start": {"trigger": "tok", "brownfield": "bool", "mode": "tok"},
    "skill_start": {"skill": "tok", "args_kind": "tok", "scope": "tok"},
    "skill_end": {"skill": "tok", "args_kind": "tok", "scope": "tok", "status": "tok"},
    "agent_spawn": {"agent": "tok", "model": "tok", "effort": "tok", "slot": "num", "scope": "tok", "background": "bool",
                    "tier": "tok", "risk_score": "num"},
    "agent_end": {"agent": "tok", "model": "tok", "effort": "tok", "slot": "num", "scope": "tok", "status": "tok",
                  "tier": "tok", "risk_score": "num",
                  "tokens": "num", "tokens_in": "num", "tokens_out": "num", "cache_read": "num", "cache_write": "num",
                  "findings": "counts", "parsable": "bool"},
    "cost": {"usd": "num", "tokens": "num", "requests": "num", "period": "tok", "stages": "numdict"},
    "score": {"scope": "tok", "kind": "tok", "overall": "num", "cutoff": "num", "verdict": "tok",
              "dimensions": "dims", "delta": "delta", "blockers": "num", "auditors": "num",
              "converged": "bool", "conflicts": "num"},
    "gate": {"scope": "tok", "value": "tok", "score": "num", "forced": "bool", "force_source": "tok", "qa_runs": "num"},
    "review": {"scope": "tok", "value": "tok", "score": "num", "forced": "bool", "force_source": "tok"},
    "task": {"task": "tok", "transition": "tok", "type": "tok", "milestone": "tok", "parallel": "bool",
             "tier": "tok", "risk_score": "num"},
    "route": {"context": "tok", "rule_tier": "tok", "arm": "tok", "reason_code": "tok", "explore": "bool", "agent": "tok"},
    "pause": {"point": "tok", "action": "tok", "outcome": "tok"},
    "escalation": {"agent": "tok", "from": "mtok", "to": "mtok", "consent": "tok"},
    "preview": {"scope": "tok", "mode": "tok", "status": "tok"},
    "deploy": {"scope": "tok", "env": "tok", "status": "tok", "commits_behind": "num", "migrations_behind": "num"},
    "release_gate": {"scope": "tok", "transition": "tok", "tasks": "num"},
    "cleanup": {"killed": "num", "stale_files": "num", "skipped": "num"},
    "config": {"key": "tok", "value": "tok"},
    "issue": {"issue": "tok", "type": "tok", "class": "tok", "transition": "tok", "severity": "tok", "origin": "tok"},
    "tip": {"tip": "tok", "context": "tok"},
    "error": {"component": "tok", "code": "tok", "skill": "tok", "agent": "tok"},
    "session_feedback": {"trigger": "tok"},
    "ledger": {"scope": "tok", "review": "num", "reuse": "num", "spot": "num", "no_cache": "bool"},
}

PATH_RE = re.compile(r"[/\\]|\b\w+\.(py|ts|tsx|js|jsx|md|json|ya?ml|toml|sql|sh|css|html|go|rs|java|rb|php|cs)\b", re.I)
URL_RE = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|org|net|io|dev|app|br)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
NUM_RE = re.compile(r"\d{6,}")
HEX_RE = re.compile(r"\b[0-9a-f]{16,}\b", re.I)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def kit_version() -> str:
    pj = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
    try:
        return str(json.loads(pj.read_text(encoding="utf-8")).get("version", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def _tok(v: object) -> str:
    if isinstance(v, str) and (ID_RE.match(v) or TOKEN_RE.match(v)):
        return v
    raise ValueError(f"value {v!r} is not an id or a short lowercase token")


def denylist(dev: Path) -> set[str]:
    """Words that identify the project: name, folder, brief title and core entities (lowercase, >= 3 chars)."""
    words: set[str] = set()

    def add(text: str) -> None:
        words.update(w for w in re.findall(r"[a-z0-9]{3,}", text.lower()))

    add(dev.parent.name)
    try:
        add(str(json.loads((dev / "state.json").read_text(encoding="utf-8")).get("project") or ""))
    except (OSError, json.JSONDecodeError):
        pass
    try:
        for line in (dev / "brief.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("# ") or "core entities" in line.lower():
                add(line.split("—", 1)[-1] if line.startswith("# ") else line.split(":", 1)[-1])
    except OSError:
        pass
    return words - {"the", "and", "app", "api", "web", "project", "brief", "core", "entities", "relationships"}


def check_note(note: object, deny: set[str]) -> str:
    if not isinstance(note, str) or not note.strip():
        raise ValueError("feedback note must be a non-empty string")
    note = " ".join(note.split())
    if len(note) > 140:
        raise ValueError("feedback note longer than 140 characters")
    for rx, what in ((URL_RE, "a URL"), (EMAIL_RE, "an e-mail"), (PATH_RE, "a file path"),
                     (NUM_RE, "a long number"), (HEX_RE, "a hex string")):
        if rx.search(note):
            raise ValueError(f"feedback note contains {what}; describe the dev-kit, not the project")
    hit = set(re.findall(r"[a-z0-9]{3,}", note.lower())) & deny
    if hit:
        raise ValueError("feedback note mentions the project (" + ", ".join(sorted(hit)) + "); describe the dev-kit only")
    return note


def check_feedback(fb: object, deny: set[str]) -> dict:
    if not isinstance(fb, dict) or set(fb) - set(FEEDBACK_LISTS):
        raise ValueError("feedback must be an object with worked / failed / improve lists")
    out: dict[str, list] = {}
    for k in FEEDBACK_LISTS:
        items = fb.get(k) or []
        if not isinstance(items, list) or len(items) > 3:
            raise ValueError(f"feedback.{k} must be a list of at most 3 items")
        clean = []
        for it in items:
            if not isinstance(it, dict) or it.get("area") not in FEEDBACK_AREAS:
                raise ValueError(f"feedback.{k} item needs an area in: {', '.join(sorted(FEEDBACK_AREAS))}")
            clean.append({"area": it["area"], "note": check_note(it.get("note"), deny)})
        if clean:
            out[k] = clean
    return out


def check_field(key: str, kind: str, v: object, deny: set[str]) -> object:
    if kind == "num":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{key} must be a number")
        return v
    if kind == "bool":
        if not isinstance(v, bool):
            raise ValueError(f"{key} must be true or false")
        return v
    if kind == "tok":
        return _tok(v)
    if kind == "counts":
        if not isinstance(v, dict) or set(v) - COUNTS or not all(isinstance(x, int) for x in v.values()):
            raise ValueError(f"{key} must be {{critical, high, medium, low: int}}")
        return v
    if kind == "dims":
        if not isinstance(v, dict) or set(v) - DIMENSIONS or not all(isinstance(x, (int, float)) for x in v.values()):
            raise ValueError(f"{key} must map known dimensions to scores")
        return v
    if kind == "delta":
        allowed = {"closed", "still_open", "new_scored", "new_deferred", "new_outside_change"}
        if not isinstance(v, dict) or set(v) - allowed or not all(isinstance(x, int) for x in v.values()):
            raise ValueError(f"{key} must be {{closed, still_open, new_scored, new_deferred, new_outside_change: int}}")
        return v
    if kind == "mtok":
        if not isinstance(v, dict) or set(v) - {"model", "effort"}:
            raise ValueError(f"{key} must be {{model, effort}}")
        return {k: _tok(x) for k, x in v.items()}
    if kind == "numdict":
        if not isinstance(v, dict) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()):
            raise ValueError(f"{key} must map short tokens to numbers")
        return {_tok(k): x for k, x in v.items()}
    if kind == "feedback":
        return check_feedback(v, deny)
    raise ValueError(f"unknown kind {kind}")


def validate(event: str, fields: dict, deny: set[str]) -> dict:
    if event not in SCHEMA:
        raise ValueError(f"unknown event {event}; one of {', '.join(sorted(SCHEMA))}")
    allowed = {**COMMON, **SCHEMA[event]}
    out = {}
    for k, v in fields.items():
        if v is None:
            continue
        if k not in allowed:
            raise ValueError(f"key {k!r} is not allowed in {event} events")
        out[k] = check_field(k, allowed[k], v, deny)
    return out


def session_id(dev: Path, rotate: bool = False) -> str:
    sp = dev / "telemetry-session"
    if not rotate and sp.exists():
        sid = sp.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{8}", sid):
            return sid
    sid = secrets.token_hex(4)
    dev.mkdir(parents=True, exist_ok=True)
    sp.write_text(sid + "\n", encoding="utf-8")
    return sid


def emit(dev: Path, event: str, fields: dict, rotate_session: bool = False) -> dict:
    """Validate and append one event. Raises ValueError for anything outside the allowlist."""
    deny = denylist(dev)
    clean = validate(event, fields, deny)
    rec = {"v": VERSION, "ts": now(), "session": session_id(dev, rotate_session), "kit": kit_version(), "event": event, **clean}
    dev.mkdir(parents=True, exist_ok=True)
    with (dev / "telemetry.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def safe_emit(dev: Path, event: str, fields: dict) -> None:
    """For automatic emission from the scripts: never break the main command because of the log."""
    try:
        if dev.exists():
            emit(dev, event, fields)
    except (ValueError, OSError):
        pass


def scope_token(scope: object) -> str:
    s = str(scope or "")
    if ID_RE.match(s) or TOKEN_RE.match(s):
        return s
    return s.lower() if TOKEN_RE.match(s.lower()) else "other"


def read_events(dev: Path) -> tuple[list[dict], int]:
    """Read the log and re-validate every line; invalid lines are dropped and counted."""
    events, dropped = [], 0
    path = dev / "telemetry.jsonl"
    if not path.exists():
        return events, dropped
    deny = denylist(dev)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            ev = rec.get("event")
            fields = {k: v for k, v in rec.items() if k not in ("v", "ts", "session", "kit", "event")}
            clean = validate(ev, fields, deny)
            _tok(rec.get("session", "x"))
            events.append({"ts": rec.get("ts"), "session": rec.get("session"), "kit": _tok(str(rec.get("kit", "unknown"))), "event": ev, **clean})
        except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
            dropped += 1
    return events, dropped


def summarize(events: list[dict], dropped: int, stack: dict) -> dict:
    by_event: dict[str, int] = {}
    agents: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    scores: dict[str, list] = {}
    pauses: dict[str, int] = {}
    errors: dict[str, int] = {}
    escalations = 0
    gates_forced = 0
    feedback: dict[str, dict[str, list]] = {k: {} for k in FEEDBACK_LISTS}
    for e in events:
        by_event[e["event"]] = by_event.get(e["event"], 0) + 1
        if e["event"] == "agent_end":
            a = agents.setdefault(e.get("agent", "other"), {"runs": 0, "duration_s": 0, "tokens": 0, "models": {}})
            a["runs"] += 1
            a["duration_s"] += e.get("duration_s", 0) or 0
            a["tokens"] += e.get("tokens", 0) or 0
            m = e.get("model", "unknown")
            a["models"][m] = a["models"].get(m, 0) + 1
        elif e["event"] == "skill_end":
            s = skills.setdefault(e.get("skill", "other"), {"runs": 0, "duration_s": 0, "status": {}})
            s["runs"] += 1
            s["duration_s"] += e.get("duration_s", 0) or 0
            st = e.get("status", "unknown")
            s["status"][st] = s["status"].get(st, 0) + 1
        elif e["event"] == "score":
            scores.setdefault(e.get("scope", "other"), []).append(
                {k: e.get(k) for k in ("kind", "round", "overall", "cutoff", "verdict", "delta") if e.get(k) is not None})
        elif e["event"] == "pause":
            k = f"{e.get('point', 'other')}:{e.get('action', 'other')}"
            pauses[k] = pauses.get(k, 0) + 1
        elif e["event"] == "escalation":
            escalations += 1
        elif e["event"] == "error":
            k = f"{e.get('component', 'other')}:{e.get('code', 'other')}"
            errors[k] = errors.get(k, 0) + 1
        elif e["event"] in ("gate", "review") and e.get("forced"):
            gates_forced += 1
        for kind, items in (e.get("feedback") or {}).items():
            for it in items:
                feedback[kind].setdefault(it["area"], []).append(it["note"])
    stack_cats = {k: v for k, v in (stack or {}).items() if k in ("lang", "framework", "pkg", "test", "db") and isinstance(v, str)
                  and TOKEN_RE.match(v.lower())}
    return {
        "kit": events[-1]["kit"] if events else "unknown",
        "sessions": len({e["session"] for e in events}),
        "from": events[0]["ts"] if events else None, "to": events[-1]["ts"] if events else None,
        "stack": {k: v.lower() for k, v in stack_cats.items()},
        "events": by_event, "dropped_invalid_lines": dropped,
        "skills": skills, "agents": agents, "scores": scores,
        "pauses": pauses, "escalations": escalations, "forced_passes": gates_forced, "errors": errors,
        "feedback": {k: v for k, v in feedback.items() if v},
    }


def render_summary(s: dict) -> str:
    lines = [f"dev-kit {s['kit']} · {s['sessions']} session(s) · {s['from']} → {s['to']}",
             f"events: " + ", ".join(f"{k} {v}" for k, v in sorted(s["events"].items())) +
             (f" · dropped invalid: {s['dropped_invalid_lines']}" if s["dropped_invalid_lines"] else "")]
    for name, a in sorted(s["agents"].items()):
        lines.append(f"  agent {name}: {a['runs']} runs · {round(a['duration_s'] / 60)} min · {a['tokens']} tokens · " +
                     ", ".join(f"{m} {n}" for m, n in a["models"].items()))
    for scope, rs in sorted(s["scores"].items()):
        lines.append(f"  score {scope}: " + " → ".join(f"{r.get('overall')}" + ("✓" if r.get("verdict") == "pass" else "✗") for r in rs))
    if s["pauses"]:
        lines.append("  pauses: " + ", ".join(f"{k} {v}" for k, v in sorted(s["pauses"].items())))
    if s["errors"]:
        lines.append("  errors: " + ", ".join(f"{k} {v}" for k, v in sorted(s["errors"].items())))
    lines.append(f"  escalations {s['escalations']} · forced passes {s['forced_passes']}")
    for kind, areas in s["feedback"].items():
        lines.append(f"  feedback {kind}:")
        for area, notes in sorted(areas.items()):
            for n in notes:
                lines.append(f"    [{area}] {n}")
    return "\n".join(lines)


# ---------------------------------------------------------------- period filter and per-stage evaluation

def filter_period(events: list[dict], mode: str = "session", since: str | None = None) -> list[dict]:
    """mode: session (default: the last session_start onwards, else the last session id) | all | since."""
    if mode == "all":
        return events
    if mode == "since":
        return [e for e in events if str(e.get("ts", "")) >= str(since or "")]
    starts = [e["session"] for e in events if e["event"] == "session_start"]
    sid = starts[-1] if starts else (events[-1]["session"] if events else None)
    return [e for e in events if e.get("session") == sid]


STAGES = ["start", "interview", "prd", "architecture", "design", "plan", "implement", "qa", "usability",
          "deploy", "docs_release", "autopilot", "scripts"]
STAGE_LABEL = {"start": "start / status", "interview": "interview", "prd": "prd + review prd", "architecture": "architecture",
               "design": "ux + ui + review design", "plan": "plan + review plan", "implement": "implement",
               "qa": "qa (milestone gates)", "usability": "usability", "deploy": "preview / deploy",
               "docs_release": "docs / release", "autopilot": "autopilot", "scripts": "scripts (dev_state / dev_score)"}
SKILL_STAGE = {"start": "start", "status": "start", "board": "start", "interview": "interview", "prd": "prd", "architecture": "architecture",
               "ux": "design", "ui": "design", "plan": "plan", "implement": "implement", "test": "implement", "qa": "qa",
               "usability": "usability", "deploy": "deploy", "docs": "docs_release", "release": "docs_release",
               "autopilot": "autopilot", "review": None, "feedback": None, "issue": "plan", "backlog": None,
               "costs": None, "help": None, "settings": None, "worker": None}
AREA_STAGE = {"interview": "interview", "prd": "prd", "architecture": "architecture", "design": "design", "plan": "plan",
              "implement": "implement", "test": "implement", "qa": "qa", "usability": "usability", "deploy": "deploy",
              "autopilot": "autopilot", "scripts": "scripts", "start": "start", "board": "start", "docs": "docs_release",
              "release": "docs_release", "issue": "plan"}
AGENT_STAGE = {"implementer": "implement", "architect": "architecture", "requirements-reviewer": None,
               "design-reviewer": "design", "docs-reviewer": "docs_release"}


def scope_stage(scope: object) -> str | None:
    s = str(scope or "")
    if re.fullmatch(r"M\d+", s) or re.fullmatch(r"(?i)T-\d+", s) or s.lower().startswith("hotfix-"):
        return "qa"
    return {"prd": "prd", "design": "design", "plan": "plan", "ux": "usability", "docs": "docs_release",
            "release": "docs_release"}.get(s)


def stage_of(e: dict) -> str | None:
    ev = e["event"]
    if ev in ("skill_start", "skill_end"):
        if e.get("skill") == "review":
            return scope_stage(e.get("scope"))
        return SKILL_STAGE.get(e.get("skill", ""), None)
    if ev in ("score", "gate", "review"):
        return scope_stage(e.get("scope"))
    if ev in ("agent_spawn", "agent_end"):
        return scope_stage(e.get("scope")) or AGENT_STAGE.get(e.get("agent", ""))
    if ev in ("task", "route"):
        return "implement"
    if ev in ("preview", "deploy"):
        return "deploy"
    if ev == "release_gate":
        return "docs_release"
    if ev in ("pause", "escalation", "session_feedback"):
        return "autopilot"
    if ev == "cleanup":
        return "scripts"
    if ev == "error":
        if e.get("component") == "script":
            return "scripts"
        return SKILL_STAGE.get(e.get("skill", ""), None) or AGENT_STAGE.get(e.get("agent", "")) or "autopilot"
    return None


def stage_report(events: list[dict], state: dict) -> dict:
    """Deterministic grade per stage (conventions.md §13), with the reasons that produced it."""
    max_rounds = int((state.get("autonomy") or {}).get("max_fix_rounds_per_gate", 3))
    max_review = int((state.get("autonomy") or {}).get("max_review_rounds", max_rounds))
    review_scopes: set[str] = set()
    st = {s: {"events": 0, "agents": 0, "duration_s": 0, "tokens": 0, "rounds": {}, "scores": {}, "forced": [],
              "errors": {}, "unparsable": 0, "ends": {}, "final": {}, "na": 0, "feedback": {k: [] for k in FEEDBACK_LISTS}}
          for s in STAGES}
    general = {k: [] for k in FEEDBACK_LISTS}
    for e in events:
        s = stage_of(e)
        for kind, items in (e.get("feedback") or {}).items():
            for it in items:
                target = AREA_STAGE.get(it["area"])
                (st[target]["feedback"][kind] if target else general[kind]).append(it)
        if s is None:
            continue
        x = st[s]
        x["events"] += 1
        ev = e["event"]
        if ev == "agent_end":
            x["agents"] += 1
            x["duration_s"] += e.get("duration_s", 0) or 0
            x["tokens"] += e.get("tokens", 0) or 0
            if e.get("parsable") is False:
                x["unparsable"] += 1
        elif ev == "skill_end":
            x["duration_s"] += e.get("duration_s", 0) or 0
            stt = e.get("status", "ok")
            x["ends"][stt] = x["ends"].get(stt, 0) + 1
        elif ev == "score":
            x["scores"].setdefault(e.get("scope", "other"), []).append(e.get("overall"))
        elif ev in ("gate", "review"):
            sc = e.get("scope", "other")
            val = e.get("value")
            if val == "na":
                x["final"][sc] = "n/a"
                x["na"] += 1
            elif val in ("passed", "pending", "pass", "fail"):
                x["rounds"][sc] = x["rounds"].get(sc, 0) + 1
                if ev == "review":
                    review_scopes.add(sc)
                x["final"][sc] = "pass" if val in ("passed", "pass") else "fail"
            if e.get("forced"):
                x["forced"].append(e.get("force_source", "user"))
        elif ev == "error":
            c = e.get("code", "other")
            x["errors"][c] = x["errors"].get(c, 0) + 1
    out = []
    for s in STAGES:
        x = st[s]
        ran = x["events"] > x["na"]  # a stage recorded only as n/a (brownfield) did not run
        reasons, score = [], 100
        if ran:
            for sc, n in sorted(x["rounds"].items()):
                if n > 1:
                    pen = 10 * (n - 1) + 10 * max(0, n - (max_review if sc in review_scopes else max_rounds))
                    score -= pen
                    reasons.append(f"{sc} rounds {n} (-{pen})")
            for src in x["forced"]:
                pen = 15 if src == "policy" else 25
                score -= pen
                reasons.append(f"forced by {src} (-{pen})")
            drops = sum(1 for seq in x["scores"].values() for a, b in zip(seq, seq[1:])
                        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b < a)
            if drops:
                score -= 10 * drops
                reasons.append(f"score dropped {drops}x (-{10 * drops})")
            n_err = sum(x["errors"].values())
            if n_err:
                pen = min(30, 5 * n_err)
                score -= pen
                reasons.append(f"errors {n_err} (-{pen})")
            if x["unparsable"]:
                score -= 5 * x["unparsable"]
                reasons.append(f"agents without JSON {x['unparsable']} (-{5 * x['unparsable']})")
            if x["ends"].get("failed"):
                score -= 10 * x["ends"]["failed"]
                reasons.append(f"skill failed {x['ends']['failed']}x (-{10 * x['ends']['failed']})")
            if x["ends"].get("parked"):
                score -= 5 * x["ends"]["parked"]
                reasons.append(f"parked {x['ends']['parked']}x (-{5 * x['ends']['parked']})")
            fb = max(-15, min(6, 2 * len(x["feedback"]["worked"]) - 3 * len(x["feedback"]["failed"])))
            if fb:
                score += fb
                reasons.append(f"feedback ({'+' if fb > 0 else ''}{fb})")
            if any(v == "fail" for v in x["final"].values()):
                if score > 60:
                    reasons.append("not passed yet (cap 60)")
                score = min(score, 60)
            score = max(0, min(100, score))
        out.append({
            "stage": s, "label": STAGE_LABEL[s], "ran": ran, "score": score if ran else None, "reasons": reasons,
            "agents": x["agents"], "duration_s": x["duration_s"], "tokens": x["tokens"],
            "rounds": x["rounds"], "scores": x["scores"], "errors": x["errors"],
            "feedback": {k: v for k, v in x["feedback"].items() if v},
        })
    graded = [r["score"] for r in out if r["ran"]]
    return {"stages": out, "overall": round(sum(graded) / len(graded)) if graded else None,
            "general_feedback": {k: v for k, v in general.items() if v}}


def render_report(rep: dict) -> str:
    lines = [f"{'stage':<32}{'grade':>6}  reasons"]
    for r in rep["stages"]:
        g = "—" if r["score"] is None else str(r["score"])
        lines.append(f"{r['label']:<32}{g:>6}  {' · '.join(r['reasons'])}")
    lines.append(f"{'overall':<32}{'—' if rep['overall'] is None else rep['overall']:>6}")
    return "\n".join(lines)
