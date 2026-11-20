"""Tests for the work ledger (dev_state.py ledger, dev_ledger.py). Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "scripts" / "dev_state.py"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ds("init", "--project", "demo")
        for i in range(10):
            self.write(f"src/m{i}.py", f"x = {i}\n")
        self.write("checklist.md", "- check things\n")
        self.files = ",".join(f"src/m{i}.py" for i in range(10))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def ds(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                              capture_output=True, text=True, cwd=self.root)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=f"{args}\n{proc.stdout}\n{proc.stderr}")
        return proc

    def plan(self, *extra: str) -> dict:
        return json.loads(self.ds("ledger", "plan", "--prefix", "audit:code", "--files", self.files,
                                  "--context", "checklist.md", "--seed", "r2", "--json", *extra).stdout)

    def record(self, findings: list[dict] | None = None) -> None:
        raw = self.root / "raw.json"
        raw.write_text(json.dumps({"auditor": "code-reviewer", "findings": findings or []}), encoding="utf-8")
        self.ds("ledger", "record", "--prefix", "audit:code", "--files", self.files, "--context", "checklist.md",
                "--findings-from", str(raw))


class TestAuditPlan(Base):
    def test_never_reviewed_then_incremental_with_spot_check(self) -> None:
        first = self.plan()
        self.assertEqual(len(first["never"]), 10)                       # full coverage on round 1
        self.record([{"id": "F-001", "severity": "high", "file": "src/m3.py", "line": 1}])
        self.write("src/m7.py", "x = 70\n")
        res = self.plan()
        why = {x["unit"]: x["why"] for x in res["review"]}
        self.assertEqual(why["src/m7.py"], "inputs changed")
        self.assertEqual(why["src/m3.py"], "last result findings")     # findings never close from the cache
        self.assertEqual(len(res["spot"]), 1)                           # 10% of 8 reusable, at least one
        self.assertEqual(len(res["reuse"]), 7)
        self.assertEqual(res, self.plan())                              # seeded: same sample for the same round

    def test_context_salt_shared_and_no_cache_invalidate(self) -> None:
        self.record()
        self.assertEqual(len(self.plan("--spot-pct", "0")["review"]), 0)
        self.write("checklist.md", "- check more things\n")             # checklist changed: whole dimension
        self.assertEqual(len(self.plan("--spot-pct", "0")["review"]), 10)
        self.record()
        self.assertEqual(len(self.plan("--spot-pct", "0", "--salt", "tier:opus")["review"]), 10)
        self.assertTrue(all(x["why"] == "no-cache" for x in self.plan("--no-cache")["review"]))
        self.write("src/shared.py", "A = 1\n")
        self.ds("ledger", "record", "--prefix", "audit:code", "--files", self.files, "--context", "checklist.md",
                "--shared", "src/shared.py")
        self.assertEqual(len(self.plan("--spot-pct", "0", "--shared", "src/shared.py")["review"]), 0)
        self.write("src/shared.py", "A = 2\n")
        self.assertEqual(len(self.plan("--spot-pct", "0", "--shared", "src/shared.py")["review"]), 10)

    def test_drop_and_disabled_setting(self) -> None:
        self.record()
        self.ds("ledger", "drop", "--prefix", "audit:code:")
        self.assertEqual(len(self.plan()["never"]), 10)
        self.record()
        self.ds("set", "autonomy.incremental.enabled", "false")
        self.assertEqual(len(self.plan()["review"]), 10)

    def test_put_check_get(self) -> None:
        self.write("package-lock.json", "{}\n")
        self.ds("ledger", "check", "deps:package-lock.json", "--files", "package-lock.json", expect=3)
        self.ds("ledger", "put", "deps:package-lock.json", "--files", "package-lock.json", "--result", "ok", "--ref", ".dev/qa/M1/raw/deps-auditor.json")
        self.ds("ledger", "check", "deps:package-lock.json", "--files", "package-lock.json")
        self.assertEqual(json.loads(self.ds("ledger", "get", "deps:package-lock.json").stdout)["ref"], ".dev/qa/M1/raw/deps-auditor.json")
        self.write("package-lock.json", "{\"a\": 1}\n")
        self.ds("ledger", "check", "deps:package-lock.json", "--files", "package-lock.json", expect=3)
        self.ds("ledger", "put", "task:T-004", "--result", "failed", "--note", "migration conflicts with T-003", "--ref", "dev-kit/T-004")
        self.assertEqual(json.loads(self.ds("ledger", "get", "task:T-004").stdout)["result"], "failed")


class TestScreenUnits(Base):
    def test_screen_unit_follows_its_route_files(self) -> None:
        units = "S-01=src/m1.py+src/m2.py,S-02=src/m3.py"
        raw = self.root / "v.json"
        raw.write_text(json.dumps({"auditor": "visual-reviewer", "findings": [{"id": "F-1", "severity": "medium", "file": "S-02"}]}))
        self.ds("ledger", "record", "--prefix", "shot", "--files", units, "--findings-from", str(raw))
        self.write("src/m2.py", "x = 22\n")
        res = json.loads(self.ds("ledger", "plan", "--prefix", "shot", "--files", units, "--spot-pct", "0", "--json").stdout)
        self.assertEqual({x["unit"]: x["why"] for x in res["review"]}, {"S-01": "inputs changed", "S-02": "last result findings"})


class TestSections(Base):
    PRD = ("# PRD\n- status: draft\n\n## 1. Problem\nUsers lose data.\n\n## 2. Stories\n### US-1 Login\n- AC-1: inline error\n"
           "- AC-2: redirect\n\n### US-2 Reports\n- AC-3: report uses AC-1 rules\n\n## 3. NFR\nfast within 200 ms\n")

    def test_changed_sections_and_their_citers(self) -> None:
        self.write(".dev/prd.md", self.PRD)
        first = json.loads(self.ds("ledger", "sections", "--target", "prd", "--json").stdout)
        self.assertEqual(len(first["review"]), first["sections"])
        f = self.root / "f.json"
        f.write_text(json.dumps({"findings": [{"id": "F-1", "severity": "medium", "file": "prd.md", "line": 5}]}), encoding="utf-8")
        self.ds("ledger", "record-sections", "--target", "prd", "--findings-from", str(f))
        self.write(".dev/prd.md", self.PRD.replace("AC-1: inline error", "AC-1: inline error under the field").replace("draft", "approved"))
        res = json.loads(self.ds("ledger", "sections", "--target", "prd", "--spot-pct", "0", "--json").stdout)
        why = {x["section"]: x["why"] for x in res["review"]}
        self.assertEqual(why["2. Stories > US-1 Login"], "text or context changed")
        self.assertIn("cites changed AC-1", why["2. Stories > US-2 Reports"])
        self.assertEqual(why["1. Problem"], "last result findings")
        self.assertNotIn("3. NFR", why)
        self.assertNotIn("(preamble)", why)                              # status change only


class TestBatchAndBrief(Base):
    PLAN = """# Plan

## M1 — One
Goal.

### T-001 Scaffold
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-0: green
- test_notes: smoke
- files: package.json

### T-002 Login
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-1: inline error
- test_notes: unit
- files: src/login.ts

### T-003 Profile
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-2: edit name
- test_notes: unit
- files: src/profile.ts

### T-004 Login copy
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-3: copy
- test_notes: unit
- files: src/login.ts

### T-005 Add table
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-4: table
- test_notes: unit
- files: migrations/0002.sql
"""

    def test_batch_skips_overlaps_and_serialising_files(self) -> None:
        (self.root / ".dev" / "plan.md").write_text(self.PLAN, encoding="utf-8")
        self.ds("sync-plan")
        got = [t["task"] for t in json.loads(self.ds("next", "--batch", "5", "--json").stdout)["tasks"]]
        self.assertEqual(got, ["T-001", "T-002", "T-003"])   # T-004 overlaps T-002; T-005 is a second serial task
        self.assertEqual(len(json.loads(self.ds("next", "--batch", "2", "--json").stdout)["tasks"]), 2)

    def test_brief_has_languages_commands_rule_and_history(self) -> None:
        (self.root / ".dev" / "plan.md").write_text(self.PLAN, encoding="utf-8")
        self.ds("sync-plan")
        self.ds("set", "language", "pt-BR")
        (self.root / ".dev" / "brief.md").write_text("# Brief\n- Application language: pt-BR (Brazil)\n", encoding="utf-8")
        (self.root / ".dev" / "architecture.md").write_text("## 8. Testing\n| Purpose | Command |\n|---|---|\n| test (full suite) | pytest |\n| lint | ruff check |\n\n## 9. Open\n", encoding="utf-8")
        self.ds("ledger", "put", "task:T-002", "--result", "failed", "--note", "fixture missing", "--ref", "dev-kit/T-002")
        out = self.ds("brief", "T-002").stdout
        self.assertIn("Language for prose (report): pt-BR · application language (UI copy): pt-BR (Brazil)", out)
        self.assertIn("  - test (full suite): pytest", out)
        self.assertIn("only the integration tests", out)
        self.assertIn("Previous attempt (failed", out)
        self.assertIn("dev-kit/T-002", out)


if __name__ == "__main__":
    unittest.main()
