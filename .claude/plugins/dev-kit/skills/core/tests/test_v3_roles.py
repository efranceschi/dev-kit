"""dev-kit 3.0.0-alpha.3: adversarial challenge of blocking findings (item 17), the verified facts registry (item 18),
the file fence of kit agents (item 19) and lessons of method per role (item 20).

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
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
SCORE = SCRIPTS / "dev_score.py"
FENCE = SCRIPTS / "dev_fence.py"
sys.path.insert(0, str(SCRIPTS))

PLAN = """# Implementation plan — demo

## M1 — Checkout
A user pays.
- exit_check: cmd: make smoke

### T-010 Login form
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-4: the login form rejects a bad password
- test_notes: unit
- files: src/a.ts

### T-011 Orders
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-5: orders list
- test_notes: unit
- files: src/orders/

"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
        self.ds("init", "--language", "en", "--project", "demo")
        (self.dev / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                           capture_output=True, text=True, cwd=self.root, env=self.env)
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def sc(self, *args: str) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(SCORE), *args], capture_output=True, text=True, cwd=self.root, env=self.env)
        self.assertIn(p.returncode, (0, 1), msg=f"{args}\n{p.stdout}\n{p.stderr}")  # 1 = the scope fails
        return p

    def state(self) -> dict:
        return json.loads((self.dev / "state.json").read_text(encoding="utf-8"))

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()


# ------------------------------------------------------------------ item 17: challenge of blocking findings

class TestChallenge(Base):
    def setUp(self) -> None:
        super().setUp()
        (self.root / "src").mkdir()
        (self.root / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
        (self.root / "src" / "auth.ts").write_text("export const t = 1;\n", encoding="utf-8")
        self.qa = self.dev / "qa" / "M1"
        (self.qa / "raw").mkdir(parents=True)
        self.raw = {
            "code-reviewer": {"auditor": "code-reviewer", "findings": [
                {"id": "F-001", "severity": "high", "title": "Race in the login handler", "file": "src/a.ts", "line": 1,
                 "evidence": "src/a.ts:1 two awaits", "recommendation": "lock it"}]},
            "security-auditor": {"auditor": "security-auditor", "findings": [
                {"id": "F-001", "severity": "critical", "title": "Token signed with a weak key", "file": "src/auth.ts", "line": 1,
                 "evidence": "src/auth.ts:1", "recommendation": "rotate"}]},
        }
        for k, v in self.raw.items():
            (self.qa / "raw" / f"{k}.json").write_text(json.dumps(v), encoding="utf-8")

    def run_round(self, challenges: bool = False) -> tuple[dict, dict]:
        inputs = [str(p) for p in sorted((self.qa / "raw").glob("*.json"))]
        extra = ["--challenges", str(self.qa / "challenges.json")] if challenges else []
        self.sc("score", "--scope", "M1", "--kind", "gate", "--root", str(self.root), "--out", str(self.qa / "scores.json"), *extra, *inputs)
        self.sc("consolidate", "--scope", "M1", "--round", "1", "--out-dir", str(self.qa), "--root", str(self.root), *extra, *inputs)
        return (json.loads((self.qa / "scores.json").read_text(encoding="utf-8")),
                json.loads((self.qa / "findings.json").read_text(encoding="utf-8")))

    def fid(self, findings: dict, auditor: str) -> str:
        return next(f["id"] for f in findings["findings"] if f["auditor"] == auditor)

    def record(self, fid: str, verdict: str, challenger: str, model: str, expect: int = 0, **extra: object) -> subprocess.CompletedProcess:
        f = self.qa / "challenges" / f"{fid}.json"
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps({"finding": fid, "verdict": verdict, "challenger": challenger, "model": model,
                                 "evidence": "ran npm test -- login: 40 runs, no interleaving; src/a.ts:1 is synchronous", **extra}),
                     encoding="utf-8")
        return self.ds("challenge", "record", "M1", "--from", str(f), expect=expect)

    def dim(self, scores: dict, name: str) -> dict:
        dims = scores.get("dimensions") or {}
        return dims[name] if isinstance(dims, dict) else next(d for d in dims if d.get("dimension") == name)

    def test_disputed_high_finding_gets_no_fix_task_is_contested_and_does_not_penalise(self) -> None:
        before, findings = self.run_round()
        fid = self.fid(findings, "code-reviewer")
        ch = json.loads(self.ds("challenger", "M1", fid, "--json").stdout)
        self.assertNotEqual(ch["challenger"]["agent"], "code-reviewer")
        self.record(fid, "dispute", ch["challenger"]["agent"], ch["challenger"]["model"])
        after, findings2 = self.run_round(challenges=True)
        self.assertNotIn(fid, [f["id"] for f in findings2["findings"]])  # no fix task is made from it
        self.assertIn(fid, [f["id"] for f in findings2.get("disputed") or []])
        self.assertGreater(self.dim(after, "code")["score"], self.dim(before, "code")["score"])
        dc = json.loads(self.ds("debt", "status", "--json").stdout)
        self.assertGreaterEqual(dc["total"], 1)  # it counts toward the debt cap
        tmpl = (CORE / "shared" / "templates" / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("## Contested", tmpl)

    def test_disputed_security_critical_keeps_blocking_and_asks_the_user(self) -> None:
        _, findings = self.run_round()
        fid = self.fid(findings, "security-auditor")
        ch = json.loads(self.ds("challenger", "M1", fid, "--json").stdout)["challenger"]
        p = self.record(fid, "dispute", ch["agent"], ch["model"])
        self.assertIn("still blocking", p.stdout)
        rec = json.loads((self.qa / "challenges.json").read_text(encoding="utf-8"))[fid]
        self.assertRegex(rec["question"], r"^Q-\d+")
        self.assertIn("keep blocking", (self.dev / "open-questions.md").read_text(encoding="utf-8"))
        after, findings2 = self.run_round(challenges=True)
        self.assertIn(fid, [f["id"] for f in findings2["findings"]])
        self.assertFalse(after.get("pass", after.get("passed", False)))
        self.assertTrue(any("disputed" in r for r in after.get("reasons") or []), after.get("reasons"))

    def test_challenger_is_never_the_authors_agent_and_model(self) -> None:
        _, findings = self.run_round()
        fid = self.fid(findings, "code-reviewer")
        p = self.record(fid, "dispute", "code-reviewer", "sonnet", expect=1)
        self.assertIn("cannot be the author's own agent and model", p.stderr)
        self.record(fid, "agree", "code-reviewer", "opus")  # same role on another family is allowed
        import dev_state as dsm
        f = {"auditor": "docs-reviewer", "dimension": "docs", "severity": "high"}
        store = dsm.Store(self.root)
        store.load()
        ch = dsm.pick_challenger(store, "M1", f)
        self.assertEqual(ch["agent"], "docs-reviewer")
        self.assertNotEqual(dsm._family(ch["model"]), dsm._family(dsm.author_model(store, "M1", "docs-reviewer")))

    def test_a_change_to_the_judged_files_reopens_the_finding(self) -> None:
        _, findings = self.run_round()
        fid = self.fid(findings, "code-reviewer")
        self.record(fid, "dispute", "test-auditor", "sonnet")
        _, f2 = self.run_round(challenges=True)
        self.assertIn(fid, [f["id"] for f in f2.get("disputed") or []])
        (self.root / "src" / "a.ts").write_text("export const a = 2;\n", encoding="utf-8")
        _, f3 = self.run_round(challenges=True)
        self.assertIn(fid, [f["id"] for f in f3["findings"]])

    def test_refine_rewrites_the_severity(self) -> None:
        _, findings = self.run_round()
        fid = self.fid(findings, "code-reviewer")
        self.record(fid, "refine", "test-auditor", "sonnet", expect=1)  # refine needs the new severity
        self.record(fid, "refine", "test-auditor", "sonnet", refined={"severity": "medium"})
        _, f2 = self.run_round(challenges=True)
        f = next(x for x in f2["findings"] + (f2.get("deferred") or []) if x["id"] == fid)
        self.assertEqual(f["severity"], "medium")


# ------------------------------------------------------------------ item 18: verified facts

class TestFacts(Base):
    def add(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        return self.ds("fact", "add", *args, expect=expect)

    def test_a_fact_without_evidence_is_refused(self) -> None:
        p = self.add("--text", "Sessions last 15 minutes", "--origin", "T-010", expect=1)
        self.assertIn("--evidence", p.stderr)

    def test_a_fact_with_an_api_token_or_personal_data_is_refused(self) -> None:
        for text in ("The key is AKIAABCDEFGHIJKLMNOP", "api_key=sk_live_abcdefghijklmnop", "Admin is maria@example.com"):
            p = self.add("--text", text, "--evidence", "src/a.ts:3", "--origin", "T-010", expect=1)
            self.assertIn("refused", p.stderr)
        self.assertFalse((self.dev / "facts.md").exists())

    def test_brief_lists_the_facts_tagged_with_the_tasks_files(self) -> None:
        self.add("--text", "Login throttles after 5 attempts", "--evidence", "src/a.ts:40", "--files", "src/a.ts", "--origin", "T-010")
        self.add("--text", "Orders are paginated by 50", "--evidence", "src/orders/list.ts:9", "--files", "src/orders/list.ts", "--origin", "T-011")
        self.add("--text", "Bad password message is locked copy", "--evidence", "ux-flows.md 7.1", "--acs", "AC-4", "--origin", "user")
        b = self.ds("brief", "T-010").stdout
        self.assertIn("Login throttles after 5 attempts", b)
        self.assertIn("Bad password message is locked copy", b)  # tagged with the task's AC
        self.assertNotIn("paginated", b)
        self.assertIn("paginated", self.ds("brief", "T-011").stdout)  # a folder covers what is under it
        md = (self.dev / "facts.md").read_text(encoding="utf-8")
        self.assertRegex(md, r"- K-001 Login throttles after 5 attempts — evidence: src/a.ts:40 @\S+ — \d{4}-\d\d-\d\d, T-010 \[files: src/a.ts\]")

    def test_brief_lists_at_most_10_newest_first(self) -> None:
        for i in range(12):
            self.add("--text", f"Fact number {i}", "--evidence", f"src/a.ts:{i}", "--files", "src/a.ts", "--origin", "T-010")
        lines = [ln for ln in self.ds("brief", "T-010").stdout.splitlines() if "Fact number" in ln]
        self.assertEqual(len(lines), 10)
        self.assertIn("Fact number 11", lines[0])

    def test_a_stale_fact_stays_struck_through(self) -> None:
        self.add("--text", "Tokens expire after 15 min", "--evidence", "src/a.ts:42", "--files", "src/a.ts", "--origin", "T-010")
        self.ds("fact", "stale", "K-001", "--by", "T-011", "--evidence", "src/a.ts:50 now says 30 min")
        md = (self.dev / "facts.md").read_text(encoding="utf-8")
        self.assertIn("~~K-001 Tokens expire after 15 min", md)
        self.assertIn("→ contradicted by T-011 (src/a.ts:50 now says 30 min", md)
        self.assertNotIn("Tokens expire", self.ds("brief", "T-010").stdout)
        self.assertEqual(json.loads(self.ds("fact", "list", "--all", "--json").stdout)[0]["id"], "K-001")
        self.assertEqual(json.loads(self.ds("fact", "list", "--json").stdout), [])

    def test_board_snapshot_has_the_facts(self) -> None:
        import dev_board
        self.add("--text", "Login throttles after 5 attempts", "--evidence", "src/a.ts:40", "--files", "src/a.ts", "--origin", "T-010")
        snap = dev_board.build_state(self.root)
        self.assertEqual(snap["facts"][0]["id"], "K-001")
        js = (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8")
        self.assertIn("function renderFacts", js)


# ------------------------------------------------------------------ item 19: file fence

class TestFence(Base):
    def setUp(self) -> None:
        super().setUp()
        import dev_fence
        self.fence = dev_fence
        run = self.dev / "run"
        run.mkdir(exist_ok=True)
        self.ds("slot", "open", "1", "--task", "T-010")
        (run / "agent-slots.json").write_text(json.dumps({"a1": {"slot": 1, "agent": "implementer"}}), encoding="utf-8")

    def call(self, tool: str, **ti: str) -> dict | None:
        return self.fence.decide({"hook_event_name": "PreToolUse", "agent_id": "a1", "agent_type": "dev-kit:implementer",
                                  "tool_name": tool, "tool_input": ti, "cwd": str(self.root)}, self.root)

    def test_edit_outside_the_tasks_files_is_denied_and_its_test_is_allowed(self) -> None:
        out = self.call("Edit", file_path=str(self.root / "src" / "b.ts"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Outside the files of T-010", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.call("Edit", file_path=str(self.root / "src" / "a.test.ts")))
        self.assertIsNone(self.call("Write", file_path=str(self.root / "src" / "a.ts")))
        self.assertIsNone(self.call("Write", file_path=str(self.root / "changelog.d" / "T-010.md")))
        self.assertIsNotNone(self.call("Write", file_path=str(self.root / ".dev" / "state.json")))
        ev = [json.loads(x) for x in (self.dev / "telemetry.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertTrue(any(e["event"] == "fence_deny" and e.get("reason") == "outside_files" for e in ev))

    def test_git_commit_no_verify_is_denied(self) -> None:
        out = self.call("Bash", command="git commit --no-verify -m wip")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        for cmd in ("git push --force origin main", "git rebase -i HEAD~2", "git reset --hard HEAD~1", "git commit -nm x"):
            self.assertIsNotNone(self.call("Bash", command=cmd), cmd)
        self.assertIsNone(self.call("Bash", command="git commit -m 'feat: login'"))
        self.assertIsNone(self.call("Bash", command="npm test"))

    def test_the_main_session_and_a_closed_slot_are_not_fenced(self) -> None:
        main = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(self.root / "src" / "b.ts")}}
        self.assertIsNone(self.fence.decide(main, self.root))
        self.ds("slot", "close", "1")
        self.assertIsNone(self.call("Edit", file_path=str(self.root / "src" / "b.ts")))

    def test_the_hook_script_prints_the_denial(self) -> None:
        payload = {"hook_event_name": "PreToolUse", "agent_id": "a1", "tool_name": "Edit",
                   "tool_input": {"file_path": str(self.root / "src" / "b.ts")}, "cwd": str(self.root)}
        p = subprocess.run([sys.executable, "-I", str(FENCE)], input=json.dumps(payload), capture_output=True, text=True,
                           env={**self.env, "CLAUDE_PROJECT_DIR": str(self.root)})
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        hooks = json.loads((CORE.parent.parent / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("dev_fence.py", json.dumps(hooks["hooks"]["PreToolUse"]))

    def test_slot_check_refuses_a_diff_outside_the_files(self) -> None:
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / "src").mkdir()
        (self.root / "src" / "a.ts").write_text("1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        base = self.git("rev-parse", "HEAD")
        (self.root / "src" / "a.ts").write_text("2\n", encoding="utf-8")
        (self.root / "src" / "a.test.ts").write_text("t\n", encoding="utf-8")
        self.ds("slot", "check", "1", "--since", base)
        (self.root / "src" / "b.ts").write_text("sed -i\n", encoding="utf-8")
        p = self.ds("slot", "check", "1", "--since", base, expect=1)
        self.assertIn("src/b.ts", p.stdout + p.stderr)


# ------------------------------------------------------------------ item 20: lessons per role

class TestLessons(Base):
    def events(self, rows: list[dict]) -> None:
        import dev_telemetry as tel
        for r in rows:
            tel.safe_emit(self.dev, r.pop("event"), r)

    def test_high_dispute_rate_in_two_milestones_proposes_a_lesson_and_the_approved_one_reaches_the_prompt(self) -> None:
        rows = []
        for m in ("M1", "M2"):
            for i, verdict in enumerate(("dispute", "dispute", "agree")):
                rows.append({"event": "challenge", "scope": m, "finding": f"F-00{i + 1}", "auditor": "code-reviewer",
                             "challenger": "test-auditor", "model": "sonnet", "verdict": verdict, "dimension": "code", "severity": "high"})
        self.events(rows)
        sug = json.loads(self.ds("lesson", "suggest", "--json").stdout)
        cr = [s for s in sug if s["agent"] == "code-reviewer"]
        self.assertEqual(len(cr), 1)
        self.assertIn("4/6", cr[0]["evidence"])
        needs = json.loads(self.ds("backlog", "--json").stdout)["needs"]
        self.assertTrue(any(n["kind"] == "lesson" and n["agent"] == "code-reviewer" for n in needs))
        self.ds("lesson", "add", "code-reviewer", cr[0]["text"])
        self.assertIn(cr[0]["text"], self.ds("lesson", "show", "code-reviewer").stdout)
        self.assertFalse([s for s in json.loads(self.ds("lesson", "suggest", "--json").stdout) if s["agent"] == "code-reviewer"])
        self.ds("lesson", "add", "implementer", "Run the login tests before reporting")
        self.assertIn("Run the login tests before reporting", self.ds("brief", "T-010").stdout)

    def test_one_milestone_above_40_percent_is_not_enough(self) -> None:
        self.events([{"event": "challenge", "scope": "M1", "finding": "F-001", "auditor": "code-reviewer", "challenger": "test-auditor",
                      "model": "sonnet", "verdict": "dispute", "dimension": "code", "severity": "high"}])
        self.assertEqual(json.loads(self.ds("lesson", "suggest", "--json").stdout), [])

    def test_the_ninth_lesson_is_refused(self) -> None:
        for i in range(8):
            self.ds("lesson", "add", "code-reviewer", f"Lesson {i}")
        p = self.ds("lesson", "add", "code-reviewer", "One more", expect=1)
        self.assertIn("consolidate", p.stderr)
        self.ds("lesson", "rm", "code-reviewer", "1")
        self.ds("lesson", "add", "code-reviewer", "Merged lesson")
        self.assertEqual(len((self.dev / "lessons" / "code-reviewer.md").read_text(encoding="utf-8").split("\n- ")) - 1, 8)

    def test_unknown_agent_and_board_request_are_validated(self) -> None:
        self.ds("lesson", "add", "nobody", "x", expect=1)
        import dev_worker as dw
        ok = dw.validate("lesson_decision", {"agent": "code-reviewer", "signal": "dispute_rate", "decision": "approve", "text": "Reproduce first"})
        self.assertEqual(ok["decision"], "approve")
        with self.assertRaises(dw.Invalid):
            dw.validate("lesson_decision", {"agent": "code-reviewer", "signal": "dispute_rate", "decision": "approve"})
        self.ds("lesson", "dismiss", "code-reviewer", "dispute_rate")
        self.assertIn("code-reviewer:dispute_rate", self.state()["lessons_dismissed"])


if __name__ == "__main__":
    unittest.main()
