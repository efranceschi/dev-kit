"""dev-kit 3.0, phase 2 (quality): executable exit check (item 7), hard floor, CI and debt cap (item 10), human
checkpoints on the PRD and the plan (item 11), scope change reaching the current milestone (item 8) and the
milestone size range (item 1b).

Each acceptance criterion of the 3.0 specification for these items is one test (or a few) here.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
SCORE = SCRIPTS / "dev_score.py"
sys.path.insert(0, str(SCRIPTS))


def task(n: int, title: str, ac: str, deps: str = "") -> str:
    return (f"### T-{n:03d} {title}\n- status: todo\n- deps: {deps}\n- type: feature\n- acceptance:\n  - {ac}\n"
            f"- test_notes: unit\n- files: f{n}.py\n\n")


def plan(m1_extra: str = "- exit_check: e2e: checkout.spec; acs: AC-1\n", m1_tasks: int = 5, m2: bool = True,
         m2_extra: str = "- exit_check: cmd: make smoke\n") -> str:
    out = "# Implementation plan — demo\n\n## M1 — Checkout\nA user pays.\n" + m1_extra + "\n"
    out += "".join(task(i, f"Step {i}", f"AC-{i}: step {i} works") for i in range(1, m1_tasks + 1))
    if m2:
        out += "## M2 — Orders\nOrders list.\n" + m2_extra + "\n"
        out += "".join(task(i, f"Order {i}", f"AC-{i}: order {i}") for i in range(m1_tasks + 1, m1_tasks + 6))
    return out


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env=self.env)
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def state(self) -> dict:
        return json.loads((self.dev / "state.json").read_text(encoding="utf-8"))

    def setup_plan(self, text: str | None = None) -> subprocess.CompletedProcess:
        self.ds("init", "--language", "en", "--project", "demo")
        (self.dev / "plan.md").write_text(plan() if text is None else text, encoding="utf-8")
        return self.ds("sync-plan")

    def finish(self, m: str) -> None:
        for tid, t in sorted(self.state()["tasks"].items()):
            if t["milestone"] == m and t["status"] == "todo":
                self.ds("start", tid)
                self.ds("done", tid)

    def floor(self, m: str, expect: int | None = 0, **checks: object) -> subprocess.CompletedProcess:
        base = {k: {"status": "pass"} for k in ("tests", "lint", "typecheck", "deps", "secrets")}
        base["a11y"] = {"status": "n/a", "reason": "no UI"}
        base.update(checks)
        f = self.root / "floor.json"
        f.write_text(json.dumps(base), encoding="utf-8")
        return self.ds("hard-floor", m, "--from", str(f), expect=expect)

    def scores(self, m: str, exit_result: str | None) -> Path:
        raw = self.dev / "qa" / m / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        tracer = {"auditor": "spec-tracer", "findings": []}
        if exit_result:
            tracer["exit_check"] = {"result": exit_result, "checks": [
                {"check": "e2e: checkout.spec", "result": exit_result, "detail": "ran it"},
                {"check": "acs: AC-1", "result": "pass"}]}
        (raw / "spec-tracer.json").write_text(json.dumps(tracer), encoding="utf-8")
        (raw / "code-reviewer.json").write_text(json.dumps({"auditor": "code-reviewer", "findings": []}), encoding="utf-8")
        out = self.dev / "qa" / m / "scores.json"
        subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", m, "--kind", "gate", "--root", str(self.root),
                        "--out", str(out), *map(str, sorted(raw.glob("*.json")))], capture_output=True, text=True, cwd=self.root)
        return out


# ------------------------------------------------------------------ item 7: exit check

class TestExitCheck(Base):
    def test_exit_check_is_parsed_into_the_milestone(self) -> None:
        self.setup_plan()
        m = self.state()["milestones"]
        self.assertEqual(m["M1"]["exit_check"], {"e2e": ["checkout.spec"], "acs": ["AC-1"]})
        self.assertEqual(m["M2"]["exit_check"], {"cmd": ["make smoke"]})
        self.assertEqual(self.state()["tasks"]["T-001"]["milestone"], "M1")

    def test_sync_plan_refuses_a_new_milestone_without_exit_check(self) -> None:
        self.ds("init", "--language", "en", "--project", "demo")
        (self.dev / "plan.md").write_text(plan(m2_extra=""), encoding="utf-8")
        p = self.ds("sync-plan", expect=1)
        self.assertIn("M2 has no exit_check", p.stderr)

    def test_fixes_and_maintenance_milestones_are_exempt(self) -> None:
        text = plan(m2=False) + "## M2 — Maintenance\nHousekeeping.\n\n" + task(9, "Bump", "AC-9: bumped") \
            + "## M1.1 — R1 · Fixes 1\n\n" + task(10, "Fix", "AC-1: fixed")
        self.assertIn("synced", self.setup_plan(text).stdout)

    def test_old_plan_without_exit_check_only_warns(self) -> None:
        p = self.setup_plan(plan(m1_extra="", m2_extra=""))
        self.assertIn("M1: no exit_check", p.stdout)
        self.assertIn("--annotate-exit", p.stdout)
        self.assertNotIn("exit_checks", self.state())

    def test_gate_with_good_scores_but_failing_exit_check_is_refused(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.floor("M1")
        out = self.scores("M1", "fail")
        res = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(res["exit"]["result"], "fail")
        self.assertEqual(res["overall"], 100)  # every dimension at or above its cut-off
        self.assertEqual(res["verdict"], "fail")
        p = self.ds("gate", "M1", "passed", "--score", "100", expect=1)
        self.assertIn("exit_check failed", p.stderr)
        self.scores("M1", "pass")
        self.ds("gate", "M1", "passed", "--score", "100")

    def test_gate_needs_an_exit_result(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.floor("M1")
        self.scores("M1", None)
        p = self.ds("gate", "M1", "passed", "--score", "100", expect=1)
        self.assertIn("exit_check: no result", p.stderr)
        self.ds("gate", "M1", "passed", "--score", "100", "--force", "--note", "ADR-001 user accepted")

    def test_bad_exit_check_syntax_is_refused(self) -> None:
        self.ds("init", "--language", "en", "--project", "demo")
        (self.dev / "plan.md").write_text(plan(m1_extra="- exit_check: run the app\n"), encoding="utf-8")
        p = self.ds("sync-plan", expect=1)
        self.assertIn("M1: exit_check part", p.stderr)


# ------------------------------------------------------------------ item 1b: milestone size

class TestMilestoneSize(Base):
    def test_29_tasks_without_size_reason_warn(self) -> None:
        p = self.setup_plan(plan(m1_tasks=29, m2=False))
        self.assertIn("M1: size", p.stdout)
        self.assertIn("outside 5-12", p.stdout)
        self.assertIn("size_reason", p.stdout)

    def test_29_tasks_with_size_reason_do_not_warn(self) -> None:
        p = self.setup_plan(plan(m1_extra="- exit_check: acs: AC-1\nsize_reason: one migration, cannot be split\n",
                                 m1_tasks=29, m2=False))
        self.assertNotIn("M1: size", p.stdout)
        self.assertEqual(self.state()["milestones"]["M1"]["size_reason"], "one migration, cannot be split")

    def test_count_includes_buffer_slots(self) -> None:
        p = self.setup_plan(plan(m1_tasks=11, m2=False))  # 11 planned + ceil(20% of 11) = 3 buffer = 14
        self.assertIn("M1: size 14 (11 planned + 3 buffer)", p.stdout)
        self.ds("set", "autonomy.milestone_size", '{"min": 3, "max": 20}')
        self.assertNotIn("M1: size", self.ds("sync-plan").stdout)

    def test_range_is_validated(self) -> None:
        self.setup_plan()
        self.ds("set", "autonomy.milestone_size", '{"min": 9, "max": 4}', expect=1)
        self.ds("set", "autonomy.milestone_size.max", "15")
        self.assertEqual(self.state()["autonomy"]["milestone_size"], {"min": 5, "max": 15})


# ------------------------------------------------------------------ item 10: hard floor, CI, debt cap

class TestHardFloor(Base):
    def test_score_96_with_a_high_npm_audit_finding_fails_and_creates_the_fix(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.scores("M1", "pass")
        p = self.floor("M1", deps={"status": "fail", "severity": "high", "detail": "lodash prototype pollution", "tool": "npm audit"})
        self.assertIn("deps: fail (high)", p.stdout)
        fix = [(k, t) for k, t in self.state()["tasks"].items() if t.get("source") == "hard_floor:deps"]
        self.assertEqual(len(fix), 1)
        self.assertEqual(fix[0][1]["type"], "fix")
        self.assertEqual(fix[0][1]["milestone"], "M1")
        p = self.ds("gate", "M1", "passed", "--score", "96", expect=1)
        self.assertIn("hard floor: deps fails (high)", p.stderr)
        self.floor("M1", deps={"status": "fail", "severity": "high"})  # same check again: same fix task
        self.assertEqual(sum(1 for t in self.state()["tasks"].values() if t.get("source") == "hard_floor:deps"), 1)
        self.assertIn(fix[0][0], (self.dev / "plan.md").read_text(encoding="utf-8"))

    def test_secrets_and_critical_deps_cannot_be_forced(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.scores("M1", "pass")
        self.floor("M1", secrets={"status": "fail", "detail": "AWS key in config.py"})
        p = self.ds("gate", "M1", "passed", "--score", "96", "--force", "--note", "ADR-002", expect=1)
        self.assertIn("not even with --force", p.stderr)
        self.floor("M1", deps={"status": "fail", "severity": "critical"})
        self.ds("gate", "M1", "passed", "--score", "96", "--force", "--note", "ADR-002", expect=1)
        self.floor("M1", lint={"status": "fail"})
        self.ds("gate", "M1", "passed", "--score", "96", "--force", "--note", "ADR-002")

    def test_na_needs_a_reason(self) -> None:
        self.setup_plan()
        self.assertIn("n/a needs a reason", self.floor("M1", expect=1, tests={"status": "n/a"}).stderr)
        p = self.floor("M1", tests={"status": "n/a", "reason": "no test runner yet"})
        self.assertIn("no tests in the project is a high finding", p.stdout)

    def test_a_3_0_plan_needs_the_floor_recorded(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.scores("M1", "pass")
        p = self.ds("gate", "M1", "passed", "--score", "96", expect=1)
        self.assertIn("no deterministic checks recorded", p.stderr)


class TestCI(Base):
    def setUp(self) -> None:
        super().setUp()
        self.setup_plan()
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")
        self.finish("M1")
        self.floor("M1")
        self.scores("M1", "pass")

    def test_red_ci_on_the_frozen_commit_fails_the_gate_with_green_local_suite(self) -> None:
        self.ds("ci", "record", "M1", "--sha", "abc1234def", "--status", "failure")
        p = self.ds("gate", "M1", "passed", "--score", "98", expect=1)
        self.assertIn("ci: github is failure at abc1234def", p.stderr)
        self.ds("ci", "record", "M1", "--sha", "abc1234def", "--status", "success")
        self.ds("gate", "M1", "passed", "--score", "98")

    def test_no_ci_result_blocks_and_not_required_does_not(self) -> None:
        p = self.ds("gate", "M1", "passed", "--score", "98", expect=1)
        self.assertIn("no github result recorded", p.stderr)
        self.ds("set", "autonomy.ci.required", "false")
        self.ds("gate", "M1", "passed", "--score", "98")

    def test_pending_ci_reports_the_timeout(self) -> None:
        env = dict(self.env)
        self.env = dict(env, DEV_KIT_NOW="2026-11-23T10:00:00Z")
        self.ds("ci", "record", "M1", "--sha", "abc", "--status", "pending")
        self.env = dict(env, DEV_KIT_NOW="2026-11-23T10:45:00Z")
        p = self.ds("ci", "record", "M1", "--sha", "abc", "--status", "pending")
        self.assertIn("ci_timeout", p.stdout)
        self.assertEqual(self.state()["milestones"]["M1"]["ci"]["since"][:19], "2026-11-23T10:00:00")

    def test_provider_none_skips_ci(self) -> None:
        self.ds("set", "autonomy.ci", "none")
        self.ds("gate", "M1", "passed", "--score", "98")


class TestDebtCap(Base):
    def write_deferred(self, m: str, n: int, medium: int = 0) -> None:
        d = self.dev / "qa" / m
        d.mkdir(parents=True, exist_ok=True)
        items = [{"id": f"D-{i:03d}", "severity": "medium" if i <= medium else "low", "title": f"thing {i}"} for i in range(1, n + 1)]
        (d / "findings-round-1.json").write_text(json.dumps({"findings": [], "deferred": items}), encoding="utf-8")

    def test_21_deferred_findings_raise_the_needs_you_item_with_three_actions(self) -> None:
        self.setup_plan()
        self.finish("M1")
        self.floor("M1")
        self.scores("M1", "pass")
        self.write_deferred("M1", 21)
        p = self.ds("gate", "M1", "passed", "--score", "96")
        self.assertIn("debt_over_cap: 21 deferred findings open (cap 20)", p.stdout)
        needs = json.loads(self.ds("backlog", "--json").stdout)["needs"]
        debt = [n for n in needs if n["kind"] == "debt_over_cap"]
        self.assertEqual(len(debt), 1)
        self.assertEqual(debt[0]["actions"], ["promote", "accept", "cooldown"])
        self.assertIn("Needs you: Deferred debt above the cap", self.ds("status").stdout)
        self.ds("debt", "decide", "cooldown")
        self.assertTrue(self.state()["autonomy"]["cooldown"]["enabled"])
        self.assertFalse([n for n in json.loads(self.ds("backlog", "--json").stdout)["needs"] if n["kind"] == "debt_over_cap"])

    def test_20_do_not_and_medium_cap_counts(self) -> None:
        self.setup_plan()
        self.write_deferred("M1", 20)
        self.assertFalse(json.loads(self.ds("debt", "status", "--json").stdout)["over"])
        self.write_deferred("M1", 12, medium=11)
        self.assertTrue(json.loads(self.ds("debt", "status", "--json").stdout)["over"])

    def test_board_decision_is_validated(self) -> None:
        import dev_worker as dw
        self.assertEqual(dw.validate("debt_decision", {"decision": "accept"}), {"decision": "accept"})
        with self.assertRaises(dw.Invalid):
            dw.validate("debt_decision", {"decision": "ignore"})


# ------------------------------------------------------------------ item 11: checkpoints

class TestCheckpoint(Base):
    def conceive(self) -> None:
        for f in ("brief.md", "prd.md", "architecture.md"):
            (self.dev / f).write_text(f"# {f}\n", encoding="utf-8")
        self.ds("artifact", "mark", "brief")
        self.ds("artifact", "mark", "prd")
        self.ds("review", "prd", "pass", "--score", "90")

    def test_no_implement_of_the_first_milestone_before_confirm_plan(self) -> None:
        self.setup_plan()
        self.conceive()
        self.assertIn("checkpoint prd: pending", self.ds("checkpoint", "status", "prd").stdout)
        self.ds("checkpoint", "confirm", "prd")
        p = self.ds("review", "plan", "pass", "--score", "90")
        self.assertIn("checkpoint plan: waiting for the user's confirmation", p.stdout)
        p = self.ds("next", expect=3)
        self.assertIn("waits for the plan's confirmation", p.stdout + p.stderr)
        self.ds("start", "T-001", expect=1)
        needs = json.loads(self.ds("backlog", "--json").stdout)["needs"]
        cp = [n for n in needs if n["kind"] == "checkpoint"]
        self.assertEqual(cp[0]["title"], "Confirm plan")
        self.assertEqual(cp[0]["doc"], "plan.md")  # the board opens it as #doc:plan.md
        self.ds("checkpoint", "confirm", "plan")
        self.assertTrue(self.ds("next").stdout.startswith("T-001"))
        cps = self.state()["checkpoints"]["plan"]
        self.assertEqual(cps["status"], "confirmed")
        self.assertEqual(cps["by"], "user")
        self.assertTrue(cps["version"])
        self.assertTrue(cps["confirmed_at"])

    def test_prd_checkpoint_holds_architecture(self) -> None:
        self.setup_plan()
        self.conceive()
        st = json.loads(self.ds("status", "--json").stdout)
        self.assertEqual(st["step"], "prd")
        self.assertEqual(st["next_command"], "/dev-kit:review prd")
        self.ds("checkpoint", "adjust", "prd", expect=1)  # needs feedback
        self.ds("checkpoint", "adjust", "prd", "--feedback", "split the admin persona")
        self.assertEqual(json.loads(self.ds("status", "--json").stdout)["next_command"], "/dev-kit:prd")
        (self.dev / "prd.md").write_text("# prd.md\n\nrevised\n", encoding="utf-8")
        self.ds("artifact", "mark", "prd")
        self.ds("review", "prd", "pass", "--score", "92")
        cp = self.state()["checkpoints"]["prd"]
        self.assertEqual((cp["status"], cp["round"]), ("pending", 2))
        self.assertEqual(cp["history"][0]["decision"], "adjust")

    def test_replan_keeps_the_running_milestone(self) -> None:
        self.setup_plan()
        self.conceive()
        self.ds("checkpoint", "confirm", "prd")
        self.ds("review", "plan", "pass", "--score", "90")
        self.ds("checkpoint", "confirm", "plan")
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        (self.dev / "plan.md").write_text(plan() + "\n<!-- replan -->\n", encoding="utf-8")
        self.ds("review", "plan", "pass", "--score", "88")  # a replan: new checkpoint
        self.assertTrue(self.ds("next").stdout.startswith("T-002"))  # M1 has started: it continues

    def test_same_version_reviewed_again_needs_no_new_confirmation(self) -> None:
        self.setup_plan()
        self.conceive()
        self.ds("checkpoint", "confirm", "prd")
        p = self.ds("review", "prd", "pass", "--score", "91")
        self.assertNotIn("checkpoint prd", p.stdout)

    def test_board_request(self) -> None:
        import dev_worker as dw
        self.setup_plan()
        self.conceive()
        with self.assertRaises(dw.Invalid):
            dw.validate("checkpoint", {"target": "plan", "decision": "adjust"})
        item = dw.submit(self.root, "checkpoint", {"target": "prd", "decision": "confirm"})
        self.ds("checkpoint", "confirm", "prd", "--request", item["id"])
        self.assertEqual(self.state()["checkpoints"]["prd"]["by"], "board")
        self.assertEqual(self.state()["checkpoints"]["prd"]["history"][-1]["request"], item["id"])


# ------------------------------------------------------------------ item 8: scope change pauses affected tasks

class TestScopeChange(Base):
    def test_change_to_ac4_lists_and_pauses_the_tasks_and_the_replan_resolves_them(self) -> None:
        self.setup_plan()
        p = self.ds("affected", "--acs", "AC-4")
        self.assertIn("T-004", p.stdout)
        self.assertNotIn("T-003", p.stdout)
        iid = self.ds("add-issue", "--type", "change", "--class", "change", "--title", "AC-4 changes", "--severity", "medium").stdout.split()[0]
        rows = json.loads(self.ds("affected", "--acs", "AC-4,AC-5", "--json").stdout)
        self.assertEqual([r["task"] for r in rows], ["T-004", "T-005"])
        for r in rows:
            self.ds("block", r["task"], "--blocked-by", iid)
        t = self.state()["tasks"]["T-004"]
        self.assertEqual((t["status"], t["blocked_by"]), ("blocked", iid))
        self.assertEqual(t["blocked_reason"], f"waiting for the replan of {iid}")
        p = self.ds("review", "plan", "pass", "--score", "90")
        self.assertIn(f"T-004 ({iid})", p.stdout)
        self.ds("unblock", "T-004")
        self.ds("drop", "T-005", "--reason", f"{iid}: AC-5 removed")
        s = self.state()["tasks"]
        self.assertNotIn("blocked_by", s["T-004"])
        self.assertEqual(s["T-005"]["status"], "dropped")

    def test_paused_tasks_do_not_count_in_a_frozen_milestone(self) -> None:
        self.setup_plan()
        iid = self.ds("add-issue", "--type", "change", "--class", "change", "--title", "AC-5", "--severity", "medium").stdout.split()[0]
        for tid in ("T-001", "T-002", "T-003", "T-004"):
            self.ds("start", tid)
            self.ds("done", tid)
        self.ds("block", "T-005", "--blocked-by", iid)
        import dev_state as dsm

        def done() -> bool:
            st = dsm.Store(self.root)
            st.load()
            return st.milestone_done("M1")
        self.assertFalse(done())
        self.ds("freeze", "M1")
        self.assertTrue(done())  # the paused task waits for the replan; the gate does not wait for it

    def test_blocked_by_needs_a_known_issue(self) -> None:
        self.setup_plan()
        self.ds("block", "T-001", "--blocked-by", "I-999", expect=1)
        self.ds("block", "T-001", expect=1)  # neither reason nor issue


if __name__ == "__main__":
    unittest.main()
