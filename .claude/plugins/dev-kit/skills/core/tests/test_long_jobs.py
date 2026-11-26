"""dev-kit 3.19: a long command's end is read from its exit code, never from a process listing.

Field report (T-110): during the autopilot, the check "is the full pipeline still running?" matched its own command
line (`ps | grep`), so it said "running" for 12 hours while the suite had finished green at 00:28. Now long commands
run as kit jobs (`dev_state.py job`): a supervisor records the exit code (the sentinel), stops the process group at
its time limit, a lost or silent job is a Needs-you item, `job wait` is bounded, and the fence denies `pgrep -f` and
`ps | grep` to everyone.
Run: python3 -I -m unittest .claude/plugins/dev-kit/skills/core/tests/test_long_jobs.py -v
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
sys.path.insert(0, str(SCRIPTS))

import dev_debug  # noqa: E402
import dev_fence  # noqa: E402
import dev_spog  # noqa: E402


def live_in_group(pgid: int) -> list[int]:
    """Processes of a group that still run (a zombie left to an init that does not reap is not running)."""
    out = []
    for d in Path("/proc").iterdir() if Path("/proc").is_dir() else []:
        if not d.name.isdigit():
            continue
        try:
            f = (d / "stat").read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if int(f[2]) == pgid and f[0] not in ("Z", "X"):
            out.append(int(d.name))
    return out


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DEV_KIT_")}
        subprocess.run(["git", "-C", str(self.root), "init", "-q", "-b", "main"], check=True)
        self.ds("init", "--language", "en", "--project", "shop")

    def tearDown(self) -> None:
        for p in (self.dev / "run" / "jobs").glob("*.json") if (self.dev / "run" / "jobs").is_dir() else []:
            rec = json.loads(p.read_text(encoding="utf-8"))
            for k in ("pid", "supervisor"):
                if rec.get(k):
                    try:
                        os.killpg(int(rec[k]), signal.SIGKILL)
                    except OSError:
                        pass
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0, env: dict | None = None) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args], capture_output=True, text=True,
                           env={**self.env, **(env or {})}, timeout=120)
        if expect is not None:
            self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return p

    def job(self, name: str) -> dict:
        return json.loads(self.ds("job", "status", name, "--json").stdout)

    def needs(self) -> list[dict]:
        return [n for n in json.loads(self.ds("status", "--json").stdout).get("needs", []) if n.get("kind") == "long_job"]


class TestJobEnd(Base):
    def test_green_run_ends_passed_with_its_exit_code(self) -> None:
        self.ds("job", "start", "full-suite", "--cmd", "echo 12 passed; sleep 1")
        first = self.ds("job", "wait", "full-suite", "--max", "0", expect=None)
        self.assertIn(first.returncode, (0, 3))  # bounded: returns at once when it is still running
        done = self.ds("job", "wait", "full-suite", "--json")
        rec = json.loads(done.stdout)
        self.assertEqual((rec["state"], rec["exit_code"]), ("passed", 0))
        self.assertIn("12 passed", self.ds("job", "log", "full-suite").stdout)
        self.assertEqual(self.needs(), [])

    def test_the_command_line_of_the_check_never_keeps_it_running(self) -> None:
        # the T-110 case: the command line holds the job's own words; the state comes from the job file only
        self.ds("job", "start", "t-110", "--cmd", "true # full pipeline T-110")
        self.ds("job", "wait", "t-110")
        self.assertEqual(self.job("t-110")["state"], "passed")

    def test_red_run_ends_failed_and_shows_the_end_of_the_log(self) -> None:
        self.ds("job", "start", "suite", "--cmd", "echo FAILED test_x; exit 2")
        p = self.ds("job", "wait", "suite", expect=1)
        self.assertIn("FAILED test_x", p.stdout)
        self.assertEqual(self.job("suite")["exit_code"], 2)

    def test_time_limit_stops_the_process_group_and_opens_a_need(self) -> None:
        self.ds("job", "start", "slow", "--cmd", "sleep 300 & sleep 300; wait", env={"DEV_KIT_JOB_TIMEOUT_S": "1"})
        self.ds("job", "wait", "slow", expect=4)
        rec = self.job("slow")
        self.assertEqual((rec["state"], rec["exit_code"]), ("timed_out", 124))
        time.sleep(0.3)
        self.assertEqual(live_in_group(int(rec["pid"])), [])  # the whole group is gone, the background child included
        need = self.needs()
        self.assertEqual([(n["job"], n["why"]) for n in need], [("slow", "timed_out")])
        self.ds("job", "ack", "slow")
        self.assertEqual(self.needs(), [])

    def test_a_dead_supervisor_is_lost_not_running(self) -> None:
        self.ds("job", "start", "build", "--cmd", "sleep 300")
        rec = self.job("build")
        self.assertEqual(rec["state"], "running")
        os.kill(int(rec["supervisor"]), signal.SIGKILL)
        os.killpg(int(rec["pid"]), signal.SIGKILL)
        time.sleep(0.3)
        self.assertEqual(self.ds("job", "wait", "build", "--max", "5", expect=4).returncode, 4)
        self.assertEqual(self.job("build")["state"], "lost")
        self.assertEqual([n["why"] for n in self.needs()], ["lost"])
        codes = {c["code"] for c in dev_debug.checks(self.root)}
        self.assertIn("job_lost", codes)

    def test_silent_output_is_stalled_and_a_need_while_it_runs(self) -> None:
        self.ds("job", "start", "quiet", "--cmd", "sleep 300", env={"DEV_KIT_JOB_STALL_S": "1"})
        time.sleep(1.5)
        self.assertTrue(self.job("quiet")["stalled"])
        self.assertEqual([n["why"] for n in self.needs()], ["stalled"])
        p = self.ds("job", "wait", "quiet", "--max", "1", expect=3)
        self.assertIn("call `job wait quiet` again", p.stdout)
        self.ds("job", "stop", "quiet")
        self.assertEqual(self.job("quiet")["state"], "stopped")

    def test_one_run_per_name_and_a_new_start_clears_the_need(self) -> None:
        self.ds("job", "start", "suite", "--cmd", "sleep 300")
        self.assertIn("already running", self.ds("job", "start", "suite", "--cmd", "true", expect=1).stderr)
        self.ds("job", "stop", "suite")
        self.ds("job", "start", "suite", "--cmd", "true")
        self.ds("job", "wait", "suite")
        self.assertEqual(self.needs(), [])

    def test_wait_is_bounded_and_names_are_checked(self) -> None:
        self.ds("job", "start", "x", "--cmd", "sleep 300")
        t = time.monotonic()
        self.ds("job", "wait", "x", "--max", "1", expect=3)
        self.assertLess(time.monotonic() - t, 15)
        self.ds("job", "stop", "x")
        self.ds("job", "start", "../evil", "--cmd", "true", expect=1)
        self.ds("job", "wait", "nothing", expect=3)

    def test_watchdog_accepts_the_job_limits(self) -> None:
        self.ds("set", "autonomy.quality.watchdog", '{"job_timeout_min": 120, "job_stall_min": 15}')
        st = json.loads((self.dev / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(st["autonomy"]["quality"]["watchdog"]["job_timeout_min"], 120)
        self.ds("set", "autonomy.quality.watchdog", '{"job_timeout_min": 1}', expect=1)


class TestSelfMatchFence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".dev").mkdir()
        (self.root / ".dev" / "state.json").write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def decide(self, cmd: str, agent_id: str = "") -> dict | None:
        return dev_fence.decide({"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_id": agent_id,
                                 "tool_input": {"command": cmd}}, self.root)

    def test_process_listing_polls_are_denied_to_the_main_session_too(self) -> None:
        for cmd in ("ps aux | grep 'pytest' | grep -v grep", "pgrep -f 'npm test'", "until ! pgrep -f vitest; do sleep 5; done",
                    "ps -ef | egrep T-110"):
            out = self.decide(cmd)
            self.assertIsNotNone(out, cmd)
            self.assertIn("job wait", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNotNone(self.decide("pgrep -f vitest", agent_id="a1"))

    def test_other_commands_pass(self) -> None:
        for cmd in ("kill -0 1234", "pgrep node", "npm test 2>&1 | grep -c passed", "python3 -I dev_state.py job wait full-suite",
                    "ps -p 1234 -o etime="):
            self.assertIsNone(self.decide(cmd), cmd)


class TestBoards(unittest.TestCase):
    def test_spog_groups_long_jobs(self) -> None:
        st = {"backlog": {"needs": [{"kind": "long_job", "job": "full-suite", "why": "timed_out", "since": "2026-11-26T00:00:00Z"}]}}
        groups = {g["kind"]: g for g in dev_spog.needs(st, [])}
        self.assertEqual(groups["long_job"]["items"][0]["id"], "full-suite")
        self.assertNotIn("issue_queue", groups)

    def test_board_has_a_job_row(self) -> None:
        js = (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8")
        self.assertIn('x.kind === "long_job"', js)
        self.assertIn("function jobRow", js)


if __name__ == "__main__":
    unittest.main()
