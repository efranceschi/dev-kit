"""Migration of real dev-kit 2.6.1 projects to 3.0 (state version 2).

The fixtures in fixtures/v2.6.1/ were written by the 2.6.1 scripts themselves (fixtures/v2.6.1/build_fixture_261.py):
- proj-cut-releases: no planned releases, M1 cut as v1.0.0 and M2 as v1.1.0, M3 half done, M4 to do, an open issue
  and a board request in the 2.x R-nnn format;
- proj-planned-releases: R1 released, R2 rejected (fixes milestone), R3 to do;
- proj-maintenance: brownfield maintenance, M7 — Maintenance cut as v2.3.1, M8 — Maintenance open.
Each test copies one to a temporary folder and runs the 3.0 scripts on it.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v2.6.1"
sys.path.insert(0, str(SCRIPTS))


class Base(unittest.TestCase):
    fixture = "proj-cut-releases"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / self.fixture
        shutil.copytree(FIXTURES / self.fixture, self.root)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION")}

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


class TestCutReleases(Base):
    def test_fixture_is_a_2x_project(self) -> None:
        s = self.state()
        self.assertEqual(s["version"], 1)
        self.assertNotIn("release_plan", s)
        self.assertEqual([r["tag"] for r in s["releases"]], ["v1.0.0", "v1.1.0"])

    def test_first_read_backs_up_and_bumps_the_state_version(self) -> None:
        before = (self.dev / "state.json").read_text(encoding="utf-8")
        self.ds("status")  # read only: nothing is written but the backup
        backups = sorted((self.dev / "backup").glob("state-v1-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), before)
        self.assertTrue(list((self.dev / "backup").glob("plan-v1-*.md")))
        self.ds("sync-plan")
        s = self.state()
        self.assertEqual(s["version"], 2)
        self.assertTrue(s["kit_version"].startswith("3."))
        self.ds("status")
        self.assertEqual(len(list((self.dev / "backup").glob("state-v1-*.json"))), 1)  # once

    def test_sync_plan_groups_into_r0_and_r1_keeping_every_2x_version(self) -> None:
        p = self.ds("sync-plan")
        self.assertIn("migrated to planned releases (ADR-001)", p.stdout)
        self.assertIn("Confirm plan holds every milestone not started yet", p.stdout)
        s = self.state()
        self.assertEqual([(r["id"], r["milestones"]) for r in s["release_plan"]], [("R0", ["M1", "M2"]), ("R1", ["M3", "M4"])])
        self.assertEqual(s["release_plan"][1]["title"], "shop")
        self.assertEqual([(r["tag"], r.get("release")) for r in s["releases"]], [("v1.0.0", "R0"), ("v1.1.0", "R0")])
        self.assertEqual(s["release_state"]["R0"]["status"], "released")
        rel = json.loads(self.ds("status", "--json").stdout)["lifecycle"]["releases"]
        self.assertEqual([(r["id"], r["status"]) for r in rel], [("R0", "released"), ("R1", "in_progress")])
        plan = (self.dev / "plan.md").read_text(encoding="utf-8")
        self.assertLess(plan.index("## R0 — Released before 3.0"), plan.index("## M1 — Catalog"))
        self.assertLess(plan.index("## M2 — Cart"), plan.index("## R1 — shop"))
        self.assertLess(plan.index("## R1 — shop"), plan.index("## M3 — Checkout"))
        adr = (self.dev / "decisions.md").read_text(encoding="utf-8")
        self.assertIn("### ADR-001 — Migration to planned releases (auto)", adr)
        self.assertIn("source: auto", adr)
        stale = json.loads(self.ds("status", "--json").stdout)["stale"]["reviews"]
        self.assertTrue(any(r["review"] == "plan" for r in stale))
        self.assertNotIn("migrated", self.ds("sync-plan").stdout)  # once

    def test_exit_check_warnings_only_for_open_milestones(self) -> None:
        out = self.ds("sync-plan").stdout
        self.assertNotIn("M1: no exit_check", out)
        self.assertNotIn("M2: no exit_check", out)
        self.assertIn("M3: no exit_check", out)
        self.assertIn("M4: no exit_check", out)

    def test_annotating_one_milestone_warns_that_checks_are_on_for_all(self) -> None:
        self.ds("sync-plan")
        plan = (self.dev / "plan.md").read_text(encoding="utf-8")
        plan = plan.replace("## M3 — Checkout\nPay.\n", "## M3 — Checkout\nPay.\n- exit_check: cmd: make smoke\n")
        (self.dev / "plan.md").write_text(plan, encoding="utf-8")
        out = self.ds("sync-plan").stdout
        self.assertIn("exit checks are now on for the whole project", out)
        self.assertIn("no exit_check: M4", out)

    def test_gitignore_is_managed_and_keeps_the_users_rules(self) -> None:
        gi = self.dev / ".gitignore"
        gi.write_text(gi.read_text(encoding="utf-8") + "my-notes/\n", encoding="utf-8")
        self.assertIn("updated .dev/.gitignore", self.ds("sync-plan").stdout)
        text = gi.read_text(encoding="utf-8")
        for rule in ("run/", "backup/", "telemetry.jsonl", "tips-seen.json", "costs/*", "!costs/prices.json"):
            self.assertIn(rule + "\n", text)
        self.assertIn("my-notes/\n", text)
        self.assertNotIn("# written by dev_state.py init", text)
        self.assertEqual(text.count("run/\n"), 1)
        import dev_state as dsm
        self.assertEqual(dsm.gitignore_text(text), text)  # idempotent

    def test_no_release_without_approval_after_the_migration(self) -> None:
        self.ds("sync-plan")
        p = self.ds("release-record", "--version", "1.2.0", "--milestones", "M3", expect=1)
        self.assertIn("record R1 with --release R1 after its approval", p.stderr)

    def test_old_board_request_and_open_work_survive(self) -> None:
        self.ds("sync-plan")
        s = self.state()
        self.assertEqual(sum(1 for t in s["tasks"].values() if t["status"] == "done"), 15)
        self.assertEqual(len(s.get("issues") or {}), 1)
        import dev_worker as dw
        self.assertEqual([x["id"] for x in dw.items(self.root)], ["P-001"])
        nxt = json.loads(self.ds("next", "--json").stdout)
        self.assertEqual(nxt["milestone"], "M3")  # the milestone in progress goes on while the plan review is stale

    def test_feedback_shows_no_data_for_milestones_closed_before_3_0(self) -> None:
        self.ds("sync-plan")
        rep = json.loads(self.ds("telemetry", "report", "--json", "--all").stdout)["report"]
        cyc = {c["milestone"]: c for c in rep["cycles"]}
        self.assertTrue(cyc["M1"]["no_data"])
        self.assertIsNone(cyc["M1"]["cycle_grade"])
        self.assertIn("M1: final state 95 · cycle: no data (closed before 3.0)", self.ds("telemetry", "report", "--all").stdout)


class TestPlannedReleases(Base):
    fixture = "proj-planned-releases"

    def test_keeps_its_releases_and_the_rejected_one_goes_on(self) -> None:
        out = self.ds("sync-plan").stdout
        self.assertNotIn("migrated to planned releases", out)
        s = self.state()
        self.assertEqual(s["version"], 2)
        self.assertEqual([r["id"] for r in s["release_plan"]], ["R1", "R2", "R3"])
        rel = {r["id"]: r["status"] for r in json.loads(self.ds("status", "--json").stdout)["lifecycle"]["releases"]}
        self.assertEqual(rel, {"R1": "released", "R2": "in_progress", "R3": "in_progress"})
        fix = next(t for t, v in s["tasks"].items() if v.get("source") == "release:R2")
        self.assertEqual(json.loads(self.ds("next", "--json").stdout)["task"], fix)


class TestMaintenance(Base):
    fixture = "proj-maintenance"

    def test_maintenance_milestones_go_to_a_maintenance_release(self) -> None:
        self.ds("sync-plan")
        s = self.state()
        self.assertEqual([(r["id"], r["title"], r["milestones"]) for r in s["release_plan"]],
                         [("R0", "Released before 3.0", ["M7"]), ("R1", "Maintenance", ["M8"])])
        self.assertEqual(s["releases"][0]["release"], "R0")
        self.ds("start", "T-002")
        self.ds("done", "T-002")
        self.ds("gate", "M8", "passed", "--score", "95")
        self.ds("add-task", "--milestone", "M9", "--milestone-title", "Maintenance", "--title", "Fix", "--type", "fix", "--files", "x.py")
        self.assertEqual(self.state()["milestones"]["M9"]["release"], "R1")


if __name__ == "__main__":
    unittest.main()
