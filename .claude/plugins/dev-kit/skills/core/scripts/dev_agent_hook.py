#!/usr/bin/env python3
"""Hook handler: the board's live agents panel and the Claude Code interface of a dev-kit project.

Wired to the SessionStart, PreToolUse (Agent tool), PermissionRequest, SubagentStart, SubagentStop and Stop hooks
(hooks/hooks.json).
Reads the hook payload from stdin.
- SessionStart, SubagentStart, SubagentStop: append one JSON line to <project>/.dev/run/agents.jsonl:
  {"ts": "...Z", "event": "session_start|agent_start|agent_stop", "session": "<id>", "agent_id": "<id>", "agent": "<type>",
   "transcript": "<path of the subagent's own transcript>"}; the board reads the `Scope:` line of the agent's prompt
  from that transcript to put it on its task card (Claude Code sends no task with the hook).
- SessionStart of a new session (source startup), with autonomy.ui.title on (default): set the session title
  ("dev-kit · <project> · <milestone, or phase and step>") and show one line with the next command (systemMessage).
- Stop, with autonomy.ui.notify on: show the notices queued by dev_state.py (gates, blocks, autopilot) as a
  desktop notification (OSC 9 terminal sequence) and a line in the chat, then clear the queue.
- PermissionRequest, only in a round child (`dev_state.py round run`, DEV_KIT_ROUND_ID set), where nobody is at
  the console: a Bash command made only of the kit's safe set (dev_perms.py: read-only inspection, a timed
  measurement script in .dev/tmp/) is allowed at once. Any other permission is left to Claude Code (in a headless
  child nobody answers, so it is denied) and is kept in .dev/run/permission-misses.json with the rule that would
  allow it (`dev_perms.py show`, read-only in the board's Needs you). Anywhere else it returns nothing.
- PreToolUse (Agent tool), SubagentStart, SubagentStop: the session log's agent_spawn / agent_end events
  (conventions.md §13), written here so no skill has to: agent, model and effort (from the kit agent's frontmatter,
  or the model the Agent call asked for), the skill running it (innermost open skill in .dev/run/skills.json),
  scope (the `Scope:` line of the prompt, read at PreToolUse and kept as a token only), round (a milestone's QA
  round), duration and tokens (from the subagent's own transcript). The `Slot:` line binds the agent id to its slot
  in .dev/run/agent-slots.json, for the file fence (dev_fence.py, conventions.md §17).

Privacy: only ids, the agent type and the subagent transcript's path are kept; prompts, messages and tool data in the
payload are ignored.
It never fails a hook (always exits 0) and does nothing outside a dev-kit project (no .dev/state.json).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir

EVENTS = {"SessionStart": "session_start", "SubagentStart": "agent_start", "SubagentStop": "agent_stop"}
MAX_BYTES = 256 * 1024
KEEP_LINES = 500
TOKEN = re.compile(r"[^A-Za-z0-9_.:\-]")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def tok(v: object) -> str:
    return TOKEN.sub("", str(v or ""))[:80]


def ui_flags(dev: Path) -> dict:
    try:
        auto = json.loads((dev / "state.json").read_text(encoding="utf-8")).get("autonomy", {})
        return {"title": True, "notify": False, **(auto.get("ui") or {})}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {"title": True, "notify": False}


SUBAGENT_FILE = re.compile(r"agent-[A-Za-z0-9_\-]{1,128}\.jsonl")


def subagent_transcript(payload: dict) -> str | None:
    """Path of a subagent's own transcript: given on SubagentStop (agent_transcript_path); on SubagentStart derived
    from the session transcript, as <dir>/<session>/subagents/agent-<agent_id>.jsonl. Only that shape is kept."""
    if payload.get("hook_event_name") not in ("SubagentStart", "SubagentStop"):
        return None
    given = payload.get("agent_transcript_path")
    if isinstance(given, str) and given:
        p = Path(given).expanduser()
    else:
        main_tr, sid, aid = payload.get("transcript_path"), tok(payload.get("session_id")), tok(payload.get("agent_id"))
        if not (isinstance(main_tr, str) and main_tr and sid and aid):
            return None
        p = Path(main_tr).expanduser().parent / sid / "subagents" / f"agent-{aid.removeprefix('agent-')}.jsonl"
    if not (SUBAGENT_FILE.fullmatch(p.name) and p.parent.name == "subagents" and p.is_absolute()) or CONTROL.search(str(p)):
        return None
    return str(p)


SLOT_RE = re.compile(r"(?m)^\s*Slot:\s*(\d{1,3})\b")
SCOPE_RE = re.compile(r"(?m)^\s*Scope:\s*(T-\d{1,5}|M\d{1,3}(?:\.\d{1,2})?|hotfix-T-\d{1,5})\b")
AGENT_TOOLS = ("Agent", "Task")
# the read-only kit agents: a permission of theirs denied in a round child is recorded as skipped by the auditor (§17)
AUDITOR_AGENTS = {"a11y-auditor", "code-reviewer", "copy-reviewer", "data-reviewer", "deps-auditor", "design-reviewer",
                  "docs-reviewer", "ops-reviewer", "performance-auditor", "requirements-reviewer", "security-auditor",
                  "spec-tracer", "test-auditor", "usability-auditor", "visual-reviewer"}
KIT_DIR = Path(__file__).resolve().parents[3]


def agent_meta(agent_type: str) -> dict:
    """model and effort of a kit agent, from its frontmatter (agents/<name>.md); {} for other agents."""
    name = agent_type.removeprefix("dev-kit:")
    p = KIT_DIR / "agents" / f"{name}.md"
    if not re.fullmatch(r"[a-z0-9-]{1,60}", name) or not p.is_file():
        return {}
    out = {}
    try:
        head = p.read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, IndexError):
        return {}
    for line in head.splitlines():
        k, _, v = line.partition(":")
        if k.strip() in ("model", "effort"):
            out[k.strip()] = tok(v.strip()).lower()
    return out


def pending_path(dev: Path) -> Path:
    return dev / "run" / "agent-pending.jsonl"


def note_pending(dev: Path, payload: dict) -> None:
    """PreToolUse of the Agent tool: keep the scope and the model asked for until SubagentStart pairs them."""
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    m = SCOPE_RE.search(str(ti.get("prompt") or "")) or SCOPE_RE.search("Scope: " + str(ti.get("description") or "").split(" ")[0])
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "session": tok(payload.get("session_id")),
           "agent": tok(ti.get("subagent_type") or "general-purpose"), "scope": m.group(1) if m else None,
           "model": tok(ti.get("model")).lower() or None}
    sl = SLOT_RE.search(str(ti.get("prompt") or ""))
    if sl:
        rec["slot"] = int(sl.group(1))
    p = pending_path(dev)
    p.parent.mkdir(exist_ok=True)
    lines = p.read_text(encoding="utf-8").splitlines()[-50:] if p.exists() else []
    lines.append(json.dumps(rec, separators=(",", ":")))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def take_pending(dev: Path, session: str, agent: str) -> dict:
    p = pending_path(dev)
    if not p.exists():
        return {}
    recs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    i = next((n for n, r in enumerate(recs) if r.get("session") == session and r.get("agent") == agent), None)
    if i is None:
        return {}
    rec = recs.pop(i)
    p.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in recs), encoding="utf-8")
    return rec


def agents_log(dev: Path) -> list[dict]:
    out = []
    try:
        for line in (dev / "run" / "agents.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    return out


def _secs(a: str, b: str) -> float | None:
    try:
        f = "%Y-%m-%dT%H:%M:%SZ"
        return max(0.0, (datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds())
    except (TypeError, ValueError):
        return None


def bind_slot(dev: Path, aid: str, slot: object, agent: object, scope: object) -> None:
    """.dev/run/agent-slots.json: agent id -> its `Slot:` (when the prompt had one), agent and scope."""
    p = dev / "run" / "agent-slots.json"
    try:
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        cur = {}
    if not isinstance(cur, dict):
        cur = {}
    cur[aid] = {"slot": slot, "agent": agent, "scope": scope, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    cur = dict(list(cur.items())[-200:])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    tmp.replace(p)


def emit_agent_event(dev: Path, event: str, payload: dict) -> None:
    """agent_spawn at SubagentStart, agent_end at SubagentStop, in the session log (never fails the hook)."""
    import dev_telemetry as tel
    session, aid = tok(payload.get("session_id")), tok(payload.get("agent_id")).lower()
    agent = tok(payload.get("agent_type")) or "subagent"
    log = agents_log(dev)
    start = next((r for r in reversed(log) if r.get("event") == "agent_start" and r.get("agent_id") == tok(payload.get("agent_id"))), None)
    if event == "agent_start":
        pend = take_pending(dev, session, agent)
        meta = agent_meta(agent)
        fields = {"agent": agent.removeprefix("dev-kit:").lower(), "agent_id": aid or None, "source": "hook",
                  "model": pend.get("model") or meta.get("model") or "inherit", "effort": meta.get("effort"),
                  "scope": pend.get("scope")}
        open_sk = [x for x in tel.open_skills(dev) if x["session"] in (session, "-")] or tel.open_skills(dev)
        if open_sk:
            fields["skill"] = tok(open_sk[-1]["skill"]).lower() or None
            fields["scope"] = fields["scope"] or open_sk[-1]["scope"]
        sc = str(fields.get("scope") or "")
        if re.fullmatch(r"M\d+(?:\.\d+)?", sc):
            try:
                st = json.loads((dev / "state.json").read_text(encoding="utf-8"))
                fields["round"] = int(((st.get("milestones") or {}).get(sc) or {}).get("qa_runs", 0)) + 1
            except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
                pass
        if fields["scope"] and not tel.ID_RE.match(str(fields["scope"])):
            fields["scope"] = tel.scope_token(fields["scope"])
        # remember what the spawn said, for the end event
        payload["_spawn"] = fields
        if aid:  # the file fence (dev_fence.py) finds the agent's slot by its id
            bind_slot(dev, aid, pend.get("slot"), fields.get("agent"), fields.get("scope"))
        tel.safe_emit(dev, "agent_spawn", fields)
        return
    spawn = next((e for e in reversed(tel.read_events(dev)[0]) if e["event"] == "agent_spawn" and e.get("agent_id") == aid), {}) if aid else {}
    fields = {k: spawn.get(k) for k in ("agent", "agent_id", "model", "effort", "scope", "skill", "round")}
    fields.update(agent=fields.get("agent") or agent.removeprefix("dev-kit:").lower(), source="hook", status="ok",
                  duration_s=_secs(start["ts"], datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")) if start else None)
    tr = subagent_transcript(payload)
    if tr and Path(tr).is_file():
        try:
            import dev_cost
            rows = dev_cost.parse_file(Path(tr), agent, aid)
            fields.update(tokens_in=sum(r["input"] for r in rows), tokens_out=sum(r["output"] for r in rows),
                          cache_read=sum(r["cache_read"] for r in rows),
                          cache_write=sum(r["cache_write_5m"] + r["cache_write_1h"] for r in rows))
            fields["tokens"] = fields["tokens_in"] + fields["tokens_out"] + fields["cache_read"] + fields["cache_write"]
        except Exception:  # noqa: BLE001 - tokens are a bonus; the event is written without them
            pass
    tel.safe_emit(dev, "agent_end", fields)


def record_agent(dev: Path, event: str, payload: dict) -> None:
    run = dev / "run"
    run.mkdir(exist_ok=True)
    if not (run / ".gitignore").exists():
        (run / ".gitignore").write_text("*\n", encoding="utf-8")
    path = run / "agents.jsonl"
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": event,
           "session": tok(payload.get("session_id")), "agent_id": tok(payload.get("agent_id")),
           "agent": tok(payload.get("agent_type"))}
    tr = subagent_transcript(payload)
    if tr:
        rec["transcript"] = tr
    if path.exists() and path.stat().st_size > MAX_BYTES:
        lines = path.read_text(encoding="utf-8").splitlines()[-KEEP_LINES:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def session_banner(root: Path) -> dict | None:
    import dev_state as ds
    store = ds.Store(root)
    store.state = json.loads(store.path.read_text(encoding="utf-8"))
    name = str(store.state.get("project") or root.name)[:40]
    where = ds.phase_label(store, ds.lifecycle(store))
    for m in store.milestone_order():
        live = [v for v in store.tasks().values() if v["milestone"] == m and v["status"] != "dropped"]
        if live and store.milestones()[m].get("gate", "pending") == "pending":
            where = m
            break
    nxt = ds.next_command(store)
    return {"systemMessage": f"dev-kit · {name} · {where} · next: {nxt}",
            "hookSpecificOutput": {"hookEventName": "SessionStart", "sessionTitle": CONTROL.sub(" ", f"dev-kit · {name} · {where}")}}


def take_notices(dev: Path) -> dict | None:
    path = dev / "run" / "notify.jsonl"
    if not path.exists():
        return None
    texts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            texts.append(CONTROL.sub(" ", str(json.loads(line).get("text", ""))).strip())
        except json.JSONDecodeError:
            continue
    path.unlink(missing_ok=True)
    texts = [t for t in texts if t][-5:]
    if not texts or not ui_flags(dev).get("notify"):
        return None
    return {"systemMessage": "\n".join(texts), "terminalSequence": f"\x1b]9;{texts[-1][:180]}\x07"}


def permission(root: Path, dev: Path, payload: dict) -> dict | None:
    """A permission prompt of Claude Code in a round child (conventions.md §17): the kit's safe set is allowed at
    once, so an audit never waits for `gzip -c a.js | wc -c`; anything else is recorded as a miss and left to Claude
    Code. Outside a round child nothing is returned and Claude Code's own prompt applies as usual."""
    import dev_perms
    rnd = os.environ.get("DEV_KIT_ROUND_ID") or ""
    tool = str(payload.get("tool_name") or "")
    if not rnd or not tool or tool in ("AskUserQuestion", "ExitPlanMode"):
        return None
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool == "Bash" and dev_perms.is_safe(str(ti.get("command") or "")):
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
    target = next((str(ti[k]) for k in ("command", "file_path", "notebook_path", "url", "path", "pattern", "query") if ti.get(k)),
                  "") or json.dumps(ti, ensure_ascii=False)
    agent = str(payload.get("agent_type") or "").removeprefix("dev-kit:")
    with_miss(root, tool, target, agent, "auditor_skipped" if agent in AUDITOR_AGENTS else "no_answer", suggested_rule(payload), rnd)
    return None


def suggested_rule(payload: dict) -> str | None:
    """The allow rule Claude Code itself suggests for this request, as text (shown with a denied permission)."""
    labels: list[str] = []
    sug = payload.get("permission_suggestions")
    for s in sug if isinstance(sug, list) else []:
        if isinstance(s, dict) and s.get("type") == "addRules" and s.get("behavior") == "allow" and isinstance(s.get("rules"), list):
            labels += [f"{r['toolName']}({r['ruleContent']})" if isinstance(r.get("ruleContent"), str) else r["toolName"]
                       for r in s["rules"] if isinstance(r, dict) and isinstance(r.get("toolName"), str)]
    return CONTROL.sub(" ", ", ".join(labels))[:200] or None


def with_miss(root: Path, tool: str, target: str, agent: str, how: str, label: str | None, where: str) -> None:
    try:
        import dev_perms
        dev_perms.record_miss(root, tool, target, agent or None, how, label, where)
    except Exception:  # noqa: BLE001 - the record is a convenience; it never breaks the hook
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        name = str(payload.get("hook_event_name"))
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
        dev = root / ".dev"
        if not (dev / "state.json").is_file():
            return 0
        out = None
        if name in EVENTS:
            record_agent(dev, EVENTS[name], payload)
            if name in ("SubagentStart", "SubagentStop"):
                try:
                    emit_agent_event(dev, EVENTS[name], payload)
                except Exception:  # noqa: BLE001 - the session log must never break a hook
                    pass
        if name == "PreToolUse" and payload.get("tool_name") in AGENT_TOOLS:
            try:
                note_pending(dev, payload)
            except Exception:  # noqa: BLE001
                pass
        if name == "SessionStart" and payload.get("source", "startup") == "startup" and ui_flags(dev).get("title"):
            out = session_banner(root)
        elif name == "Stop":
            out = take_notices(dev)
        elif name == "PermissionRequest":
            out = permission(root, dev, payload)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
