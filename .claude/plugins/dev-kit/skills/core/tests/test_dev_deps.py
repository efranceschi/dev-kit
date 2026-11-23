"""Tests for dependency justification: dep_reasons, xref unjustified_dep and critical_path, next --batch
maybe_false_deps, and review `plan` staying valid after dependency-only edits (stdlib unittest)."""
from __future__ import annotations

import json
import unittest

from test_dev_state import CORE, Base

KIT = CORE.parent.parent


def plan(a_files="src/engine/x.js", b_files="src/adapter/y.js, tests/adapter.test.js", b_extra="",
         c_files="tests/fixtures/golden/, tests/engine.test.js", c_extra="", a_extra="", c_deps="T-002") -> str:
    return f"""# Implementation plan - demo

## M1 - Engine
Goal.

### T-001 Engine feature
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-1: engine works
- test_notes: unit
- contract: engine api
- files: {a_files}
{a_extra}
### T-002 Adapter over the engine
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-2: adapter works
- test_notes: unit
- consumes: T-001
- files: {b_files}
{b_extra}
### T-003 Golden files of the engine
- status: todo
- deps: {c_deps}
- type: test
- acceptance:
  - AC-3: golden files match
- test_notes: snapshot
- files: {c_files}
{c_extra}"""


CHAIN = """# Plan

## M1 - Chain
Goal.

""" + "".join(f"""### T-00{i} Step {i}
- status: todo
- deps: {f'T-00{i - 1}' if i > 1 else ''}
- type: feature
- acceptance:
  - AC-{i}: step
- test_notes: unit
- files: src/s{i}.js

""" for i in range(1, 5))


class DepBase(Base):
    def setup_plan(self, text: str) -> None:
        self.run_state("init", "--language", "en", "--project", "demo")
        (self.root / ".dev" / "plan.md").write_text(text, encoding="utf-8")
        self.run_state("sync-plan")

    def xref(self) -> dict:
        return json.loads(self.run_state("xref", "--json").stdout)

    def unjust(self) -> list[tuple[str, str]]:
        return [(x["task"], x["dep"]) for x in self.xref()["unjustified_deps"]]


class TestUnjustifiedDep(DepBase):
    def test_false_dependency_is_flagged_once(self) -> None:
        self.setup_plan(plan())
        rep = self.xref()
        self.assertEqual(self.unjust(), [("T-003", "T-002")])
        self.assertEqual(len([n for n in rep["notes"] if n.startswith("unjustified_dep")]), 1)
        self.assertIn("T-003 depends on T-002", rep["notes"][0])
        self.assertEqual(rep["problems"], [])
        self.run_state("xref", "--strict")          # a note never fails --strict

    def test_each_valid_reason_clears_it(self) -> None:
        cases = {
            "consumes": dict(b_extra="- contract: adapter api\n", c_extra="- consumes: T-002\n"),
            "common file": dict(c_files="tests/fixtures/golden/, tests/adapter.test.js"),
            "shared": dict(b_extra="- shared: yes\n"),
            "dep_reasons": dict(c_extra="- dep_reasons: T-002=reads the generated adapter schema\n"),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                self.setup_plan(plan(**kw))
                self.assertEqual(self.unjust(), [])

    def test_folder_prefix_overlap_counts(self) -> None:
        self.setup_plan(plan(b_files="tests/", c_files="tests/engine.test.js"))
        self.assertEqual(self.unjust(), [])
        self.tearDown()
        self.setUp()
        self.setup_plan(plan(b_files="tests/a", c_files="tests/ab/x.js"))
        self.assertEqual(self.unjust(), [("T-003", "T-002")])    # `tests/a` is not a prefix of `tests/ab`

    def test_only_pending_tasks_are_checked(self) -> None:
        self.setup_plan(plan())
        for t in ("T-001", "T-002", "T-003"):
            self.run_state("start", t, "--force")
            self.run_state("done", t, "--force")
        self.assertEqual(self.unjust(), [])

    def test_dep_reasons_for_a_non_dependency_warns_on_sync(self) -> None:
        self.setup_plan(plan())
        (self.root / ".dev" / "plan.md").write_text(plan(c_extra="- dep_reasons: T-001=why\n"), encoding="utf-8")
        out = self.run_state("sync-plan").stdout
        self.assertIn("dep_reasons explains T-001", out)


class TestRunTimeHint(DepBase):
    def test_next_batch_lists_maybe_false_deps(self) -> None:
        self.setup_plan(plan())
        self.run_state("start", "T-001", "--force"); self.run_state("done", "T-001", "--force")
        self.run_state("start", "T-002")
        proc = self.run_state("next", "--batch", "3", "--json", expect=3)
        rep = json.loads(proc.stdout)
        self.assertEqual(rep["tasks"], [])
        self.assertEqual(rep["maybe_false_deps"], [{"task": "T-003", "waits_on": ["T-002"]}])
        text = self.run_state("next", "--batch", "3", expect=3).stdout
        self.assertIn("maybe false dependency: T-003 waits only on T-002", text)

    def test_no_hint_with_a_reason_or_a_full_batch(self) -> None:
        self.setup_plan(plan(c_extra="- dep_reasons: T-002=reads its output\n"))
        self.run_state("start", "T-001", "--force"); self.run_state("done", "T-001", "--force")
        self.run_state("start", "T-002")
        rep = json.loads(self.run_state("next", "--batch", "3", "--json", expect=3).stdout)
        self.assertNotIn("maybe_false_deps", rep)


class TestDepReasonsSurvive(DepBase):
    REASON = "- dep_reasons: T-002=reads the generated schema; \n"

    def reason_in_plan(self) -> bool:
        return "dep_reasons: T-002=reads the generated schema" in (self.root / ".dev" / "plan.md").read_text(encoding="utf-8")

    def test_sync_brief_and_rewrites_keep_it(self) -> None:
        self.setup_plan(plan(c_extra="- dep_reasons: T-002=reads the generated schema\n"))
        self.assertEqual(self.state()["tasks"]["T-003"]["dep_reasons"], "T-002=reads the generated schema")
        self.run_state("set-risk", "T-003", "--risk", "high", "--risk-reasons", "touches schema")
        self.assertTrue(self.reason_in_plan())
        self.run_state("add-task", "--milestone", "M1", "--title", "Extra", "--deps", "T-001", "--acceptance", "AC-9: x")
        self.run_state("reorder", "M1", "T-001", "T-004", "T-002", "T-003")
        self.assertTrue(self.reason_in_plan())
        self.run_state("new-milestone", "M2", "Second")
        self.run_state("move-task", "T-003", "M2")
        self.assertTrue(self.reason_in_plan())
        ops = json.dumps([{"op": "move_task", "task": "T-003", "milestone": "M1"}])
        self.run_state("plan-apply", "--ops", ops)
        self.assertTrue(self.reason_in_plan())
        self.run_state("sync-plan")
        self.assertTrue(self.reason_in_plan())
        self.assertEqual(self.state()["tasks"]["T-003"]["dep_reasons"], "T-002=reads the generated schema")
        self.run_state("start", "T-001", "--force"); self.run_state("done", "T-001", "--force")
        self.run_state("start", "T-002", "--force"); self.run_state("done", "T-002", "--force")
        self.assertIn("needed because reads the generated schema", self.run_state("brief", "T-003").stdout)

    def test_board_drawer_carries_the_reason(self) -> None:
        import sys
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_state as ds  # noqa: E402
        self.setup_plan(plan(c_extra="- dep_reasons: T-002=reads the generated schema\n"))
        board = (CORE / "scripts" / "dev_board.py").read_text(encoding="utf-8")
        self.assertIn('"reason": why.get(d)', board)
        self.assertIn('"dep_reasons")}', board)
        self.assertIn("needed because", (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8"))
        self.assertEqual(ds.parse_dep_reasons(self.state()["tasks"]["T-003"]["dep_reasons"]), {"T-002": "reads the generated schema"})


class TestCriticalPath(DepBase):
    def test_chain_is_reported(self) -> None:
        self.setup_plan(CHAIN)
        e = self.xref()["critical_path"]["M1"]
        self.assertEqual((e["tasks"], e["critical_path"]), (4, 4))
        self.assertEqual(e["chain"], ["T-001", "T-002", "T-003", "T-004"])
        rep = self.xref()
        self.assertTrue(any(n.startswith("critical_path: M1") and "T-001 -> T-002" in n for n in rep["notes"]))
        self.assertIn("M1: 4 task(s), critical path 4", self.run_state("xref").stdout)

    def test_short_chain_has_no_note(self) -> None:
        self.setup_plan(CHAIN.replace("deps: T-003", "deps: T-001").replace("deps: T-002", "deps: T-001"))
        e = self.xref()["critical_path"]["M1"]
        self.assertEqual((e["tasks"], e["critical_path"]), (4, 2))
        self.assertFalse(any(n.startswith("critical_path") for n in self.xref()["notes"]))


class TestDependencyOnlyEdits(DepBase):
    def test_deps_edits_keep_the_review_acceptance_edits_do_not(self) -> None:
        self.setup_plan(plan())
        dev = self.root / ".dev"
        self.run_state("artifact", "mark", "all")
        self.run_state("review", "plan", "pass", "--score", "90")
        self.assertEqual(json.loads(self.run_state("stale", "--json").stdout)["reviews"], [])
        text = (dev / "plan.md").read_text(encoding="utf-8")
        (dev / "plan.md").write_text(text.replace("- deps: T-002", "- deps: T-001\n- dep_reasons: T-001=reads its output"), encoding="utf-8")
        rep = json.loads(self.run_state("stale", "--json").stdout)
        self.assertEqual(rep["reviews"], [])
        self.assertEqual([x["artifact"] for x in rep["stale"]], [])
        self.run_state("stale", "--strict")
        (dev / "plan.md").write_text((dev / "plan.md").read_text(encoding="utf-8").replace("AC-3: golden files match", "AC-3: golden files differ"), encoding="utf-8")
        rep = json.loads(self.run_state("stale", "--json").stdout)
        self.assertEqual([r["review"] for r in rep["reviews"]], ["plan"])


class TestPromptsMentionTheCheck(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (KIT / rel).read_text(encoding="utf-8")

    def test_reviewer_plan_mode_knows_unjustified_dep(self) -> None:
        text = self.read("agents/requirements-reviewer.md")
        self.assertIn("unjustified_dep", text)
        self.assertIn("remove the dependency, or add `consumes` or `dep_reasons`", text)
        self.assertIn("critical_path", text)

    def test_plan_and_implement_skills_know_it(self) -> None:
        self.assertIn("dep_reasons", self.read("skills/plan/SKILL.md"))
        self.assertIn("maybe_false_deps", self.read("skills/implement/SKILL.md"))
        self.assertIn("dep_reasons", self.read("skills/core/shared/templates/plan.md"))
        self.assertIn("`dep_reasons: T-nnn=<text>; T-mmm=<text>`", self.read("skills/core/shared/conventions.md"))


if __name__ == "__main__":
    unittest.main()
