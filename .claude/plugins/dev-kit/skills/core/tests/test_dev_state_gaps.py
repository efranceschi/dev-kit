"""Regression tests for the 1.12.0 gap review: brownfield onboarding order, maintenance milestones,
autonomy validation and presets, dropped tasks, hotfix reviews, telemetry n/a, stack detection.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_dev_state import DETECT, PLAN, SCORE, Base

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dev_telemetry as tel  # noqa: E402

BF = '{"baseline_ref":"dev-kit-baseline","baseline_sha":"abc1234","mode":"maintenance","first_milestone":7}'


class TestOnboardingOrder(Base):
    def test_event_before_init_is_skipped_not_an_error(self) -> None:
        proc = self.run_state("event", "session_start", "--set", "trigger=start")
        self.assertIn("no state yet", proc.stderr)
        self.assertFalse((self.root / ".dev").exists())

    def test_onboarding_sequence_with_first_milestone(self) -> None:
        # onboarding.md order: init first, then baseline issues, then the maintenance milestone
        self.run_state("init", "--language", "en", "--phase", "interview", "--brownfield-json", BF,
                       "--autonomy-json", '{"commit_style":"{type}: {summary}"}')
        self.assertTrue((self.root / ".dev" / ".gitignore").exists())
        self.run_state("event", "session_start", "--set", "trigger=start", "--set", "brownfield=true", "--set", "mode=maintenance")
        iid = self.run_state("add-issue", "--type", "bug", "--class", "intangible", "--origin", "baseline",
                             "--title", "test_export fails at baseline").stdout.split()[0]
        (self.root / ".dev" / "plan.md").write_text("# Plan\n\n## M7 — Maintenance\n", encoding="utf-8")
        self.run_state("sync-plan")
        self.assertIn("M7", self.state()["milestones"])
        short = self.run_state("status", "--short").stdout
        self.assertIn("existing project: maintenance", short)
        self.assertIn("first milestone M7", self.run_state("status").stdout)
        bl = json.loads(self.run_state("backlog", "--json").stdout)
        self.assertEqual(bl["issues"][iid]["origin"], "baseline")
        self.assertIn("| baseline |", (self.root / ".dev" / "issues.md").read_text(encoding="utf-8"))
        tid = self.run_state("add-task", "--milestone", "M7", "--type", "fix", "--issue", iid, "--title", "Fix export").stdout.split()[0]
        self.run_state("set", "phase", "implement")
        self.run_state("start", tid)
        self.run_state("done", tid, "--commit", "1111111")
        self.assertEqual(self.state()["phase"], "qa")
        self.run_state("gate", "M7", "passed", "--score", "90")
        # a passed gate is closed: new work goes to the next maintenance milestone
        out = self.run_state("add-task", "--milestone", "M7", "--title", "Another bug", "--type", "fix", expect=1)
        self.assertIn("M8", out.stderr)
        self.run_state("add-task", "--milestone", "M8", "--milestone-title", "Maintenance", "--title", "Another bug", "--type", "fix")
        self.run_state("add-task", "--milestone", "M7", "--title", "Hot", "--type", "fix", "--lane", "hotfix")

    def test_first_milestone_is_validated(self) -> None:
        self.run_state("init", "--brownfield-json", '{"first_milestone":0}', expect=1)
        self.run_state("init", "--brownfield-json", '{"first_milestone":"3"}', expect=1)

    def test_maintenance_to_feature_reopens_na_reviews(self) -> None:
        self.run_state("init", "--brownfield-json", BF)
        self.run_state("review", "prd", "n/a", "--note", "maintenance mode")
        self.run_state("review", "plan", "n/a", "--note", "maintenance mode")
        self.run_state("init", "--brownfield-json", '{"mode":"feature"}')
        revs = self.state()["reviews"]
        self.assertEqual(revs["prd"]["verdict"], "pending")
        self.assertEqual(revs["plan"]["verdict"], "pending")


class TestAutonomy(Base):
    def test_unattended_keeps_dirty_tree_ask_in_existing_projects(self) -> None:
        self.run_state("init", "--brownfield-json", BF, "--autonomy-json", '{"level":"unattended"}')
        pp = self.state()["autonomy"]["pause_policy"]
        self.assertEqual(pp["dirty_tree"]["action"], "ask")
        self.assertEqual(pp["credentials"]["action"], "park")
        self.run_state("set", "autonomy.level", "unattended")
        self.assertEqual(self.state()["autonomy"]["pause_policy"]["dirty_tree"]["action"], "ask")
        self.assertIn("dev_tooling", self.state()["autonomy"]["always_ask"])

    def test_greenfield_unattended_and_back(self) -> None:
        self.run_state("init")
        self.run_state("set", "autonomy.level", "unattended")
        a = self.state()["autonomy"]
        self.assertEqual(a["pause_policy"]["dirty_tree"]["action"], "auto_recommend")
        self.assertEqual(a["model_policy"]["mode"], "preapproved")
        self.run_state("set", "autonomy.level", "high")
        a = self.state()["autonomy"]
        self.assertEqual(a["pause_policy"], {})
        self.assertEqual(a["model_policy"]["mode"], "ask")

    def test_cautious_preset_raises_bars_and_lists(self) -> None:
        self.run_state("init", "--autonomy-json", '{"quality":{"min_overall":92}}')
        self.run_state("set", "autonomy.level", "cautious")
        a = self.state()["autonomy"]
        self.assertEqual(a["quality"]["min_overall"], 92)  # never lowered
        self.assertEqual(a["quality"]["dimension_min"]["security"], 95)
        self.assertEqual(a["decide_alone"], ["naming", "file_structure"])
        self.assertIn("library_choice", a["always_ask"])
        self.run_state("set", "autonomy.level", "reckless", expect=1)

    def test_nested_set_merges_and_validates(self) -> None:
        self.run_state("init", "--autonomy-json", '{"quality":{"dimension_min":{"security":95}}}')
        self.run_state("set", "autonomy.quality.min_overall", "90")
        q = self.state()["autonomy"]["quality"]
        self.assertEqual(q["min_overall"], 90)
        self.assertEqual(q["dimension_min"]["security"], 95)
        self.assertNotIn("quality.min_overall", self.state()["autonomy"])
        self.run_state("set", "autonomy.quality", '{"low_cap": 6}')
        q = self.state()["autonomy"]["quality"]
        self.assertEqual((q["low_cap"], q["min_overall"], q["dimension_min"]["security"]), (6, 90, 95))
        self.run_state("set", "autonomy.production.when", "manual", expect=1)  # needs a method
        self.run_state("set", "autonomy.production", '{"when":"manual","method":"systemd"}')
        self.run_state("set", "autonomy.production.when", "on_release")
        self.assertEqual(self.state()["autonomy"]["production"]["method"], "systemd")

    def test_typed_fields(self) -> None:
        self.run_state("init")
        self.run_state("set", "autonomy.may_push", "yes")
        self.assertIs(self.state()["autonomy"]["may_push"], True)
        self.run_state("set", "autonomy.may_push", "maybe", expect=1)
        self.run_state("set", "autonomy.max_fix_rounds_per_gate", "five", expect=1)
        self.run_state("set", "autonomy.max_fix_rounds_per_gate", "4")
        self.assertEqual(self.state()["autonomy"]["max_fix_rounds_per_gate"], 4)
        self.run_state("init", "--autonomy-json", '{"tips":"loud"}', expect=1)
        self.run_state("init", "--autonomy-json", '{"issue_buffer_pct":90}', expect=1)
        self.run_state("init", "--autonomy-json", '{"level":"nope"}', expect=1)


class TestTasks(Base):
    def test_drop_frees_the_milestone(self) -> None:
        self.init_with_plan()
        for t in ("T-001", "T-002"):
            self.run_state("start", t)
            self.run_state("done", t, "--commit", "abc")
        self.run_state("gate", "M1", "passed", "--score", "90")
        self.run_state("drop", "T-003", "--reason", "dropped in replan ADR-009")
        self.assertEqual(self.state()["tasks"]["T-003"]["status"], "dropped")
        self.assertIn("all tasks done", self.run_state("next", expect=3).stdout)
        self.run_state("start", "T-003", expect=1)
        self.run_state("drop", "T-001", "--reason", "x", expect=1)  # done work is not dropped
        self.assertIn("1 dropped", self.run_state("status").stdout)

    def test_done_force_corrects_commit(self) -> None:
        self.init_with_plan()
        self.run_state("start", "T-001")
        self.run_state("done", "T-001", "--commit", "aaaaaaa")
        self.run_state("done", "T-001", "--commit", "bbbbbbb")
        self.assertEqual(self.state()["tasks"]["T-001"]["commit"], "aaaaaaa")
        self.run_state("done", "T-001", "--commit", "bbbbbbb", "--force")
        self.assertEqual(self.state()["tasks"]["T-001"]["commit"], "bbbbbbb")

    def test_hotfix_review_is_recorded_without_touching_the_gate(self) -> None:
        self.init_with_plan()
        self.run_state("review", "hotfix-T-001", "pass", "--score", "90")
        self.assertEqual(self.state()["reviews"]["hotfix-T-001"]["verdict"], "pass")
        self.assertEqual(self.state()["milestones"]["M1"]["gate"], "pending")
        ev = [json.loads(x) for x in (self.root / ".dev" / "telemetry.jsonl").read_text().splitlines()]
        self.assertEqual([e for e in ev if e["event"] == "review"][-1]["scope"], "hotfix-t-001")


class TestScoringAndTelemetry(Base):
    def test_legacy_previous_findings_are_not_rescored(self) -> None:
        prev = self.root / "prev.json"
        prev.write_text(json.dumps({"findings": [
            {"id": "F-001", "severity": "high", "title": "old", "auditor": "code-reviewer", "legacy": True, "file": "a.py"}]}))
        raw = self.root / "code-reviewer.json"
        raw.write_text(json.dumps({"auditor": "code-reviewer", "findings": [], "previous": []}))
        proc = subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", "M1", "--root", str(self.root),
                               "--previous", str(prev), "--round", "2", "--json", str(raw)], capture_output=True, text=True)
        res = json.loads(proc.stdout)
        self.assertEqual(res["dimensions"]["code"]["score"], 100, proc.stdout)

    def test_na_only_stage_is_not_graded(self) -> None:
        events = [{"event": "review", "scope": "design", "value": "na", "ts": "2026-11-19T00:00:00Z"}]
        rep = tel.stage_report(events, {})
        design = next(r for r in rep["stages"] if r["stage"] == "design")
        self.assertFalse(design["ran"])
        self.assertIsNone(rep["overall"])

    def test_feedback_areas_cover_every_skill_stage(self) -> None:
        for area in ("docs", "release", "review", "issue", "test", "board", "start"):
            self.assertIn(area, tel.FEEDBACK_AREAS)
        self.assertEqual(tel.AREA_STAGE["docs"], "docs_release")
        self.assertEqual(tel.scope_stage("T-004"), "qa")


class TestDetection(Base):
    def detect(self) -> dict:
        return json.loads(subprocess.run([sys.executable, "-I", str(DETECT), str(self.root)], capture_output=True, text=True).stdout)

    def test_setup_py_only_is_existing(self) -> None:
        (self.root / "setup.py").write_text("from setuptools import setup\n")
        self.assertFalse(self.detect()["greenfield"])

    def test_plain_sources_are_existing(self) -> None:
        (self.root / "www").mkdir()
        (self.root / "www" / "index.php").write_text("<?php echo 1;")
        self.assertFalse(self.detect()["greenfield"])

    def test_monorepo_manifest_in_subfolder(self) -> None:
        (self.root / "apps" / "web").mkdir(parents=True)
        (self.root / "apps" / "web" / "package.json").write_text("{}")
        d = self.detect()
        self.assertFalse(d["greenfield"])
        self.assertTrue(any("monorepo" in n for n in d["notes"]))

    def test_empty_dir_is_greenfield(self) -> None:
        (self.root / "README.md").write_text("# idea\n")
        self.assertTrue(self.detect()["greenfield"])


class TestFixTasks(Base):
    def test_blockers_become_fix_tasks_once(self) -> None:
        self.init_with_plan()
        f = self.root / ".dev" / "qa" / "M1" / "findings.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"findings": [
            {"id": "F-001", "severity": "high", "title": "Login accepts empty password", "file": "src/a.py",
             "recommendation": "reject empty password with 422", "acceptance_ref": "AC-2", "auditor": "code-reviewer"},
            {"id": "F-002", "severity": "medium", "title": "Long function", "file": "src/b.py", "auditor": "code-reviewer"},
            {"id": "F-003", "severity": "medium", "title": "Weak test", "file": "tests/t.py", "auditor": "test-auditor"},
            {"id": "F-004", "severity": "critical", "title": "Old debt", "legacy": True, "auditor": "security-auditor"},
        ]}), encoding="utf-8")
        out = json.loads(self.run_state("fix-tasks", "--from", ".dev/qa/M1/findings.json", "--milestone", "M1",
                                        "--include", "F-003", "--json").stdout)
        self.assertEqual(len(out["created"]), 2)
        tasks = {t["source"]: t for t in self.state()["tasks"].values() if t.get("type") == "fix"}
        t1 = tasks["qa/M1/report.md#F-001"]
        self.assertEqual(t1["files"], ["src/a.py"])
        self.assertIn("AC-2 met", t1["acceptance"])
        self.assertTrue(any(x.startswith("F-001 resolved: reject empty password") for x in t1["acceptance"]))
        self.assertIn("qa/M1/report.md#F-003", tasks)
        again = json.loads(self.run_state("fix-tasks", "--from", ".dev/qa/M1/findings.json", "--milestone", "M1",
                                          "--include", "F-003", "--json").stdout)
        self.assertEqual((again["created"], sorted(again["skipped"])), ([], ["F-001", "F-003"]))


class TestArtifactsAndXref(Base):
    def setup_docs(self) -> Path:
        self.init_with_plan()
        dev = self.root / ".dev"
        (dev / "brief.md").write_text("# Brief\n- date: 2026-11-01\nlogin and dashboard\n", encoding="utf-8")
        (dev / "prd.md").write_text("# PRD\n- status: draft\n- AC-0: lint green\n- AC-1: inline error\n- AC-2: redirect\n"
                                    "- AC-3: dashboard (ADR-002)\n- AC-4: chart\n- AC-5: export\n"
                                    "- AC-6: old flow (superseded by ADR-001)\n", encoding="utf-8")
        (dev / "architecture.md").write_text("# Architecture\npostgres\n", encoding="utf-8")
        (dev / "decisions.md").write_text("# Decisions\n\n### ADR-001 — Drop old flow\n", encoding="utf-8")
        return dev

    def test_prd_change_makes_downstream_stale_until_marked(self) -> None:
        dev = self.setup_docs()
        self.assertIn("not tracked yet", self.run_state("stale").stdout)
        self.run_state("artifact", "mark", "all")
        self.run_state("review", "plan", "pass", "--score", "90")
        self.assertEqual(json.loads(self.run_state("stale", "--json").stdout)["stale"], [])
        # header-only change (status/date) is not a change
        (dev / "prd.md").write_text((dev / "prd.md").read_text().replace("status: draft", "status: approved"), encoding="utf-8")
        self.assertEqual(json.loads(self.run_state("stale", "--json").stdout)["stale"], [])
        (dev / "prd.md").write_text((dev / "prd.md").read_text() + "- AC-7: new rule\n", encoding="utf-8")
        rep = json.loads(self.run_state("stale", "--json").stdout)
        self.assertEqual([x["artifact"] for x in rep["stale"]], ["architecture", "plan"])
        self.assertIn("architecture is stale", rep["stale"][1]["because"])
        self.run_state("stale", "--strict", expect=1)
        self.assertIn("[dev-kit] stale: architecture, plan", self.run_state("status", "--short").stdout)
        self.run_state("artifact", "mark", "architecture", "--note", "no impact: new AC is UI only")
        rep = json.loads(self.run_state("stale", "--json").stdout)
        self.assertEqual([x["artifact"] for x in rep["stale"]], ["plan"])
        self.assertEqual(self.state()["artifacts"]["architecture"]["note"], "no impact: new AC is UI only")
        (dev / "plan.md").write_text((dev / "plan.md").read_text() + "\n<!-- replanned -->\n", encoding="utf-8")
        self.run_state("artifact", "mark", "plan")
        rep = json.loads(self.run_state("stale", "--json").stdout)
        self.assertEqual(rep["stale"], [])
        self.assertEqual([r["review"] for r in rep["reviews"]], ["plan"])   # passed on the old plan

    def test_xref_finds_cross_document_gaps(self) -> None:
        self.setup_docs()
        rep = json.loads(self.run_state("xref", "--json").stdout)
        got = {(x["check"], x["id"]) for x in rep["problems"]}
        self.assertIn(("ac_unplanned", "AC-5"), got)
        self.assertNotIn(("ac_unplanned", "AC-6"), got)      # superseded
        self.assertIn(("adr_unknown", "ADR-002"), got)
        self.assertNotIn(("adr_unknown", "ADR-001"), got)
        self.run_state("xref", "--strict", expect=1)
        dev = self.root / ".dev"
        (dev / "design").mkdir()
        (dev / "design" / "ux-flows.md").write_text("| id | name | tag |\n|---|---|---|\n| S-01 | Login | new |\n"
                                                    "| S-02 | Home | new |\n| S-03 | Legacy | existing |\n", encoding="utf-8")
        (dev / "design" / "ui-spec.md").write_text("## 5. Screen specs\n### S-01 — Login\n### S-09 — Ghost\n", encoding="utf-8")
        got = {(x["check"], x["id"]) for x in json.loads(self.run_state("xref", "--json").stdout)["problems"]}
        self.assertIn(("screen_unspecified", "S-02"), got)
        self.assertNotIn(("screen_unspecified", "S-03"), got)
        self.assertIn(("screen_unknown", "S-09"), got)


if __name__ == "__main__":
    unittest.main()
