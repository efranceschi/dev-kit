"""dev-kit 3.6: work on a task is always started. The field case: a round adopted an earlier attempt's worktree
(.claude/worktrees/T-023, made outside the kit) and ran the task with the state still saying todo, so the board
showed nothing running. Commands that bring a task's work into play now record the start, `start --resume` takes
over an earlier attempt, the round's reconcile catches what was done without a start, the fence denies applying a
worktree by hand in a round, the board sees the round, and dev_debug.py finds what is out of step.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p test_adopt_start.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_worktree_isolation import STATE, Base  # noqa: E402

DEBUG = STATE.parent / "dev_debug.py"


class Started(Base):
    def status(self, tid: str) -> str:
        return self.state()["tasks"][tid]["status"]

    def foreign(self, tid: str = "T-001", content: str = "a = 5\n") -> Path:
        """An earlier attempt made by Claude Code's own isolation: .claude/worktrees/T-nnn on dev-kit/T-nnn."""
        wt = self.root / ".claude" / "worktrees" / tid
        self.git("worktree", "add", "-q", "-b", f"dev-kit/{tid}", str(wt), "new_version")
        (wt / "src" / "a.py").write_text(content, encoding="utf-8")
        return wt


class TestCommandsStartTheTask(Started):
    def test_slot_open_starts_a_todo_task_and_refuses_a_blocked_one(self) -> None:
        out = self.ds("slot", "open", "1", "--task", "T-001", "--worktree").stdout
        self.assertIn("started by slot open", out)
        self.assertEqual(self.status("T-001"), "in_progress")
        self.ds("block", "T-002", "--reason", "needs decision: Q-1")
        p = self.ds("slot", "open", "2", "--task", "T-002", expect=1)
        self.assertIn("unblock it first", p.stderr)

    def test_adopt_starts_the_task(self) -> None:
        (self.root / "src" / "a.py").write_text("a = 9\n", encoding="utf-8")
        self.ds("reconcile", "--adopt", "T-001")
        self.assertEqual(self.status("T-001"), "in_progress")

    def test_done_on_a_todo_task_says_start_first(self) -> None:
        p = self.ds("done", "T-001", expect=1)
        self.assertIn("run `start T-001` first", p.stderr)


class TestResume(Started):
    def test_field_case_inline_task_resumes_a_foreign_worktree(self) -> None:
        wt = self.foreign()
        t0 = "2026-11-24T03:18:22+00:00"
        self.ds("start", "T-001")
        self.ds("block", "T-001", "--reason", "needs decision: Q-004")
        self.ds("unblock", "T-001")
        st = json.loads((self.dev / "state.json").read_text(encoding="utf-8"))
        st["tasks"]["T-001"]["started_at"] = t0
        (self.dev / "state.json").write_text(json.dumps(st), encoding="utf-8")
        with mock.patch.dict(os.environ, {}):
            out = self.ds("start", "T-001", "--resume").stdout
        self.assertIn("applied", out)
        t = self.state()["tasks"]["T-001"]
        self.assertEqual((t["status"], t["started_at"]), ("in_progress", t0))  # the first start is kept
        self.assertEqual(t["resumed_from"]["worktree"], str(wt))
        self.assertEqual((self.root / "src" / "a.py").read_text(encoding="utf-8"), "a = 5\n")
        self.assertIn("M  src/a.py", self.git("status", "--porcelain"))
        self.assertIn("already applied", self.ds("start", "T-001", "--resume").stdout)
        self.git("commit", "-qm", "[T-001] feat: a")
        self.ds("done", "T-001", "--commit", self.git("rev-parse", "HEAD"))
        self.assertFalse(wt.exists())
        self.assertNotIn("dev-kit/T-001", self.git("branch"))

    def test_resume_refuses_files_outside_the_task(self) -> None:
        wt = self.foreign()
        (wt / "src" / "zz.py").write_text("x\n", encoding="utf-8")
        p = self.ds("start", "T-001", "--resume", expect=1)
        self.assertIn("outside the task", p.stderr)

    def test_slot_open_reuses_a_foreign_worktree(self) -> None:
        wt = self.foreign()
        out = self.ds("slot", "open", "1", "--task", "T-001", "--worktree").stdout
        self.assertIn("made outside the kit, reused", out)
        self.assertEqual(self.slot(1)["worktree"], str(wt))

    def test_no_earlier_attempt(self) -> None:
        self.assertIn("no earlier attempt", self.ds("start", "T-001", "--resume").stdout)
        self.assertEqual(self.status("T-001"), "in_progress")


FAKE_UNSTARTED = """#!/bin/sh
# an implement round that works on T-001 and commits it, and leaves T-002's file changed, without starting either
cd "$CLAUDE_PROJECT_DIR"
echo "a = 7" > src/a.py
git add src/a.py
git commit -qm "[T-001] feat: a"
echo "b = 1" > src/b.py
exit 0
"""


class TestReconcileUnstarted(Started):
    def test_round_reconcile_records_done_and_keeps_unstarted_work(self) -> None:
        exe = self.dev / "tmp" / "fake-claude"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(FAKE_UNSTARTED, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        out = json.loads(self.ds("round", "run", "implement", "M1", expect=None, env={"DEV_KIT_CLAUDE": str(exe)}).stdout)
        self.assertEqual(out["reconciled"]["tasks_done"], ["T-001"])
        self.assertEqual(out["reconciled"]["tasks_blocked"], ["T-002"])
        t = self.state()["tasks"]
        self.assertEqual((t["T-001"]["status"], t["T-001"]["commit"]), ("done", self.git("rev-parse", "HEAD")))
        self.assertEqual(t["T-002"]["status"], "blocked")
        self.assertFalse((self.root / "src" / "b.py").exists())  # moved out of the main checkout
        self.assertEqual((self.dev / "run" / "worktrees" / "T-002" / "src" / "b.py").read_text(encoding="utf-8"), "b = 1\n")


class TestRoundFenceAndBoard(Started):
    def decide(self, cmd: str, rnd: str = "implement-M1-x", agent_id: str = "") -> dict | None:
        import dev_fence
        with mock.patch.dict(os.environ, {"DEV_KIT_ROUND_ID": rnd} if rnd else {}, clear=False):
            if not rnd:
                os.environ.pop("DEV_KIT_ROUND_ID", None)
            return dev_fence.decide({"hook_event_name": "PreToolUse", "agent_id": agent_id, "tool_name": "Bash",
                                     "tool_input": {"command": cmd, "description": "apply it"}, "cwd": str(self.root)}, self.root)

    def test_manual_apply_is_denied_in_a_round_only(self) -> None:
        for cmd in ("git -C .claude/worktrees/T-001 diff | git apply --index", "git checkout dev-kit/T-001 -- src/a.py",
                    "cp .claude/worktrees/T-001/src/a.py src/a.py", "git cherry-pick dev-kit/T-001"):
            d = self.decide(cmd)
            self.assertEqual(d["hookSpecificOutput"]["permissionDecision"], "deny", cmd)
            self.assertIn("start T-nnn --resume", d["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.decide("git status"))
        self.assertIsNone(self.decide("git apply x.patch", rnd=""))  # the user's own session: untouched
        act = json.loads((self.dev / "run" / "round-activity.json").read_text(encoding="utf-8"))
        self.assertEqual((act["round"], act["what"]), ("implement-M1-x", "apply it"))

    def test_headless_tools_no_longer_allow_git_apply(self) -> None:
        import dev_state
        store = dev_state.Store(self.root)
        store.load()
        self.assertFalse(any("git apply" in x for x in dev_state.headless_allowed_tools(store)))

    def test_board_shows_the_round_its_tasks_and_a_warning(self) -> None:
        import dev_worker as dw
        run = self.dev / "run"
        run.mkdir(parents=True, exist_ok=True)
        (run / "round.json").write_text(json.dumps({"pid": os.getpid(), "child": os.getpid(), "skill": "implement", "scope": "M1",
                                                    "round": "implement-M1-x", "started": "2026-11-24T09:30:26+00:00"}), encoding="utf-8")
        (run / "round-activity.json").write_text(json.dumps({"round": "implement-M1-x", "at": "2026-11-24T09:44:00Z", "tool": "Bash",
                                                             "what": "e2e", "agent": None}), encoding="utf-8")
        rd = dw.autopilot_status(self.root)["round"]
        self.assertTrue(rd["unregistered"])
        self.assertEqual((rd["skill"], rd["scope"], rd["last"]["what"]), ("implement", "M1", "e2e"))
        self.ds("start", "T-001")
        rd = dw.autopilot_status(self.root)["round"]
        self.assertEqual([t["id"] for t in rd["tasks"]], ["T-001"])
        self.assertFalse(rd["unregistered"])
        (run / "round.json").unlink()
        self.assertIsNone(dw.autopilot_status(self.root)["round"])


class TestDebug(Started):
    def dd(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(DEBUG), "--root", str(self.root), *args], capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(p.returncode, expect, msg=p.stdout + p.stderr)
        return p

    def test_checks_find_the_field_case(self) -> None:
        self.foreign()
        (self.root / "src" / "a.py").write_text("a = 5\n", encoding="utf-8")
        self.git("add", "src/a.py")
        run = self.dev / "run"
        run.mkdir(parents=True, exist_ok=True)
        (run / "round.json").write_text(json.dumps({"pid": os.getpid(), "child": os.getpid(), "skill": "implement", "scope": "M1",
                                                    "round": "r1", "started": "2026-11-24T09:30:26+00:00"}), encoding="utf-8")
        found = json.loads(self.dd("check", "--json", expect=1).stdout)
        codes = {x["code"] for x in found}
        self.assertTrue({"round_without_task", "foreign_task_worktree", "dirty_files_of_unstarted_task"} <= codes, codes)

    def test_dump_is_written_under_run_and_names_no_home(self) -> None:
        out = json.loads(self.dd("dump", "--json").stdout)
        p = Path(out["path"])
        self.assertTrue(str(p).startswith(str(self.dev / "run" / "debug")))
        text = p.read_text(encoding="utf-8")
        for title in ("## Checks", "## git", "## Tasks not done", "## Run files", "## .dev/log.md"):
            self.assertIn(title, text)
        self.assertNotIn(str(Path.home()) + "/", text.replace(str(self.root), ""))

    def secrets_fixture(self) -> None:
        wt = self.foreign()
        (self.root / "src" / "a.py").write_text("a = 5\n", encoding="utf-8")
        st = json.loads((self.dev / "state.json").read_text(encoding="utf-8"))
        st["tasks"]["T-001"]["title"] = "Databricks credential rows"
        (self.dev / "state.json").write_text(json.dumps(st), encoding="utf-8")
        gh, db = "ghp" + "_" + "abcdefghijklmnopqrstuvwxyz0123", "da" + "pi" + "0123456789abcdef" * 2  # built here: no secret-shaped literal in the repo
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write("- 2026-11-24T05:38:08+00:00 add-question Q-003 (autopilot): Databricks credential rows in "
                    f"{wt} token=abc123secretvalue {gh} {db} by a@b.com\n")
        run = self.dev / "run"
        run.mkdir(parents=True, exist_ok=True)
        (run / "board.json").write_text(json.dumps({"pid": 1, "token": "board-secret-token-value", "url": "http://127.0.0.1:8765/"}), encoding="utf-8")
        (run / "round-activity.json").write_text(json.dumps({"round": "r1", "tool": "Bash", "what": "curl -H 'Authorization: Bearer abcdefghijklmnop1234' https://x"}),
                                                 encoding="utf-8")

    def test_every_dump_redacts_secrets(self) -> None:
        self.secrets_fixture()
        text = Path(json.loads(self.dd("dump", "--json").stdout)["path"]).read_text(encoding="utf-8")
        for secret in ("abc123secretvalue", "ghp_abcdef", "dapi0123", "a@b.com", "board-secret-token-value", "abcdefghijklmnop1234"):
            self.assertNotIn(secret, text, secret)
        self.assertNotIn("Databricks credential rows", text)  # names never go in, only codes
        self.assertIn("T-001", text)
        self.assertIn("Q-003", text)
        self.assertIn("src/a.py", text)  # the local dump keeps paths

    def test_share_dump_is_anonymised(self) -> None:
        self.secrets_fixture()
        out = json.loads(self.dd("dump", "--share", "--json").stdout)
        p = Path(out["path"])
        self.assertTrue(out["share"] and p.name.startswith("dump-share-"))
        text = p.read_text(encoding="utf-8")
        for leak in ("abc123secretvalue", "ghp_abcdef", "dapi0123", "a@b.com", "board-secret-token-value", "Databricks", "src/a.py",
                     str(self.root), "new_version", "work on new_version", "curl"):
            self.assertNotIn(leak, text, leak)
        self.assertIn("T-001", text)
        self.assertIn("Q-003", text)
        self.assertRegex(text, r"p:[0-9a-f]{6}\.py")
        self.assertIn("<branch-", text)
        self.assertIn("foreign_task_worktree", text)

    def test_share_refuses_to_write_a_leak(self) -> None:
        import dev_debug
        self.secrets_fixture()
        with mock.patch.object(dev_debug.Sharer, "text", lambda self, t: t):  # a broken anonymiser
            with self.assertRaises(dev_debug.LeakError) as e:
                dev_debug.dump(self.root, 40, share=True)
        self.assertTrue(any("project folder" in x or "project name" in x for x in e.exception.leaks))

    def test_question_text_and_milestone_name_never_go_in(self) -> None:
        (self.dev / "open-questions.md").write_text("| id | date | skill | question | answer | note |\n|---|---|---|---|---|---|\n"
                                                    "| Q-007 | 2026-11-24 | implement | Should the vault keep old keys? | - | - |\n", encoding="utf-8")
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write("- 2026-11-24T05:38:08+00:00 add-question Q-007 (implement): Should the vault keep old keys?\n")
        for args in (("dump",), ("dump", "--share")):
            text = Path(json.loads(self.dd(*args, "--json").stdout)["path"]).read_text(encoding="utf-8")
            self.assertNotIn("vault", text, args)
            self.assertIn("Q-007", text, args)

    def test_committed_but_not_done(self) -> None:
        (self.root / "src" / "a.py").write_text("a = 3\n", encoding="utf-8")
        self.git("commit", "-qam", "[T-001] feat: a")
        codes = {x["code"] for x in json.loads(self.dd("check", "--json", expect=1).stdout)}
        self.assertIn("committed_not_done", codes)


if __name__ == "__main__":
    unittest.main()
