"""Tests for scripts/dev_state.py and scripts/dev_detect_stack.py (stdlib unittest).

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
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
CLAUDE = CORE.parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
SCORE = SCRIPTS / "dev_score.py"
DETECT = SCRIPTS / "dev_detect_stack.py"

PLAN = """# Implementation plan — demo

## Milestone overview
| Milestone | Goal |
|---|---|

## M1 — Walking skeleton
Setup and first slice.

### T-001 Project scaffold
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-0: test and lint run green
- test_notes: smoke test
- files: package.json

### T-002 Login form
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-1: invalid email shows inline error
  - AC-2: valid login redirects
- test_notes: unit for validator; e2e happy path
- files: src/auth/LoginForm.tsx, src/auth/validate.ts

## M2 — Dashboard
Second milestone.

### T-003 Dashboard page
- status: todo
- deps: T-002
- type: feature
- acceptance: AC-3, AC-4
- test_notes: render test
- files: src/dashboard/page.tsx
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_state(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
            capture_output=True, text=True, cwd=self.root,
        )
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=f"args={args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        return proc

    def state(self) -> dict:
        return json.loads((self.root / ".dev" / "state.json").read_text(encoding="utf-8"))

    def init_with_plan(self) -> None:
        self.run_state("init", "--language", "pt-BR", "--project", "demo")
        (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
        self.run_state("sync-plan")


class TestInitAndSync(Base):
    def test_init_creates_state_and_files(self) -> None:
        out = self.run_state("init", "--language", "pt-BR", "--project", "demo",
                             "--stack-json", '{"lang":"typescript"}', "--autonomy-json", '{"level":"balanced"}')
        self.assertIn("created", out.stdout)
        s = self.state()
        self.assertEqual(s["language"], "pt-BR")
        self.assertEqual(s["project"], "demo")
        self.assertEqual(s["phase"], "init")
        self.assertEqual(s["stack"]["lang"], "typescript")
        self.assertEqual(s["autonomy"]["level"], "balanced")
        self.assertIn("always_ask", s["autonomy"])
        self.assertTrue((self.root / ".dev" / "open-questions.md").exists())
        self.assertTrue((self.root / ".dev" / "log.md").exists())

    def test_init_is_idempotent_and_updates_fields(self) -> None:
        self.run_state("init", "--language", "en")
        out = self.run_state("init", "--language", "pt-BR", "--phase", "prd")
        self.assertIn("updated", out.stdout)
        s = self.state()
        self.assertEqual(s["language"], "pt-BR")
        self.assertEqual(s["phase"], "prd")

    def test_init_rejects_bad_phase(self) -> None:
        self.run_state("init", "--phase", "bogus", expect=1)

    def test_sync_plan_parses_milestones_and_tasks(self) -> None:
        self.init_with_plan()
        s = self.state()
        self.assertEqual(set(s["milestones"]), {"M1", "M2"})
        self.assertEqual(s["milestones"]["M1"]["title"], "Walking skeleton")
        self.assertEqual(s["milestones"]["M1"]["gate"], "pending")
        self.assertEqual(set(s["tasks"]), {"T-001", "T-002", "T-003"})
        t2 = s["tasks"]["T-002"]
        self.assertEqual(t2["deps"], ["T-001"])
        self.assertEqual(t2["type"], "feature")
        self.assertEqual(len(t2["acceptance"]), 2)
        self.assertEqual(t2["files"], ["src/auth/LoginForm.tsx", "src/auth/validate.ts"])
        self.assertEqual(s["tasks"]["T-003"]["acceptance"], ["AC-3", "AC-4"])
        self.assertEqual(s["next_task_id"], 4)

    def test_sync_plan_preserves_status(self) -> None:
        self.init_with_plan()
        self.run_state("start", "T-001")
        self.run_state("done", "T-001", "--commit", "abc1234")
        self.run_state("sync-plan")
        s = self.state()
        self.assertEqual(s["tasks"]["T-001"]["status"], "done")
        self.assertEqual(s["tasks"]["T-001"]["commit"], "abc1234")

    def test_sync_plan_warns_on_missing_dep(self) -> None:
        self.run_state("init")
        (self.root / ".dev" / "plan.md").write_text("## M1 — X\n### T-001 A\n- deps: T-999\n- type: feature\n", encoding="utf-8")
        out = self.run_state("sync-plan")
        self.assertIn("T-999 does not exist", out.stdout)

    def test_status_quiet_if_missing_prints_nothing(self) -> None:
        out = self.run_state("status", "--short", "--quiet-if-missing")
        self.assertEqual(out.stdout, "")
        self.run_state("status", expect=2)


class TestTransitions(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def test_next_respects_dependencies(self) -> None:
        out = self.run_state("next")
        self.assertTrue(out.stdout.startswith("T-001"))
        self.run_state("start", "T-002", expect=1)  # unmet dep
        self.run_state("start", "T-001")
        self.run_state("next", expect=3)  # in progress blocks picking another
        self.run_state("done", "T-001")
        out = self.run_state("next")
        self.assertTrue(out.stdout.startswith("T-002"))

    def test_done_requires_in_progress(self) -> None:
        self.run_state("done", "T-001", expect=1)
        self.run_state("done", "T-001", "--force")
        self.assertEqual(self.state()["tasks"]["T-001"]["status"], "done")

    def test_single_in_progress_unless_force(self) -> None:
        self.run_state("start", "T-001")
        self.run_state("done", "T-001")
        self.run_state("start", "T-002")
        # T-003 depends on T-002, so use a fix task to test parallel guard
        tid = self.run_state("add-task", "--milestone", "M1", "--title", "Hotfix", "--type", "fix").stdout.strip()
        self.run_state("start", tid, expect=1)
        self.run_state("start", tid, "--force")
        self.assertEqual(self.state()["tasks"][tid]["status"], "in_progress")

    def test_block_unblock(self) -> None:
        self.run_state("start", "T-001")
        self.run_state("block", "T-001", "--reason", "missing credentials")
        s = self.state()
        self.assertEqual(s["tasks"]["T-001"]["status"], "blocked")
        self.assertEqual(s["tasks"]["T-001"]["blocked_reason"], "missing credentials")
        out = self.run_state("next", expect=3)
        self.assertIn("blocked", out.stdout)
        self.run_state("unblock", "T-001")
        self.assertEqual(self.state()["tasks"]["T-001"]["status"], "todo")

    def test_gate_blocks_next_milestone(self) -> None:
        for t in ("T-001", "T-002"):
            self.run_state("start", t)
            out = self.run_state("done", t)
        self.assertIn("milestone M1 complete", out.stdout)
        out = self.run_state("next", expect=3)
        self.assertIn("gate of M1 is pending", out.stdout)
        self.run_state("start", "T-003", expect=1)
        self.run_state("gate", "M1", "passed", "--count-run", "--score", "90")
        s = self.state()
        self.assertEqual(s["milestones"]["M1"]["gate"], "passed")
        self.assertEqual(s["milestones"]["M1"]["qa_runs"], 1)
        out = self.run_state("next")
        self.assertTrue(out.stdout.startswith("T-003"))

    def test_gate_skipped_also_opens(self) -> None:
        for t in ("T-001", "T-002"):
            self.run_state("start", t)
            self.run_state("done", t)
        self.run_state("gate", "M1", "skipped", "--note", "user decision ADR-009")
        out = self.run_state("next")
        self.assertTrue(out.stdout.startswith("T-003"))
        self.run_state("gate", "M1", "weird", expect=1)

    def test_fix_tasks_jump_the_queue(self) -> None:
        self.run_state("start", "T-001")
        self.run_state("done", "T-001")
        tid = self.run_state(
            "add-task", "--milestone", "M1", "--title", "Fix null crash", "--type", "fix",
            "--acceptance", "AC-1: no crash on empty email", "--source", "qa/M1/report.md#F-002",
        ).stdout.strip()
        self.assertEqual(tid, "T-004")
        out = self.run_state("next")
        self.assertTrue(out.stdout.startswith("T-004"), out.stdout)
        plan = (self.root / ".dev" / "plan.md").read_text(encoding="utf-8")
        self.assertIn("### T-004 Fix null crash", plan)
        self.assertIn("- source: qa/M1/report.md#F-002", plan)
        # task was appended inside M1 section, before M2 heading
        self.assertLess(plan.index("### T-004"), plan.index("## M2"))
        # re-sync keeps it
        self.run_state("sync-plan")
        self.assertEqual(self.state()["tasks"]["T-004"]["type"], "fix")

    def test_add_task_new_milestone_requires_title(self) -> None:
        self.run_state("add-task", "--milestone", "M3", "--title", "X", expect=1)
        tid = self.run_state("add-task", "--milestone", "M3", "--milestone-title", "Polish", "--title", "X").stdout.strip()
        s = self.state()
        self.assertEqual(s["milestones"]["M3"]["title"], "Polish")
        self.assertEqual(s["tasks"][tid]["milestone"], "M3")
        self.assertIn("## M3 — Polish", (self.root / ".dev" / "plan.md").read_text(encoding="utf-8"))

    def test_add_question_appends_row_and_counts(self) -> None:
        qid = self.run_state("add-question", "Which currency?", "--skill", "prd", "--assumption", "BRL", "--impact", "pricing display").stdout.strip()
        self.assertEqual(qid, "Q-001")
        text = (self.root / ".dev" / "open-questions.md").read_text(encoding="utf-8")
        self.assertIn("| Q-001 |", text)
        self.assertIn("Which currency?", text)
        self.assertLess(text.index("Q-001"), text.index("## Resolved"))
        out = self.run_state("status", "--json")
        self.assertEqual(json.loads(out.stdout)["open_questions"], 1)

    def test_set_and_status_views(self) -> None:
        self.run_state("set", "phase", "implement")
        self.run_state("set", "autonomy.level", "cautious")
        self.run_state("set", "autonomy.max_fix_rounds_per_gate", "5")
        self.run_state("set", "phase", "nope", expect=1)
        s = self.state()
        self.assertEqual(s["phase"], "implement")
        self.assertEqual(s["autonomy"]["level"], "cautious")
        self.assertEqual(s["autonomy"]["max_fix_rounds_per_gate"], 5)
        short = self.run_state("status", "--short").stdout.splitlines()
        self.assertEqual(len(short), 3)
        self.assertIn("phase: implement", short[0])
        self.assertIn("next: T-001", short[1])
        full = self.run_state("status").stdout
        self.assertIn("M1 — Walking skeleton", full)
        js = json.loads(self.run_state("status", "--json").stdout)
        self.assertEqual(js["progress"]["total"], 3)
        self.assertEqual(js["next"]["task"], "T-001")

    def test_model_policy_default_and_validation(self) -> None:
        s = self.state()
        self.assertEqual(s["autonomy"]["model_policy"], {"mode": "ask", "tiers": {}})
        self.assertIn("model_escalation", s["autonomy"]["always_ask"])
        self.run_state("set", "autonomy.model_policy", "preapproved")
        self.assertEqual(self.state()["autonomy"]["model_policy"]["mode"], "preapproved")
        self.run_state("set", "autonomy.model_policy", '{"mode": "off", "tiers": {"copy-reviewer": "balanced"}}')
        self.assertEqual(self.state()["autonomy"]["model_policy"]["tiers"], {"copy-reviewer": "balanced"})
        self.run_state("set", "autonomy.model_policy", "always", expect=1)
        self.run_state("set", "autonomy.model_policy", '{"tiers": {"x": "turbo"}}', expect=1)

    def test_log_records_transitions(self) -> None:
        self.run_state("start", "T-001")
        log = (self.root / ".dev" / "log.md").read_text(encoding="utf-8")
        self.assertIn("start T-001", log)

    def test_root_discovery_from_subdir(self) -> None:
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        proc = subprocess.run([sys.executable, "-I", str(STATE), "status", "--short"], capture_output=True, text=True, cwd=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[dev-kit]", proc.stdout)


class TestDetectStack(unittest.TestCase):
    def run_detect(self, root: Path) -> dict:
        proc = subprocess.run([sys.executable, "-I", str(DETECT), str(root)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_greenfield(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self.run_detect(Path(d))
            self.assertTrue(out["greenfield"])
            self.assertIsNone(out["lang"])

    def test_next_pnpm_vitest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "package.json").write_text(json.dumps({
                "dependencies": {"next": "15", "react": "19", "@prisma/client": "6"},
                "devDependencies": {"typescript": "5", "vitest": "2", "eslint": "9"},
                "scripts": {"dev": "next dev", "test": "vitest"},
            }), encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("", encoding="utf-8")
            out = self.run_detect(root)
            self.assertEqual(out["lang"], "typescript")
            self.assertEqual(out["framework"], "next.js")
            self.assertEqual(out["pkg"], "pnpm")
            self.assertEqual(out["test"], "vitest")
            self.assertEqual(out["lint"], "eslint")
            self.assertEqual(out["db"], "prisma")
            self.assertIn("package.json", out["detected_from"])
            self.assertEqual(out["scripts"]["test"], "vitest")

    def test_python_fastapi_uv(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "x"\ndependencies = [\n  "fastapi>=0.115",\n  "sqlalchemy>=2",\n]\n'
                '[dependency-groups]\ndev = ["pytest>=8", "ruff>=0.6"]\n', encoding="utf-8")
            (root / "uv.lock").write_text("", encoding="utf-8")
            out = self.run_detect(root)
            self.assertEqual(out["lang"], "python")
            self.assertEqual(out["framework"], "fastapi")
            self.assertEqual(out["pkg"], "uv")
            self.assertEqual(out["test"], "pytest")
            self.assertEqual(out["lint"], "ruff")
            self.assertEqual(out["db"], "sqlalchemy")

    def test_go_gin(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\nrequire github.com/gin-gonic/gin v1.10.0\n", encoding="utf-8")
            out = self.run_detect(root)
            self.assertEqual(out["lang"], "go")
            self.assertEqual(out["framework"], "gin")
            self.assertEqual(out["pkg"], "go")


class TestGateAndReviewCutoff(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()
        for t in ("T-001", "T-002"):
            self.run_state("start", t)
            self.run_state("done", t)

    def test_gate_requires_score(self) -> None:
        out = self.run_state("gate", "M1", "passed", expect=1)
        self.assertIn("without --score", out.stderr)

    def test_gate_rejects_score_below_cutoff(self) -> None:
        out = self.run_state("gate", "M1", "passed", "--score", "84", expect=1)
        self.assertIn("below the cut-off 85", out.stderr)
        self.assertEqual(self.state()["milestones"]["M1"]["gate"], "pending")

    def test_gate_accepts_score_at_cutoff_and_stores_it(self) -> None:
        self.run_state("gate", "M1", "passed", "--score", "85")
        m = self.state()["milestones"]["M1"]
        self.assertEqual((m["gate"], m["score"]), ("passed", 85))
        self.assertIn("M1:passed(85)", self.run_state("status", "--short").stdout)

    def test_gate_force_is_recorded(self) -> None:
        self.run_state("gate", "M1", "passed", "--score", "50", "--force")
        self.assertTrue(self.state()["milestones"]["M1"]["forced"])

    def test_cutoff_is_configurable_from_interview(self) -> None:
        self.run_state("init", "--autonomy-json", json.dumps({"quality": {"min_overall": 92, "dimension_min": {"security": 95}}}))
        q = self.state()["autonomy"]["quality"]
        self.assertEqual(q["min_overall"], 92)
        self.assertEqual(q["dimension_min"]["security"], 95)
        self.assertEqual(q["dimension_min"]["tests"], 80)  # deep merge keeps the other defaults
        self.run_state("gate", "M1", "passed", "--score", "90", expect=1)
        self.run_state("gate", "M1", "passed", "--score", "92")

    def test_review_cutoff(self) -> None:
        self.run_state("review", "design", "pass", expect=1)
        self.run_state("review", "design", "pass", "--score", "79", expect=1)
        self.run_state("review", "design", "fail", "--score", "62", "--count-run")
        self.run_state("review", "design", "pass", "--score", "88", "--count-run")
        r = self.state()["reviews"]["design"]
        self.assertEqual((r["verdict"], r["score"], r["rounds"]), ("pass", 88, 2))
        self.assertIn("design:pass(88)", self.run_state("status").stdout)


class TestPausePolicy(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()
        for t in ("T-001", "T-002"):
            self.run_state("start", t)
            self.run_state("done", t)

    def write_scores(self, blockers: list, security_ok: bool = True) -> None:
        d = self.root / ".dev" / "qa" / "M1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "scores.json").write_text(json.dumps({"overall": 82, "blockers": blockers,
            "dimensions": {"security": {"score": 95 if security_ok else 80, "ok": security_ok}}}), encoding="utf-8")

    def test_default_is_supervised(self) -> None:
        s = self.state()["autonomy"]
        self.assertEqual(s["pause_policy"], {})
        self.assertEqual(s["on_park"], "stop_when_idle")

    def test_unattended_preset_fills_recommended_values(self) -> None:
        self.run_state("set", "autonomy.level", "unattended")
        a = self.state()["autonomy"]
        self.assertEqual(a["pause_policy"]["rounds_exhausted"]["action"], "auto_recommend")
        self.assertEqual(a["pause_policy"]["scope_change_major"]["action"], "park")
        self.assertEqual(a["model_policy"]["mode"], "preapproved")
        self.assertIn("Pause policy:", self.run_state("status").stdout)

    def test_floors_are_enforced(self) -> None:
        self.run_state("set", "autonomy.pause_policy.scope_change_major", "auto_recommend", expect=1)
        self.run_state("set", "autonomy.pause_policy.credentials", "preauthorize", expect=1)
        self.run_state("set", "autonomy.pause_policy.paid_services", "preauthorize", expect=1)  # needs a limit
        self.run_state("set", "autonomy.pause_policy.delete_data",
                       json.dumps({"action": "preauthorize", "limit": {"environments": ["dev", "production"]}}), expect=1)
        self.run_state("set", "autonomy.pause_policy.nope", "ask", expect=1)
        self.run_state("set", "autonomy.pause_policy.paid_services",
                       json.dumps({"action": "preauthorize", "limit": {"max_monthly": 50, "currency": "BRL"}}))
        self.assertEqual(self.state()["autonomy"]["pause_policy"]["paid_services"]["limit"]["max_monthly"], 50)
        self.run_state("set", "autonomy.on_park", "whenever", expect=1)

    def test_interview_json_merges_pause_policy(self) -> None:
        self.run_state("init", "--autonomy-json", json.dumps({"level": "unattended", "pause_policy": {"public_exposure": {"action": "ask"}}}))
        pp = self.state()["autonomy"]["pause_policy"]
        self.assertEqual(pp["public_exposure"]["action"], "ask")
        self.assertEqual(pp["dirty_tree"]["action"], "auto_recommend")
        self.run_state("init", "--autonomy-json", json.dumps({"pause_policy": {"credentials": {"action": "auto_recommend"}}}), expect=1)

    def test_policy_force_needs_policy_and_respects_floors(self) -> None:
        self.write_scores([])
        out = self.run_state("gate", "M1", "passed", "--score", "82", "--force", "--note", "policy:rounds_exhausted", expect=1)
        self.assertIn("not auto_recommend", out.stderr)
        self.run_state("set", "autonomy.level", "unattended")
        self.write_scores([{"dimension": "code", "severity": "high"}])
        out = self.run_state("gate", "M1", "passed", "--score", "82", "--force", "--note", "policy:rounds_exhausted", expect=1)
        self.assertIn("critical/high", out.stderr)
        self.write_scores([], security_ok=False)
        out = self.run_state("gate", "M1", "passed", "--score", "82", "--force", "--note", "policy:rounds_exhausted", expect=1)
        self.assertIn("security", out.stderr)
        self.write_scores([])
        self.run_state("gate", "M1", "passed", "--score", "82", "--force", "--note", "policy:rounds_exhausted")
        m = self.state()["milestones"]["M1"]
        self.assertTrue(m["forced"])
        self.assertEqual(m["gate_note"], "policy:rounds_exhausted")


class TestLocalDeploy(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def test_default_off_and_validation(self) -> None:
        self.assertEqual(self.state()["autonomy"]["local_deploy"]["mode"], "off")
        self.run_state("set", "autonomy.local_deploy", "always", expect=1)
        self.run_state("set", "autonomy.local_deploy", json.dumps({"mode": "keep_running", "port": 80}), expect=1)
        self.run_state("set", "autonomy.local_deploy", json.dumps({"mode": "keep_running", "port": 4173}))
        self.run_state("set", "autonomy.local_deploy", "smoke")
        ld = self.state()["autonomy"]["local_deploy"]
        self.assertEqual((ld["mode"], ld["port"]), ("smoke", 4173))
        self.run_state("init", "--autonomy-json", json.dumps({"local_deploy": {"notify": True}}))
        ld = self.state()["autonomy"]["local_deploy"]
        self.assertEqual((ld["mode"], ld["notify"]), ("smoke", True))

    def test_preview_record_status_and_stop(self) -> None:
        self.run_state("preview", "M1", "--url", "http://127.0.0.1:4173", expect=1)
        self.run_state("preview", "M1", "--url", "http://127.0.0.1:4173", "--sha", "abc1234def", "--pid", "999")
        self.assertIn("Preview: M1 http://127.0.0.1:4173 (abc1234)", self.run_state("status").stdout)
        self.run_state("preview", "M2", "--url", "http://127.0.0.1:4173", "--sha", "fff0000aaa", "--pid", "1000")
        ms = self.state()["milestones"]
        self.assertNotIn("pid", ms["M1"]["preview"])  # only one preview runs at a time
        self.run_state("preview", "M2", "--stopped")
        self.assertNotIn("pid", self.state()["milestones"]["M2"]["preview"])
        self.assertNotIn("Preview:", self.run_state("status").stdout)


def finding(sev: str, **kw) -> dict:
    return {"id": "F-1", "severity": sev, "title": "t", "file": "a.py", "line": 1, **kw}


class TestScore(Base):
    def write(self, name: str, auditor: str, findings: list[dict]) -> str:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps({"auditor": auditor, "findings": findings, "verdict": "pass"}), encoding="utf-8")
        return str(path)

    def run_score(self, *files: str, kind: str = "gate", expect: int | None = None) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [sys.executable, "-I", str(SCORE), "score", "--scope", "M1", "--kind", kind, "--root", str(self.root),
             "--out", str(self.root / "scores.json"), *files], capture_output=True, text=True)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=proc.stdout + proc.stderr)
        return proc

    def test_clean_run_scores_100_and_passes(self) -> None:
        a = self.write("a", "code-reviewer", [])
        b = self.write("b", "security-auditor", [])
        self.run_score(a, b, expect=0)
        res = json.loads((self.root / "scores.json").read_text())
        self.assertEqual(res["overall"], 100)
        self.assertEqual(res["verdict"], "pass")

    def test_penalties_and_caps(self) -> None:
        a = self.write("a", "code-reviewer", [finding("medium"), finding("medium"), finding("low")])
        self.run_score(a, expect=1)  # 82 passes the dimension minimum but not the overall cut-off of 85
        res = json.loads((self.root / "scores.json").read_text())
        self.assertEqual(res["dimensions"]["code"]["score"], 100 - 8 - 8 - 2)
        b = self.write("b", "code-reviewer", [finding("high")])
        self.run_score(b, expect=1)
        res = json.loads((self.root / "scores.json").read_text())
        self.assertEqual(res["dimensions"]["code"]["score"], 69)  # cap for any high
        self.assertEqual(len(res["blockers"]), 1)

    def test_critical_caps_at_40(self) -> None:
        a = self.write("a", "security-auditor", [finding("critical")])
        self.run_score(a, expect=1)
        self.assertEqual(json.loads((self.root / "scores.json").read_text())["dimensions"]["security"]["score"], 40)

    def test_low_confidence_counts_half(self) -> None:
        a = self.write("a", "code-reviewer", [finding("medium", confidence="low")])
        self.run_score(a, expect=0)
        self.assertEqual(json.loads((self.root / "scores.json").read_text())["dimensions"]["code"]["score"], 96)

    def test_dimension_minimum_blocks_even_with_high_overall(self) -> None:
        # security min is 90: four mediums = 68 -> fails although others are perfect
        sec = self.write("s", "security-auditor", [finding("medium")] * 2)  # 84 < 90
        code = self.write("c", "code-reviewer", [])
        tests = self.write("t", "test-auditor", [])
        spec = self.write("p", "spec-tracer", [])
        proc = self.run_score(sec, code, tests, spec, expect=1)
        self.assertIn("security score 84 < 90", proc.stdout)
        res = json.loads((self.root / "scores.json").read_text())
        self.assertGreaterEqual(res["overall"], 85)  # overall alone would have passed

    def test_overall_cutoff(self) -> None:
        files = [self.write(f"f{i}", a, [finding("medium")] * 2 + [finding("low")]) for i, a in enumerate(
            ["code-reviewer", "copy-reviewer", "visual-reviewer"])]
        proc = self.run_score(*files, expect=1)
        self.assertIn("overall", proc.stdout)

    def test_review_kind_uses_review_cutoff(self) -> None:
        a = self.write("a", "design-reviewer", [finding("medium")] * 2)  # 84
        self.run_score(a, kind="review", expect=0)  # 84 >= 80 and >= min_dimension 70
        self.run_score(a, kind="gate", expect=1)  # 84 < 85

    def test_invalid_or_unknown_input_fails(self) -> None:
        bad = self.root / "bad.json"
        bad.write_text("{nope", encoding="utf-8")
        ok = self.write("a", "code-reviewer", [])
        self.run_score(str(bad), ok, expect=1)
        unk = self.write("u", "dev-unknown", [])
        self.run_score(unk, expect=1)
        self.run_score(str(self.root / "missing.json"), expect=2)

    def test_state_thresholds_are_used(self) -> None:
        self.run_state("init", "--autonomy-json", json.dumps({"quality": {"min_overall": 99, "min_dimension": 99}}))
        a = self.write("a", "design-reviewer", [finding("low")])  # 98
        self.run_score(a, expect=1)


class TestSuiteLayout(unittest.TestCase):
    """The suite lives only under .claude/: it must lint clean and work when copied somewhere else."""

    def test_lint_is_clean(self) -> None:
        proc = subprocess.run([sys.executable, "-I", str(CORE / "tests" / "lint_suite.py")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 errors", proc.stdout)

    def test_installed_skills_run_their_injected_commands_from_another_location(self) -> None:
        """Copy only skills/ and agents/ to a new place (as a publisher would) and execute every !`cmd` injection."""
        import re
        import shutil
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home" / ".claude"
            project = Path(d) / "someapp"
            project.mkdir()
            shutil.copytree(CLAUDE / "skills", home / "skills", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(CLAUDE / "agents", home / "agents")
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            ran = 0
            for skill_md in sorted((home / "skills").glob("*/SKILL.md")):
                text = skill_md.read_text(encoding="utf-8")
                for cmd in re.findall(r"!`([^`]+)`", text):
                    resolved = cmd.replace("${CLAUDE_SKILL_DIR}", str(skill_md.parent)).replace("${CLAUDE_PROJECT_DIR}", str(project))
                    self.assertNotIn("${", resolved, f"unresolved variable in {skill_md.parent.name}: {cmd}")
                    proc = subprocess.run(resolved, shell=True, cwd=project, capture_output=True, text=True)
                    self.assertNotIn("can't open file", proc.stderr, f"{skill_md.parent.name}: {resolved}\n{proc.stderr}")
                    self.assertIn(proc.returncode, (0, 2), f"{skill_md.parent.name}: {resolved}\n{proc.stderr}")  # 2 = no state yet
                    ran += 1
            self.assertGreater(ran, 10)
            core = home / "skills" / "core"
            for f in list((home / "skills").glob("*/SKILL.md")) + list((home / "agents").glob("*.md")):
                for ref in re.findall(r"(?:\$\{CLAUDE_SKILL_DIR\}/\.\./core|<KIT>)/((?:shared|scripts)/[A-Za-z0-9_./-]+\.(?:md|py|json))", f.read_text(encoding="utf-8")):
                    self.assertTrue((core / ref).exists(), f"{f.name}: missing {ref}")
            state = core / "scripts" / "dev_state.py"
            proc = subprocess.run([sys.executable, "-I", str(state), "--root", str(project), "init", "--language", "pt-BR"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((project / ".dev" / "state.json").exists())
            self.assertFalse((CLAUDE.parent / ".dev").exists(), "nothing may be created in the skills repository")
            self.assertFalse((CLAUDE / ".dev").exists())


class TestScoreConvergence(Base):
    write = TestScore.write
    run_score = TestScore.run_score

    def scores(self) -> dict:
        return json.loads((self.root / "scores.json").read_text(encoding="utf-8"))

    def write_full(self, name: str, auditor: str, findings: list[dict], previous: list[dict] | None = None) -> str:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps({"auditor": auditor, "findings": findings, "previous": previous or [], "verdict": "pass"}), encoding="utf-8")
        return str(path)

    def run_delta(self, prev: list[dict], *files: str, expect: int | None = None) -> subprocess.CompletedProcess:
        pf = self.root / "prev.json"
        pf.write_text(json.dumps({"findings": prev}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(SCORE), "score", "--scope", "ux", "--kind", "review", "--root", str(self.root),
             "--out", str(self.root / "scores.json"), "--previous", str(pf), *files], capture_output=True, text=True)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=proc.stdout + proc.stderr)
        return proc

    def test_same_finding_from_two_audits_counts_once(self) -> None:
        f = [finding("medium", id="F-1", file="ui/menu.tsx", line=10, title="Focus trapped in menu")]
        a = self.write("ua1", "usability-auditor", f)
        b = self.write("ua2", "usability-auditor", [dict(f[0], id="F-9")])
        self.run_score(a, b)
        ux = self.scores()["dimensions"]["ux"]
        self.assertEqual((ux["score"], ux["counts"]["medium"]), (92, 1))

    def test_low_findings_are_capped(self) -> None:
        lows = [finding("low", id=f"F-{i}", line=i) for i in range(20)]
        self.run_score(self.write("c", "code-reviewer", lows))
        self.assertEqual(self.scores()["dimensions"]["code"]["score"], 90)

    def test_delta_rules(self) -> None:
        prev = [
            {"id": "F-001", "auditor": "usability-auditor", "severity": "medium", "title": "a", "file": "x.tsx", "line": 1},
            {"id": "F-002", "auditor": "usability-auditor", "severity": "medium", "title": "b", "file": "x.tsx", "line": 2},
        ]
        new = [finding("low", id="N-1", line=50), finding("medium", id="N-2", line=60)]
        a = self.write_full("ua", "usability-auditor", new, previous=[{"id": "F-001", "state": "closed"}])
        self.run_delta(prev, a)
        s = self.scores()
        self.assertEqual(s["delta"], {"closed": 1, "still_open": 1, "new_scored": 1, "new_deferred": 1})
        self.assertEqual(s["dimensions"]["ux"]["score"], 84)  # F-002 (omitted = open) + N-2
        self.assertEqual(s["dimensions"]["ux"]["deferred"], 1)
        b = self.write_full("ub", "usability-auditor", [finding("high", id="N-3", line=70)],
                            previous=[{"id": "F-001", "state": "closed"}, {"id": "F-002", "state": "closed"}])
        self.run_delta(prev, b, expect=1)  # a new high still blocks
        self.assertEqual(self.scores()["delta"]["closed"], 2)

    def test_open_wins_over_closed(self) -> None:
        prev = [{"id": "F-001", "auditor": "usability-auditor", "severity": "medium", "title": "a", "file": "x.tsx", "line": 1}]
        a = self.write_full("u1", "usability-auditor", [], previous=[{"id": "F-001", "state": "closed"}])
        b = self.write_full("u2", "usability-auditor", [], previous=[{"id": "F-001", "state": "open"}])
        self.run_delta(prev, a, b)
        self.assertEqual(self.scores()["delta"]["still_open"], 1)

    def test_real_case_round_two_goes_up(self) -> None:
        """memory-archive: round 1 had many mediums and lows; round 2 closes the mediums and brings 25 new lows."""
        r1 = [finding("medium", id=f"F-{i:03d}", line=i) for i in range(1, 6)] + \
             [finding("low", id=f"F-{i:03d}", line=i) for i in range(6, 31)]
        a = self.write("r1", "usability-auditor", r1)
        self.run_score(a, kind="review")
        first = self.scores()["dimensions"]["ux"]["score"]
        prev = [dict(f, auditor="usability-auditor") for f in r1]
        closed = [{"id": f"F-{i:03d}", "state": "closed"} for i in range(1, 31)]
        new_lows = [finding("low", id=f"N-{i}", line=100 + i) for i in range(25)]
        b = self.write_full("r2", "usability-auditor", new_lows, previous=closed)
        self.run_delta(prev, b, expect=0)
        second = self.scores()["dimensions"]["ux"]["score"]
        self.assertGreater(second, first)
        self.assertEqual(second, 100)


class TestTelemetry(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def events(self) -> list[dict]:
        path = self.root / ".dev" / "telemetry.jsonl"
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_allowlist_rejects_sensitive_values(self) -> None:
        self.run_state("event", "agent_end", "--set", "agent=code-reviewer", "--set", "model=sonnet", "--set", "tokens=1200")
        self.run_state("event", "agent_end", "--set", "title=Fix login bug", expect=1)          # key not allowed
        self.run_state("event", "agent_end", "--set", "agent=src/auth/login.py", expect=1)    # path as value
        self.run_state("event", "error", "--set", "code=https://example.com", expect=1)       # URL as value
        self.run_state("event", "pause", "--set", "point=Fix the login page now", expect=1)   # free text as value
        self.run_state("event", "nope", expect=1)
        evs = [e for e in self.events() if e["event"] == "agent_end"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["tokens"], 1200)

    def test_scripts_emit_events(self) -> None:
        self.run_state("start", "T-001")
        self.run_state("done", "T-001", "--commit", "abc1234")
        self.run_state("review", "prd", "fail", "--score", "60", "--count-run")
        a = self.root / "code.json"
        a.write_text(json.dumps({"auditor": "code-reviewer", "findings": []}), encoding="utf-8")
        subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", "M1", "--root", str(self.root),
                        "--out", str(self.root / "s.json"), "--round", "2", str(a)], capture_output=True, text=True)
        kinds = [(e["event"], e.get("transition") or e.get("value") or e.get("verdict")) for e in self.events()]
        self.assertIn(("task", "start"), kinds)
        self.assertIn(("task", "done"), kinds)
        self.assertIn(("review", "fail"), kinds)
        self.assertIn(("score", "pass"), kinds)
        score = [e for e in self.events() if e["event"] == "score"][0]
        self.assertEqual((score["round"], score["dimensions"]), (2, {"code": 100}))

    def test_feedback_rules(self) -> None:
        self.run_state("feedback", "--worked", "scoring:delta mode closed old findings", "--improve", "prompts:checklist lacks 404 pages")
        self.run_state("feedback", "--worked", "nonsense:x", expect=1)                         # area not in enum
        self.run_state("feedback", "--failed", "isolation:clash in src/app.py", expect=1)      # path
        self.run_state("feedback", "--failed", "deploy:see https://x.io/log", expect=1)        # URL
        self.run_state("feedback", "--failed", "other:mail me at a@b.co", expect=1)            # e-mail
        self.run_state("feedback", "--failed", "other:the demo project broke", expect=1)       # project name
        self.run_state("feedback", "--failed", "other:" + "x" * 141, expect=1)                 # too long
        self.run_state("feedback", "--json", json.dumps({"improve": [{"area": "qa", "note": "n"}] * 4}), expect=1)  # > 3 items
        summary = self.run_state("telemetry", "summary").stdout
        self.assertIn("[scoring] delta mode closed old findings", summary)
        self.assertIn("feedback improve:", summary)

    def test_export_contains_no_project_strings(self) -> None:
        secret_title = "Zyxwq reminder sync for Hortensia"
        self.run_state("add-task", "--milestone", "M1", "--type", "fix", "--title", secret_title, "--acceptance", "Hortensia sees it")
        self.run_state("start", "T-001")
        self.run_state("block", "T-001", "--reason", "Hortensia credentials missing")
        self.run_state("gate", "M1", "pending", "--score", "70", "--note", "Zyxwq regression")
        self.run_state("feedback", "--improve", "qa:parallel auditors overload small hosts")
        self.run_state("telemetry", "export", "--events")
        text = sorted((self.root / ".dev" / "feedback").glob("telemetry-export-*.json"))[-1].read_text(encoding="utf-8")
        for s in ("Zyxwq", "Hortensia", "demo", str(self.root)):
            self.assertNotIn(s, text)
        bundle = json.loads(text)
        self.assertGreater(len(bundle["events"]), 3)
        self.assertIn("qa", bundle["summary"]["feedback"]["improve"])

    def test_tampered_lines_are_dropped_on_export(self) -> None:
        self.run_state("event", "cleanup", "--set", "killed=1")
        with (self.root / ".dev" / "telemetry.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "ts": "x", "session": "abcd1234", "kit": "1", "event": "task", "title": "leak"}) + "\n")
        self.run_state("telemetry", "export")
        bundle = json.loads(sorted((self.root / ".dev" / "feedback").glob("telemetry-export-*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(bundle["summary"]["dropped_invalid_lines"], 1)
        self.assertNotIn("leak", json.dumps(bundle))


class TestCleanupAndDeploy(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()
        self.procs: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        for pr in self.procs:
            if pr.poll() is None:
                pr.kill()
            pr.wait()
        super().tearDown()

    def test_cleanup_kills_only_project_processes(self) -> None:
        inside = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=self.root)
        with tempfile.TemporaryDirectory() as other:
            outside = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=other)
            self.procs += [inside, outside]
            run = self.root / ".dev" / "run"
            run.mkdir(parents=True)
            (run / "test-auditor-1.pids").write_text(f"{inside.pid}\n{outside.pid}\n", encoding="utf-8")
            self.assertIn("Leftover agent processes: 2", self.run_state("status").stdout)
            self.run_state("cleanup", "--dry-run")
            self.assertIsNone(inside.poll())
            out = self.run_state("cleanup").stdout
            self.assertIn("1 killed", out)
            inside.wait(timeout=5)
            self.assertIsNotNone(inside.poll())
            self.assertIsNone(outside.poll())   # decoy outside the project survives
            self.assertFalse((run / "test-auditor-1.pids").exists())

    def test_deploy_records_and_status_shows_drift(self) -> None:
        self.run_state("deploy", "--sha", "abc1234def", "--status", "ok", "--milestone", "M1", "--migration", "0031")
        self.run_state("deploy", "--sha", "fff9999", "--status", "failed", "--milestone", "M1")
        d = self.state()["deploys"]["production"]
        self.assertEqual((d["current"]["sha"], len(d["history"])), ("abc1234def", 2))
        out = self.run_state("status", "--head-migration", "0038").stdout
        self.assertIn("Production: abc1234 (M1, migr 0031)", out)
        self.assertIn("7 migrations behind", out)
        self.run_state("deploy", "--sha", "x", "--status", "maybe", expect=1)

    def test_production_policy_and_floor(self) -> None:
        self.run_state("set", "autonomy.production", json.dumps({"when": "per_milestone"}), expect=1)  # needs a method
        self.run_state("set", "autonomy.production", json.dumps({"when": "per_milestone", "method": "install-script", "host": "local",
                                                                  "smoke": ["health"], "prerequisites": ["backup-credentials"]}))
        self.assertEqual(self.state()["autonomy"]["production"]["when"], "per_milestone")
        self.run_state("set", "autonomy.pause_policy.production_deploy", "preauthorize", expect=1)  # needs targets
        self.run_state("set", "autonomy.pause_policy.production_deploy", json.dumps({"action": "auto_recommend"}), expect=1)
        self.run_state("set", "autonomy.pause_policy.production_deploy", json.dumps({"action": "preauthorize", "limit": {"targets": ["local-systemd"]}}))


class TestFeedbackReport(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def ev(self, event_type: str, **fields) -> None:
        args = ["event", event_type]
        js = {k: v for k, v in fields.items() if isinstance(v, (dict, list))}
        for k, v in fields.items():
            if k not in js:
                args += ["--set", f"{k}={json.dumps(v) if isinstance(v, bool) else v}"]
        if js:
            args += ["--json", json.dumps(js)]
        self.run_state(*args)

    def report(self, *extra: str) -> dict:
        return json.loads(self.run_state("telemetry", "report", "--json", *extra).stdout)

    def stage(self, rep: dict, name: str) -> dict:
        return next(s for s in rep["report"]["stages"] if s["stage"] == name)

    def test_period_session_and_all(self) -> None:
        self.ev("skill_end", skill="interview", status="ok")
        self.ev("session_start", trigger="autopilot")
        self.ev("skill_end", skill="prd", status="ok")
        rep = self.report()
        self.assertIsNone(self.stage(rep, "interview")["score"])     # earlier session not included
        self.assertEqual(self.stage(rep, "prd")["score"], 100)
        rep_all = self.report("--all")
        self.assertEqual(self.stage(rep_all, "interview")["score"], 100)
        self.assertEqual(self.report("--since", "2000-01-01")["period"]["mode"], "since")

    def test_forced_prd_after_four_rounds(self) -> None:
        self.ev("session_start", trigger="autopilot")
        for i, sc in enumerate([40, 45, 50]):
            self.run_state("review", "prd", "fail", "--score", str(sc), "--count-run")
        self.run_state("review", "prd", "pass", "--score", "52", "--force", "--count-run")
        st = self.stage(self.report(), "prd")
        # 4 rounds: 3 extra rounds (-30) plus 1 beyond the limit of 3 (-10); forced by the user (-25)
        self.assertEqual(st["score"], 35)
        self.assertIn("prd rounds 4 (-40)", st["reasons"])
        self.assertIn("forced by user (-25)", st["reasons"])
        self.assertIsNone(self.stage(self.report(), "deploy")["score"])   # did not run: shown as —
        self.assertIn("—", self.run_state("telemetry", "report").stdout)

    def test_score_drop_and_unpassed_cap(self) -> None:
        self.ev("session_start", trigger="usability")
        self.ev("score", scope="ux", kind="gate", overall=47, verdict="fail")
        self.ev("score", scope="ux", kind="gate", overall=40, verdict="fail")
        self.run_state("review", "ux", "fail", "--score", "40", "--count-run")
        st = self.stage(self.report(), "usability")
        self.assertIn("score dropped 1x (-10)", st["reasons"])
        self.assertLessEqual(st["score"], 60)

    def test_exports_never_overwrite(self) -> None:
        self.ev("skill_end", skill="qa", status="ok")
        self.run_state("telemetry", "export", "--stamp", "20261118-120000")
        self.run_state("telemetry", "export", "--stamp", "20261118-120000")
        names = sorted(x.name for x in (self.root / ".dev" / "feedback").glob("telemetry-export-*.json"))
        self.assertEqual(names, ["telemetry-export-20261118-120000-2.json", "telemetry-export-20261118-120000.json"])

    def test_report_has_no_project_strings(self) -> None:
        self.run_state("add-task", "--milestone", "M1", "--type", "fix", "--title", "Qwertzu flow", "--acceptance", "Qwertzu ok")
        self.run_state("start", "T-001")
        self.run_state("feedback", "--improve", "qa:auditors repeat low findings")
        out = self.run_state("telemetry", "report", "--json").stdout
        self.assertNotIn("Qwertzu", out)
        self.assertNotIn("demo", out)
        self.assertIn("Session log:", self.run_state("status").stdout)

    def test_memory_archive_like_session(self) -> None:
        self.ev("session_start", trigger="autopilot")
        for sc in (30, 35):
            self.run_state("review", "design", "fail", "--score", str(sc), "--count-run")
        self.run_state("review", "design", "pass", "--score", "41", "--force", "--count-run")
        for _ in range(4):
            self.run_state("gate", "M1", "pending", "--score", "70", "--count-run")
        self.run_state("gate", "M1", "passed", "--score", "91", "--count-run")
        self.ev("score", scope="ux", kind="gate", overall=40, verdict="fail")
        self.ev("score", scope="ux", kind="gate", overall=47, verdict="fail")
        rep = self.report()
        self.assertEqual(self.stage(rep, "design")["score"], 55)        # 3 rounds (-20), forced user (-25)
        self.assertEqual(self.stage(rep, "qa")["score"], 40)            # 5 rounds: -40 and 2 beyond the limit -20
        self.assertLessEqual(self.stage(rep, "usability")["score"], 100)
        self.assertIsNotNone(rep["report"]["overall"])


class TestIssues(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def milestones(self) -> list[str]:
        return sorted(self.state()["milestones"])

    def add(self, *args: str, expect: int = 0) -> str:
        return self.run_state("add-issue", *args, expect=expect).stdout.splitlines()[0] if expect == 0 else ""

    def test_create_validate_and_markdown(self) -> None:
        iid = self.add("--type", "bug", "--class", "standard", "--title", "Save button ignores input", "--severity", "medium", "--effort", "S")
        self.assertEqual(iid, "I-001")
        self.add("--type", "bug", "--class", "nope", "--title", "x", expect=1)
        self.add("--type", "change", "--class", "standard", "--title", "x", expect=1)          # change goes with class change
        self.add("--type", "bug", "--class", "expedite", "--title", "x", "--severity", "low", expect=1)  # expedite criterion
        self.add("--type", "improvement", "--class", "expedite", "--title", "x", expect=1)
        md = (self.root / ".dev" / "issues.md").read_text(encoding="utf-8")
        self.assertIn("| I-001 | standard | bug | medium | S | open |", md)
        self.run_state("issue", "I-001", "--status", "wontfix")
        self.assertIn("| I-001 | wontfix |", (self.root / ".dev" / "issues.md").read_text(encoding="utf-8"))

    def test_pull_respects_buffer_and_order_and_never_creates_milestones(self) -> None:
        before = self.milestones()
        for title, cls, sev in (("low polish", "intangible", "low"), ("medium bug", "standard", "medium"),
                                ("high bug", "standard", "high"), ("another", "standard", "low")):
            self.add("--type", "bug" if "bug" in title else "improvement", "--class", cls, "--title", title, "--severity", sev)
        out = self.run_state("pull-issues", "M2").stdout     # M2 has 1 planned task -> ceil(20%) = 1
        self.assertIn("pulled 1: I-003", out)                # standard, highest severity first
        self.assertIn("stay in the queue", out)
        self.run_state("pull-issues", "M2")
        self.assertEqual(sum(1 for v in self.state()["tasks"].values() if v["milestone"] == "M2"), 2)  # buffer full: no more
        self.run_state("pull-issues", "M9", expect=1)
        self.run_state("cooldown", "M1")                     # off by default
        self.assertEqual(self.milestones(), before)

    def test_hotfix_lane_priority_gate_and_wip(self) -> None:
        self.add("--type", "bug", "--class", "expedite", "--title", "crash", "--severity", "critical")
        self.run_state("add-task", "--milestone", "M2", "--title", "fix crash", "--type", "fix", "--issue", "I-001", "--lane", "hotfix")
        self.assertIn("T-004", self.run_state("next").stdout)       # ahead of M1 tasks, despite M1 gate pending
        self.run_state("start", "T-004")
        self.assertEqual(self.state()["issues"]["I-001"]["status"], "in_progress")
        self.add("--type", "bug", "--class", "expedite", "--title", "crash 2", "--severity", "high")
        self.run_state("add-task", "--milestone", "M2", "--title", "fix 2", "--type", "fix", "--issue", "I-002", "--lane", "hotfix", expect=1)
        out = self.run_state("done", "T-004", "--commit", "abc").stdout
        self.assertIn("qa --scope T-004", out)
        self.assertEqual(self.state()["issues"]["I-001"]["status"], "done")

    def test_cooldown_takes_small_items_into_next_milestone(self) -> None:
        self.run_state("set", "autonomy.cooldown", json.dumps({"enabled": True, "max_tasks": 1}))
        self.add("--type", "improvement", "--class", "intangible", "--title", "tiny", "--severity", "low", "--effort", "S")
        self.add("--type", "improvement", "--class", "intangible", "--title", "tiny 2", "--severity", "low", "--effort", "S")
        self.add("--type", "improvement", "--class", "intangible", "--title", "big", "--severity", "low", "--effort", "L")
        self.run_state("cooldown", "M1", expect=1)                  # gate of M1 not passed yet
        for tid in ("T-001", "T-002"):
            self.run_state("start", tid)
            self.run_state("done", tid)
        self.run_state("gate", "M1", "passed", "--score", "90")
        self.run_state("cooldown", "M1")
        cool = [k for k, v in self.state()["tasks"].items() if v.get("lane") == "cooldown"]
        self.assertEqual(len(cool), 1)                               # max_tasks
        self.assertEqual(self.state()["tasks"][cool[0]]["milestone"], "M2")
        self.assertEqual(self.run_state("next").stdout.split()[0], cool[0])   # cool-down first in M2
        self.assertEqual(self.state()["issues"]["I-003"]["status"], "open")  # effort L stays queued

    def test_backlog_aggregates_and_status_line(self) -> None:
        self.add("--type", "bug", "--class", "standard", "--title", "queued bug", "--severity", "medium")
        self.run_state("add-question", "Which currency?", "--skill", "prd")
        d = self.root / ".dev" / "qa" / "M1"
        d.mkdir(parents=True)
        (d / "findings-round-2.json").write_text(json.dumps({"findings": [{"id": "F-003", "severity": "medium", "title": "x"}],
                                                             "deferred": [{"id": "F-009", "severity": "low", "title": "y"}]}), encoding="utf-8")
        data = json.loads(self.run_state("backlog", "--json").stdout)
        self.assertEqual(data["queue"]["standard"], ["I-001"])
        self.assertEqual(data["open_questions"], 1)
        self.assertEqual({f["id"] for f in data["deferred_findings"]}, {"F-003", "F-009"})
        self.assertIn("M1", data["tasks"])
        self.assertNotIn("💡", self.run_state("backlog", "--json").stdout)
        self.assertIn("Issues: 0 hotfix · 1 queued (1 standard)", self.run_state("status").stdout)

    def test_telemetry_issue_event_has_no_title(self) -> None:
        self.add("--type", "bug", "--class", "standard", "--title", "Zquxv broken", "--severity", "low")
        log = (self.root / ".dev" / "telemetry.jsonl").read_text(encoding="utf-8")
        self.assertIn('"event": "issue"', log)
        self.assertIn('"issue": "I-001"', log)
        self.assertNotIn("Zquxv", log)


class TestTips(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def test_catalog_is_valid(self) -> None:
        cat = json.loads((Path(STATE).resolve().parents[1] / "shared" / "tips.json").read_text(encoding="utf-8"))["tips"]
        ids = [t["id"] for t in cat]
        self.assertEqual(len(ids), len(set(ids)))
        for t in cat:
            self.assertEqual(set(t) - {"id", "context", "en", "command"}, set(), f"{t['id']}: English only")
            self.assertTrue(t.get("en"), t["id"])
            self.assertLessEqual(len(t["en"]), 140, t["id"])

    def test_rotation_limit_off_and_reset(self) -> None:
        shown = [self.run_state("tip", "backlog").stdout.strip() for _ in range(5)]
        self.assertEqual(len([s for s in shown if s]), 4)       # 2 tips x 2 times each, then silence
        self.assertNotEqual(shown[0], shown[1])                  # least shown first: they alternate
        self.run_state("tips", "--reset")
        self.run_state("set", "autonomy.tips", "off")
        self.assertEqual(self.run_state("tip", "backlog").stdout.strip(), "")
        self.run_state("set", "autonomy.tips", "always")
        for _ in range(3):
            self.assertTrue(self.run_state("tip", "backlog").stdout.strip())
        self.run_state("set", "autonomy.tips", "loud", expect=1)

    def test_json_and_english_only(self) -> None:
        js = json.loads(self.run_state("tip", "status", "--json").stdout)
        self.assertEqual(set(js), {"id", "text", "command"})
        self.run_state("tip", "status", "--lang", "pt-BR", expect=2)  # no language option: tips are English
        self.assertIn("💡", self.run_state("add-issue", "--type", "bug", "--class", "standard", "--title", "t", "--severity", "low").stdout)


if __name__ == "__main__":
    unittest.main()
