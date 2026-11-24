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

- In a headless round (`dev_state.py round run`, DEV_KIT_ROUND_ID set), the orchestrator itself: applying a task's
  worktree by hand (`git apply`/`am`/`cherry-pick`, `git checkout|restore` from a dev-kit/T-nnn branch, `cp`/`rsync`
  out of a worktrees/ folder) is denied; `slot apply` and `start T-nnn --resume` do it and record the start. Every
  tool call of the round (orchestrator and agents) also leaves its last action in .dev/run/round-activity.json, which
  the board shows while the round runs.
- With a worktree (`slot open --worktree`, the slot records it): an edit outside the worktree is denied, the main
  checkout included, and so is a Bash command run from outside it, except `cd` into it, a read-only look, a kit script
  or a command that names the worktree (`git -C <wt>`).

- Auditors (the read-only kit agents): every tool call is a heartbeat in .dev/run/agent-beats.json (`dev_state.py
  qa-watch` reads it); a measurement script in .dev/tmp/ must run under `timeout`; once the auditor's time budget
  (autonomy.quality.watchdog.auditor_budget_min, from its SubagentStart) is spent, only writing its result file and
  `dev_score.py check` pass, so a stuck audit ends with what it verified.

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
MANUAL_ADOPT = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:apply|am|cherry-pick)\b"
    r"|\bgit\s+(?:-C\s+\S+\s+)?(?:checkout|restore|merge)\b[^;&|\n]*dev-kit/T-\d+"
    r"|\b(?:cp|rsync|ditto)\b[^;&|\n]*worktrees/")
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


def inside(path: str, folder: str) -> bool:
    """Whether a path is the folder or under it (lexically and after resolving links)."""
    for f in (os.path.normpath, os.path.realpath):
        try:
            a, b = f(path), f(folder)
        except (OSError, ValueError):
            continue
        if a == b or a.startswith(b.rstrip(os.sep) + os.sep):
            return True
    return False


READ_ONLY = re.compile(r"^\s*(?:git\s+(?:-C\s+\S+\s+)?(?:status|diff|log|show|rev-parse)\b|ls\b|pwd\s*$)")


def bash_ok_outside(cmd: str, wt: str) -> bool:
    """A command an agent with a worktree may run from outside it: `cd` into it, a read-only look, a kit script (they
    take --root), or a command that names the worktree itself (`git -C <wt>`, `npm --prefix <wt>`)."""
    c = cmd.strip()
    if re.fullmatch(r"cd\s+[\"']?" + re.escape(wt.rstrip("/")) + r"/?[\"']?", c):
        return True
    if wt.rstrip("/") in c or READ_ONLY.match(c):
        return True
    return bool(re.match(r"^\s*python3\s+-I\s+\S*core/scripts/dev_\w+\.py\b", c.replace('"', "")))


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


def note_activity(dev: Path, payload: dict, rnd: str) -> None:
    """The round's last action, for the board: tool, a short description, who (the orchestrator or an agent)."""
    from datetime import datetime, timezone
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tool = str(payload.get("tool_name") or "")
    what = ti.get("description") or ti.get("command") or ti.get("file_path") or ti.get("notebook_path") or ti.get("prompt") or ""
    what = " ".join(str(what).split())[:140]
    rec = {"round": rnd, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": tool, "what": what,
           "agent": str(payload.get("agent_type") or "").removeprefix("dev-kit:") or None}
    p = dev / "run" / "round-activity.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    os.replace(tmp, p)


AUDITORS = {"a11y-auditor", "code-reviewer", "copy-reviewer", "data-reviewer", "deps-auditor", "design-reviewer",
            "docs-reviewer", "ops-reviewer", "performance-auditor", "requirements-reviewer", "security-auditor",
            "spec-tracer", "test-auditor", "usability-auditor", "visual-reviewer"}
SCRATCH_RUN = re.compile(r"(?:^|[;&|]\s*)(?:node|python3?|bun|deno\s+run|npx\s+tsx|tsx)\s+(?:\./)?\.dev/tmp/")
WRAP_UP_OK = re.compile(r"dev_score\.py\s+check\b")


def watchdog_cfg(dev: Path) -> dict:
    q = (read_json(dev / "state.json").get("autonomy") or {}).get("quality") or {}
    wd = q.get("watchdog") if isinstance(q.get("watchdog"), dict) else {}
    try:
        return {"auditor_budget_min": int(os.environ.get("DEV_KIT_AUDITOR_BUDGET_MIN") or wd.get("auditor_budget_min", 30)),
                "stall_min": int(wd.get("stall_min", 20))}
    except (TypeError, ValueError):
        return {"auditor_budget_min": 30, "stall_min": 20}


def _age_s(iso: str) -> float | None:
    from datetime import datetime, timezone
    try:
        t = datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds()


def beat(dev: Path, aid: str, bound: dict, agent: str, payload: dict) -> None:
    """An auditor's heartbeat: its last tool call, in .dev/run/agent-beats.json (read by `dev_state.py qa-watch`)."""
    from datetime import datetime, timezone
    p = dev / "run" / "agent-beats.json"
    cur = read_json(p)
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    what = " ".join(str(ti.get("description") or ti.get("command") or ti.get("file_path") or ti.get("pattern") or "").split())[:120]
    cur[aid] = {"agent": agent, "scope": bound.get("scope"), "started": bound.get("at"), "tool": str(payload.get("tool_name") or ""),
                "what": what, "last": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    cur = dict(list(cur.items())[-100:])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".beat.tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def auditor_guard(dev: Path, payload: dict, agent: str, bound: dict) -> dict | None:
    """The time budget of an auditor (autonomy.quality.watchdog.auditor_budget_min): once it is spent, only writing
    the result file and `dev_score.py check` are allowed, so a stuck audit ends with what it verified instead of
    holding the whole round. A measurement script in .dev/tmp/ must run under `timeout`, so it cannot hang."""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    cmd = str(ti.get("command") or "") if tool == "Bash" else ""
    if cmd and SCRATCH_RUN.search(cmd) and not re.search(r"\btimeout\s+", cmd):
        return deny(dev, "dev-kit: run a measurement script under a time limit, e.g. `timeout 300 node .dev/tmp/<you>-<N>/bench.mjs`: "
                         "a script that hangs would hold the whole QA round (resource-isolation.md).", "untimed_script", agent,
                    bound.get("scope"), tool)
    age = _age_s(str(bound.get("at") or ""))
    budget = watchdog_cfg(dev)["auditor_budget_min"] * 60
    if age is None or age <= budget:
        return None
    if tool in EDIT_TOOLS and re.search(r"\.dev/(?:qa|review)/.+\.json$", str(ti.get("file_path") or "").replace("\\", "/")):
        return None
    if cmd and WRAP_UP_OK.search(cmd):
        return None
    return deny(dev, f"dev-kit: your time budget ({budget // 60} min) is spent. Stop auditing now: write your result to your "
                     "Output file with what you verified (name what you could not finish in `stats.not_run`), validate it "
                     "with dev_score.py check, and end with your short summary.", "budget_spent", agent, bound.get("scope"), tool)


def decide(payload: dict, root: Path) -> dict | None:
    dev = root / ".dev"
    if payload.get("hook_event_name") != "PreToolUse" or not (dev / "state.json").is_file():
        return None
    aid = str(payload.get("agent_id") or "").lower()
    rnd = os.environ.get("DEV_KIT_ROUND_ID") or ""
    if rnd:
        try:
            note_activity(dev, payload, rnd)
        except Exception:  # noqa: BLE001 - the board's view must never break the fence
            pass
    if not aid:
        if rnd and payload.get("tool_name") == "Bash":
            ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            if MANUAL_ADOPT.search(str(ti.get("command") or "")):
                return deny(dev, "dev-kit: a round never applies a task's worktree by hand: it would work on the task without "
                                 "recording its start. Use `dev_state.py start T-nnn --resume` (inline task: it applies the "
                                 "earlier attempt, staged) or `slot open N --task T-nnn --worktree` + `slot apply N` "
                                 "(implementer), conventions.md §17.", "manual_adopt", "orchestrator", None, "Bash")
        return None  # the main session: never fenced
    bound = read_json(dev / "run" / "agent-slots.json").get(aid) or {}
    agent = str(bound.get("agent") or payload.get("agent_type") or "").removeprefix("dev-kit:").lower()
    slot_n = bound.get("slot")
    slot = read_json(dev / "run" / "slots" / f"{slot_n}.json") if slot_n is not None else {}
    if slot.get("closed_at"):
        slot = {}
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    wt = str(slot.get("worktree") or "")
    if agent in AUDITORS:
        try:
            beat(dev, aid, bound, agent, payload)
        except Exception:  # noqa: BLE001 - the heartbeat must never break the fence
            pass
        out = auditor_guard(dev, payload, agent, bound)
        if out:
            return out
    if tool == "Bash":
        if not slot and agent not in kit_agents():
            return None
        cmd = str(ti.get("command") or "")
        for code, rx in GIT_DENY:
            if rx.search(cmd):
                return deny(dev, f"dev-kit fence: `{code.replace('_', ' ')}` is not allowed for kit agents (conventions.md §17); "
                                 "commit normally and let the orchestrator integrate.", code, agent, slot.get("task"), tool)
        if wt and not inside(payload.get("cwd") or str(root), wt) and not bash_ok_outside(cmd, wt):
            return deny(dev, f"dev-kit fence: you work in the worktree {wt}, not in {payload.get('cwd') or root}. Run `cd {wt}` "
                             "first (one command), then your command (conventions.md §17).", "outside_worktree", agent,
                        slot.get("task"), tool)
        return None
    if tool not in EDIT_TOOLS or not slot:
        return None
    target = str(ti.get("file_path") or ti.get("notebook_path") or "")
    if not target:
        return None
    if wt:
        ab = target if Path(target).is_absolute() else str(Path(payload.get("cwd") or wt) / target)
        if not inside(ab, wt):
            return deny(dev, f"dev-kit fence: {target} is outside your worktree {wt}. Never edit the main checkout: edit the same "
                             f"path under {wt} (conventions.md §17).", "outside_worktree", agent, slot.get("task"), tool)
        rel = norm(Path(os.path.normpath(ab)).relative_to(Path(os.path.normpath(wt))).as_posix())
    else:
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
        try:  # a tool call: the session works (dev_worker.parked)
            import dev_worker as dw
            dw.note_session(root, "tool")
        except Exception:  # noqa: BLE001 - never breaks the fence
            pass
        out = decide(payload, root)
        if out:
            print(json.dumps(out))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
