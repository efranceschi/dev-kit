#!/usr/bin/env python3
"""Hook handler: the board's live agents panel and the Claude Code interface of a dev-kit project.

Wired to the SessionStart, SubagentStart, SubagentStop and Stop hooks (hooks/hooks.json). Reads the hook payload
from stdin.
- SessionStart, SubagentStart, SubagentStop: append one JSON line to <project>/.dev/run/agents.jsonl:
  {"ts": "...Z", "event": "session_start|agent_start|agent_stop", "session": "<id>", "agent_id": "<id>", "agent": "<type>"}
- SessionStart of a new session (source startup), with autonomy.ui.title on (default): set the session title
  ("dev-kit · <project> · <milestone or phase>") and show one line with the next command (systemMessage).
- Stop, with autonomy.ui.notify on: show the notices queued by dev_state.py (gates, blocks, autopilot) as a
  desktop notification (OSC 9 terminal sequence) and a line in the chat, then clear the queue.

Privacy: only ids and the agent type are kept; prompts, messages and tool data in the payload are ignored.
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


def record_agent(dev: Path, event: str, payload: dict) -> None:
    run = dev / "run"
    run.mkdir(exist_ok=True)
    if not (run / ".gitignore").exists():
        (run / ".gitignore").write_text("*\n", encoding="utf-8")
    path = run / "agents.jsonl"
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": event,
           "session": tok(payload.get("session_id")), "agent_id": tok(payload.get("agent_id")),
           "agent": tok(payload.get("agent_type"))}
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
    where = str(store.state.get("phase") or "")
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
        if name == "SessionStart" and payload.get("source", "startup") == "startup" and ui_flags(dev).get("title"):
            out = session_banner(root)
        elif name == "Stop":
            out = take_notices(dev)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
