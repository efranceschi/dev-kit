"""Tests for the risk tier (scripts/dev_risk.py, dev_state.py tier/set-risk/risk-report/risk-profile) and the
model/effort router (scripts/dev_router.py) - stdlib unittest.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
ROUTER = SCRIPTS / "dev_router.py"
sys.path.insert(0, str(SCRIPTS))
import dev_risk as risk  # noqa: E402
import dev_router as router  # noqa: E402

PLAN = """# Plan

## M1 — Core
Goal.

### T-001 Scaffold
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-0: ci green
- test_notes: smoke
- files: package.json

### T-002 Users list screen
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-1: list
- test_notes: unit
- files: src/components/UsersList.tsx

### T-003 Login
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-2: login
- test_notes: unit
- files: src/auth/login.ts

### T-004 Session guard and invite e-mail
- status: todo
- deps: T-002, T-003
- type: feature
- acceptance:
  - AC-3: invite
- test_notes: e2e
- files: src/auth/guard.ts, src/mail/invite.ts, db/migrations/002_invites.sql
- risk: high
- uncertainty: high
- risk_reasons: guardrail de envio; integra T-002 e T-003
- opportunity: none

### T-005 Readme
- status: todo
- deps: T-001
- type: docs
- acceptance:
  - AC-0: readme
- test_notes: -
- files: README.md
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_py(self, script: Path, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, "-I", str(script), "--root", str(self.root), *args],
                              capture_output=True, text=True, cwd=self.root)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=f"args={args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        return proc

    def ds(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        return self.run_py(STATE, *args, expect=expect)

    def dr(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        return self.run_py(ROUTER, *args, expect=expect)

    def init(self, plan: str = PLAN) -> None:
        self.ds("init", "--language", "en", "--project", "demo")
        (self.root / ".dev" / "plan.md").write_text(plan, encoding="utf-8")
        self.ds("sync-plan")

    def state(self) -> dict:
        return json.loads((self.root / ".dev" / "state.json").read_text(encoding="utf-8"))

    def tier(self, tid: str) -> dict:
        return json.loads(self.ds("tier", tid, "--json").stdout)

    def router_json(self) -> dict:
        return json.loads((self.root / ".dev" / "router.json").read_text(encoding="utf-8"))


class TestRiskRule(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init()

    def test_tiers_from_objective_signals_and_planner_fields(self) -> None:
        self.assertEqual(self.tier("T-001")["tier"], "balanced")      # ordinary work starts in balanced
        self.assertEqual(self.tier("T-002")["tier"], "balanced")
        t3 = self.tier("T-003")
        self.assertEqual((t3["tier"], t3["final_arm"]), ("balanced+", "sonnet/high"))  # base + auth path
        t4 = self.tier("T-004")
        self.assertEqual((t4["tier"], t4["final_model"], t4["final_effort"]), ("quality", "opus", "high"))
        self.assertTrue(t4["floor"])
        self.assertEqual({s["signal"] for s in t4["reasons"]} - {"base"},
                         {"auth", "external_send", "schema", "new_api", "integration", "planner_high"})
        self.assertEqual(self.tier("T-005")["tier"], "speed")         # docs only

    def test_plan_without_risk_fields_uses_objective_signals_only(self) -> None:
        out = self.ds("tier", "T-003").stdout
        self.assertIn("planner fields: none (objective signals only)", out)
        self.assertIn("auth path src/auth/login.ts +3", out)
        brief = self.ds("brief", "T-003").stdout
        self.assertIn("Tier: balanced+ (4) → sonnet / high", brief)
        self.assertIn("Route: sonnet / high", brief)

    def test_override_needs_a_reason_and_wins(self) -> None:
        self.ds("set-risk", "T-002", "--tier", "quality", expect=1)
        self.ds("set-risk", "T-002", "--tier", "quality", "--tier-reason", "first use of the payments SDK")
        t = self.tier("T-002")
        self.assertEqual((t["tier"], t["source"], t["final_arm"]), ("quality", "plan", "opus/high"))
        self.assertEqual(t["route"]["reason_code"], "override")

    def test_set_risk_keeps_plan_and_state_in_step(self) -> None:
        self.ds("set-risk", "T-002", "--risk", "low", "--opportunity", "downgrade-ok", "--risk-reasons", "simple list; reuse table")
        plan = (self.root / ".dev" / "plan.md").read_text(encoding="utf-8")
        self.assertIn("- opportunity: downgrade-ok", plan)
        self.ds("sync-plan")
        t = self.state()["tasks"]["T-002"]
        self.assertEqual((t["risk"], t["opportunity"], t["risk_reasons"]), ("low", ["downgrade-ok"], "simple list; reuse table"))
        self.assertEqual(self.tier("T-002")["tier"], "speed")
        self.ds("set-risk", "T-002", "--opportunity", "-")
        self.assertNotIn("opportunity", self.state()["tasks"]["T-002"])
        section = (self.root / ".dev" / "plan.md").read_text(encoding="utf-8").split("### T-002")[1].split("###")[0]
        self.assertNotIn("- opportunity:", section)
        self.assertIn("- risk: low", section)
        self.ds("set-risk", "T-002", "--risk", "huge", expect=1)

    def test_sync_rejects_invalid_risk_fields(self) -> None:
        bad = PLAN.replace("- risk: high", "- risk: extreme")
        (self.root / ".dev" / "plan.md").write_text(bad, encoding="utf-8")
        proc = self.ds("sync-plan")  # plan problems are warnings, as for deps and types
        self.assertIn("T-004: risk must be one of", proc.stdout)
        self.assertNotIn("planner_high", {s["signal"] for s in self.tier("T-004")["reasons"]})

    def test_retry_steps_up_and_low_fix_goes_to_speed(self) -> None:
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.ds("start", "T-002")
        self.assertEqual(self.state()["tasks"]["T-002"]["tier"]["rule"], "balanced")
        self.ds("block", "T-002", "--reason", "env")
        self.ds("unblock", "T-002")
        t = self.tier("T-002")
        self.assertEqual(t["tier"], "balanced+")  # +2 failed before, and never below one step above the last attempt
        findings = {"round": 1, "findings": [
            {"id": "F-1", "severity": "low", "file": "src/components/UsersList.tsx", "dimension": "copy", "title": "label"},
            {"id": "F-2", "severity": "high", "file": "src/auth/login.ts", "dimension": "security", "title": "csrf"}]}
        qa = self.root / ".dev" / "qa" / "M1"
        qa.mkdir(parents=True)
        (qa / "findings-round-1.json").write_text(json.dumps(findings), encoding="utf-8")
        out = self.ds("fix-tasks", "--from", ".dev/qa/M1/findings-round-1.json", "--milestone", "M1", "--include", "F-1").stdout
        self.assertIn("T-006=F-1", out)
        tasks = self.state()["tasks"]
        self.assertEqual((tasks["T-006"]["finding_severity"], tasks["T-007"]["finding_severity"]), ("low", "high"))
        low = self.tier("T-006")
        self.assertEqual((low["tier"], low["final_arm"], low["source"]), ("speed", "haiku/low", "fix-low"))
        self.assertIn("reopened_high", {s["signal"] for s in self.tier("T-007")["reasons"]})

    def test_old_fix_task_without_severity_reads_its_source_finding(self) -> None:
        qa = self.root / ".dev" / "qa" / "M1"
        qa.mkdir(parents=True)
        (qa / "findings-round-1.json").write_text(json.dumps({"round": 1, "findings": [
            {"id": "F-9", "severity": "low", "file": "README.md", "title": "typo"}]}), encoding="utf-8")
        self.ds("add-task", "--milestone", "M1", "--title", "Fix typo", "--type", "fix", "--files", "README.md",
                "--source", "qa/M1/report.md#F-9")
        self.assertEqual(self.tier("T-006")["source"], "fix-low")

    def test_risk_tiers_off_restores_the_agent_base(self) -> None:
        self.ds("set", "autonomy.model_policy.risk_tiers", "off")
        self.ds("set", "autonomy.model_policy.router.mode", "off")
        for tid in ("T-002", "T-004", "T-005"):
            self.assertEqual(self.tier(tid)["final_arm"], "sonnet/medium")
        self.assertIn("risk_tiers off", self.ds("tier", "T-004").stdout)

    def test_model_policy_validation(self) -> None:
        self.ds("set", "autonomy.model_policy.router.balance", "fast", expect=1)
        self.ds("set", "autonomy.model_policy.risk_weights", '{"auth": 0}', expect=1)   # floor signal
        self.ds("set", "autonomy.model_policy.risk_weights", '{"nope": 1}', expect=1)
        self.ds("set", "autonomy.model_policy.router.budget_usd_per_milestone", "25")
        self.ds("set", "autonomy.model_policy.risk_weights", '{"schema": 3}')
        mp = self.state()["autonomy"]["model_policy"]
        self.assertEqual((mp["router"]["budget_usd_per_milestone"], mp["risk_weights"], mp["mode"]), (25, {"schema": 3}, "ask"))
        self.assertEqual(self.tier("T-004")["score"], 15)  # schema 2 -> 3

    def test_state_without_new_keys_uses_defaults(self) -> None:
        st = self.state()
        st["autonomy"]["model_policy"] = {"mode": "ask", "tiers": {}}  # a 1.31 state.json
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        t = self.tier("T-004")
        self.assertEqual((t["mode"], t["route"]["mode"], t["final_arm"]), ("apply", "apply", "opus/high"))

    def test_xref_flags_disagreement_and_missing_fields(self) -> None:
        self.ds("set-risk", "T-003", "--risk", "low")
        rep = json.loads(self.ds("xref", "--json").stdout)
        self.assertIn(("risk_disagrees", "T-003"), {(p["check"], p["id"]) for p in rep["problems"]})
        self.assertTrue(any("without risk fields" in n for n in rep["notes"]))

    def test_risk_profile_drives_round_one_auditors(self) -> None:
        prof = json.loads(self.ds("risk-profile", "M1", "--json").stdout)
        self.assertEqual((prof["profile"], prof["max_tier"]), ("risky", "quality"))
        self.assertIn("T-004", prof["high_risk_tasks"])
        self.assertIn(["T-003", "T-004"], prof["seams"])
        self.assertEqual(prof["auditors"]["security-auditor"], "opus/high")
        self.assertEqual(prof["auditors"]["data-reviewer"], "sonnet/high")
        self.assertEqual(prof["auditors"]["copy-reviewer"], "sonnet/medium")
        plain = PLAN.split("### T-003")[0]
        self.tmp.cleanup()
        self.setUp_plain(plain)
        prof = json.loads(self.ds("risk-profile", "M1", "--json").stdout)
        self.assertEqual(prof["profile"], "plain")
        self.assertEqual((prof["auditors"]["security-auditor"], prof["auditors"]["data-reviewer"]), ("sonnet/high", "haiku/medium"))
        out = self.dr("route", "--audit", "spec-tracer", "M1").stdout
        self.assertIn("opus / high", out)

    def setUp_plain(self, plan: str) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.init(plan)

    def test_telemetry_accepts_tier_route_and_scores(self) -> None:
        self.ds("start", "T-003", "--force")
        events = [json.loads(x) for x in (self.root / ".dev" / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()]
        start = [e for e in events if e["event"] == "task" and e.get("transition") == "start"][-1]
        self.assertEqual((start["tier"], start["risk_score"]), ("balanced-plus", 4))
        route = [e for e in events if e["event"] == "route"][-1]
        self.assertEqual((route["arm"], route["rule_tier"]), ("sonnet.high", "balanced-plus"))
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-003", "--set", "tier=balanced-plus",
                "--set", "risk_score=4", "--set", "model=sonnet", "--set", "effort=high")


class TestRiskReportAndLearning(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init()

    def finish_milestone(self, findings: list[dict]) -> None:
        for tid in ("T-001", "T-002", "T-003", "T-004", "T-005"):
            self.ds("start", tid, "--force")
            self.ds("event", "agent_end", "--set", "agent=implementer", "--set", f"scope={tid}", "--set", "model=sonnet",
                    "--set", "effort=medium", "--set", "duration_s=600", "--set", "tokens_in=200000", "--set", "tokens_out=20000")
            self.ds("done", tid, "--force")
        qa = self.root / ".dev" / "qa" / "M1"
        qa.mkdir(parents=True, exist_ok=True)
        (qa / "findings-round-1.json").write_text(json.dumps({"round": 1, "findings": findings}), encoding="utf-8")

    def test_report_attributes_findings_and_gate_closes_the_loop(self) -> None:
        self.finish_milestone([{"id": "F-1", "severity": "high", "file": "src/components/UsersList.tsx", "title": "xss"}])
        rows = json.loads(self.ds("risk-report", "M1", "--json").stdout)["milestones"]["M1"]
        by = {r["task"]: r for r in rows}
        self.assertTrue(by["T-002"]["escape"])
        self.assertIn("loose_rule", by["T-002"]["readings"])
        self.assertIn("maybe_overpaid", by["T-004"]["readings"])
        self.assertEqual(by["T-002"]["duration_s"], 600)
        out = self.ds("gate", "M1", "passed", "--score", "90").stdout
        self.assertIn("router learned M1", out)
        self.assertTrue((self.root / ".dev" / "qa" / "M1" / "risk-report.md").exists())
        data = self.router_json()
        self.assertIn("M1", data["learned"])
        rec = data["records"]["T-002#final"]
        self.assertTrue(rec["escape"])
        self.assertGreater(rec["usd"], 0)
        again = json.dumps(self.router_json()["records"], sort_keys=True)
        self.dr("learn", "M1")
        self.assertEqual(json.dumps(self.router_json()["records"], sort_keys=True), again)  # idempotent

    def test_retroactive_tier_for_tasks_started_before_the_rule(self) -> None:
        self.finish_milestone([])
        st = self.state()
        for t in st["tasks"].values():
            t.pop("tier", None)
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        md_out = self.ds("risk-report", "M1").stdout
        self.assertIn("risk report", md_out)
        md = (self.root / ".dev" / "qa" / "M1" / "risk-report.md").read_text(encoding="utf-8")
        self.assertIn("retroactive", md)

    def test_backfill_seeds_the_router_from_history(self) -> None:
        self.finish_milestone([])
        self.ds("set", "autonomy.model_policy.router.mode", "off")
        self.ds("gate", "M1", "passed", "--score", "90")
        (self.root / ".dev" / "router.json").unlink(missing_ok=True)
        self.dr("learn", "--backfill")
        data = self.router_json()
        self.assertEqual(data["learned"], ["M1"])
        self.assertEqual(len([k for k in data["records"] if k.endswith("#final")]), 5)
        self.assertIn("router:", self.dr("explain").stdout)
        self.dr("reset")
        self.assertEqual(self.router_json()["records"], {})


class TestRouterDecision(unittest.TestCase):
    """The decision itself, on a hand-made router.json (pure function, deterministic)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name)
        self.cfg = {"mode": "apply", "balance": "balanced", "budget_usd_per_milestone": None}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def data(self, runs: list[tuple[str, float, float, int, bool]], ctx: str = "task:balanced:ui:feature") -> dict:
        d = router.empty()
        for i, (arm, usd, s, rounds, esc) in enumerate(runs):
            d["records"][f"T-{i:03d}#final"] = {"key": f"T-{i:03d}#final", "kind": "task", "context": ctx, "arm": arm,
                                                "rule_arm": "sonnet/medium", "milestone": "M1", "at": f"2026-11-0{1 + i % 9}T00:00:{i:02d}Z",
                                                "usd": usd, "s": s, "rounds": rounds, "escape": esc, "fails": 0}
        return d

    def decide(self, d: dict, rule: str = "sonnet/medium", **kw) -> dict:
        args = {"floor_idx": 0, "fixed": False, "cfg": self.cfg, "milestone": "M2", "spent": 0.0}
        args.update(kw)
        return router.decide(self.dev, d, "task:balanced:ui:feature", rule, **args)

    def test_rule_until_enough_data(self) -> None:
        d = self.data([("sonnet/medium", 1.0, 600, 0, False)] * 2)
        r = self.decide(d)
        self.assertEqual((r["arm"], r["reason_code"]), ("sonnet/medium", "rule"))

    def test_cheaper_arm_wins_without_escapes_and_is_deterministic(self) -> None:
        runs = [("sonnet/medium", 1.0, 900, 0, False)] * 4 + [("haiku/medium", 0.1, 500, 0, False)] * 4
        d = self.data(runs)
        r1, r2 = self.decide(d), self.decide(json.loads(json.dumps(d)))
        self.assertEqual(r1["arm"], "haiku/medium")
        self.assertEqual(r1["reason_code"], "learned")
        self.assertEqual(r1, r2)
        self.assertGreater(r1["saves_usd"], 0)

    def test_escapes_keep_the_rule(self) -> None:
        runs = [("sonnet/medium", 1.0, 900, 0, False)] * 4 + [("haiku/medium", 0.1, 500, 1, True)] * 4
        self.assertEqual(self.decide(self.data(runs))["arm"], "sonnet/medium")

    def test_floor_and_one_tier_bound(self) -> None:
        runs = [("opus/high", 5.0, 900, 0, False)] * 4 + [("sonnet/high", 1.0, 600, 0, False)] * 4 + \
               [("sonnet/medium", 0.5, 500, 0, False)] * 4
        d = self.data(runs)
        self.assertEqual(self.decide(d, rule="opus/high", floor_idx=router.ARM_TIER["opus/high"])["arm"], "opus/high")
        free = self.decide(d, rule="opus/high")
        self.assertEqual(free["arm"], "sonnet/high")  # sonnet/medium is two tiers away: never a candidate
        self.assertNotIn("sonnet/medium", [c["arm"] for c in free["candidates"]])
        self.assertEqual(self.decide(d, rule="opus/high", fixed=True)["reason_code"], "fixed")

    def test_balance_presets_change_the_choice(self) -> None:
        # the cheaper arm is slower: cost-first takes it, speed-first does not
        runs = [("sonnet/medium", 1.0, 600, 0, False)] * 4 + [("haiku/medium", 0.2, 1800, 0, False)] * 4
        d = self.data(runs)
        self.assertEqual(self.decide(d, cfg={**self.cfg, "balance": "cost"})["arm"], "haiku/medium")
        self.assertEqual(self.decide(d, cfg={**self.cfg, "balance": "speed"})["arm"], "sonnet/medium")

    def test_budget_used_picks_the_cheapest_allowed_arm(self) -> None:
        d = self.data([("sonnet/medium", 1.0, 600, 0, False)] * 4)
        r = self.decide(d, cfg={**self.cfg, "budget_usd_per_milestone": 5}, spent=6.0)
        self.assertEqual((r["arm"], r["reason_code"]), ("haiku/medium", "budget"))
        floor = self.decide(d, cfg={**self.cfg, "budget_usd_per_milestone": 5}, spent=6.0, floor_idx=1)
        self.assertEqual(floor["arm"], "sonnet/medium")

    def test_cooldown_blocks_downgrades_and_exploration_is_periodic(self) -> None:
        runs = [("sonnet/medium", 1.0, 900, 0, False)] * 3
        d = self.data(runs)
        r = self.decide(d)
        self.assertEqual((r["arm"], r["explore"]), ("haiku/medium", True))  # 4th eligible run, rule was always fine
        d["contexts"]["task:balanced:ui:feature"] = {"cooldown": 5, "offset": 0, "streak_fail": 0}
        self.assertEqual(self.decide(d)["reason_code"], "cooldown")

    def test_suggest_mode_shows_but_applies_the_rule(self) -> None:
        runs = [("sonnet/medium", 1.0, 900, 0, False)] * 4 + [("haiku/medium", 0.1, 500, 0, False)] * 4
        r = self.decide(self.data(runs), cfg={**self.cfg, "mode": "suggest"})
        self.assertEqual((r["arm"], r["applied_arm"]), ("haiku/medium", "sonnet/medium"))

    def test_learned_offset_raises_a_context_that_keeps_needing_rounds(self) -> None:
        d = self.data([("sonnet/medium", 1.0, 900, 1, False)] * 3)
        router._learn_offsets(d)
        self.assertEqual(d["contexts"]["task:balanced:ui:feature"]["offset"], 1)
        r = self.decide(d)
        self.assertEqual((r["arm"], r["reason_code"]), ("sonnet/high", "learned_up"))

    def test_weights_learn_within_bounds(self) -> None:
        d = router.empty()
        for i in range(6):
            d["records"][f"T-{i}#final"] = {"key": f"T-{i}#final", "kind": "task", "context": "c", "arm": "sonnet/medium",
                                            "rule_arm": "sonnet/medium", "signals": ["integration"], "tier": "balanced",
                                            "escape": i < 4, "rounds": 0}
        for i in range(3):
            d["records"][f"Q-{i}#final"] = {"key": f"Q-{i}#final", "kind": "task", "context": "q", "arm": "opus/high",
                                            "rule_arm": "opus/high", "signals": ["complex", "auth"], "tier": "quality",
                                            "escape": False, "rounds": 0}
        changes = router._learn_weights(d)
        self.assertEqual(d["weights"], {"integration": 2, "complex": -1})  # auth is a floor signal: never down
        self.assertEqual({c["signal"] for c in changes}, {"integration", "complex"})


class TestRouterFastLoop(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init()

    def test_two_failures_in_a_row_raise_the_context_for_the_milestone(self) -> None:
        plan = PLAN.replace("### T-005 Readme", "### T-006 Orders list screen\n- status: todo\n- deps: T-001\n- type: feature\n"
                            "- acceptance:\n  - AC-4: orders\n- test_notes: unit\n- files: src/components/Orders.tsx\n\n### T-005 Readme")
        (self.root / ".dev" / "plan.md").write_text(plan, encoding="utf-8")
        self.ds("sync-plan")
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.ds("start", "T-002")
        self.ds("block", "T-002", "--reason", "env")
        self.ds("start", "T-006", "--force")
        out = self.ds("block", "T-006", "--reason", "env").stdout
        self.assertIn("one tier up", out)
        ctx = self.router_json()["contexts"]["task:balanced:ui:feature"]
        self.assertEqual(ctx["bump"]["milestone"], "M1")

    def test_a_routed_downgrade_that_fails_is_a_mistake_with_cooldown(self) -> None:
        self.ds("start", "T-001")
        st = self.state()
        st["tasks"]["T-001"]["tier"].update({"arm": "haiku/medium", "routed": True})
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.ds("block", "T-001", "--reason", "did not converge")
        data = self.router_json()
        self.assertEqual(data["mistakes"][0]["task"], "T-001")
        self.assertEqual(data["contexts"][data["mistakes"][0]["context"]]["cooldown"], router.COOLDOWN)

    def test_router_off_never_writes(self) -> None:
        self.ds("set", "autonomy.model_policy.router.mode", "off")
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.assertFalse((self.root / ".dev" / "router.json").exists())



class TestAutoTune(unittest.TestCase):
    """Auto-tune: a context that escalation keeps solving starts higher (pure functions on a hand-made router.json)."""
    CTX = "task:balanced:ui:feature"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name)
        self.cfg = {"mode": "apply", "balance": "balanced", "budget_usd_per_milestone": None, "auto_tune": "apply", "max_offset": 1}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add(self, d: dict, tid: str, *, escalated_to: str | None = None, milestone: str = "M1", arm: str = "sonnet/medium",
            tags: list[str] | None = None, at: str | None = None, probe: bool = False, clean: bool = True) -> None:
        at = at or f"2026-11-{10 + int(tid[2:]) % 18:02d}T00:00:00Z"
        base = {"task": tid, "kind": "task", "context": self.CTX, "rule_arm": "sonnet/medium", "milestone": milestone,
                "tags": tags or [], "escape": False, "probe": probe}
        if escalated_to:
            d["records"][f"{tid}#first"] = {**base, "key": f"{tid}#first", "arm": arm, "at": at, "fails": 1, "rounds": 0, "attempt": "first"}
            d["records"][f"{tid}#final"] = {**base, "key": f"{tid}#final", "arm": escalated_to, "at": at, "fails": 0, "rounds": 0,
                                            "attempt": "retry"}
            router.note_escalation(d, tid, self.CTX, arm, escalated_to, milestone, tags or [], solved=True, at=at)
        else:
            d["records"][f"{tid}#final"] = {**base, "key": f"{tid}#final", "arm": arm, "at": at, "rounds": 0 if clean else 1,
                                            "fails": 0, "attempt": "first"}

    def decide(self, d: dict, **kw) -> dict:
        args = {"floor_idx": 0, "fixed": False, "cfg": self.cfg, "milestone": "M3", "spent": 0.0}
        args.update(kw)
        return router.decide(self.dev, d, self.CTX, "sonnet/medium", **args)

    def tuned(self, n_esc: int = 3, n_clean: int = 1) -> dict:
        d = router.empty()
        d["learned"] = ["M1"]
        for i in range(n_esc):
            self.add(d, f"T-{i + 1:03d}", escalated_to="sonnet/high")
        for i in range(n_clean):
            self.add(d, f"T-{i + 50:03d}")
        router._learn_tune(d, milestone="M1")
        return d

    def test_escalation_that_keeps_solving_raises_the_context(self) -> None:
        d = self.tuned()
        t = d["tune"][self.CTX]
        self.assertEqual((t["offset"], t["wins"], t["of"]), (1, 3, 4))
        self.assertEqual(t["evidence"], ["T-001", "T-002", "T-003"])
        r = self.decide(d)
        self.assertEqual((r["arm"], r["reason_code"]), ("sonnet/high", "auto_tune"))
        self.assertIn("auto-tune +1: escalation solved 3 of 4 (T-001, T-002, T-003)", r["reason"])
        self.assertEqual(d["tune_log"][-1]["to"], 1)

    def test_below_the_thresholds_nothing_changes(self) -> None:
        self.assertNotIn(self.CTX, self.tuned(n_esc=2, n_clean=0)["tune"])   # 2 wins < TUNE_MIN
        d = self.tuned(n_esc=3, n_clean=3)                                   # 3 of 6 = 50% < 60%
        self.assertNotIn(self.CTX, d["tune"])
        self.assertNotIn("tune", self.decide(d))

    def test_old_evidence_fades(self) -> None:
        d = self.tuned()
        d["learned"] = [f"M{i}" for i in range(1, 11)]          # nine gates later
        for i in range(3):                                      # three clean first attempts in the latest milestone
            self.add(d, f"T-{i + 80:03d}", milestone="M10")
        router._learn_tune(d, milestone="M10")
        self.assertEqual(d["tune"][self.CTX]["offset"], 0)
        self.assertIn("faded", d["tune_log"][-1]["why"])

    def test_suggest_and_off_modes(self) -> None:
        d = self.tuned()
        r = self.decide(d, cfg={**self.cfg, "auto_tune": "suggest"})
        self.assertNotEqual(r["reason_code"], "auto_tune")
        self.assertTrue(r["tune"]["suggested"])
        line = router.route_line({"final_model": "sonnet", "final_effort": "medium", "route": r})
        self.assertIn("suggests sonnet / high (router.auto_tune suggest)", line)
        off = self.decide(d, cfg={**self.cfg, "auto_tune": "off"})
        self.assertNotEqual(off["reason_code"], "auto_tune")
        self.assertNotIn("tune", off)

    def test_two_tiers_only_with_max_offset_2(self) -> None:
        d = router.empty()
        d["learned"] = ["M1"]
        for i in range(3):
            self.add(d, f"T-{i + 1:03d}", escalated_to="opus/high")
        router._learn_tune(d, max_offset=1, milestone="M1")
        self.assertEqual(d["tune"][self.CTX]["offset"], 1)
        router._learn_tune(d, max_offset=2, milestone="M1")
        self.assertEqual(d["tune"][self.CTX]["offset"], 2)
        self.assertEqual(self.decide(d)["arm"], "sonnet/high")  # the setting caps it at decision time too
        self.assertEqual(self.decide(d, cfg={**self.cfg, "max_offset": 2})["arm"], "opus/high")

    def test_a_tag_with_its_own_evidence_is_tuned_alone(self) -> None:
        d = router.empty()
        d["learned"] = ["M1"]
        for i in range(3):
            self.add(d, f"T-{i + 1:03d}", escalated_to="sonnet/high", tags=["payments"])
        for i in range(4):
            self.add(d, f"T-{i + 50:03d}")
        router._learn_tune(d, milestone="M1")
        self.assertNotIn(self.CTX, [k for k, v in d["tune"].items() if v["offset"]])  # 3 of 7 overall
        self.assertEqual(d["tune"][f"{self.CTX}#tag:payments"]["offset"], 1)
        self.assertEqual(self.decide(d, tags=["Payments"])["reason_code"], "auto_tune")
        self.assertNotIn("tune", self.decide(d))

    def test_clean_runs_up_there_lead_to_one_probe_and_a_clean_probe_undoes(self) -> None:
        d = self.tuned()
        for i in range(router.TUNE_PROBE_AFTER):
            self.add(d, f"T-{i + 20:03d}", arm="sonnet/high", at=f"2026-12-0{1 + i}T00:00:00Z")
        router._learn_tune(d, milestone="M2")
        self.assertTrue(d["tune"][self.CTX]["probe"])
        r = self.decide(d)
        self.assertEqual((r["arm"], r["reason_code"]), ("sonnet/medium", "tune_probe"))
        self.assertEqual(self.decide(d, probed={self.CTX})["reason_code"], "auto_tune")  # one probe at a time
        self.add(d, "T-090", at="2026-12-20T00:00:00Z", probe=True)
        router._learn_tune(d, milestone="M3")
        t = d["tune"][self.CTX]
        self.assertEqual((t["offset"], t["reset_at"]), (0, "2026-12-20T00:00:00Z"))
        self.assertIn("probe T-090 passed", d["tune_log"][-1]["why"])
        router._learn_tune(d, milestone="M3")                  # older evidence no longer counts
        self.assertEqual(d["tune"][self.CTX]["offset"], 0)

    def test_a_failed_probe_keeps_the_tune(self) -> None:
        d = self.tuned()
        for i in range(router.TUNE_PROBE_AFTER):
            self.add(d, f"T-{i + 20:03d}", arm="sonnet/high", at=f"2026-12-0{1 + i}T00:00:00Z")
        self.add(d, "T-091", escalated_to="sonnet/high", at="2026-12-20T00:00:00Z", probe=True)
        router._learn_tune(d, milestone="M3")
        t = d["tune"][self.CTX]
        self.assertEqual((t["offset"], t["clean"], t["probe"]), (1, 0, False))

    def test_untune_by_the_user(self) -> None:
        d = self.tuned()
        router.untune(d, self.CTX)
        self.assertEqual(d["tune"][self.CTX]["offset"], 0)
        router._learn_tune(d, milestone="M1")
        self.assertEqual(d["tune"][self.CTX]["offset"], 0)     # the old escalations are before reset_at
        self.assertNotIn("tune", self.decide(d))
        s = router.tune_summary(d, self.cfg)
        self.assertEqual((s["active"], s["mode"]), ([], "apply"))


class TestAutoTuneFlow(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init(PLAN.replace("- files: src/components/UsersList.tsx", "- files: src/components/UsersList.tsx\n- tags: Payments, ui"))

    def test_tags_reach_the_state(self) -> None:
        self.assertEqual(self.state()["tasks"]["T-002"]["tags"], ["payments", "ui"])

    def test_retry_is_filed_under_the_first_attempt_and_the_gate_records_the_escalation(self) -> None:
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.ds("start", "T-002")
        first_ctx = self.state()["tasks"]["T-002"]["tier"]["context"]
        self.ds("block", "T-002", "--reason", "did not converge")
        self.ds("unblock", "T-002")
        self.ds("start", "T-002")
        tier = self.state()["tasks"]["T-002"]["tier"]
        self.assertEqual((tier["first"]["context"], tier["first"]["arm"]), (first_ctx, "sonnet/medium"))
        self.assertNotEqual(tier["context"], first_ctx)        # the retry runs one tier up
        self.ds("sync-plan")                                    # a re-sync keeps the recorded tier
        self.assertIn("first", self.state()["tasks"]["T-002"]["tier"])
        self.ds("done", "T-002")
        esc = self.router_json()["escalations"]["T-002"]
        self.assertEqual((esc["context"], esc["from"], esc["to"]), (first_ctx, "sonnet/medium", "sonnet/high"))
        for tid in ("T-003", "T-004", "T-005"):
            self.ds("start", tid, "--force")
            self.ds("done", tid, "--force")
        (self.root / ".dev" / "qa" / "M1").mkdir(parents=True, exist_ok=True)
        (self.root / ".dev" / "qa" / "M1" / "findings-round-1.json").write_text('{"round": 1, "findings": []}', encoding="utf-8")
        self.ds("gate", "M1", "passed", "--score", "90")
        recs = self.router_json()["records"]
        self.assertEqual((recs["T-002#first"]["context"], recs["T-002#first"]["fails"]), (first_ctx, 1))
        self.assertEqual((recs["T-002#final"]["context"], recs["T-002#final"]["arm"], recs["T-002#final"]["fails"]),
                         (first_ctx, "sonnet/high", 0))
        self.assertIn("auto-tune apply", self.dr("explain").stdout)

    def test_retry_steps_up_from_the_arm_it_really_ran_on(self) -> None:
        self.ds("start", "T-002", "--force")
        st = self.state()
        st["tasks"]["T-002"]["tier"].update({"arm": "sonnet/high", "routed": True})
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.ds("block", "T-002", "--reason", "did not converge")
        self.ds("unblock", "T-002")
        self.assertEqual(self.tier("T-002")["tier"], "quality")  # above sonnet/high, not just above the balanced rule

    def test_settings_validate_auto_tune(self) -> None:
        self.ds("set", "autonomy.model_policy.router.auto_tune", "suggest")
        self.ds("set", "autonomy.model_policy.router.max_offset", "2")
        self.ds("set", "autonomy.model_policy.router.auto_tune", "maybe", expect=None)
        self.assertEqual(self.state()["autonomy"]["model_policy"]["router"]["auto_tune"], "suggest")
        self.ds("set", "autonomy.model_policy.router.max_offset", "3", expect=None)
        self.assertEqual(self.state()["autonomy"]["model_policy"]["router"]["max_offset"], 2)

    def test_untune_cli(self) -> None:
        self.dr("untune", "task:balanced:ui:feature", expect=1)
        d = router.empty()
        d["tune"] = {"task:balanced:ui:feature": {"offset": 1, "wins": 3, "of": 3, "evidence": ["T-002"]}}
        router.save(self.root / ".dev", d)
        self.assertIn("undone", self.dr("untune", "task:balanced:ui:feature").stdout)
        self.assertEqual(self.router_json()["tune"]["task:balanced:ui:feature"]["offset"], 0)


if __name__ == "__main__":
    unittest.main()
