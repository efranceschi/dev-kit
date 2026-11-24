"""dev-kit 3.5: implementers' worktrees are created by the kit from the work branch, never from main by the agent
tool; the fence keeps an agent inside its worktree; a round that stops leaves a true state (reconcile); a headless
round does not wait for a person on the kit's own commands and stops at the first unanswered permission.

The central case is the field report: main is old, the project works on new_version.
Run: python3 -I -m unittest .claude/plugins/dev-kit/skills/core/tests/test_worktree_isolation.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
sys.path.insert(0, str(SCRIPTS))


def task(n: int, files: str) -> str:
    return (f"### T-{n:03d} Step {n}\n- status: todo\n- deps: \n- type: feature\n- acceptance:\n  - AC-{n}: step {n} works\n"
            f"- test_notes: unit\n- files: {files}\n\n")


PLAN = "# Implementation plan — shop\n\n## R1 — First\n\n## M1 — Core\nCore.\n\n" + task(1, "src/a.py") + task(2, "src/b.py")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION", "DEV_KIT_CLAUDE", "DEV_KIT_ROUND_ID")}
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / "README.md").write_text("old main\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "old main")
        self.git("checkout", "-qb", "new_version")
        self.ds("init", "--language", "en", "--project", "shop")
        (self.dev / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "work on new_version")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0, env: dict | None = None) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env={**self.env, **(env or {})})
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(["git", "-C", str(cwd or self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def state(self) -> dict:
        return json.loads((self.dev / "state.json").read_text(encoding="utf-8"))

    def slot(self, n: int) -> dict:
        return json.loads((self.dev / "run" / "slots" / f"{n}.json").read_text(encoding="utf-8"))


class TestWorktreeBase(Base):
    def test_worktree_starts_from_the_work_branch_not_main(self) -> None:
        self.ds("start", "T-001")
        out = self.ds("slot", "open", "1", "--task", "T-001", "--worktree").stdout
        self.assertIn("from new_version", out)
        rec = self.slot(1)
        self.assertEqual(rec["base_sha"], self.git("rev-parse", "new_version"))
        wt = Path(rec["worktree"])
        self.assertTrue((wt / ".dev" / "state.json").exists() and (wt / "src" / "a.py").exists())
        self.assertIn(f"Worktree: {wt}", self.ds("brief", "T-001").stdout)

    def test_configured_base_branch_wins_and_a_wrong_base_is_refused(self) -> None:
        self.ds("set", "autonomy.git.base_branch", "main")
        self.ds("start", "T-001")
        p = self.ds("slot", "open", "1", "--task", "T-001", "--worktree", expect=1)
        self.assertIn("no .dev/state.json", p.stderr)
        self.assertFalse((self.dev / "run" / "worktrees" / "T-001").exists())
        self.ds("set", "autonomy.git.base_branch", "null")
        self.ds("slot", "open", "1", "--task", "T-001", "--worktree")

    def test_pipeline_uses_the_work_branch(self) -> None:
        out = json.loads(self.ds("pipeline", "status", "--json").stdout)
        self.assertEqual(out["work_branch"], "new_version")

    def test_apply_brings_only_the_task_changes_and_remove_needs_them_applied(self) -> None:
        self.ds("start", "T-001")
        self.ds("slot", "open", "1", "--task", "T-001", "--worktree")
        wt = Path(self.slot(1)["worktree"])
        (wt / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
        self.ds("slot", "close", "1", "--remove", expect=1)  # not applied yet: kept
        (wt / "src" / "zz.py").write_text("x\n", encoding="utf-8")
        self.assertIn("outside the fence", self.ds("slot", "apply", "1", expect=1).stdout)
        (wt / "src" / "zz.py").unlink()
        self.ds("slot", "apply", "1")
        self.assertEqual((self.root / "src" / "a.py").read_text(encoding="utf-8"), "a = 2\n")
        self.assertIn("already applied", self.ds("slot", "apply", "1").stdout)
        self.ds("slot", "close", "1", "--remove")
        self.assertFalse(wt.exists())
        self.assertNotIn("dev-kit/T-001", self.git("branch"))


class TestFence(Base):
    def decide(self, tool: str, ti: dict, cwd: Path) -> dict | None:
        import dev_fence
        (self.dev / "run").mkdir(parents=True, exist_ok=True)
        (self.dev / "run" / "agent-slots.json").write_text(json.dumps({"a1": {"slot": 1, "agent": "implementer"}}), encoding="utf-8")
        return dev_fence.decide({"hook_event_name": "PreToolUse", "agent_id": "a1", "tool_name": tool, "tool_input": ti,
                                 "cwd": str(cwd)}, self.root)

    def test_edits_and_commands_outside_the_worktree_are_denied(self) -> None:
        self.ds("start", "T-001")
        self.ds("slot", "open", "1", "--task", "T-001", "--worktree")
        wt = Path(self.slot(1)["worktree"])
        denied = self.decide("Edit", {"file_path": str(self.root / "src" / "a.py")}, self.root)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("outside your worktree", denied["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.decide("Edit", {"file_path": str(wt / "src" / "a.py")}, wt))
        self.assertIsNone(self.decide("Edit", {"file_path": "src/a.py"}, wt))
        self.assertEqual(self.decide("Edit", {"file_path": str(wt / "src" / "b.py")}, wt)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNotNone(self.decide("Bash", {"command": "pytest -q"}, self.root))
        self.assertIsNone(self.decide("Bash", {"command": f"cd {wt}"}, self.root))
        self.assertIsNone(self.decide("Bash", {"command": "git status"}, self.root))
        self.assertIsNone(self.decide("Bash", {"command": "pytest -q"}, wt))

    def test_implementer_and_implement_say_it(self) -> None:
        imp = (CORE.parents[1] / "agents" / "implementer.md").read_text(encoding="utf-8")
        self.assertIn("show-toplevel", imp)
        sk = (CORE.parent / "implement" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("slot open N --task T-xxx --worktree", sk)
        self.assertNotIn('isolation: "worktree"', sk)
        self.assertIn("DS reconcile", sk)


FAKE_STUCK = """#!/bin/sh
# an implement round that starts two tasks with their slots, then dies before closing anything
printf '%s\\n' "$@" > "$CLAUDE_PROJECT_DIR/.dev/run/fake-args"
DS="{py} -I {state} --root $CLAUDE_PROJECT_DIR"
$DS start T-001 >/dev/null
$DS start T-002 --force >/dev/null
$DS slot open 1 --task T-001 --worktree >/dev/null
$DS slot open 2 --task T-002 --worktree >/dev/null
echo "a = 3" > "$CLAUDE_PROJECT_DIR/.dev/run/worktrees/T-001/src/a.py"
exit 1
"""

class TestRoundReconcile(Base):
    def fake(self, body: str) -> Path:
        exe = self.root / ".dev" / "tmp" / "fake-claude"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(body.format(py=sys.executable, state=STATE), encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        return exe

    def test_a_round_that_dies_leaves_a_true_state(self) -> None:
        (self.dev / "architecture.md").write_text("# Arch\n\n## 8 Commands\n\n| purpose | command |\n|---|---|\n| test | `pytest -q` |\n",
                                                  encoding="utf-8")
        p = self.ds("round", "run", "implement", "M1", expect=1, env={"DEV_KIT_CLAUDE": str(self.fake(FAKE_STUCK))})
        out = json.loads(p.stdout)
        self.assertEqual(sorted(out["reconciled"]["tasks_blocked"]), ["T-001", "T-002"])
        self.assertEqual(out["verdict"], "error")  # the child failed; the state says why
        s = self.state()["tasks"]
        self.assertEqual((s["T-001"]["status"], s["T-002"]["status"]), ("blocked", "blocked"))
        self.assertTrue(self.slot(1).get("closed_at") and self.slot(2).get("closed_at"))
        self.assertTrue((self.dev / "run" / "worktrees" / "T-001").exists())   # has changes: kept
        self.assertFalse((self.dev / "run" / "worktrees" / "T-002").exists())  # clean: removed
        import dev_ledger
        self.assertEqual(dev_ledger.load(self.dev)["task:T-001"].get("ref"), "dev-kit/T-001")
        args = (self.dev / "run" / "fake-args").read_text(encoding="utf-8").split("\n")
        allowed = args[args.index("--allowedTools") + 1:]
        self.assertTrue(any("core/scripts/dev_" in x for x in allowed))
        self.assertIn("Bash(pytest -q*)", allowed)
        self.assertFalse((self.dev / "run" / "round.json").exists())

    def test_adopt_moves_only_the_task_files_out_of_the_main_checkout(self) -> None:
        self.ds("start", "T-001")
        (self.root / "src" / "a.py").write_text("a = 9\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("mine\n", encoding="utf-8")
        res = json.loads(self.ds("reconcile", "--adopt", "T-001", "--json").stdout)
        self.assertEqual(res["moved"], ["src/a.py"])
        self.assertEqual(res["left"], ["notes.txt"])
        self.assertEqual((self.root / "src" / "a.py").read_text(encoding="utf-8"), "a = 1\n")
        self.assertEqual((Path(res["worktree"]) / "src" / "a.py").read_text(encoding="utf-8"), "a = 9\n")
        self.assertTrue((self.root / "notes.txt").exists())


if __name__ == "__main__":
    unittest.main()
