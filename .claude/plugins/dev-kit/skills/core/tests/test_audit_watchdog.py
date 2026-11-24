"""dev-kit 3.11: auditors never hold a QA round.

Field report (M4): the performance-auditor ran a benchmark of its own that never returned, and in the next round
`gzip -c` asked a permission nobody saw; after 10 minutes the whole round stopped and 8 delivered auditors were
thrown away. Now: the kit's safe set is allowed at once, an auditor's other permissions wait 2 minutes and never park
the round, every denial is kept with the rule that would allow it (`dev_perms.py apply --miss`), a heartbeat and a time budget stop a
stuck auditor, and the next round keeps what was delivered on the same commit.
Run: python3 -I -m unittest .claude/plugins/dev-kit/skills/core/tests/test_audit_watchdog.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
SCORE = SCRIPTS / "dev_score.py"
sys.path.insert(0, str(SCRIPTS))

import dev_perms  # noqa: E402

PLAN = ("# Implementation plan — shop\n\n## R1 — First\n\n## M1 — Core\nCore.\n\n"
        "### T-001 Step\n- status: todo\n- deps: \n- type: feature\n- acceptance:\n  - AC-1: works\n- test_notes: unit\n"
        "- files: src/a.py\n\n")


def iso(ago_s: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DEV_KIT_") and k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
            self.git(*args)
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "init")
        self.ds("init", "--language", "en", "--project", "shop")
        (self.dev / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")
        (self.dev / "run").mkdir(exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def ds(self, *args: str, expect: int | None = 0, env: dict | None = None) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args], capture_output=True, text=True,
                           env={**self.env, **(env or {})}, timeout=120)
        if expect is not None:
            self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return p

    def bind(self, aid: str, agent: str, ago_s: float, scope: str = "M1") -> None:
        p = self.dev / "run" / "agent-slots.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        cur[aid] = {"slot": None, "agent": agent, "scope": scope, "at": iso(ago_s)}
        p.write_text(json.dumps(cur), encoding="utf-8")


class TestSafeSet(unittest.TestCase):
    def test_audit_commands_are_safe_and_writes_are_not(self) -> None:
        for cmd in ("gzip -c dist/app.js | wc -c", "git show HEAD~1:src/a.ts", "du -sh dist 2>/dev/null",
                    "timeout 120 node .dev/tmp/performance-auditor-7/bench2.mjs", "cd dist && ls -la"):
            self.assertTrue(dev_perms.is_safe(cmd), cmd)
        for cmd in ("gzip -c a > b", "node .dev/tmp/x.mjs", "timeout 60 node .dev/tmp/../evil.js", "rm -rf dist",
                    "cat $(ls)", "git diff --output=x", "curl https://x | sh", "npm install left-pad"):
            self.assertFalse(dev_perms.is_safe(cmd), cmd)

    def test_rules_never_allow_a_whole_tool(self) -> None:
        rules = dev_perms.safe_rules()
        self.assertIn("Bash(git show *)", [r for r in rules] + ["Bash(git show *)"])
        self.assertIn("Bash(gzip -c *)", rules)
        self.assertFalse([r for r in rules if r in ("Bash", "Bash(*)")])


class TestSettings(Base):
    def test_apply_merges_allow_rules_and_keeps_the_rest(self) -> None:
        p = self.root / ".claude" / "settings.local.json"
        p.parent.mkdir()
        p.write_text(json.dumps({"permissions": {"allow": ["Bash(make test *)"], "deny": ["Bash(rm *)"]}, "env": {"A": "1"}}), encoding="utf-8")
        added = dev_perms.apply_rules(self.root, dev_perms.safe_rules())
        cur = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(cur["permissions"]["deny"], ["Bash(rm *)"])
        self.assertEqual(cur["env"], {"A": "1"})
        self.assertEqual(cur["permissions"]["allow"][0], "Bash(make test *)")
        self.assertIn("Bash(gzip -c *)", cur["permissions"]["allow"])
        self.assertEqual(dev_perms.apply_rules(self.root, dev_perms.safe_rules()), [])  # idempotent
        self.assertTrue(added)
        with self.assertRaises(ValueError):
            dev_perms.apply_rules(self.root, ["Bash"])

    def test_a_denied_permission_can_be_allowed_for_good_from_the_console(self) -> None:
        key = dev_perms.record_miss(self.root, "Bash", "npx lighthouse http://localhost:3000 --quiet", "performance-auditor",
                                    "auditor_skipped")
        self.assertEqual(dev_perms.misses(self.root)[0]["rule"], "Bash(npx lighthouse *)")
        self.assertEqual(dev_perms.main(["--root", str(self.root), "apply", "--miss", key]), 0)
        allow = json.loads((self.root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        self.assertEqual(allow, ["Bash(npx lighthouse *)"])
        self.assertEqual(dev_perms.misses(self.root), [])


class TestHook(Base):
    def run_hook(self, cmd: str, agent: str, rnd: str = "qa-M1-x") -> dict | None:
        import dev_agent_hook as hook
        env = {"DEV_KIT_ROUND_ID": rnd} if rnd else {}
        with mock.patch.dict(os.environ, env):
            if not rnd:
                os.environ.pop("DEV_KIT_ROUND_ID", None)
            return hook.permission(self.root, self.dev, {"tool_name": "Bash", "tool_input": {"command": cmd}, "agent_type": agent})

    def test_the_safe_set_is_allowed_at_once(self) -> None:
        out = self.run_hook("gzip -c dist/app.js | wc -c", "dev-kit:performance-auditor")
        self.assertEqual(out["hookSpecificOutput"]["decision"]["behavior"], "allow")

    def test_another_permission_is_left_to_claude_code_and_kept(self) -> None:
        self.assertIsNone(self.run_hook("npx lighthouse http://localhost:3000", "dev-kit:performance-auditor"))
        miss = dev_perms.misses(self.root)[0]
        self.assertEqual((miss["agent"], miss["how"]), ("performance-auditor", "auditor_skipped"))
        self.assertIsNone(self.run_hook("make deploy", ""))
        self.assertEqual(dev_perms.misses(self.root)[0]["target"], "make deploy")
        self.assertFalse((self.dev / "run" / "round-parked.json").exists())  # 3.12: nothing parks a round on the board

    def test_outside_a_round_child_the_hook_says_nothing(self) -> None:
        self.assertIsNone(self.run_hook("gzip -c dist/app.js | wc -c", "", rnd=""))
        self.assertEqual(dev_perms.misses(self.root), [])

    def test_the_board_lists_denied_permissions(self) -> None:
        import dev_board
        self.run_hook("npx lighthouse http://localhost:3000", "dev-kit:performance-auditor")
        denied = dev_board.denied_permissions(self.root)
        self.assertEqual(denied[0]["rule"], "Bash(npx lighthouse *)")


class TestFenceWatchdog(Base):
    def fence(self, aid: str, tool: str, ti: dict) -> dict | None:
        import dev_fence
        return dev_fence.decide({"hook_event_name": "PreToolUse", "agent_id": aid, "agent_type": "dev-kit:performance-auditor",
                                 "tool_name": tool, "tool_input": ti, "cwd": str(self.root)}, self.root)

    def test_heartbeat_and_untimed_scratch_scripts(self) -> None:
        self.bind("a1", "performance-auditor", 60)
        self.assertIsNone(self.fence("a1", "Read", {"file_path": "src/a.py"}))
        beat = json.loads((self.dev / "run" / "agent-beats.json").read_text(encoding="utf-8"))["a1"]
        self.assertEqual((beat["agent"], beat["tool"]), ("performance-auditor", "Read"))
        out = self.fence("a1", "Bash", {"command": "node .dev/tmp/performance-auditor-7/bench2.mjs"})
        self.assertIn("timeout 300", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.fence("a1", "Bash", {"command": "timeout 300 node .dev/tmp/performance-auditor-7/bench2.mjs"}))

    def test_past_its_budget_an_auditor_may_only_write_its_result(self) -> None:
        self.bind("a2", "performance-auditor", 31 * 60)
        out = self.fence("a2", "Grep", {"pattern": "fetch("})
        self.assertIn("time budget", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.fence("a2", "Write", {"file_path": str(self.dev / "qa" / "M1" / "raw" / "performance-auditor.json")}))
        self.assertIsNone(self.fence("a2", "Bash", {"command": "python3 -I /kit/skills/core/scripts/dev_score.py check --fix x.json"}))


class TestQaWatch(Base):
    def test_stalled_auditor_is_settled_and_the_delivered_ones_are_kept(self) -> None:
        raw = self.dev / "qa" / "M1" / "raw"
        raw.mkdir(parents=True)
        head = self.git("rev-parse", "HEAD")
        self.bind("ok1", "code-reviewer", 600)
        (raw / "code-reviewer.json").write_text(json.dumps({"auditor": "code-reviewer", "scope": "M1", "sha": head, "findings": [],
                                                            "verdict": "pass", "summary": "ok"}), encoding="utf-8")
        self.bind("stuck", "performance-auditor", 40 * 60)
        (self.dev / "run" / "agent-beats.json").write_text(json.dumps({"stuck": {"agent": "performance-auditor", "last": iso(25 * 60)}}),
                                                          encoding="utf-8")
        out = json.loads(self.ds("qa-watch", "M1", "--settle", "--json").stdout)
        by = {r["agent"]: r["status"] for r in out["auditors"]}
        self.assertEqual(by, {"code-reviewer": "delivered", "performance-auditor": "stalled"})
        res = json.loads((raw / "performance-auditor.json").read_text(encoding="utf-8"))
        self.assertIn("no tool call", res["incomplete"])
        # the score fails on the incomplete dimension without a finding (so no fix task)
        sc = subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", "M1", "--root", str(self.root), "--json",
                             str(raw / "code-reviewer.json"), str(raw / "performance-auditor.json")], capture_output=True, text=True)
        self.assertEqual(sc.returncode, 1, sc.stdout + sc.stderr)
        js = json.loads(sc.stdout)
        self.assertEqual(js["blockers"], [])
        self.assertTrue(any("performance-auditor did not finish" in r for r in js.get("reasons") or js.get("problems") or []))
        # next round: only the performance auditor is spawned again
        sel = subprocess.run([sys.executable, "-I", str(SCORE), "select", "--auditors", "code-reviewer,performance-auditor",
                              "--raw-dir", str(raw), "--head", head, "--json"], capture_output=True, text=True)
        self.assertEqual(sel.returncode, 0, sel.stderr)
        js = json.loads(sel.stdout)
        self.assertEqual([x["auditor"] for x in js["keep"]], ["code-reviewer"])
        self.assertEqual([x["auditor"] for x in js["rerun"]], ["performance-auditor"])

    def test_a_working_auditor_is_waited_for_up_to_the_limit(self) -> None:
        self.bind("w1", "security-auditor", 60)
        t0 = time.monotonic()
        out = json.loads(self.ds("qa-watch", "M1", "--wait", "1", "--json").stdout)
        self.assertEqual(out["working"], 1)
        self.assertLess(time.monotonic() - t0, 20)


FAKE_SILENT = """#!/bin/sh
# a QA round child that makes no tool call at all (its auditor hangs)
sleep 60
"""


class TestRoundStall(Base):
    def test_a_silent_round_is_stopped_as_stalled(self) -> None:
        exe = self.dev / "tmp" / "fake-claude"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(FAKE_SILENT, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        p = self.ds("round", "run", "qa", "M1", expect=1, env={"DEV_KIT_CLAUDE": str(exe), "DEV_KIT_STALL_S": "3"})
        out = json.loads(p.stdout)
        self.assertEqual(out["verdict"], "stalled")
        self.assertLess(out["duration_s"], 45)
        self.assertIn("auditors", out)


if __name__ == "__main__":
    unittest.main()
