#!/usr/bin/env python3
"""Hook handler: the board's live agents panel and the Claude Code interface of a dev-kit project.

Wired to the SessionStart, SubagentStart, SubagentStop, UserPromptSubmit, PermissionRequest and Stop hooks
(hooks/hooks.json). Reads the hook payload from stdin.
- SessionStart, SubagentStart, SubagentStop: append one JSON line to <project>/.dev/run/agents.jsonl:
  {"ts": "...Z", "event": "session_start|agent_start|agent_stop", "session": "<id>", "agent_id": "<id>", "agent": "<type>",
   "transcript": "<path of the subagent's own transcript>"}; the board reads the `Scope:` line of the agent's prompt
  from that transcript to put it on its task card (Claude Code sends no task with the hook).
- SessionStart of a new session (source startup), with autonomy.ui.title on (default): set the session title
  ("dev-kit · <project> · <milestone, or phase and step>") and show one line with the next command (systemMessage).
- Stop, with autonomy.ui.notify on: show the notices queued by dev_state.py (gates, blocks, autopilot) as a
  desktop notification (OSC 9 terminal sequence) and a line in the chat, then clear the queue.
- SessionStart, UserPromptSubmit and Stop: when the board queued requests for Claude Code (dev_worker.py), one line
  with how many and the command that runs them (/dev-kit:worker); at a prompt or the end of a turn only when the
  set of waiting requests changed since the last notice. Only ids and counts: the text of a request never enters
  the session from here. Silent while a session listens (the plugin's monitor, armed by /dev-kit:board, announces
  each request by itself).
- PermissionRequest, only while this session runs a request from the board and a board is up to answer on: the
  permission goes to the board (tool, and the command or path cut to 300 characters, kept in .dev/run/approvals/
  until answered), the hook waits up to 10 minutes for Allow, Allow for this session or Deny, and answers Claude
  Code with it; no answer is a denial. Anywhere else it returns nothing and Claude Code's own prompt applies.

Privacy: only ids, the agent type and the subagent transcript's path are kept; prompts, messages and tool data in the payload are ignored, except
the tool and target of a permission request while it waits on the board.
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


def board_requests(root: Path, dev: Path, only_new: bool) -> dict | None:
    """One line about the requests the board queued, or None (nothing waiting, nothing new since the last one, or a
    session is listening: its monitor announces each request by itself)."""
    import dev_worker as dw
    if dw.listening(root):
        return None
    waiting = [x for x in dw.items(root) if x["status"] == "pending"]
    nxt = dw.claimable(root)
    ids = [x["id"] for x in waiting]
    seen_path = dev / "run" / "worker-notice.json"
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8")).get("ids")
    except (OSError, json.JSONDecodeError, AttributeError):
        seen = None
    if seen != ids:
        dw._write(seen_path, {"ids": ids})
    if not nxt or dw.modes(root)["paused"] or (only_new and seen == ids):
        return None
    n = len(waiting) or 1
    text = f"dev-kit board: {n} request{'s' if n != 1 else ''} waiting ({', '.join(ids[:5]) or nxt['id']}) · run /dev-kit:worker"
    return {"systemMessage": text, "context": f"{text}. The requests come from the project's web board; /dev-kit:worker runs them."}


def session_rules(suggestions: object) -> tuple[list[dict], str | None]:
    """What "Allow for this session" keeps: the allow rules Claude Code itself suggests for this request (and
    "accept edits" for file edits), always with destination `session`, so nothing outlives the session and nothing
    is written to a settings file. Never a deny/ask rule, a directory, or any other permission mode."""
    keep: list[dict] = []
    labels: list[str] = []
    for s in suggestions if isinstance(suggestions, list) else []:
        if not isinstance(s, dict):
            continue
        if s.get("type") == "addRules" and s.get("behavior") == "allow" and isinstance(s.get("rules"), list):
            rules = [{k: r[k] for k in ("toolName", "ruleContent") if isinstance(r.get(k), str)}
                     for r in s["rules"] if isinstance(r, dict) and isinstance(r.get("toolName"), str)]
            if rules:
                keep.append({"type": "addRules", "rules": rules, "behavior": "allow", "destination": "session"})
                labels += [f"{r['toolName']}({r['ruleContent']})" if r.get("ruleContent") else r["toolName"] for r in rules]
        elif s.get("type") == "setMode" and s.get("mode") == "acceptEdits":
            keep.append({"type": "setMode", "mode": "acceptEdits", "destination": "session"})
            labels.append("all file edits")
    return keep, (CONTROL.sub(" ", ", ".join(labels))[:200] or None)


def board_takes_requests(dev: Path) -> bool:
    try:
        rec = json.loads((dev / "run" / "board.json").read_text(encoding="utf-8"))
        os.kill(int(rec["pid"]), 0)
        return bool(rec.get("actions"))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def permission(root: Path, dev: Path, payload: dict) -> dict | None:
    """A permission prompt of Claude Code while this session runs a request from the board: the user answers on the
    board (Allow, Allow for this session, Deny), because nobody may be at the console. No answer within 10 minutes
    is a denial. Outside a board request, or with no board to answer on, nothing is returned and Claude Code's own
    prompt handles it as usual."""
    import dev_worker as dw
    tool = str(payload.get("tool_name") or "")
    if not tool or tool in ("AskUserQuestion", "ExitPlanMode"):
        return None  # a question goes to the board as a question (board mode), never as a permission
    run = dw.board_run(root)
    if not run or not board_takes_requests(dev):
        return None
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    target = next((str(ti[k]) for k in ("command", "file_path", "notebook_path", "url", "path", "pattern", "query") if ti.get(k)),
                  "") or json.dumps(ti, ensure_ascii=False)
    keep, label = session_rules(payload.get("permission_suggestions"))
    try:
        wait_s = min(float(dw.APPROVAL_WAIT_S), max(1.0, float(os.environ.get("DEV_KIT_APPROVAL_WAIT_S") or dw.APPROVAL_WAIT_S)))
    except ValueError:
        wait_s = float(dw.APPROVAL_WAIT_S)
    rid = run["id"]
    aid = dw.request_approval(root, tool, target, rid, label, wait_s)
    got = dw.wait_decision(root, aid, wait_s, rid)
    if got in ("allow", "allow_session"):
        decision: dict = {"behavior": "allow"}
        if got == "allow_session" and keep:
            decision["updatedPermissions"] = keep
    else:
        why = {"deny": f"Denied by the user on the dev-kit board ({rid}). Do not retry this action: go on without it, or "
                       "finish the request as failed with a note naming what was denied.",
               "cancelled": f"{rid} was cancelled on the dev-kit board. Stop at the next safe point, as the worker skill says.",
               "timeout": f"Nobody answered this permission on the dev-kit board within {max(1, round(wait_s / 60))} minutes, so it "
                          f"is denied ({rid}). Do not retry it now: finish what does not need it, or finish the request as "
                          "failed with a note naming the permission that was missing."}[got]
        decision = {"behavior": "deny", "message": why}
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def trace(dev: Path, name: str, payload: dict, out: dict | None, started: float) -> None:
    """With DEV_KIT_HOOK_TRACE=1 in Claude Code's environment: one line per hook run in .dev/run/hook-trace.jsonl,
    for docs/board-autonomy-check.md. It records which keys the payload has, never their values, except what a
    permission check needs to be understood: the tool name and the rules Claude Code suggested."""
    import time
    import dev_worker as dw
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": name, "parents": dw.ancestors()[1:8],
           "payload_keys": sorted(payload), "elapsed_s": round(time.monotonic() - started, 2), "answered": bool(out)}
    if name == "PermissionRequest":
        rec.update(tool=tok(payload.get("tool_name")), permission_mode=tok(payload.get("permission_mode")),
                   agent_type=tok(payload.get("agent_type")), suggestions=payload.get("permission_suggestions"),
                   decision=((out or {}).get("hookSpecificOutput") or {}).get("decision"))
    path = dev / "run" / "hook-trace.jsonl"
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def merge(out: dict | None, extra: dict | None, event: str) -> dict | None:
    if not extra:
        return out
    out = dict(out or {})
    out["systemMessage"] = "\n".join(x for x in (out.get("systemMessage"), extra["systemMessage"]) if x)
    if event in ("SessionStart", "UserPromptSubmit"):
        hso = dict(out.get("hookSpecificOutput") or {"hookEventName": event})
        hso["additionalContext"] = extra["context"]
        out["hookSpecificOutput"] = hso
    return out


def main() -> int:
    try:
        import time
        started = time.monotonic()
        payload = json.load(sys.stdin)
        name = str(payload.get("hook_event_name"))
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
        dev = root / ".dev"
        if not (dev / "state.json").is_file():
            return 0
        out = None
        if name in EVENTS:
            record_agent(dev, EVENTS[name], payload)
        if name == "SessionStart" and payload.get("source", "startup") == "startup" and ui_flags(dev).get("title"):
            out = session_banner(root)
        elif name == "Stop":
            out = take_notices(dev)
        elif name == "PermissionRequest":
            out = permission(root, dev, payload)
        if name in ("SessionStart", "UserPromptSubmit", "Stop") and not str(payload.get("prompt") or "").startswith("/dev-kit:worker"):
            try:
                out = merge(out, board_requests(root, dev, only_new=name != "SessionStart"), name)
            except Exception:  # noqa: BLE001 - the board's queue must never break a hook
                pass
        if os.environ.get("DEV_KIT_HOOK_TRACE") == "1":
            try:
                trace(dev, name, payload, out, started)
            except Exception:  # noqa: BLE001
                pass
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
