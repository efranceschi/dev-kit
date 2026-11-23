#!/usr/bin/env python3
"""dev_fence.py - the file fence of kit agents (conventions.md §17), run by Claude Code as a PreToolUse hook.

Standard library only. Reads the hook payload on stdin. It acts only for a subagent that has a slot: its agent id is
bound to the `Slot:` of its prompt in .dev/run/agent-slots.json (dev_agent_hook.py, at SubagentStart), and the slot's
allowed files are in .dev/run/slots/<n>.json (`dev_state.py slot open`). Anything else (the user's own session, an
agent without a slot, a project without .dev/state.json) passes untouched.

- Edit, Write, MultiEdit, NotebookEdit: allowed are the task's `files:` (a folder covers what is under it), the test
  files that match one of them by name (src/a.ts -> src/a.test.ts, tests/test_a.py, a_test.go), changelog.d/ and
  docs/setup.d/, and under .dev/ only the paths the slot lists (the agent's own outputs). Everything else is denied
  with the reason, and a `fence_deny` event is logged.
- Bash (every kit agent, slot or not): `git commit --no-verify` / `-n`, `git push --force` / `-f`, `git rebase` and
  `git reset --hard` are denied. The orchestrator uses the kit's scripts, never these.

Bash in general (`sed -i`, a script) is not covered: `dev_state.py slot check <n> --since <sha>` compares the agent's
diff with the same list at integration and fails it on a file outside.

It never fails the session: any error lets the call through (exit 0, no output).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
ALWAYS = ("changelog.d/", "docs/setup.d/")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|specs?)/|[._-](test|spec)\.[A-Za-z0-9]+$|(^|/)test_[^/]+$|_test\.[A-Za-z0-9]+$")
GIT_DENY = [
    ("git_no_verify", re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?commit\b[^;&|\n]*(?:--no-verify\b|\s-[A-Za-z]*n[A-Za-z]*\b)")),
    ("git_force_push", re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?push\b[^;&|\n]*(?:--force(?:-with-lease)?\b|\s-[A-Za-z]*f[A-Za-z]*\b|\s\+\S)")),
    ("git_rebase", re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?rebase\b")),
    ("git_reset_hard", re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?reset\b[^;&|\n]*--hard\b")),
]
KIT_AGENTS = None


def norm(p: str) -> str:
    return str(PurePosixPath(p.replace("\\", "/"))).lstrip("./").rstrip("/") if p else ""


def stem(p: str) -> str:
    name = PurePosixPath(p).name
    name = re.sub(r"^test_", "", name)
    name = name.split(".")[0]
    return re.sub(r"[._-](test|spec)$|_test$", "", name)


def allowed(slot: dict, rel: str) -> bool:
    """Whether a path (relative to the project or worktree root) is inside the slot's fence."""
    rel = norm(rel)
    if not rel:
        return False
    files = [norm(f) for f in slot.get("files") or [] if norm(f)]
    extra = [norm(f) for f in slot.get("allow") or [] if norm(f)]
    for f in files + extra:
        if rel == f or rel.startswith(f + "/"):
            return True
    if rel.startswith(".dev/") or rel == ".dev":
        return False  # only the outputs the slot lists, checked above
    if any(rel.startswith(a) for a in ALWAYS):
        return True
    if TEST_PATH.search(rel):
        st = stem(rel)
        return any(stem(f) == st for f in files if "." in PurePosixPath(f).name)
    return False


def kit_agents() -> set[str]:
    global KIT_AGENTS
    if KIT_AGENTS is None:
        d = Path(__file__).resolve().parents[3] / "agents"
        KIT_AGENTS = {p.stem for p in d.glob("*.md")} if d.is_dir() else set()
    return KIT_AGENTS


def read_json(p: Path) -> dict:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def rel_path(target: str, payload: dict, root: Path) -> str:
    t = Path(target)
    for base in (payload.get("cwd"), str(root)):
        if not base:
            continue
        b = Path(base)
        if not t.is_absolute():
            return norm(str(t))
        try:
            return norm(t.resolve().relative_to(b.resolve()).as_posix())
        except (ValueError, OSError):
            continue
    return norm(str(t))


def deny(dev: Path, reason: str, code: str, agent: str, scope: object, tool: str) -> dict:
    try:
        import dev_telemetry as tel
        tel.safe_emit(dev, "fence_deny", {"agent": agent or None, "scope": scope if scope and tel.ID_RE.match(str(scope)) else None,
                                          "tool": tool.lower(), "reason": code})
    except Exception:  # noqa: BLE001 - the log must never break the fence
        pass
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def decide(payload: dict, root: Path) -> dict | None:
    dev = root / ".dev"
    if payload.get("hook_event_name") != "PreToolUse" or not (dev / "state.json").is_file():
        return None
    aid = str(payload.get("agent_id") or "").lower()
    if not aid:
        return None  # the main session: never fenced
    bound = read_json(dev / "run" / "agent-slots.json").get(aid) or {}
    agent = str(bound.get("agent") or payload.get("agent_type") or "").removeprefix("dev-kit:").lower()
    slot_n = bound.get("slot")
    slot = read_json(dev / "run" / "slots" / f"{slot_n}.json") if slot_n is not None else {}
    if slot.get("closed_at"):
        slot = {}
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool == "Bash":
        if not slot and agent not in kit_agents():
            return None
        cmd = str(ti.get("command") or "")
        for code, rx in GIT_DENY:
            if rx.search(cmd):
                return deny(dev, f"dev-kit fence: `{code.replace('_', ' ')}` is not allowed for kit agents (conventions.md §17); "
                                 "commit normally and let the orchestrator integrate.", code, agent, slot.get("task"), tool)
        return None
    if tool not in EDIT_TOOLS or not slot:
        return None
    target = str(ti.get("file_path") or ti.get("notebook_path") or "")
    if not target:
        return None
    rel = rel_path(target, payload, root)
    if allowed(slot, rel):
        return None
    task = slot.get("task") or "this task"
    return deny(dev, f"Outside the files of {task}. If you need to edit {rel}, finish, and record the dependency or open an "
                     f"out_of_scope issue (conventions.md §17).", "outside_files", agent, slot.get("task"), tool)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
        out = decide(payload, root)
        if out:
            print(json.dumps(out))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
