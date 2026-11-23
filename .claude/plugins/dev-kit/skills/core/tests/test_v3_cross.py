"""dev-kit 3.0, cross-cutting changes: every autonomy key is exposed in /dev-kit:settings, the lint rejects a skill
that measures time or agents by hand, and conventions §21 holds the release flags and the production health check.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
KIT = CORE.parents[1]
sys.path.insert(0, str(CORE / "scripts"))


class TestSettingsCoverage(unittest.TestCase):
    def test_every_autonomy_key_is_in_settings(self) -> None:
        import dev_state as ds
        text = (KIT / "skills" / "settings" / "SKILL.md").read_text(encoding="utf-8")
        missing = [k for k in ds.DEFAULT_AUTONOMY if f"autonomy.{k}" not in text and f"`{k}`" not in text]
        self.assertEqual(missing, [])
        for sub in ("autonomy.production.health", "autonomy.quality.hard_floor", "deferred_cap", "per_milestone_flagged"):
            self.assertIn(sub, text)


class TestLintManualMeasuring(unittest.TestCase):
    def lint(self, line: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "dev-kit"
            shutil.copytree(KIT, dst, ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
            sk = dst / "skills" / "status" / "SKILL.md"
            sk.write_text(sk.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")
            return subprocess.run([sys.executable, "-I", str(dst / "skills" / "core" / "tests" / "lint_suite.py"), "--claude-dir", str(dst)],
                                  capture_output=True, text=True, timeout=300)

    def test_manual_measuring_is_an_error(self) -> None:
        for bad in ("Note the start time before you spawn the auditors.", "Record how long each agent took.",
                    "Count the agents you spawned and log it.", "Log `agent_spawn` for each auditor."):
            with self.subTest(bad=bad):
                p = self.lint(bad)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn("skills do not measure time or agents", p.stdout)

    def test_the_kit_is_clean(self) -> None:
        p = self.lint("Run the next step.")
        self.assertEqual(p.returncode, 0, p.stdout)


class TestConventions21(unittest.TestCase):
    def test_section_21_holds_flags_and_health(self) -> None:
        text = (CORE / "shared" / "conventions.md").read_text(encoding="utf-8")
        sec = text.split("## 21. ", 1)[1]
        for word in ("release_R<n>", "per_milestone_flagged", "flag set release_R<n> off --rollback", "Remove flag release_R<n>",
                     "prod-check", "expedite"):
            self.assertIn(word, sec)
        self.assertEqual(re.findall(r"^## (\d+)\.", text, re.M)[-1], "21")


if __name__ == "__main__":
    unittest.main()
