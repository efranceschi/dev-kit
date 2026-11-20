"""Tests for dev_score.py check / normalize (auditor output contract). Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCORE = Path(__file__).resolve().parents[1] / "scripts" / "dev_score.py"


class TestCheck(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
