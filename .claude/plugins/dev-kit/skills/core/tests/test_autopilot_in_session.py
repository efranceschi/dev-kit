"""dev-kit 3.7.0: the board's Autopilot runs in the session that listens to the board, so the implementers and
auditors it spawns are that session's own subagents and show in its task list (Eduardo's choice, option A,
2026-11-24). With no session listening, the run stays headless as before. Rounds go to child sessions only in a
headless run (or with --rounds child).

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p test_autopilot_in_session.py -v
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
from test_v3_autopilot_board import WORKER, Base  # noqa: E402

import dev_worker as dw  # noqa: E402


class SessionBase(Base):
    def listen(self, pid: int | None = None) -> int:
        """A session (pid) armed on the board whose monitor is alive: what /dev-kit:board leaves."""
        pid = pid or os.getpid()
        run = self.root / ".dev" / "run"
        run.mkdir(parents=True, exist_ok=True)
        (run / "worker-armed.json").write_text(json.dumps({"pid": pid, "session": f"claude-{pid}"}), encoding="utf-8")
        (run / "worker-watch.json").write_text(json.dumps({"pid": pid, "watch_pid": os.getpid(), "last_seen": dw.now()}),
                                               encoding="utf-8")
        self.assertTrue(dw.listening(self.root))
        return pid

    def handed(self) -> dict:
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        self.assertIsNone(self.ex.proc, "nothing headless while a session listens")
        return self.status()


class TestHandoff(SessionBase):
    def test_on_with_a_listening_session_hands_the_run_to_it(self) -> None:
        pid = self.listen()
        st = self.handed()
        self.assertEqual((st["state"], st["where"], st["handoff"], st["pid"]), ("running", "session", "pending", pid))
        self.assertEqual(st["command"], dw.AP_SESSION_COMMAND)
        self.assertEqual(self.runs(), [])

    def test_the_session_takes_it_and_its_exit_ends_the_run(self) -> None:
        pid = self.listen()
        self.handed()
        with self.assertRaises(dw.Invalid):
            dw.autopilot_take(self.root, pid + 1)  # another session: never a second driver
        self.assertTrue(dw.autopilot_take(self.root, pid)["taken"])
        self.assertEqual(self.status()["handoff"], "taken")
        self.ex.tick()
        self.assertEqual(self.status()["state"], "running")
        self.cli("autopilot-exit", "--reason", "waiting_for_user")
        self.ex.tick()
        self.assertEqual(self.status()["state"], "waiting_user")

    def test_a_handoff_nobody_takes_falls_back_to_headless(self) -> None:
        self.listen()
        self.handed()
        run = self.root / ".dev" / "run" / dw.AP_RUN
        st = json.loads(run.read_text(encoding="utf-8"))
        st["at_s"] -= dw.HANDOFF_WAIT_S + 5
        run.write_text(json.dumps(st), encoding="utf-8")
        self.ex.tick()
        self.assertEqual(self.status()["reason"], "session_did_not_take")
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)  # headless now
        self.ex.proc.wait(30)
        self.assertEqual(self.runs()[0]["argv"][:2], ["-p", dw.AP_COMMAND])

    def test_without_a_listening_session_or_with_the_setting_off_it_stays_headless(self) -> None:
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)
        self.ex.stop()
        self.ex = dw.AutoExecutor(self.root, Path(WORKER).parents[3])
        self.addCleanup(self.ex.stop)
        (self.root / ".dev" / "run" / dw.AP_RUN).unlink()
        self.listen()
        self.ds("set", "autonomy.board_executor", json.dumps({"auto": True, "autopilot_in_session": False}))
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)

    def test_force_stop_never_ends_the_users_session(self) -> None:
        self.listen()
        self.handed()
        with mock.patch.object(dw.os, "killpg") as kill:
            st = dw.autopilot_force_stop(self.root)
        kill.assert_not_called()
        self.assertEqual(st["state"], "off")

    def test_the_session_running_it_may_claim_requests_others_may_not(self) -> None:
        pid = self.listen()
        self.handed()
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.assertIsNone(dw.claim(self.root, "claude-x", pid + 1)[0])
        self.assertIsNotNone(dw.claim(self.root, f"claude-{pid}", pid)[0])


class TestPaneData(SessionBase):
    def test_pane_shows_the_run_in_this_session_and_what_waits(self) -> None:
        self.listen()
        self.handed()
        dw.submit(self.root, "issue_new", {"title": "Secret product name"})
        out = subprocess.run([sys.executable, "-I", str(Path(WORKER).parent / "dev_board.py"), "--root", str(self.root), "pane", "--json"],
                             capture_output=True, text=True, check=True).stdout
        self.assertNotIn("Secret product name", out)  # ids and actions only
        d = json.loads(out)
        self.assertEqual((d["autopilot"]["state"], d["autopilot"]["where"], d["autopilot"]["handoff"]), ("running", "session", "pending"))
        self.assertEqual([(r["id"], r["action"], r["status"]) for r in d["requests"]], [("P-001", "issue_new", "pending")])
        self.assertEqual((d["agents"], d["approvals"], d["board"]), ([], [], {"running": False}))
        self.assertTrue(d["executor"]["listening"])


class TestMonitorAndRounds(SessionBase):
    def test_the_monitor_announces_the_handoff_to_its_session(self) -> None:
        self.listen(os.getppid())  # watch() announces only to the session it runs under
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        lines: list[str] = []
        dw.watch(self.root, once=True, emit=lines.append, grace=0)
        self.assertEqual(len(lines), 1)
        self.assertIn("the Autopilot run is handed to this session", lines[0])
        self.assertIn("--milestones 1 --board --rounds session", lines[0])

    def test_rounds_go_to_children_only_in_a_headless_run(self) -> None:
        with mock.patch.dict(os.environ, {"DEV_KIT_BOARD_CHILD": "", "DEV_KIT_ROUND_CHILD": ""}):
            self.assertEqual(dw.rounds_mode()["rounds"], "session")
            self.assertEqual(dw.rounds_mode("child")["rounds"], "child")
        with mock.patch.dict(os.environ, {"DEV_KIT_BOARD_CHILD": "1"}):
            self.assertEqual(dw.rounds_mode()["rounds"], "child")
            self.assertFalse(dw.autopilot_take(self.root, 1)["taken"])  # a headless board run is the run itself
        out = subprocess.run([sys.executable, "-I", str(WORKER), "--root", str(self.root), "autopilot", "where", "--rounds", "child", "--json"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out)["rounds"], "child")

    def test_the_autopilot_skill_is_started_by_the_user_or_the_board(self) -> None:
        skill = (Path(WORKER).parents[2] / "autopilot" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("disable-model-invocation", skill)
        self.assertIn("Never start it on your own initiative", skill)
        self.assertIn("DW autopilot take --pid $PPID", skill)


if __name__ == "__main__":
    unittest.main()
