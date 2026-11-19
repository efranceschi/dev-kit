#!/usr/bin/env python3
"""Hook handler: records when agents and subagents start and stop, for the live agents panel of the board.

Wired to the SessionStart, SubagentStart and SubagentStop hooks (hooks/hooks.json). Reads the hook payload
from stdin and appends one JSON line to <project>/.dev/run/agents.jsonl:
  {"ts": "...Z", "event": "session_start|agent_start|agent_stop", "session": "<id>", "agent_id": "<id>", "agent": "<type>"}

Privacy: only ids and the agent type are kept; prompts, messages and tool data in the payload are ignored.
It never fails a hook (always exits 0) and does nothing outside a dev-kit project (no .dev/ folder).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENTS = {"SessionStart": "session_start", "SubagentStart": "agent_start", "SubagentStop": "agent_stop"}
MAX_BYTES = 256 * 1024
KEEP_LINES = 500
TOKEN = re.compile(r"[^A-Za-z0-9_.:\-]")


def tok(v: object) -> str:
    return TOKEN.sub("", str(v or ""))[:80]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        event = EVENTS.get(str(payload.get("hook_event_name")))
        if not event:
            return 0
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
        dev = root / ".dev"
        if not dev.is_dir():
            return 0
        run = dev / "run"
        run.mkdir(exist_ok=True)
        path = run / "agents.jsonl"
        rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": event,
               "session": tok(payload.get("session_id")), "agent_id": tok(payload.get("agent_id")),
               "agent": tok(payload.get("agent_type"))}
        if path.exists() and path.stat().st_size > MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()[-KEEP_LINES:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
