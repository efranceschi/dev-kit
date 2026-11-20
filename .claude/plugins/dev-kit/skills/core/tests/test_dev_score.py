"""Tests for dev_score.py check / normalize (auditor output contract). Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCORE = Path(__file__).resolve().parents[1] / "scripts" / "dev_score.py"


class Helpers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def sc(self, *args: str, expect: int | None = None) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, "-I", str(SCORE), *args], capture_output=True, text=True, cwd=self.root)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=proc.stdout + proc.stderr)
        return proc

    def write(self, name: str, data: object) -> Path:
        p = self.root / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p


class TestCheck(Helpers):

    def test_normalises_drift_and_writes_back(self) -> None:
        p = self.write("code-reviewer.json", {
            "findings": [{"severity": "Major", "title": "a"}, {"id": "F-001", "severity": "nit", "title": "b"},
                         {"id": "F-001", "severity": "MODERATE", "title": "c"}],
            "previous": [{"id": "F-007", "status": "fixed"}, {"id": "F-008", "status": "still open"},
                         {"id": "F-009", "state": "maybe"}],
            "verdict": "fail"})
        out = self.sc("check", "--fix", str(p), expect=0).stdout
        self.assertIn("normalised (written)", out)
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["auditor"], "code-reviewer")                       # from the file name
        self.assertEqual([f["severity"] for f in data["findings"]], ["high", "low", "medium"])
        ids = [f["id"] for f in data["findings"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual([p["state"] for p in data["previous"]], ["closed", "open", "open"])
        self.assertNotIn("status", data["previous"][0])
        self.assertTrue(data["_normalized"])
        self.sc("check", str(p), expect=0)                                       # idempotent and now clean

    def test_errors_the_agent_must_fix(self) -> None:
        a = self.write("x.json", {"auditor": "code-reviewer", "findings": [{"severity": "spicy"}]})
        b = self.write("y.json", {"auditor": "nobody", "findings": []})
        c = self.write("z.json", {"auditor": "spec-tracer"})
        d = self.write("w.json", "not json at all")
        out = self.sc("check", str(a), str(b), str(c), str(d), expect=1).stdout
        self.assertIn("severity 'spicy'", out)
        self.assertIn("unknown auditor 'nobody'", out)
        self.assertIn("missing 'findings' list", out)
        self.assertIn("invalid JSON", out)

    def test_json_block_inside_prose_is_extracted(self) -> None:
        p = self.write("security-auditor.json",
                       "Summary line.\n\n```json\n{\"auditor\": \"security-auditor\", \"findings\": []}\n```\n")
        self.sc("check", "--fix", str(p), expect=0)
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["auditor"], "security-auditor")

    def test_score_uses_normalisation_and_rejects_unknown_severity(self) -> None:
        good = self.write("a.json", {"auditor": "code-reviewer", "findings": [{"id": "F-1", "severity": "Blocker", "title": "t"}]})
        self.sc("score", "--scope", "M1", "--root", str(self.root), "--json", str(good), expect=1)
        res = json.loads((self.root / "scores.json").read_text(encoding="utf-8"))
        self.assertEqual(res["dimensions"]["code"]["counts"]["critical"], 1)    # not silently "low"
        bad = self.write("b.json", {"auditor": "code-reviewer", "findings": [{"id": "F-1", "severity": "??", "title": "t"}]})
        self.sc("score", "--scope", "M1", "--root", str(self.root), str(bad), expect=1)
        res = json.loads((self.root / "scores.json").read_text(encoding="utf-8"))
        self.assertTrue(any("severity" in r for r in res["reasons"]))

    def test_previous_status_counts_as_closed_in_delta(self) -> None:
        prev = self.write("prev.json", {"findings": [{"id": "F-001", "severity": "high", "title": "old", "file": "a.py",
                                                      "line": 1, "auditor": "code-reviewer"}]})
        cur = self.write("code-reviewer.json", {"auditor": "code-reviewer", "findings": [],
                                                "previous": [{"id": "F-001", "status": "resolved"}]})
        self.sc("score", "--scope", "M1", "--root", str(self.root), "--previous", str(prev), str(cur), expect=0)
        self.assertEqual(json.loads((self.root / "scores.json").read_text(encoding="utf-8"))["delta"]["closed"], 1)


class TestDeltaRevision(Helpers):
    def prev(self, findings: list[dict]) -> Path:
        return self.write("prev.json", {"findings": findings})

    def score(self, prev: Path, cur: Path, expect: int | None = None) -> dict:
        self.sc("score", "--scope", "prd", "--kind", "review", "--root", str(self.root), "--previous", str(prev), str(cur), expect=expect)
        return json.loads((self.root / "scores.json").read_text(encoding="utf-8"))

    def test_findings_outside_the_change_are_deferred(self) -> None:
        prev = self.prev([{"id": "F-001", "severity": "medium", "title": "a", "file": "prd.md", "line": 3, "auditor": "requirements-reviewer"},
                          {"id": "F-002", "severity": "medium", "title": "b", "file": "prd.md", "line": 9, "auditor": "requirements-reviewer"}])
        cur = self.write("requirements-reviewer.json", {"auditor": "requirements-reviewer", "findings": [
            {"id": "F-010", "severity": "high", "title": "old section gap", "file": "prd.md", "line": 50, "in_change": False},
            {"id": "F-011", "severity": "critical", "title": "data loss", "file": "prd.md", "line": 60, "in_change": False},
            {"id": "F-012", "severity": "medium", "title": "new text vague", "file": "prd.md", "line": 4, "in_change": True}],
            "previous": [{"id": "F-001", "state": "closed"}, {"id": "F-002", "state": "closed"}]})
        res = self.score(prev, cur, expect=1)
        self.assertEqual(res["delta"]["new_outside_change"], 1)              # the high outside the change
        self.assertEqual(res["dimensions"]["requirements"]["counts"]["critical"], 1)   # critical always scores
        self.assertEqual(res["convergence"]["mediums_prev"], 2)
        self.assertEqual(res["convergence"]["mediums"], 1)
        self.assertEqual(res["convergence"]["trend"], "falling")
        self.assertFalse(res["convergence"]["converged"])                    # the critical blocks

    def test_converged_and_contradictions_capped(self) -> None:
        prev = self.prev([{"id": "F-001", "severity": "medium", "title": "a", "file": "prd.md", "line": 3, "auditor": "requirements-reviewer"}])
        cur = self.write("requirements-reviewer.json", {"auditor": "requirements-reviewer", "findings": [
            {"id": "F-020", "severity": "high", "title": "first_seen rule regresses", "file": "prd.md", "line": 8,
             "contradicts": "F-001"}],
            "previous": [{"id": "F-001", "state": "closed"}]})
        res = self.score(prev, cur)
        self.assertEqual(res["blockers"], [])
        self.assertEqual(res["conflicts"][0]["contradicts"], "F-001")
        self.assertEqual(res["convergence"]["trend"], "flat")
        self.assertTrue(res["convergence"]["converged"])


class TestConsolidateAndSelect(Helpers):
    def test_round_ids_are_stable_and_deferred_apart(self) -> None:
        a = self.write("code-reviewer.json", {"auditor": "code-reviewer", "findings": [
            {"id": "X1", "severity": "high", "title": "null deref", "file": "src/a.py", "line": 3},
            {"id": "X2", "severity": "low", "title": "naming", "file": "src/b.py", "line": 9}]})
        b = self.write("security-auditor.json", {"auditor": "security-auditor", "findings": [
            {"id": "S1", "severity": "critical", "title": "sql injection", "file": "src/a.py", "line": 3}]})
        self.sc("consolidate", "--scope", "M1", "--round", "1", "--out-dir", str(self.root / "qa"), "--root", str(self.root), str(a), str(b), expect=0)
        r1 = json.loads((self.root / "qa" / "findings-round-1.json").read_text(encoding="utf-8"))
        self.assertEqual([f["id"] for f in r1["findings"]], ["F-001", "F-002", "F-003"])
        self.assertEqual(r1["findings"][0]["severity"], "critical")             # most severe first
        self.assertEqual(r1["findings"][0]["same_as"], ["F-002"])                # same line, other dimension
        a2 = self.write("code-reviewer.json", {"auditor": "code-reviewer", "findings": [
            {"id": "N1", "severity": "medium", "title": "new issue", "file": "src/c.py", "line": 1},
            {"id": "N2", "severity": "low", "title": "nit", "file": "src/c.py", "line": 2}],
            "previous": [{"id": "F-002", "state": "closed"}, {"id": "F-003", "state": "open"}]})
        b2 = self.write("security-auditor.json", {"auditor": "security-auditor", "findings": [], "carried": True})
        self.sc("consolidate", "--scope", "M1", "--round", "2", "--out-dir", str(self.root / "qa"), "--root", str(self.root),
                "--previous", str(self.root / "qa" / "findings-round-1.json"), str(a2), str(b2), expect=0)
        r2 = json.loads((self.root / "qa" / "findings.json").read_text(encoding="utf-8"))
        ids = {f["id"]: f for f in r2["findings"]}
        self.assertIn("F-001", ids)                                             # carried dimension: still open
        self.assertIn("F-003", ids)                                             # open low keeps its id
        self.assertNotIn("F-002", ids)                                          # closed
        self.assertIn("F-004", ids)                                             # the new medium, next free id
        self.assertEqual([d["original_id"] for d in r2["deferred"]], ["N2"])
        self.assertEqual(r2["carried"], ["security-auditor"])

    def test_select_reruns_only_what_has_work(self) -> None:
        prev = self.write("prev.json", {"findings": [{"id": "F-001", "severity": "high", "title": "t", "auditor": "copy-reviewer"}]})
        changed = self.root / "changed.txt"
        changed.write_text("src/api/users.py\nmigrations/0003_add.sql\nREADME.md\n", encoding="utf-8")
        out = json.loads(self.sc("select", "--previous", str(prev), "--changed-from", str(changed), "--json", "--auditors",
                                 "code-reviewer,copy-reviewer,data-reviewer,deps-auditor,ops-reviewer,visual-reviewer,docs-reviewer", expect=0).stdout)
        rerun = {x["auditor"]: x["why"] for x in out["rerun"]}
        self.assertEqual(set(rerun), {"code-reviewer", "copy-reviewer", "data-reviewer", "docs-reviewer"})
        self.assertIn("open finding", rerun["copy-reviewer"])
        self.assertEqual(set(out["carry"]), {"deps-auditor", "ops-reviewer", "visual-reviewer"})


if __name__ == "__main__":
    unittest.main()
