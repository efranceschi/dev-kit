"""dev-kit 3.0, phase 3 (flow): one release model, always planned (item 5), rounds in a child session (item 1a) and the
pipeline that does not stop for a person (item 4), with the time spent waiting for one measured.

Each acceptance criterion of the 3.0 specification for these items is one test (or a few) here.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
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

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
sys.path.insert(0, str(SCRIPTS))


def task(n: int, ac: int, files: str, deps: str = "") -> str:
    return (f"### T-{n:03d} Step {n}\n- status: todo\n- deps: {deps}\n- type: feature\n- acceptance:\n  - AC-{ac}: step {n} works\n"
            f"- test_notes: unit\n- files: {files}\n\n")


PLAN = ("# Implementation plan — shop\n\n"
        "## R1 — First sale\n\n## M1 — Catalog\nBrowse.\n\n" + task(1, 1, "src/catalog.py")
        + "## M2 — Cart\nCart.\n\n" + task(2, 2, "src/cart.py") + task(3, 3, "src/cart_view.py", "T-002")
        + "## R2 — Payments\n\n## M3 — Checkout\nPay.\n\n" + task(4, 4, "src/pay.py") + task(5, 5, "src/cart.py")
        + "## M4 — Receipts\nReceipts.\n\n" + task(6, 6, "src/receipt.py")
        + "## R3 — Accounts\n\n## M5 — Login\nLogin.\n\n" + task(7, 7, "src/login.py"))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION", "DEV_KIT_CLAUDE")}
        self.ds("init", "--language", "en", "--project", "shop")
        (self.dev / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0, env: dict | None = None) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env={**self.env, **(env or {})})
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def state(self) -> dict:
        return json.loads((self.dev / "state.json").read_text(encoding="utf-8"))

    def events(self) -> list[dict]:
        p = self.dev / "telemetry.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []

    def close(self, *ms: str) -> None:
        for m in ms:
            for tid, t in sorted(self.state()["tasks"].items()):
                if t["milestone"] == m and t["status"] == "todo":
                    self.ds("start", tid)
                    self.ds("done", tid)
            self.ds("gate", m, "passed", "--score", "95")

    def nxt(self) -> dict:
        return json.loads(self.ds("next", "--json", expect=None).stdout)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(["git", "-C", str(cwd or self.root), *args], capture_output=True, text=True, check=True).stdout.strip()


# ------------------------------------------------------------------ item 5: always planned releases

class TestOneReleaseModel(Base):
    def test_no_path_reaches_production_without_approval_except_a_hotfix(self) -> None:
        self.close("M1", "M2")
        p = self.ds("release-record", "--version", "1.0.0", expect=1)
        self.assertIn("record R1 with --release R1 after its approval", p.stderr)
        self.ds("release-record", "--version", "1.0.0", "--milestones", "M1,M2", expect=1)
        self.ds("release-record", "--version", "1.0.0", "--release", "R1", expect=1)  # not approved yet
        self.ds("release-submit", "R1")
        self.ds("release-record", "--version", "1.0.0", "--release", "R1", expect=1)  # waiting for the decision
        self.ds("release-decide", "R1", "--approve")
        self.ds("release-record", "--version", "1.0.0", "--release", "R1")
        self.ds("release-record", "--version", "1.0.1", "--hotfix", "T-001")  # outside the release train

    def test_a_new_plan_without_release_headings_becomes_one_r1(self) -> None:
        (self.dev / "plan.md").write_text("# Implementation plan — tiny\n\n## M1 — One\nGoal.\n\n" + task(1, 1, "a.py")
                                          + "## M2 — Two\nGoal.\n\n" + task(2, 2, "b.py"), encoding="utf-8")
        p = self.ds("sync-plan")
        self.assertIn("every milestone now belongs to a planned release", p.stdout)
        self.assertEqual([(r["id"], r["title"], r["milestones"]) for r in self.state()["release_plan"]], [("R1", "tiny", ["M1", "M2"])])
        self.assertFalse((self.dev / "decisions.md").exists())  # a new project is not a migration: no ADR

    def test_a_new_maintenance_milestone_joins_the_open_maintenance_release(self) -> None:
        (self.dev / "plan.md").write_text("# Plan\n\n## R1 — Maintenance\n\n## M7 — Maintenance\n", encoding="utf-8")
        self.ds("sync-plan")
        self.ds("add-task", "--milestone", "M7", "--title", "Fix a", "--type", "fix", "--files", "a.py")
        self.close("M7")
        self.ds("add-task", "--milestone", "M8", "--milestone-title", "Maintenance", "--title", "Fix b", "--type", "fix", "--files", "b.py")
        self.assertEqual(self.state()["milestones"]["M8"]["release"], "R1")  # R1 not submitted: it keeps growing
        self.close("M8")
        self.ds("release-submit", "R1")
        self.ds("add-task", "--milestone", "M9", "--milestone-title", "Maintenance", "--title", "Fix c", "--type", "fix", "--files", "c.py")
        self.assertEqual(self.state()["milestones"]["M9"]["release"], "R2")  # R1 is with the user: a new release
        self.ds("sync-plan")
        self.assertEqual([r["id"] for r in self.state()["release_plan"]], ["R1", "R2"])
        self.assertIn("## R2 — Maintenance", (self.dev / "plan.md").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ item 1a: rounds in a child session

FAKE_CLAUDE = """#!/bin/sh
# records its arguments and environment, then plays a QA round: one fix task and the gate left pending
printf '%s\\n' "$@" > "$CLAUDE_PROJECT_DIR/.dev/run/fake-args"
env | grep -E '^(DEV_KIT_PARENT_SESSION|DEV_KIT_ROUND_CHILD|CLAUDE_PROJECT_DIR)=' > "$CLAUDE_PROJECT_DIR/.dev/run/fake-env"
DS="{py} -I {state} --root $CLAUDE_PROJECT_DIR"
$DS event skill_start --set skill=qa --set scope=M1 >/dev/null
$DS add-task --milestone M1 --title "Fix F-001" --type fix --files src/catalog.py --source qa/M1/report.md >/dev/null
$DS gate M1 pending --score 71 --count-run >/dev/null
echo '{{"result": "done"}}'
"""


class TestRoundChild(Base):
    def fake(self, body: str) -> Path:
        exe = self.root / "fake-claude"
        exe.write_text(body.format(py=sys.executable, state=STATE), encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        return exe

    def test_round_run_starts_a_headless_child_and_prints_the_summary(self) -> None:
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.ds("event", "session_start", "--set", "trigger=autopilot")
        parent = (self.dev / "telemetry-session").read_text(encoding="utf-8").strip()
        exe = self.fake(FAKE_CLAUDE)
        p = self.ds("round", "run", "qa", "M1", "--permission-mode", "acceptEdits", env={"DEV_KIT_CLAUDE": str(exe)})
        out = json.loads(p.stdout)
        self.assertEqual((out["verdict"], out["score"], out["gate"]), ("fail", 71, "pending"))
        self.assertEqual(len(out["fix_tasks"]), 1)
        for k in ("deferred", "cost", "duration_s", "report", "next", "log"):
            self.assertIn(k, out)
        args = (self.dev / "run" / "fake-args").read_text(encoding="utf-8").split("\n")
        self.assertEqual(args[:2], ["-p", "/dev-kit:qa M1 --round-child"])
        self.assertIn("--plugin-dir", args)
        self.assertEqual(args[args.index("--permission-mode") + 1], "acceptEdits")
        env = (self.dev / "run" / "fake-env").read_text(encoding="utf-8")
        self.assertIn(f"DEV_KIT_PARENT_SESSION={parent}", env)
        child = [e for e in self.events() if e.get("parent_session") == parent]
        self.assertTrue(child and all(e["session"] == parent for e in child))  # summed into the parent's session
        self.assertTrue(any(e["event"] == "round_run" and e.get("verdict") == "fail" for e in self.events()))

    def test_without_claude_on_path_it_says_plan_b(self) -> None:
        p = self.ds("round", "run", "qa", "M1", expect=3, env={"PATH": "/nonexistent"})
        self.assertIn("plan B", p.stderr)
        self.ds("round", "run", "deploy", "M1", expect=1)

    def test_skills_use_it(self) -> None:
        auto = (CORE.parent / "autopilot" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("DS round run qa <M>", auto)
        self.assertIn("DS round run implement <M>", auto)
        for s in ("qa", "implement"):
            self.assertIn("--round-child", (CORE.parent / s / "SKILL.md").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ item 4: pipeline

class TestPipeline(Base):
    def submit(self, rid: str) -> None:
        self.ds("release-submit", rid)

    def test_r2_starts_on_its_branch_while_r1_waits_and_never_reaches_main(self) -> None:
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / "README.md").write_text("shop\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "base")
        self.close("M1", "M2")
        self.assertIsNone(self.nxt()["task"])  # R1 is ready but not submitted: nothing ahead yet
        self.submit("R1")
        n = self.nxt()
        self.assertEqual((n["task"], n["branch"], n["ahead_of"]), ("T-004", "dev-kit/R2", "R1"))
        self.assertIn("dev-kit/R2", self.ds("start", "T-004").stdout)
        self.assertEqual(self.state()["tasks"]["T-004"]["branch"], "dev-kit/R2")
        wt = Path(self.ds("pipeline", "worktree", "dev-kit/R2").stdout.strip())
        (wt / "pay.py").write_text("pay\n", encoding="utf-8")
        self.git("add", "pay.py", cwd=wt)
        self.git("commit", "-qm", "[T-004] feat: pay", cwd=wt)
        self.ds("done", "T-004")
        self.assertNotIn("T-004", self.git("log", "--oneline", "main"))
        self.ds("pipeline", "integrate", "dev-kit/R2", expect=1)  # R1 is not released yet
        self.ds("release-decide", "R1", "--approve")
        self.ds("release-record", "--version", "1.0.0", "--release", "R1")
        self.ds("pipeline", "integrate", "dev-kit/R2")
        self.assertIn("T-004", self.git("log", "--oneline", "main"))

    def test_rejection_pauses_r2_and_puts_the_fixes_milestone_first(self) -> None:
        self.close("M1", "M2")
        self.submit("R1")
        self.ds("start", "T-004")
        p = self.ds("release-decide", "R1", "--reject", "--feedback", "Total is wrong")
        self.assertIn("paused ahead: T-004", p.stdout)
        s = self.state()
        self.assertEqual(s["tasks"]["T-004"]["status"], "blocked")
        fix = next(t for t, v in s["tasks"].items() if v.get("source") == "release:R1")
        self.assertEqual(self.nxt()["task"], fix)
        self.ds("start", fix)
        self.ds("done", fix)
        self.ds("gate", s["tasks"][fix]["milestone"], "passed", "--score", "95")
        self.assertIn("resumed ahead: T-004", self.ds("release-submit", "R1").stdout)
        self.assertEqual(self.state()["tasks"]["T-004"]["status"], "in_progress")

    def test_releases_ahead_limits_how_far_the_work_goes(self) -> None:
        self.close("M1", "M2")
        self.submit("R1")
        for tid in ("T-004", "T-005", "T-006"):
            self.ds("start", tid, "--force")
            self.ds("done", tid)
        for m in ("M3", "M4"):
            self.ds("gate", m, "passed", "--score", "95")
        self.submit("R2")
        n = self.nxt()
        self.assertIsNone(n["task"])  # R1 and R2 both waiting: nothing of R3
        self.ds("set", "autonomy.pipeline.releases_ahead", "2")
        self.assertEqual(self.nxt()["task"], "T-007")

    def test_independent_task_of_the_next_milestone_runs_while_the_milestone_is_in_qa(self) -> None:
        (self.dev / "plan.md").write_text("# Implementation plan — shop\n\n## R1 — All\n\n## M1 — Catalog\nBrowse.\n\n"
                                          + task(1, 1, "src/catalog.py") + "## M2 — Cart\nCart.\n\n" + task(2, 2, "src/cart.py")
                                          + task(3, 3, "src/catalog.py") + task(4, 4, "src/promo.py", "T-001")
                                          + task(5, 5, "src/banner.py"), encoding="utf-8")
        self.ds("sync-plan")
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.assertIsNone(self.nxt()["task"])  # gate of M1 pending, not frozen yet
        self.ds("freeze", "M1")
        n = self.nxt()
        self.assertEqual((n["task"], n["branch"]), ("T-002", "dev-kit/M2"))
        batch = json.loads(self.ds("next", "--batch", "3", "--json").stdout)
        # T-003 lists a file M1 touched, T-004 depends on a task of M1: only the independent ones run ahead
        self.assertEqual(sorted(t["task"] for t in batch["tasks"]), ["T-002", "T-005"])
        self.assertEqual(batch["branch"], "dev-kit/M2")
        self.ds("start", "T-002")
        self.ds("done", "T-002")
        self.ds("set", "autonomy.pipeline.milestone_overlap", "false")
        self.assertIsNone(self.nxt()["task"])
        self.ds("set", "autonomy.pipeline.milestone_overlap", "true")
        # a QA fix of M1 that touches src/cart.py sends T-002 back to todo, to redo after the gate
        self.ds("add-task", "--milestone", "M1", "--title", "Fix F-002", "--type", "fix", "--files", "src/cart.py",
                "--source", "qa/M1/report.md")
        t2 = self.state()["tasks"]["T-002"]
        self.assertEqual((t2["status"], t2["redo_after"]), ("todo", "M1"))
        self.assertNotEqual(self.nxt()["task"], "T-002")

    def test_flow_json_has_human_wait_s(self) -> None:
        self.ds("start", "T-001")
        q = self.ds("add-question", "Which currency?", "--skill", "implement", env={"DEV_KIT_NOW": "2026-11-23T10:00:00Z"}).stdout.strip()
        self.ds("answer-question", q, "--answer", "EUR", env={"DEV_KIT_NOW": "2026-11-23T10:30:00Z"})
        self.ds("done", "T-001")
        self.ds("gate", "M1", "passed", "--score", "95")
        flow = json.loads((self.dev / "qa" / "M1" / "flow.json").read_text(encoding="utf-8"))
        self.assertEqual(flow["human_wait_s"], 1800)
        self.close("M2")
        self.submit("R1")
        self.ds("release-decide", "R1", "--approve")
        self.ds("release-record", "--version", "1.0.0", "--release", "R1")
        rflow = json.loads((self.dev / "releases" / "R1" / "flow.json").read_text(encoding="utf-8"))
        self.assertIn("human_wait_s", rflow)
        self.assertEqual(rflow["milestones_wait_s"]["M1"], 1800)
        self.assertTrue(any(e["event"] == "human_wait" and e.get("kind") == "release" for e in self.events()))

    def test_pipeline_config_is_validated(self) -> None:
        self.ds("set", "autonomy.pipeline", '{"releases_ahead": 9}', expect=1)
        self.ds("set", "autonomy.pipeline.releases_ahead", "0")
        self.close("M1", "M2")
        self.submit("R1")
        self.assertIsNone(self.nxt()["task"])


if __name__ == "__main__":
    unittest.main()
