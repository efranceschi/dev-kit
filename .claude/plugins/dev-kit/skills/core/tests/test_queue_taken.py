"""dev-kit 3.6.3: a request on the board is always taken. The field case: a session ran /dev-kit:worker once, went
idle and stayed open without listening. Its heartbeat (idle, its pid alive) made it count as the executor, so the
board never started its own worker and a headless one would have been refused; the Stop hook kept saying
"run /dev-kit:worker" while the board promised the request would start by itself.

An idle executor that does not listen now holds the queue only for a moment after a request (its loop claims the
next), the hooks stay quiet when the board's worker takes the request (and say why when nobody will), and
dev_debug.py reports a request nobody takes.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p test_queue_taken.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v3_board import FAKE_CLAUDE, Base  # noqa: E402
from test_worktree_isolation import STATE  # noqa: E402

SCRIPTS = STATE.parent
sys.path.insert(0, str(SCRIPTS))
import dev_worker as dw  # noqa: E402


def ago(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))


class QueueBase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.out = self.root / "fake-claude.jsonl"
        fake = self.root / "fake-claude"
        fake.write_text(FAKE_CLAUDE, encoding="utf-8")
        fake.chmod(0o755)
        env = {"DEV_KIT_CLAUDE": str(fake), "FAKE_OUT": str(self.out), "FAKE_RC": "0", "FAKE_SLEEP": "0"}
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(dw, "AUTO_GRACE_S", 0)):
            p.start()
            self.addCleanup(p.stop)
        self.ex = dw.AutoExecutor(self.root, Path(SCRIPTS).parents[2])
        self.addCleanup(self.ex.stop)
        self.run_dir = self.root / ".dev" / "run"

    def idle_session(self, idle_s: float) -> None:
        """A live session (this test's pid) that ran /dev-kit:worker and went idle `idle_s` seconds ago."""
        dw.heartbeat(self.root, "claude-1", os.getpid(), "idle")
        w = json.loads((self.run_dir / "worker.json").read_text(encoding="utf-8"))
        w["idle_since"] = w["last_seen"] = ago(idle_s)
        (self.run_dir / "worker.json").write_text(json.dumps(w), encoding="utf-8")

    def board_up(self) -> None:
        (self.run_dir / "board.json").write_text(json.dumps({"pid": os.getpid(), "port": 1, "actions": True}), encoding="utf-8")

    def hook(self, event: str = "Stop") -> dict:
        payload = {"hook_event_name": event, "session_id": "s1", "cwd": str(self.root), "source": "startup"}
        out = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_agent_hook.py")], input=json.dumps(payload), text=True,
                             check=True, capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}).stdout
        return json.loads(out) if out.strip() else {}


class TestIdleSessionDoesNotHoldTheQueue(QueueBase):
    def test_field_case_the_board_starts_its_worker_past_an_idle_session(self) -> None:
        self.idle_session(300)
        rid = dw.submit(self.root, "task_decision", {"task": "T-001", "decision": "run"})["id"]
        self.assertTrue(dw.executor(self.root)["online"])  # the board still shows the session
        self.assertFalse(dw.executor(self.root)["holds"])
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)
        self.assertEqual(dw.auto_status(self.root)["request"], rid)
        x, why = dw.claim(self.root, "claude-2", os.getpid())  # what the headless worker does: not refused
        self.assertEqual((x["id"], why), (rid, ""))

    def test_an_executor_between_two_requests_keeps_the_queue(self) -> None:
        self.idle_session(5)
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.assertEqual(dw.claim(self.root, "claude-2")[0], None)

    def test_a_working_executor_keeps_the_queue_however_long(self) -> None:
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        dw.submit(self.root, "run", {"command": "/dev-kit:costs"})
        dw.claim(self.root, "claude-1", os.getpid())
        w = json.loads((self.run_dir / "worker.json").read_text(encoding="utf-8"))
        w["last_seen"] = ago(3600)
        (self.run_dir / "worker.json").write_text(json.dumps(w), encoding="utf-8")
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.assertEqual(dw.claim(self.root, "claude-2")[0], None)


class TestHooksSayWhoTakesIt(QueueBase):
    def test_quiet_when_the_board_takes_it(self) -> None:
        self.board_up()
        self.idle_session(300)
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.assertEqual(dw.who_takes(self.root), ("board", None))
        self.assertEqual(self.hook(), {})

    def test_says_why_when_nobody_takes_it(self) -> None:
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.assertIn("the board is not running · run /dev-kit:worker", self.hook("SessionStart")["systemMessage"])
        self.board_up()
        (self.run_dir / dw.AUTO_FILE).write_text(json.dumps({"state": "waiting", "reason": "exit 1", "until": time.time() + 300}),
                                                encoding="utf-8")
        taker, why = dw.who_takes(self.root)
        self.assertIsNone(taker)
        self.assertIn("failed (exit 1) and retries at", why)
        self.assertIn("worker-auto.log", self.hook("SessionStart")["systemMessage"])


class TestRequestsWaitForTheAutopilotRun(QueueBase):
    """Field case 2: P-009 and P-010 waited while an Autopilot run was open, and the prompt hook said to run
    /dev-kit:worker, which would have made two Claude Code sessions change the project at once."""

    def setUp(self) -> None:
        super().setUp()
        self.board_up()
        (self.run_dir / dw.AP_RUN).write_text(json.dumps({"state": "running", "pid": os.getpid()}), encoding="utf-8")
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})

    def test_the_hook_says_they_wait_and_never_to_run_the_worker(self) -> None:
        self.assertEqual(dw.who_takes(self.root)[0], "autopilot")
        out = self.hook("UserPromptSubmit")
        self.assertIn("run when the Autopilot run ends", out["systemMessage"])
        self.assertNotIn("run /dev-kit:worker", out["systemMessage"])

    def test_a_manual_worker_is_refused_while_it_runs(self) -> None:
        x, why = dw.claim(self.root, "claude-9", os.getpid())
        self.assertIsNone(x)
        self.assertIn("Autopilot run", why)
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_worker.py"), "--root", str(self.root), "claim", "--session", "s"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 4)

    def test_debug_says_it_waits(self) -> None:
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_debug.py"), "--root", str(self.root), "check", "--json"],
                           capture_output=True, text=True)
        self.assertIn("queue_waits_for_autopilot", {c["code"] for c in json.loads(p.stdout)})


class TestDebugFindsAStuckQueue(QueueBase):
    def checks(self) -> list[dict]:
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_debug.py"), "--root", str(self.root), "check", "--json"],
                           capture_output=True, text=True)
        return json.loads(p.stdout)

    def old_request(self) -> str:
        rid = dw.submit(self.root, "run", {"command": "/dev-kit:docs"})["id"]
        f = self.run_dir / "inbox" / f"{rid}.json"
        rec = json.loads(f.read_text(encoding="utf-8"))
        rec["ts"] = ago(600)
        f.write_text(json.dumps(rec), encoding="utf-8")
        return rid

    def test_queue_stuck_without_a_board(self) -> None:
        rid = self.old_request()
        found = {c["code"]: c for c in self.checks()}
        self.assertEqual(found["queue_stuck"]["level"], "error")
        self.assertIn(rid, found["queue_stuck"]["text"])
        self.assertIn("the board is not running", found["queue_stuck"]["text"])

    def test_queue_not_taken_by_a_running_board(self) -> None:
        self.board_up()
        self.old_request()
        self.assertIn("queue_not_taken", {c["code"] for c in self.checks()})

    def test_the_dump_lists_the_queue_by_code(self) -> None:
        rid = dw.submit(self.root, "issue_new", {"title": "Secret product name"})["id"]
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_debug.py"), "--root", str(self.root), "dump", "--json"],
                           capture_output=True, text=True, check=True)
        text = Path(json.loads(p.stdout)["path"]).read_text(encoding="utf-8")
        self.assertIn("## Board queue", text)
        self.assertIn(f"{rid} issue_new pending", text)
        self.assertNotIn("Secret product name", text)


if __name__ == "__main__":
    unittest.main()
