"""dev-kit 3.0, phase 1 (foundation): reliable telemetry (item 0), scope freeze at QA (item 2), queue throughput
(item 3), release grouping review (item 6), fixes milestone ids M<k>.<i> (item 9) and request ids P-nnn (item 15).

Each acceptance criterion of the 3.0 specification for these items is one test (or a few) here.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
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
KIT = CORE.parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
HOOK = SCRIPTS / "dev_agent_hook.py"
sys.path.insert(0, str(SCRIPTS))

PLAN = """# Implementation plan — demo

## M1 — Skeleton
First slice.

### T-001 Scaffold
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-1: it runs
- test_notes: smoke
- files: app.py

### T-002 Form
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-2: a form
- test_notes: unit
- files: form.py

### T-003 List
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-3: a list
- test_notes: unit
- files: list.py

## M2 — Next
Second slice.

### T-004 Page
- status: todo
- deps: T-002
- type: feature
- acceptance:
  - AC-4: a page
- test_notes: unit
- files: page.py
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0, at: str | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env, **({"DEV_KIT_NOW": at} if at else {}))
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env=env)
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def state(self) -> dict:
        return json.loads((self.root / ".dev" / "state.json").read_text(encoding="utf-8"))

    def events(self) -> list[dict]:
        p = self.root / ".dev" / "telemetry.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def setup_plan(self, plan: str = PLAN) -> None:
        self.ds("init", "--language", "en", "--project", "demo")
        (self.root / ".dev" / "plan.md").write_text(plan, encoding="utf-8")
        self.ds("sync-plan")


# ------------------------------------------------------------------ item 0: telemetry

class TestTelemetrySchema(Base):
    def test_unknown_key_is_refused_with_the_accepted_keys(self) -> None:
        self.setup_plan()
        p = self.ds("event", "skill_start", "--set", "skill=qa", "--set", "colour=blue", expect=1)
        self.assertIn("'colour' is not allowed in skill_start events", p.stderr)
        self.assertIn("accepted keys:", p.stderr)
        self.assertIn("args_kind", p.stderr)

    def test_schema_file_is_the_allowlist(self) -> None:
        import dev_telemetry as tel
        doc = json.loads((CORE / "shared" / "telemetry-schema.json").read_text(encoding="utf-8"))
        self.assertEqual(tel.SCHEMA, doc["events"])
        for ev in ("agent_spawn", "agent_end", "telemetry_gap", "flow", "scope", "agent_result"):
            self.assertIn(ev, doc["events"])


class TestSkillDuration(Base):
    def test_duration_is_measured_by_the_script(self) -> None:
        self.setup_plan()
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1", at="2026-11-23T10:00:00Z")
        out = self.ds("event", "skill_end", "--set", "skill=qa", "--set", "scope=M1", "--set", "status=ok",
                      "--set", "duration_s=0", at="2026-11-23T10:07:30Z").stdout
        self.assertIn("450 s", out)
        end = [e for e in self.events() if e["event"] == "skill_end"][-1]
        self.assertEqual(end["duration_s"], 450)  # the 0 the skill sent is ignored

    def test_nested_runs_of_the_same_skill_pair_by_scope(self) -> None:
        self.setup_plan()
        self.ds("event", "skill_start", "--set", "skill=review", "--set", "scope=plan", at="2026-11-23T10:00:00Z")
        self.ds("event", "skill_start", "--set", "skill=review", "--set", "scope=prd", at="2026-11-23T10:01:00Z")
        self.ds("event", "skill_end", "--set", "skill=review", "--set", "scope=prd", "--set", "status=ok", at="2026-11-23T10:02:00Z")
        self.ds("event", "skill_end", "--set", "skill=review", "--set", "scope=plan", "--set", "status=ok", at="2026-11-23T10:05:00Z")
        ends = {e["scope"]: e["duration_s"] for e in self.events() if e["event"] == "skill_end"}
        self.assertEqual(ends, {"prd": 60, "plan": 300})

    def test_end_without_start_is_a_gap(self) -> None:
        self.setup_plan()
        out = self.ds("event", "skill_end", "--set", "skill=plan", "--set", "status=ok").stdout
        self.assertIn("telemetry_gap", out)
        ev = self.events()
        end = [e for e in ev if e["event"] == "skill_end"][-1]
        self.assertIn("duration_s", end)
        self.assertIsNone(end["duration_s"])
        self.assertEqual([e["kind"] for e in ev if e["event"] == "telemetry_gap"], ["skill_end_without_start"])


class TestAgentEventsFromHooks(Base):
    """A qa round with N auditors logs N agent_spawn and N agent_end with no instruction in the SKILL.md."""

    def hook(self, payload: dict) -> None:
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(self.root))
        p = subprocess.run([sys.executable, "-I", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_qa_auditors_are_logged_by_the_hooks(self) -> None:
        self.setup_plan()
        for t in ("T-001", "T-002", "T-003"):
            self.ds("done", t, "--force")
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        tdir = self.root / "transcripts" / "sess-1"
        (tdir / "subagents").mkdir(parents=True)
        main_tr = self.root / "transcripts" / "sess-1.jsonl"
        main_tr.write_text("", encoding="utf-8")
        auditors = ["dev-kit:code-reviewer", "dev-kit:security-auditor", "dev-kit:spec-tracer"]
        for n, ag in enumerate(auditors, 1):
            self.hook({"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "sess-1",
                       "tool_input": {"subagent_type": ag, "description": "M1 QA x", "prompt": f"Slot: {n}\nScope: M1\nAudit it."}})
        for n, ag in enumerate(auditors, 1):
            self.hook({"hook_event_name": "SubagentStart", "session_id": "sess-1", "agent_id": f"a{n}", "agent_type": ag,
                       "transcript_path": str(main_tr)})
        for n, ag in enumerate(auditors, 1):
            tr = tdir / "subagents" / f"agent-a{n}.jsonl"
            tr.write_text(json.dumps({"type": "assistant", "requestId": f"req{n}", "timestamp": "2026-11-23T10:00:00Z",
                                      "sessionId": "sess-1", "message": {"model": "claude-sonnet-5-5", "usage": {
                                          "input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}}}) + "\n",
                          encoding="utf-8")
            self.hook({"hook_event_name": "SubagentStop", "session_id": "sess-1", "agent_id": f"a{n}", "agent_type": ag,
                       "agent_transcript_path": str(tr)})
        ev = self.events()
        spawns = [e for e in ev if e["event"] == "agent_spawn"]
        ends = [e for e in ev if e["event"] == "agent_end"]
        self.assertEqual(len(spawns), 3)
        self.assertEqual(len(ends), 3)
        self.assertEqual({e["agent"] for e in spawns}, {"code-reviewer", "security-auditor", "spec-tracer"})
        for e in spawns:
            self.assertEqual((e["scope"], e["skill"], e["round"], e["source"]), ("M1", "qa", 1, "hook"))
            self.assertTrue(e.get("model"))
        spec = next(e for e in spawns if e["agent"] == "spec-tracer")
        self.assertEqual(spec["model"], "opus")  # from the agent's frontmatter
        for e in ends:
            self.assertEqual(e["tokens"], 115)
            self.assertIsNotNone(e.get("duration_s"))
        for sk in (KIT / "skills").glob("*/SKILL.md"):
            text = sk.read_text(encoding="utf-8")
            self.assertNotIn("agent_spawn", text, sk)
            self.assertNotIn("duration_s", text, sk)


class TestCycleInFeedback(Base):
    """A milestone with 3 rounds, 11 fixes and 13 deferred findings: final state 96, but the kit grade is < 100."""

    def test_two_readings(self) -> None:
        self.setup_plan()
        self.ds("event", "session_start", "--set", "trigger=qa")
        for t in ("T-001", "T-002", "T-003"):
            self.ds("start", t, "--force")
            self.ds("done", t, "--force")
        for n in range(1, 12):
            tid = self.ds("add-task", "--milestone", "M1", "--type", "fix", "--title", f"fix {n}",
                          "--source", f"qa/M1/report.md#F-{n:03d}").stdout.strip()
            self.ds("done", tid, "--force")
        qa = self.root / ".dev" / "qa" / "M1"
        qa.mkdir(parents=True)
        (qa / "findings-round-3.json").write_text(json.dumps({"findings": [
            {"id": f"F-{100 + i}", "severity": "medium", "title": "x"} for i in range(13)]}), encoding="utf-8")
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        for _ in range(2):
            self.ds("gate", "M1", "pending", "--count-run")
        self.ds("gate", "M1", "passed", "--score", "96", "--count-run")
        self.ds("event", "skill_end", "--set", "skill=qa", "--set", "scope=M1", "--set", "status=ok")
        flow = json.loads((qa / "flow.json").read_text(encoding="utf-8"))
        self.assertEqual((flow["qa_rounds"], flow["fix_tasks"], flow["deferred_open"], flow["score"]), (3, 11, 13, 96))
        self.assertIn("cycle_time_s", flow)
        self.assertIn("human_wait_s", flow)
        self.assertEqual([e for e in self.events() if e["event"] == "flow"][-1]["qa_rounds"], 3)
        text = self.ds("telemetry", "report").stdout
        self.assertIn("M1: final state 96 · cycle: 3 rounds, 11 fixes, 13 deferred", text)
        rep = json.loads(self.ds("telemetry", "report", "--json").stdout)["report"]
        qa_stage = next(s for s in rep["stages"] if s["stage"] == "qa")
        self.assertLess(qa_stage["score"], 100)
        self.assertLess(rep["cycles"][0]["cycle_grade"], 100)
        self.assertEqual(self.state()["milestones"]["M1"]["score"], 96)  # the gate's score is untouched


# ------------------------------------------------------------------ item 2: scope freeze

class TestFreeze(Base):
    def setUp(self) -> None:
        super().setUp()
        self.setup_plan()
        self.ds("set", "autonomy.issue_buffer_pct", "50")
        for t in ("T-001", "T-002", "T-003"):
            self.ds("done", t, "--force")
        self.iid = self.ds("add-issue", "--type", "improvement", "--class", "standard", "--severity", "medium",
                           "--title", "Better empty state").stdout.split()[0]
        self.ds("freeze", "M1")

    def test_frozen_milestone_takes_nothing_new(self) -> None:
        self.assertTrue(self.state()["milestones"]["M1"]["frozen_at"])
        out = self.ds("pull-issues", "M1").stdout
        self.assertIn("frozen", out)
        self.assertFalse(any(str(t.get("source") or "").startswith("issue:") for t in self.state()["tasks"].values()))
        p = self.ds("plan-apply", "--ops", json.dumps([{"op": "schedule_issue", "issue": self.iid, "milestone": "M1"}]), expect=1)
        self.assertIn("M1 is frozen since its QA began", p.stdout)
        self.assertIn("invalidates the audit of the files it touches", p.stdout)
        p = self.ds("plan-apply", "--ops", json.dumps([{"op": "move_task", "task": "T-004", "milestone": "M1"}]), expect=1)
        self.assertIn("frozen", p.stdout)
        p = self.ds("add-task", "--milestone", "M1", "--title", "late idea", expect=1)
        self.assertIn("--confirm-frozen", p.stderr)

    def test_exceptions_qa_fixes_current_expedite(self) -> None:
        self.ds("add-task", "--milestone", "M1", "--type", "fix", "--title", "qa fix", "--source", "qa/M1/report.md#F-001")
        cur = self.ds("add-issue", "--type", "bug", "--class", "current", "--severity", "medium", "--title", "bug").stdout.split()[0]
        self.ds("add-task", "--milestone", "M1", "--type", "fix", "--title", "bug", "--issue", cur)
        self.assertFalse(any(t.get("scope_after_freeze") for t in self.state()["tasks"].values()))

    def test_confirmed_item_counts_after_freeze(self) -> None:
        self.ds("plan-apply", "--ops", json.dumps([{"op": "schedule_issue", "issue": self.iid, "milestone": "M1", "confirm_frozen": True,
                                                    "force": True}]))
        tid = self.ds("add-task", "--milestone", "M1", "--title", "late", "--files", "late.py", "--confirm-frozen").stdout.strip()
        ts = self.state()["tasks"]
        self.assertTrue(ts[tid]["scope_after_freeze"])
        led = self.root / ".dev" / "run" / "ledger.jsonl"
        led.write_text(json.dumps({"key": "audit:code:late.py", "fp": "x", "result": "ok", "at": "2026-11-23T00:00:00Z"}) + "\n", encoding="utf-8")
        self.ds("done", tid, "--force")
        last = [json.loads(x) for x in led.read_text().splitlines()][-1]
        self.assertEqual((last["key"], last["result"]), ("audit:code:late.py", "dropped"))
        for t, v in self.state()["tasks"].items():
            if v["milestone"] == "M1" and v["status"] != "done":
                self.ds("done", t, "--force")
        self.ds("gate", "M1", "passed", "--score", "90")
        flow = json.loads((self.root / ".dev" / "qa" / "M1" / "flow.json").read_text(encoding="utf-8"))
        self.assertEqual(flow["scope_added_after_freeze"], 2)

    def test_freeze_is_idempotent_and_survives_a_failed_gate(self) -> None:
        first = self.state()["milestones"]["M1"]["frozen_at"]
        self.ds("gate", "M1", "pending", "--count-run")
        self.ds("freeze", "M1", at="2030-01-01T00:00:00Z")
        self.assertEqual(self.state()["milestones"]["M1"]["frozen_at"], first)


class TestParked(Base):
    def test_parked_never_enters_a_buffer(self) -> None:
        self.setup_plan()
        self.ds("set", "autonomy.issue_buffer_pct", "50")
        self.ds("set", "autonomy.cooldown", "on")
        iid = self.ds("add-issue", "--type", "improvement", "--class", "intangible", "--severity", "low", "--effort", "S",
                      "--title", "Coming soon page").stdout.split()[0]
        self.ds("issue", iid, "--status", "parked")
        self.ds("pull-issues", "M1")
        self.ds("pull-issues", "M2")
        for t in ("T-001", "T-002", "T-003"):
            self.ds("done", t, "--force")
        self.ds("gate", "M1", "passed", "--score", "90")
        self.ds("cooldown", "M1")
        bl = json.loads(self.ds("backlog", "--json").stdout)
        self.assertEqual(bl["parked"], [iid])
        self.assertFalse(any(str(t.get("source") or "") == f"issue:{iid}" for t in self.state()["tasks"].values()))
        self.assertNotIn(iid, [k for n in bl["needs"] for k in n.get("issues", [])])
        self.ds("issue", iid, "--status", "scheduled", expect=1)  # leaves parked only by opening it again
        self.ds("issue", iid, "--status", "open")


# ------------------------------------------------------------------ item 3: queue throughput

class TestQueue(Base):
    def test_class_is_checked_against_severity(self) -> None:
        self.setup_plan()
        p = self.ds("add-issue", "--type", "bug", "--class", "standard", "--severity", "low", "--title", "x", expect=1)
        self.assertIn("intangible", p.stderr)
        self.ds("add-issue", "--type", "bug", "--class", "intangible", "--severity", "high", "--title", "x", expect=1)
        iid = self.ds("add-issue", "--type", "bug", "--class", "standard", "--severity", "low", "--title", "x",
                      "--force-class", "user facing in the demo").stdout.split()[0]
        self.assertEqual(self.state()["issues"][iid]["class_reason"], "user facing in the demo")

    def test_small_milestone_keeps_a_buffer_slot(self) -> None:
        self.setup_plan()
        info = json.loads(self.ds("backlog", "--json").stdout)["buffer"]
        self.assertEqual((info["milestone"], info["capacity"]), ("M1", 1))  # 3 tasks × 20% → ceil 1, floor 1
        self.ds("set", "autonomy.queue.buffer_floor", "2")
        self.assertEqual(json.loads(self.ds("backlog", "--json").stdout)["buffer"]["capacity"], 2)
        self.ds("set", "autonomy.queue.buffer_floor", "99", expect=1)

    def test_queue_above_the_limit_offers_a_milestone_and_creates_nothing(self) -> None:
        self.setup_plan()
        for n in range(24):
            self.ds("add-issue", "--type", "improvement", "--class", "standard", "--severity", "medium", "--title", f"idea {n}")
        before = json.dumps(self.state()["milestones"])
        out = self.ds("status").stdout
        self.assertIn("Needs you: issue queue above the limit (24 > 15)", out)
        need = next(n for n in json.loads(self.ds("backlog", "--json").stdout)["needs"] if n["kind"] == "queue_over_limit")
        self.assertEqual(need["milestone"], "M3")
        self.assertEqual(len(need["issues"]), 12)
        self.assertEqual(need["draft"]["ops"][0], {"op": "new_milestone", "milestone": "M3", "title": "Issues"})
        self.assertEqual(json.dumps(self.state()["milestones"]), before)  # nothing created
        self.ds("plan-apply", "--ops", json.dumps(need["draft"]["ops"]))  # the user's send
        self.assertIn("M3", self.state()["milestones"])
        self.assertEqual(sum(1 for v in self.state()["tasks"].values() if v["milestone"] == "M3"), 12)

    def test_aging_issue_asks_for_a_decision(self) -> None:
        self.setup_plan()
        iid = self.ds("add-issue", "--type", "improvement", "--class", "standard", "--severity", "medium", "--title", "old").stdout.split()[0]
        self.ds("set", "autonomy.queue.aging_milestones", "1")
        self.ds("set", "autonomy.issue_buffer_pct", "0")
        for t in ("T-001", "T-002", "T-003"):
            self.ds("done", t, "--force")
        self.ds("gate", "M1", "passed", "--score", "90")
        need = [n for n in json.loads(self.ds("backlog", "--json").stdout)["needs"] if n["kind"] == "issue_aging"]
        self.assertEqual([(n["issue"], n["actions"]) for n in need], [(iid, ["schedule_next", "park", "wontfix"])])
        self.ds("plan-apply", "--ops", json.dumps([{"op": "set_issue_status", "issue": iid, "status": "parked"}]))
        self.assertEqual(self.state()["issues"][iid]["status"], "parked")


# ------------------------------------------------------------------ item 6: release grouping in the plan review

class TestReleaseChecklist(unittest.TestCase):
    def test_four_release_rules(self) -> None:
        text = (CORE / "shared" / "checklists" / "requirements-review.md").read_text(encoding="utf-8")
        sec = text[text.index("**Releases**"):]
        for rule, sev in (("Complete journey", "`high`"), ("Risk ends a release", "`medium`"),
                          ("No phase milestones", "`medium`"), ("Size", "`medium`")):
            line = next(x for x in sec.splitlines() if rule in x)
            self.assertIn(sev, line)
        self.assertIn("release check", sec)
        self.assertIn("No phase milestones", (KIT / "skills" / "plan" / "SKILL.md").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ item 9: fixes milestone M<k>.<i>

RPLAN = """# Implementation plan — demo

## R1 — One
## M1 — A
### T-001 A
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-1 a
- test_notes: t
- files: a.py

## M2 — B
### T-002 B
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-2 b
- test_notes: t
- files: b.py

## R2 — Two
## M3 — C
### T-003 C
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-3 c
- test_notes: t
- files: c.py

## M4 — D
### T-004 D
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-4 d
- test_notes: t
- files: d.py
"""


class TestFixesMilestoneId(Base):
    def test_rejection_creates_suffixed_milestone_that_runs_before_the_next_release(self) -> None:
        import dev_state as ds
        self.assertEqual(sorted(["M6", "M5.2", "M5", "M10", "M5.1"], key=ds.mkey), ["M5", "M5.1", "M5.2", "M6", "M10"])
        self.setup_plan(RPLAN)
        for t, m in (("T-001", "M1"), ("T-002", "M2")):
            self.ds("done", t, "--force")
            self.ds("gate", m, "passed", "--score", "90")
        self.ds("release-submit", "R1")
        out = self.ds("release-decide", "R1", "--reject", "--feedback", "Fix the error text").stdout
        self.assertIn("M2.1 R1 · Fixes 1", out)
        s = self.state()
        self.assertEqual(s["release_plan"][0]["milestones"], ["M1", "M2", "M2.1"])
        self.assertEqual(s["milestones"]["M2.1"]["title"], "R1 · Fixes 1")
        order = json.loads(self.ds("status", "--json").stdout)
        self.assertEqual(self.ds("next").stdout.split()[0], "T-005")
        plan = (self.root / ".dev" / "plan.md").read_text(encoding="utf-8")
        self.assertLess(plan.index("## M2.1 — R1 · Fixes 1"), plan.index("## R2 — Two"))
        # the second rejection takes the next suffix
        self.ds("done", "T-005", "--force")
        self.ds("gate", "M2.1", "passed", "--score", "90")
        self.ds("release-submit", "R1")
        self.assertIn("M2.2 R1 · Fixes 2", self.ds("release-decide", "R1", "--reject", "--feedback", "Again").stdout)
        self.assertEqual(self.state()["release_plan"][0]["milestones"], ["M1", "M2", "M2.1", "M2.2"])
        # new milestones still take the next whole number
        self.assertIn("M5", self.ds("plan-apply", "--dry-run", "--ops", json.dumps([{"op": "new_milestone", "milestone": "M5", "title": "E"}])).stdout)
        self.assertTrue(order["milestones"])

    def test_ids_are_accepted_everywhere(self) -> None:
        import dev_telemetry as tel
        import dev_worker as dw
        self.assertTrue(tel.ID_RE.match("M5.1"))
        dw.validate("run", {"command": "/dev-kit:qa M5.1"})
        dw.validate("plan_draft", {"ops": [{"op": "move_task", "task": "T-001", "milestone": "M5.1"}]})
        js = (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8")
        self.assertIn(r"M\d{1,3}(?:\.\d{1,2})?|R\d{1,3}", js)


# ------------------------------------------------------------------ item 15: P-nnn requests, "Round N"

class TestRequestIds(Base):
    def test_new_requests_are_p_and_old_r_files_are_shown_as_p(self) -> None:
        import dev_worker as dw
        self.setup_plan()
        inbox = self.root / ".dev" / "run" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "R-001.json").write_text(json.dumps({"id": "R-001", "ts": "2026-11-20T00:00:00Z", "action": "run",
                                                       "args": {"command": "/dev-kit:status"}, "by": "board"}), encoding="utf-8")
        old = dw.item(self.root, "P-001")
        self.assertEqual((old["id"], old["status"]), ("P-001", "pending"))
        new = dw.submit(self.root, "run", {"command": "/dev-kit:status"})
        self.assertEqual(new["id"], "P-002")
        self.assertTrue((inbox / "P-002.json").exists())
        self.assertEqual([x["id"] for x in dw.items(self.root)], ["P-001", "P-002"])
        dw.cancel(self.root, "P-001")
        self.assertTrue((inbox / "R-001.cancel").exists())
        self.assertEqual(dw.item(self.root, "R-001")["status"], "cancelled")

    def test_no_release_like_ids_for_rounds_or_requests_in_the_board(self) -> None:
        import re
        js = (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"`R\$\{(r\.n|x\.round)\}", js))
        self.assertIn("`Round ${r.n}", js)


class TestHotfixDropped(Base):
    def test_dropped_hotfix_leaves_needs_you(self) -> None:
        self.setup_plan()
        iid = self.ds("add-issue", "--type", "bug", "--class", "expedite", "--severity", "high", "--title", "crash").stdout.split()[0]
        tid = self.ds("add-task", "--milestone", "M1", "--type", "fix", "--title", "crash", "--issue", iid, "--lane", "hotfix").stdout.strip()
        self.assertEqual(json.loads(self.ds("backlog", "--json").stdout)["hotfix_open"], [tid])
        self.ds("drop", tid, "--reason", "not needed")
        self.assertEqual(json.loads(self.ds("backlog", "--json").stdout)["hotfix_open"], [])


if __name__ == "__main__":
    unittest.main()
