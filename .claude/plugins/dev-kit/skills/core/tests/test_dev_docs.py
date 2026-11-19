"""Tests for dev_docs.py (generated docs, catalog check, help answers) and the English-only lint.
Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
DOCS_PY = "skills/core/scripts/dev_docs.py"
LINT = "skills/core/tests/lint_suite.py"


class KitCopy(unittest.TestCase):
    """Every test works on a copy of the plugin, so nothing in the real kit changes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.kit = Path(self.tmp.name) / "dev-kit"
        shutil.copytree(KIT, self.kit, ignore=shutil.ignore_patterns("__pycache__", "*.png", "*.svg"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_py(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(self.kit / script), *args], capture_output=True, text=True)

    def catalog(self) -> dict:
        return json.loads((self.kit / "skills/core/shared/help.json").read_text(encoding="utf-8"))

    def save_catalog(self, cat: dict) -> None:
        (self.kit / "skills/core/shared/help.json").write_text(json.dumps(cat, indent=2), encoding="utf-8")


class TestDocs(KitCopy):
    def test_real_kit_is_in_sync(self) -> None:
        res = subprocess.run([sys.executable, "-I", str(KIT / DOCS_PY), "check"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_build_covers_every_skill_and_agent(self) -> None:
        self.assertEqual(self.run_py(DOCS_PY, "build").returncode, 0)
        skills_md = (self.kit / "docs/skills.md").read_text(encoding="utf-8")
        agents_md = (self.kit / "docs/agents.md").read_text(encoding="utf-8")
        for p in (self.kit / "skills").glob("*/SKILL.md"):
            if p.parent.name != "core":
                self.assertIn(f"### {p.parent.name}\n", skills_md)
        for p in (self.kit / "agents").glob("*.md"):
            self.assertIn(f"| `{p.stem}` |", agents_md)
        self.assertIn("Do not edit by hand", skills_md)

    def test_check_fails_on_missing_skill_and_hand_edits(self) -> None:
        cat = self.catalog()
        cat["skills"] = [s for s in cat["skills"] if s["name"] != "costs"]
        self.save_catalog(cat)
        out = self.run_py(DOCS_PY, "check")
        self.assertEqual(out.returncode, 1)
        self.assertIn("skill 'costs' has no entry in help.json", out.stdout)
        shutil.copy(KIT / "skills/core/shared/help.json", self.kit / "skills/core/shared/help.json")
        self.run_py(DOCS_PY, "build")
        with (self.kit / "docs/skills.md").open("a", encoding="utf-8") as f:
            f.write("hand edit\n")
        out = self.run_py(DOCS_PY, "check")
        self.assertIn("docs/skills.md is stale", out.stdout)

    def test_check_catches_wrong_caller_and_example(self) -> None:
        cat = self.catalog()
        cat["agents_called_by"]["code-reviewer"] = ["qa", "costs"]
        cat["skills"][0]["examples"][0]["command"] = "/dev-kit:other thing"
        self.save_catalog(cat)
        out = self.run_py(DOCS_PY, "check").stdout
        self.assertIn("skill 'costs' never mentions agent 'code-reviewer'", out)
        self.assertIn("does not use /dev-kit:", out)

    def test_help_answers(self) -> None:
        card = json.loads(self.run_py(DOCS_PY, "help", "issue", "--json").stdout)
        self.assertEqual(card["kind"], "skill")
        self.assertGreaterEqual(len(card["examples"]), 2)
        bug = json.loads(self.run_py(DOCS_PY, "help", "I", "found", "a", "bug", "--json").stdout)
        self.assertEqual((bug["kind"], bug["id"]), ("recipe", "bug"))
        night = json.loads(self.run_py(DOCS_PY, "help", "can", "it", "run", "overnight?", "--json").stdout)
        self.assertEqual(night["id"], "overnight")
        term = json.loads(self.run_py(DOCS_PY, "help", "gate", "--json").stdout)
        self.assertEqual(term["kind"], "term")
        self.assertEqual(json.loads(self.run_py(DOCS_PY, "help", "--json").stdout)["kind"], "map")
        self.assertEqual(json.loads(self.run_py(DOCS_PY, "help", "agents", "--json").stdout)["kind"], "agents")


class TestEnglishOnly(KitCopy):
    def test_lint_rejects_portuguese_and_respects_allowlist(self) -> None:
        self.assertEqual(self.run_py(LINT).returncode, 0, self.run_py(LINT).stdout)
        (self.kit / "skills/core/shared/note.md").write_text("Este passo n\u00e3o pode falhar.\n", encoding="utf-8")  # Portuguese bait, escaped
        (self.kit / "agents/architect.md").write_text(
            (self.kit / "agents/architect.md").read_text(encoding="utf-8") + "\nNo résumé-driven design.\n", encoding="utf-8")
        out = self.run_py(LINT).stdout
        self.assertIn("skills/core/shared/note.md: non-English text", out)
        self.assertNotIn("agents/architect.md: non-English", out)       # résumé is English
        self.assertNotIn("copy-review.md", out)                          # allowlisted example
        self.assertNotIn("e2e-checklist.md", out)

    def test_tips_and_help_are_english_only(self) -> None:
        tips = json.loads((KIT / "skills/core/shared/tips.json").read_text(encoding="utf-8"))["tips"]
        self.assertTrue(all(set(t) <= {"id", "context", "en", "command"} for t in tips))
        self.assertNotIn("pt-BR", (KIT / "skills/core/shared/help.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
