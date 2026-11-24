"""dev-kit 3.2: the board's Autopilot switch runs /dev-kit:autopilot headless (dev_worker.AutoExecutor).

Decisions behind it (2026-11-24): "on" runs the kit's own /dev-kit:autopilot from the board, one milestone per run
(`--milestones 1 --board`), until a release waits for approval or the project is stable; questions go to Needs you
and the run goes on with independent work, ending with `waiting_for_user` when only such work is left, and the board
starts it again once something the user decides lands in .dev; off lets the run finish its step; permissions follow
autonomy.board_executor (acceptEdits by default); the switch is kept in .dev/run/ across board restarts.
These tests never start the real claude: DEV_KIT_CLAUDE points to a fake.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_autopilot_board.py' -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
WORKER = SCRIPTS / "dev_worker.py"
sys.path.insert(0, str(SCRIPTS))

import dev_worker as dw  # noqa: E402

PLAN = ("# Implementation plan — shop\n\n## R1 — First\n\n## M1 — One\nOne.\n\n"
        "### T-001 A\n- status: todo\n- deps: \n- type: feature\n- acceptance:\n  - AC-1: a\n- test_notes: t\n- files: a.py\n\n"
        "### T-002 B\n- status: todo\n- deps: \n- type: feature\n- acceptance:\n  - AC-2: b\n- test_notes: t\n- files: b.py\n")

# The fake autopilot: records how it was started, optionally runs dev_state commands (progress) and says why it ended,
# as /dev-kit:autopilot --board does with `dev_worker.py autopilot-exit`.
FAKE = """#!/usr/bin/env python3
import json, os, subprocess, sys, time
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
root = os.environ["CLAUDE_PROJECT_DIR"]
with open(os.environ["FAKE_OUT"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "autopilot": os.environ.get("DEV_KIT_AUTOPILOT")}) + "\\n")
for args in json.loads(os.environ.get("FAKE_DS", "[]")):
    subprocess.run([sys.executable, "-I", os.environ["FAKE_STATE"], "--root", root, *args], check=True, capture_output=True)
if os.environ.get("FAKE_EXIT"):
    subprocess.run([sys.executable, "-I", os.environ["FAKE_WORKER"], "--root", root, "autopilot-exit", "--reason", os.environ["FAKE_EXIT"]],
                   check=True, capture_output=True)
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION", "DEV_KIT_CLAUDE")}
        self.ds("init", "--language", "en", "--project", "shop")
        (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")
        self.out = self.root / "fake.jsonl"
        fake = self.root / "fake-claude"
        fake.write_text(FAKE, encoding="utf-8")
        fake.chmod(0o755)
        env = {"DEV_KIT_CLAUDE": str(fake), "FAKE_OUT": str(self.out), "FAKE_RC": "0", "FAKE_SLEEP": "0", "FAKE_EXIT": "",
               "FAKE_DS": "[]", "FAKE_STATE": str(STATE), "FAKE_WORKER": str(WORKER)}
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(dw, "AUTO_GRACE_S", 0)):
            p.start()
            self.addCleanup(p.stop)
        self.other = False
        self.ex = dw.AutoExecutor(self.root, CORE.parents[1], lambda: self.other)
        self.addCleanup(self.ex.stop)

    def ds(self, *args: str) -> str:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env=self.env)
        self.assertEqual(p.returncode, 0, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p.stdout

    def cli(self, *args: str) -> str:
        p = subprocess.run([sys.executable, "-I", str(WORKER), "--root", str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, msg=p.stderr)
        return p.stdout

    def runs(self) -> list[dict]:
        return [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines()] if self.out.exists() else []

    def run_once(self, reason: str = "", ds: list | None = None, rc: int = 0) -> None:
        """One tick that starts a run, the run ends, one tick that reads how it ended."""
        os.environ.update(FAKE_EXIT=reason, FAKE_DS=json.dumps(ds or []), FAKE_RC=str(rc))
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc, "no run started")
        self.assertEqual(self.ex.kind, "autopilot")
        self.ex.proc.wait(30)
        self.ex.tick()

    def status(self) -> dict:
        return dw.autopilot_status(self.root)


class TestTheSwitch(Base):
    def test_off_by_default_and_nothing_starts(self) -> None:
        self.assertEqual((self.status()["on"], self.status()["state"]), (False, "off"))
        self.ex.tick()
        self.assertIsNone(self.ex.proc)

    def test_on_runs_the_kits_own_autopilot_one_milestone_per_run(self) -> None:
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        self.assertEqual(self.status()["state"], "running")
        self.ex.proc.wait(30)
        run = self.runs()[0]
        self.assertEqual(run["argv"][:2], ["-p", "/dev-kit:autopilot --milestones 1 --board"])
        self.assertEqual(run["argv"][run["argv"].index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(run["autopilot"], "board")
        self.assertTrue((self.root / ".dev" / "run" / "autopilot.log").exists())

    def test_a_closed_milestone_starts_the_next_run(self) -> None:
        dw.set_autopilot(self.root, True)
        self.run_once("milestone_done", [["start", "T-001"]])
        self.assertEqual((self.status()["state"], self.status()["reason"]), ("idle", "milestone_done"))
        self.run_once("milestone_done", [["done", "T-001"]])
        self.assertEqual(len(self.runs()), 2)
        self.assertEqual(self.status()["runs"], 2)

    def test_a_run_that_changed_nothing_stops_until_switched_on_again(self) -> None:
        dw.set_autopilot(self.root, True)
        self.run_once("milestone_done")
        self.assertEqual((self.status()["state"], self.status()["reason"]), ("stopped", "no_change"))
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        time.sleep(0.01)
        dw.set_autopilot(self.root, True)  # "Start again"
        self.assertEqual(self.status()["state"], "idle")
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)

    def test_waiting_for_the_user_starts_again_once_they_decide(self) -> None:
        dw.set_autopilot(self.root, True)
        self.run_once("waiting_for_user", [["add-question", "Which database?"]])
        self.assertEqual(self.status()["state"], "waiting_user")
        self.ex.tick()
        self.assertIsNone(self.ex.proc)  # nothing the user decides has landed yet
        time.sleep(0.01)
        self.ds("answer-question", "Q-001", "--answer", "Postgres")
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)

    def test_a_release_waiting_for_approval_and_a_stable_project_wait(self) -> None:
        dw.set_autopilot(self.root, True)
        self.run_once("release_approval")
        self.assertEqual(self.status()["state"], "release")
        dw.set_autopilot(self.root, True)
        self.run_once("stable")
        self.assertEqual(self.status()["state"], "stable")
        self.ex.tick()
        self.assertIsNone(self.ex.proc)

    def test_off_while_running_lets_the_run_finish_its_step(self) -> None:
        os.environ["FAKE_SLEEP"] = "1.5"
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        st = dw.set_autopilot(self.root, False)
        self.assertEqual(st["state"], "stopping")
        self.assertTrue(dw.autopilot_stop_asked(self.root))
        self.assertIn('"state": "stopping"', self.cli("autopilot", "status", "--json"))
        self.ex.proc.wait(30)  # never killed: it ends by itself
        self.ex.tick()
        self.assertEqual((self.status()["state"], self.status()["reason"]), ("off", "switched_off"))
        self.assertFalse((self.root / ".dev" / "run" / "autopilot.stop").exists())

    def test_force_stop_ends_the_run_now(self) -> None:
        os.environ["FAKE_SLEEP"] = "30"
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        pid = self.ex.proc.pid
        st = dw.autopilot_force_stop(self.root)
        self.assertEqual((st["on"], st["state"], st["reason"]), (False, "off", "force_stopped"))
        self.ex.proc.wait(10)
        self.assertFalse(dw._alive(pid))

    def test_requests_go_first(self) -> None:
        dw.set_autopilot(self.root, True)
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertEqual(self.ex.kind, "worker")
        self.assertEqual(self.runs()[0]["argv"][1] if self.ex.proc.wait(30) == 0 else None, "/dev-kit:worker")

    def test_another_session_running_autopilot_is_never_doubled(self) -> None:
        self.other = True
        dw.set_autopilot(self.root, True)
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.assertEqual((self.status()["state"], self.status()["reason"]), ("waiting_session", "other_session"))

    def test_failed_runs_back_off_then_stop(self) -> None:
        dw.set_autopilot(self.root, True)
        for n in range(1, 4):
            self.run_once(rc=1)
            self.assertEqual(self.status()["state"], "backoff" if n < 3 else "stopped")
            self.assertEqual(self.status()["reason"], "failed")
            if n < 3:
                self.ex.tick()
                self.assertIsNone(self.ex.proc)  # not before the back-off
                rec = json.loads((self.root / ".dev" / "run" / "autopilot-run.json").read_text())
                rec["until"] = 0
                (self.root / ".dev" / "run" / "autopilot-run.json").write_text(json.dumps(rec))
        self.assertIn("3 runs in a row failed", self.status()["note"])

    def test_a_run_that_says_nothing_counts_as_failed(self) -> None:
        dw.set_autopilot(self.root, True)
        self.run_once("")
        self.assertEqual((self.status()["state"], self.status()["note"]), ("backoff", "ended without saying why"))

    def test_a_run_left_by_an_earlier_board_is_adopted(self) -> None:
        os.environ["FAKE_SLEEP"] = "1"
        dw.set_autopilot(self.root, True)
        self.run_once("milestone_done", [["start", "T-001"]])  # so the next run has a state to compare with
        os.environ.update(FAKE_EXIT="milestone_done", FAKE_DS=json.dumps([["done", "T-001"]]))
        self.ex.tick()
        proc = self.ex.proc
        fresh = dw.AutoExecutor(self.root, CORE.parents[1])  # the board restarted: a new server process
        fresh.tick()
        self.assertIsNone(fresh.proc)  # the old run still goes: no second one
        proc.wait(30)
        fresh.tick()
        self.assertEqual((self.status()["state"], self.status()["reason"]), ("idle", "milestone_done"))
        self.ex.proc = None


class TestKeptAndShown(Base):
    def test_the_switch_survives_a_restart_and_continuous_mode_carries_over(self) -> None:
        dw.set_mode(self.root, paused=False)
        (self.root / ".dev" / "run" / "worker-mode.json").write_text(json.dumps({"paused": False, "continuous": True}))
        self.assertTrue(dw.autopilot_on(self.root))  # "Go on by itself" was on before 3.2
        dw.set_autopilot(self.root, False)
        self.assertFalse(dw.autopilot_on(self.root))
        self.assertIn("autopilot on", self.cli("autopilot", "on"))
        self.assertTrue(json.loads((self.root / ".dev" / "run" / "autopilot.json").read_text())["on"])
        self.assertEqual(dw.snapshot(self.root)["autopilot"]["state"], "idle")
        self.assertNotIn("continuous", dw.executor(self.root))

    def test_exit_reasons_are_checked(self) -> None:
        with self.assertRaises(dw.Invalid):
            dw.autopilot_exit(self.root, "whatever")
        with self.assertRaises(dw.Invalid):
            dw.set_autopilot(self.root, "yes")
        self.assertIn("autopilot run ended: stable", self.cli("autopilot-exit", "--reason", "stable", "--note", "R1 released"))

    def test_permissions_of_the_autopilot_run_go_to_the_board(self) -> None:
        dw._write(self.root / ".dev" / "run" / dw.AP_RUN, {"state": "running", "pid": os.getppid()})
        self.assertEqual(dw.board_run(self.root)["id"], "autopilot")
        dw._write(self.root / ".dev" / "run" / dw.AP_RUN, {"state": "running", "pid": 1})
        self.assertIsNone(dw.board_run(self.root))

    def test_the_board_knows_a_manual_autopilot_from_its_own(self) -> None:
        import dev_board
        self.ds("event", "skill_start", "--set", "skill=autopilot", "--set", "args_kind=board")
        self.assertFalse(dev_board.manual_autopilot(self.root))
        self.ds("event", "skill_start", "--set", "skill=autopilot")
        self.assertTrue(dev_board.manual_autopilot(self.root))

    def test_the_board_skill_closes_its_own_run(self) -> None:
        text = (CORE.parent / "board" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("skill_end --set skill=board", text)
        self.assertIn("--board", (CORE.parent / "autopilot" / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
