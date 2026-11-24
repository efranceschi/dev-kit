"""dev-kit 3.0, phase 4 (board): delivery forecast (item 13), actions on every Needs-you item (item 16), the board
cleanup (item 15) and the board in the user's language (item 14).

Each acceptance criterion of the 3.0 specification for these items is one test (or a few) here.
Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p 'test_v3_*.py' -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SCRIPTS = CORE / "scripts"
STATE = SCRIPTS / "dev_state.py"
BOARD = CORE / "shared" / "board"
sys.path.insert(0, str(SCRIPTS))


def task(n: int, ac: int, files: str) -> str:
    return (f"### T-{n:03d} Step {n}\n- status: todo\n- deps: \n- type: feature\n- acceptance:\n  - AC-{ac}: step {n} works\n"
            f"- test_notes: unit\n- files: {files}\n\n")


PLAN = ("# Implementation plan — shop\n\n## R1 — First sale\n\n"
        + "".join(f"## M{m} — Part {m}\nPart {m}.\n\n" + task(2 * m - 1, 2 * m - 1, f"src/a{m}.py") + task(2 * m, 2 * m, f"src/b{m}.py")
                  for m in (1, 2, 3))
        + "## R2 — More\n\n"
        + "".join(f"## M{m} — Part {m}\nPart {m}.\n\n" + task(2 * m - 1, 2 * m - 1, f"src/a{m}.py") + task(2 * m, 2 * m, f"src/b{m}.py")
                  for m in (4, 5)))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION", "DEV_KIT_CLAUDE")}
        self.env["DEV_KIT_NOW"] = "2026-11-23T12:00:00Z"
        self.ds("init", "--language", "en", "--project", "shop")
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

    def state(self) -> dict:
        return json.loads((self.dev / "state.json").read_text(encoding="utf-8"))

    def close(self, *ms: str) -> None:
        for m in ms:
            for tid, t in sorted(self.state()["tasks"].items()):
                if t["milestone"] == m and t["status"] == "todo":
                    self.ds("start", tid)
                    self.ds("done", tid)
            self.ds("gate", m, "passed", "--score", "95")

    def measure(self, m: str, hours_per_task: float, wait_h: float, cost_per_task: float | None) -> None:
        """Stand-in for a measured cycle: the flow.json the gate writes, with chosen numbers."""
        p = self.dev / "qa" / m / "flow.json"
        f = json.loads(p.read_text(encoding="utf-8"))
        f.update(tasks=2, cycle_time_s=2 * hours_per_task * 3600, working_time_s=hours_per_task * 3600,
                 human_wait_s=wait_h * 3600, cost_per_task=cost_per_task)
        p.write_text(json.dumps(f), encoding="utf-8")


# ------------------------------------------------------------------ item 13: delivery forecast

class TestForecast(Base):
    def test_no_forecast_before_two_measured_milestones(self) -> None:
        fc = json.loads(self.ds("forecast", "--json").stdout)
        self.assertFalse(fc["available"])
        self.close("M1")
        self.measure("M1", 1, 0, 2.0)
        self.assertFalse(json.loads(self.ds("forecast", "--json").stdout)["available"])
        self.assertIn("forecast available after 2 measured milestones", self.ds("status").stdout)

    def test_three_measured_milestones_give_p50_before_p85_with_cost(self) -> None:
        self.close("M1", "M2", "M3")
        for m, hpt, w, c in (("M1", 1, 0.5, 2.0), ("M2", 2, 1, 3.0), ("M3", 4, 0, 5.0)):
            self.measure(m, hpt, w, c)
        fc = json.loads(self.ds("forecast", "--json").stdout)
        self.assertTrue(fc["available"])
        self.assertEqual(fc["basis"], ["M1", "M2", "M3"])
        self.assertEqual(fc["pace_s_per_task"]["p50"], 2 * 3600)  # median cycle time per task: 1 h, 2 h, 4 h
        self.assertEqual([x["milestone"] for x in fc["milestones"]], ["M4", "M5"])
        for x in fc["milestones"] + fc["releases"]:
            self.assertLessEqual(x["finish_p50"], x["finish_p85"])
            self.assertLessEqual(x["cost_p50_usd"], x["cost_p85_usd"])
        m4, m5 = fc["milestones"]
        self.assertLess(m4["finish_p50"], m5["finish_p50"])  # one after the other
        self.assertGreater(m4["finish_p50"], "2026-11-23T12:00:00Z")
        self.assertEqual(m4["cost_p50_usd"], 6.0)  # 2 tasks × the median cost per task
        r2 = fc["releases"][0]
        self.assertEqual((r2["release"], r2["tasks_left"], r2["finish_p85"]), ("R2", 4, m5["finish_p85"]))
        self.assertEqual(r2["cost_p50_usd"], 12.0)
        line = self.ds("status").stdout
        self.assertRegex(line, r"Forecast: R2 probable 2026-11-\d\d, by 2026-1\d-\d\d · ~US\$ 12–\d+ to finish")
        self.assertEqual(json.loads(self.ds("status", "--json").stdout)["forecast"]["releases"][0]["release"], "R2")

    def test_board_snapshot_carries_the_forecast_and_shows_it(self) -> None:
        self.close("M1", "M2")
        self.measure("M1", 1, 0, None)
        self.measure("M2", 1, 0, None)
        import dev_board
        os.environ["DEV_KIT_NOW"] = "2026-11-23T12:00:00Z"
        try:
            fc = dev_board.build_state(self.root)["forecast"]
        finally:
            os.environ.pop("DEV_KIT_NOW", None)
        self.assertTrue(fc["available"])
        self.assertNotIn("cost_p50_usd", fc["milestones"][0])  # no cost measured: no cost shown
        js = (BOARD / "board.js").read_text(encoding="utf-8")
        self.assertIn("forecastChip(fcFor(\"releases\"", js)
        self.assertIn("forecastChip(m && fcFor(\"milestones\"", js)


# ------------------------------------------------------------------ rendering the real board (Playwright, when installed)

RENDER_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [url, steps] = [process.argv[2], JSON.parse(process.argv[3])];
  const b = await chromium.launch();
  const p = await b.newPage({ locale: process.argv[4] || 'en-US' });
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.goto(url);
  await p.waitForFunction(() => document.getElementById('main').getAttribute('aria-busy') === 'false', null, { timeout: 20000 });
  await p.waitForTimeout(300);
  const out = { errors };
  for (const [op, arg, key] of steps) {
    if (op === 'click') { await p.click(arg); await p.waitForTimeout(300); }
    else if (op === 'key') { await p.keyboard.press(arg); await p.waitForTimeout(200); }
    else if (op === 'text') out[key || arg] = await p.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent || e === document.body).map((e) => e.innerText).join('\n'), arg);
    else if (op === 'buttons') out[key || arg] = await p.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent).map((e) => ({ cmd: e.dataset.cmd || null, text: e.innerText.trim(), disabled: e.disabled, title: e.title })), arg);
    else if (op === 'eval') out[key] = await p.evaluate(arg);
  }
  console.log(JSON.stringify(out));
  await b.close();
})().catch((e) => { console.error(String(e)); process.exit(1); });
"""


def _playwright() -> bool:
    try:
        return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_PLAYWRIGHT = _playwright()


class RenderBase(Base):
    """Starts the project's real board server and drives the page in Chromium (skipped without node + Playwright)."""

    def setUp(self) -> None:
        super().setUp()
        self.env.pop("DEV_KIT_NOW", None)  # live runs and "last event" are measured against the real clock

    def render(self, steps: list, locale: str = "en-US") -> dict:
        board = SCRIPTS / "dev_board.py"
        env = {k: v for k, v in self.env.items() if k != "DEV_KIT_NOW"}
        env["DEV_KIT_CLAUDE"] = __import__("shutil").which("true") or "/bin/true"  # never the real claude in a test
        subprocess.run([sys.executable, "-I", str(board), "--root", str(self.root), "start", "--no-open", "--actions", "on", "--port", "0"],
                       capture_output=True, text=True, env=env, check=True, timeout=60)
        try:
            url = json.loads((self.dev / "run" / "board.json").read_text(encoding="utf-8"))["url"]
            js = Path(self.tmp.name) / "render.js"
            js.write_text(RENDER_JS, encoding="utf-8")
            p = subprocess.run(["node", str(js), url, json.dumps(steps), locale], capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr)
            out = json.loads(p.stdout)
            self.assertEqual(out["errors"], [])
            return out
        finally:
            subprocess.run([sys.executable, "-I", str(board), "--root", str(self.root), "stop"], capture_output=True, env=env, timeout=60)


# ------------------------------------------------------------------ item 16: every Needs-you item has actions

class TestNeedsYouDecisions(Base):
    def setUp(self) -> None:
        super().setUp()
        self.ds("start", "T-001"); self.ds("done", "T-001"); self.ds("start", "T-002"); self.ds("done", "T-002")
        self.ds("add-task", "--milestone", "M1", "--title", "Fix price", "--type", "fix", "--source", "qa/M1/report.md#F-1", "--files", "src/a1.py")
        for _ in range(4):
            self.ds("gate", "M1", "pending", "--count-run", "--score", "80")
        self.fix = "T-011"
        self.assertIn("rounds_exhausted", self.state()["tasks"][self.fix]["blocked_reason"])

    def test_continue_fixing_adds_rounds_and_frees_the_fixes(self) -> None:
        out = self.ds("qa-decide", "M1", "continue", "--rounds", "2").stdout
        self.assertIn("next: /dev-kit:qa M1", out)
        s = self.state()
        self.assertEqual(s["tasks"][self.fix]["status"], "todo")
        self.assertEqual(s["milestones"]["M1"]["extra_fix_rounds"], 2)
        import dev_state as dsm
        st = dsm.Store(self.root); st.load()
        self.assertEqual(dsm.fix_rounds_allowed(st, "M1"), 5)
        self.ds("gate", "M1", "pending", "--count-run", "--score", "85")  # round 5 of 5 allowed: nothing is blocked
        self.assertEqual(self.state()["tasks"][self.fix]["status"], "todo")

    def test_accept_needs_a_reason_and_writes_an_adr(self) -> None:
        self.assertIn("needs --note", self.ds("qa-decide", "M1", "accept", expect=1).stderr)
        out = self.ds("qa-decide", "M1", "accept", "--note", "Prices are display only in R1").stdout
        self.assertIn("ADR-001", out)
        self.assertIn("gate M1 passed --force", out)
        self.assertEqual(self.state()["tasks"][self.fix]["status"], "dropped")
        self.assertIn("Prices are display only in R1", (self.dev / "decisions.md").read_text(encoding="utf-8"))

    def test_replan_and_the_board_request(self) -> None:
        import dev_worker as dw
        with self.assertRaises(dw.Invalid):
            dw.validate("qa_decision", {"milestone": "M1", "decision": "accept"})  # accept needs the justification
        with self.assertRaises(dw.Invalid):
            dw.validate("qa_decision", {"milestone": "M1", "decision": "continue", "rounds": 9})
        rid = dw.submit(self.root, "qa_decision", {"milestone": "M1", "decision": "replan"})["id"]
        self.assertTrue(rid.startswith("P-"))
        self.assertIn("next: /dev-kit:plan M1", self.ds("qa-decide", "--request", rid).stdout)

    def test_blocked_task_unblock_skip_drop_and_hotfix_run(self) -> None:
        self.ds("block", "T-003", "--reason", "needs the API key")
        self.assertIn("T-003 todo (note: key is in the vault)", self.ds("task-decide", "T-003", "unblock", "--note", "key is in the vault").stdout)
        self.ds("block", "T-003", "--reason", "again")
        self.ds("task-decide", "T-003", "skip")
        t3 = self.state()["tasks"]["T-003"]
        self.assertEqual((t3["milestone"], t3["status"]), ("M3", "blocked"))
        self.assertIn("needs --note", self.ds("task-decide", "T-004", "drop", expect=1).stderr)
        self.ds("task-decide", "T-004", "drop", "--note", "out of scope")
        self.assertEqual(self.state()["tasks"]["T-004"]["status"], "dropped")
        self.ds("add-task", "--milestone", "M2", "--title", "Crash on pay", "--type", "fix", "--lane", "hotfix", "--files", "src/c.py")
        self.assertIn("is not a hotfix", self.ds("task-decide", "T-005", "run", expect=1).stderr)
        self.assertIn("next: /dev-kit:implement T-012", self.ds("task-decide", "T-012", "run").stdout)

    def test_hotfix_open_leaves_out_dropped_hotfixes(self) -> None:
        self.ds("add-task", "--milestone", "M2", "--title", "Crash on pay", "--type", "fix", "--lane", "hotfix", "--files", "src/c.py")
        self.assertEqual(json.loads(self.ds("backlog", "--json").stdout)["hotfix_open"], ["T-012"])
        self.ds("task-decide", "T-012", "drop", "--note", "not reproducible")
        self.assertEqual(json.loads(self.ds("backlog", "--json").stdout)["hotfix_open"], [])

    def test_a_blocked_task_waiting_on_a_question_shows_it(self) -> None:
        self.ds("block", "T-003", "--reason", "needs decision: Q-001")
        self.ds("add-question", "Which payment provider?", "--options", "Stripe|Adyen", "--task", "T-003")
        import dev_board
        d = dev_board.build_state(self.root)
        self.assertEqual(d["questions"][0]["task"], "T-003")
        self.assertEqual(d["tasks"]["T-003"]["question"], "Q-001")


class TestFeed(Base):
    def test_technical_lines_stay_out_of_the_feed(self) -> None:
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write("- 2026-11-23T12:01:00Z cleanup killed=0 removed=2\n- 2026-11-23T12:02:00Z tip shown T-3 source=-\n"
                    "- 2026-11-23T12:03:00Z cost ingest 12 requests\n")
        self.ds("start", "T-001"); self.ds("done", "T-001")
        self.ds("gate", "M1", "pending", "--count-run", "--score", "80", "--note", "2 blockers")
        import dev_board
        d = dev_board.build_state(self.root)
        kinds = [r["kind"] for r in d["feed"]]
        self.assertIn("task_done", kinds)
        self.assertIn("qa_round_done", kinds)
        self.assertEqual(next(r for r in d["feed"] if r["kind"] == "task_done")["vars"], {"task": "T-001", "title": "Step 1"})
        blob = json.dumps(d["feed"])
        for word in ("cleanup", "killed=0", "source=-", "tip shown", "cost ingest", "sync-plan"):
            self.assertNotIn(word, blob)
        self.assertTrue(any("cleanup killed=0" in r["text"] for r in d["log"]))  # the full log keeps them


@unittest.skipUnless(HAS_PLAYWRIGHT, "node and Playwright are needed to render the board")
class TestNeedsYouRendered(RenderBase):
    def test_buttons_for_rounds_used_up_and_blocked_task_and_no_dropped_hotfix(self) -> None:
        self.ds("start", "T-001"); self.ds("done", "T-001"); self.ds("start", "T-002"); self.ds("done", "T-002")
        self.ds("add-task", "--milestone", "M1", "--title", "Fix price", "--type", "fix", "--source", "qa/M1/report.md#F-1", "--files", "src/a1.py")
        for _ in range(4):
            self.ds("gate", "M1", "pending", "--count-run", "--score", "80")
        self.ds("block", "T-003", "--reason", "needs the API key")
        self.ds("add-task", "--milestone", "M2", "--title", "Crash on pay", "--type", "fix", "--lane", "hotfix", "--files", "src/c.py")
        self.ds("drop", "T-012", "--reason", "not reproducible")
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write("- 2026-11-23T12:01:00Z cleanup killed=0 removed=2\n- 2026-11-23T12:02:00Z tip shown T-3 source=-\n")
        # Needs you and Activity are drawers opened from the top bar
        out = self.render([["click", "#needs-btn"], ["buttons", "#impediments button.btn", "needs"], ["text", "#impediments", "needs_text"], ["key", "Escape"],
                           ["click", "#act-btn"], ["text", "#feed", "feed"], ["text", "#foot", "foot"]])
        texts = [b["text"] for b in out["needs"]]
        for label in ("Continue fixing (+1 round)", "Accept with an ADR *", "Replan", "Unblock", "Skip to the next milestone", "Drop *"):
            self.assertTrue(any(t.startswith(label) for t in texts), (label, texts))
        self.assertNotIn("Crash on pay", out["needs_text"])
        self.assertNotIn("cleanup", out["feed"])
        self.assertNotIn("source=-", out["feed"])
        self.assertIn("T-001 done: Step 1", out["feed"])
        self.assertNotIn("pid", out["foot"])

    def test_the_run_button_of_a_running_qa_is_disabled(self) -> None:
        self.ds("start", "T-001"); self.ds("done", "T-001"); self.ds("start", "T-002"); self.ds("done", "T-002")
        self.ds("gate", "M1", "pending", "--count-run", "--score", "80")
        before = self.render([["click", "#ph-construction"], ["buttons", "button[data-cmd='/dev-kit:qa M1']", "qa"]])
        self.assertTrue(before["qa"] and not before["qa"][0]["disabled"], before)
        self.assertEqual(before["qa"][0]["text"].replace("\n", " ").replace("▶", "").strip(), "Run QA of M1")
        self.assertEqual(before["qa"][0]["title"], "Run /dev-kit:qa M1 in Claude Code")
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        out = self.render([["click", "#ph-construction"], ["buttons", "button[data-cmd='/dev-kit:qa M1']", "qa"], ["text", "#updated", "clock"]])
        self.assertTrue(out["qa"] and all(b["disabled"] for b in out["qa"]), out)
        self.assertIn("Running for", out["qa"][0]["text"])
        self.assertIn("QA of M1 for", out["clock"])
        self.assertIn("last event", out["clock"])


# ------------------------------------------------------------------ item 15: vocabulary, one source for the milestone state

class TestReleaseReview(Base):
    """The approval document of a planned release is the release review (it was the dossier before 3.0.0-alpha.6)."""

    def submit(self, *flag: str) -> None:
        self.close("M1", "M2", "M3")
        (self.dev / "releases" / "R1").mkdir(parents=True)
        (self.dev / "releases" / "R1" / flag[1].rsplit("/", 1)[1]).write_text("# R1\n", encoding="utf-8")
        self.ds("release-submit", "R1", *flag)

    def board_release(self) -> dict:
        import dev_board as db
        return next(r for r in db.build_state(self.root)["cycle"]["releases"] if r["id"] == "R1")

    def test_submit_records_the_release_review(self) -> None:
        self.submit("--review", ".dev/releases/R1/review.md")
        g = self.state()["release_state"]["R1"]
        self.assertEqual(g["review_doc"], ".dev/releases/R1/review.md")
        self.assertEqual(g["history"][-1]["review_doc"], ".dev/releases/R1/review.md")
        self.assertNotIn("dossier", json.dumps(self.state()))
        self.assertIn("release review .dev/releases/R1/review.md", self.ds("status").stdout)
        self.assertEqual(self.board_release()["review_doc"], ".dev/releases/R1/review.md")

    def test_the_old_flag_still_works(self) -> None:
        self.submit("--dossier", ".dev/releases/R1/dossier.md")
        self.assertEqual(self.state()["release_state"]["R1"]["review_doc"], ".dev/releases/R1/dossier.md")

    def test_a_project_with_a_dossier_keeps_it(self) -> None:
        self.submit("--review", ".dev/releases/R1/review.md")
        s = self.state()
        g = s["release_state"]["R1"]
        g["dossier"] = g.pop("review_doc").replace("review.md", "dossier.md")
        g["history"][-1]["dossier"] = g["history"][-1].pop("review_doc").replace("review.md", "dossier.md")
        (self.dev / "state.json").write_text(json.dumps(s), encoding="utf-8")
        self.assertEqual(self.board_release()["review_doc"], ".dev/releases/R1/dossier.md")
        import dev_board as db
        self.assertEqual(db.build_state(self.root)["release_history"]["R1"][-1]["review_doc"], ".dev/releases/R1/dossier.md")
        self.ds("release-decide", "R1", "--approve")  # the next save writes the new key
        g = self.state()["release_state"]["R1"]
        self.assertEqual((g["review_doc"], "dossier" in g), (".dev/releases/R1/dossier.md", False))

    def test_no_kit_text_says_dossier(self) -> None:
        kit = CORE.parents[1]
        allowed = {"CHANGELOG.md", "dev_state.py", "test_v3_board.py"}  # history, the compatibility code, this test
        hits = [str(p.relative_to(kit)) for p in kit.rglob("*") if p.is_file() and p.name not in allowed
                and "fixtures" not in p.parts and "__pycache__" not in p.parts
                and any(re.search(r"dossi", ln, re.I) and "3.0.0-alpha.6" not in ln  # the compatibility note names the old word
                        for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines())]
        self.assertEqual(hits, [])
        self.assertTrue((CORE / "shared" / "templates" / "release-review.md").exists())
        pt = json.loads((BOARD / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))["strings"]
        self.assertEqual(pt["Release review"], "Revis\u00e3o da release")


FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys, time
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
with open(os.environ["FAKE_OUT"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "project": os.environ.get("CLAUDE_PROJECT_DIR"),
                        "child": os.environ.get("DEV_KIT_BOARD_CHILD")}) + "\\n")
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class TestBoardStartsTheWorker(Base):
    """The worker is part of the board: with no session listening, the board's server starts a headless worker
    (`claude -p "/dev-kit:worker"`) for a waiting request, so a Needs-you action never waits for a manual step."""

    def setUp(self) -> None:
        super().setUp()
        import dev_worker as dw
        from unittest import mock
        self.dw = dw
        self.out = self.root / "fake-claude.jsonl"
        fake = self.root / "fake-claude"
        fake.write_text(FAKE_CLAUDE, encoding="utf-8")
        fake.chmod(0o755)
        env = {"DEV_KIT_CLAUDE": str(fake), "FAKE_OUT": str(self.out), "FAKE_RC": "0", "FAKE_SLEEP": "0"}
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(dw, "AUTO_GRACE_S", 0)):
            p.start()
            self.addCleanup(p.stop)
        self.kit = CORE.parents[1]
        self.ex = dw.AutoExecutor(self.root, self.kit)
        self.addCleanup(self.ex.stop)

    def finish(self) -> None:
        self.ex.proc.wait(20)
        self.ex.tick()

    def runs(self) -> list[dict]:
        return [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines()] if self.out.exists() else []

    def test_a_waiting_request_starts_a_headless_worker(self) -> None:
        rid = self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})["id"]
        self.ex.tick()
        st = self.dw.auto_status(self.root)
        self.assertEqual((st["state"], st["request"]), ("running", rid))
        self.assertEqual(self.dw.snapshot(self.root)["executor"]["auto"]["state"], "running")
        self.finish()
        run = self.runs()[0]
        self.assertEqual(run["argv"][:2], ["-p", "/dev-kit:worker"])
        self.assertEqual(run["argv"][run["argv"].index("--plugin-dir") + 1], str(self.kit))
        self.assertEqual(run["argv"][run["argv"].index("--permission-mode") + 1], "acceptEdits")  # 3.2 default
        self.assertEqual((run["project"], run["child"]), (str(self.root), "1"))

    def test_a_run_that_leaves_its_request_backs_off(self) -> None:
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.finish()  # the fake took nothing: the request is still pending
        st = self.dw.auto_status(self.root)
        self.assertEqual((st["state"], st["reason"]), ("waiting", "left the request pending"))
        self.ex.tick()
        self.assertEqual(len(self.runs()), 1)  # not again before the back-off
        self.assertGreater(st["until"], __import__("time").time() + 20)

    def test_a_failed_run_says_why(self) -> None:
        os.environ["FAKE_RC"] = "3"
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.finish()
        self.assertEqual(self.dw.auto_status(self.root)["reason"], "exit 3")

    def test_a_finished_run_goes_idle(self) -> None:
        rid = self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})["id"]
        self.ex.tick()
        self.assertEqual(self.dw.claim(self.root, "child")[0]["id"], rid)  # what the worker in the child does
        self.dw.finish(self.root, rid, "done")
        self.finish()
        self.assertEqual(self.dw.auto_status(self.root)["state"], "idle")

    def test_nothing_starts_without_a_request_or_while_paused(self) -> None:
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.dw.set_mode(self.root, paused=True)
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.dw.set_mode(self.root, paused=False)
        self.ex.tick()
        self.assertIsNotNone(self.ex.proc)

    def test_a_listening_session_keeps_priority(self) -> None:
        self.dw.heartbeat(self.root, "s1", os.getpid())
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertIsNone(self.ex.proc)

    def test_it_can_be_turned_off_and_configured(self) -> None:
        self.ds("set", "autonomy.board_executor", "off")
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.assertEqual(self.dw.auto_status(self.root)["state"], "off")
        self.ds("set", "autonomy.board_executor", '{"auto": true, "permission_mode": "default"}')
        self.assertEqual(self.state()["autonomy"]["board_executor"],
                         {"auto": True, "permission_mode": "default", "timeout_min": 180, "autopilot_timeout_min": 360})
        self.ds("set", "autonomy.board_executor", '{"permission_mode": "yolo"}', expect=1)
        self.ex.tick()
        self.finish()
        self.assertEqual(self.runs()[0]["argv"][self.runs()[0]["argv"].index("--permission-mode") + 1], "default")

    def test_the_untouched_pre_3_2_default_takes_the_new_one(self) -> None:
        st = self.state()
        st["autonomy"]["board_executor"] = {"auto": True, "permission_mode": "default", "timeout_min": 180}
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.assertEqual(self.dw.auto_cfg(self.root)["permission_mode"], "acceptEdits")

    def test_no_claude_binary_is_shown(self) -> None:
        os.environ.pop("DEV_KIT_CLAUDE")
        os.environ["PATH"] = str(self.root / "empty")
        self.dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.ex.tick()
        self.assertIsNone(self.ex.proc)
        self.assertEqual(self.dw.snapshot(self.root)["executor"]["auto"]["state"], "no_claude")


class TestRoundReasons(Base):
    def test_a_failed_round_keeps_its_reason_for_the_chip(self) -> None:
        self.ds("start", "T-001"); self.ds("done", "T-001"); self.ds("start", "T-002"); self.ds("done", "T-002")
        self.ds("gate", "M1", "pending", "--count-run", "--score", "97", "--note", "2 blockers")
        self.ds("gate", "M1", "pending", "--count-run", "--score", "95", "--note", "floor: deps")
        import dev_board
        hist = next(m for m in dev_board.build_state(self.root)["milestones"] if m["id"] == "M1")["qa"]["history"]
        self.assertEqual([(r["n"], r["reason"]) for r in hist], [(1, "2 blockers"), (2, "floor: deps")])
        js = (BOARD / "board.js").read_text(encoding="utf-8")
        self.assertNotIn("Stage ${hereIdx + 1} of", js)
        self.assertNotIn("QA round ${x.round} running`", js)


@unittest.skipUnless(HAS_PLAYWRIGHT, "node and Playwright are needed to render the board")
class TestBoardVocabularyRendered(RenderBase):
    def setUp(self) -> None:
        super().setUp()
        for t in ("T-001", "T-002"):
            self.ds("start", t); self.ds("done", t)
        self.ds("add-task", "--milestone", "M1", "--title", "Fix price", "--type", "fix", "--source", "qa/M1/report.md#F-1", "--files", "src/a1.py")
        self.ds("gate", "M1", "pending", "--count-run", "--score", "97", "--note", "2 blockers")
        self.ds("start", "T-011"); self.ds("done", "T-011")
        import dev_worker as dw
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})

    def test_r_and_a_number_only_ever_names_a_release(self) -> None:
        steps = []
        for tab in ("conception", "planning", "construction", "stable", "releases"):
            steps += [["click", f"#ph-{tab}"], ["text", "body", tab]]
        steps += [["click", "#ph-construction"], ["click", "#tab-qa"], ["text", "body", "qa"], ["click", "#ph-map"], ["text", "body", "map"],
                  ["click", "#req-btn"], ["text", "body", "requests"]]
        out = self.render(steps)
        releases = {r["id"] for r in self.state()["release_plan"]}
        for k in ("conception", "planning", "construction", "stable", "releases", "qa", "map", "requests"):
            ids = set(re.findall(r"\bR-?\d+\b", out[k]))
            self.assertTrue(ids <= releases, (k, ids - releases))
        self.assertIn("P-001", out["requests"])  # board requests are P-nnn, in the Requests drawer

    def test_in_qa_the_milestone_state_is_in_one_place_and_the_qa_tab_opens(self) -> None:
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        out = self.render([["click", "#ph-construction"], ["text", "#ms-facts", "facts"], ["text", "#stages-sub", "sub"], ["text", "#tabs", "tabs"],
                           ["eval", "document.getElementById('ms-count').textContent", "count"], ["text", "#stages", "stages"], ["text", "body", "body"],
                           ["eval", "document.getElementById('board-card').dataset.view", "view"], ["text", "#qa-panel", "panel"]])
        self.assertNotIn("QA", out["facts"])
        self.assertEqual(out["sub"].strip(), "")
        self.assertNotIn("QA", out["tabs"])
        self.assertNotRegex(out["body"], r"Stage \d+ of \d+")
        self.assertNotIn("is in QA", out["body"])
        self.assertEqual(len(re.findall(r"[Rr]ound 2 running", out["body"])), 1)  # the QA stage chevron, nowhere else
        self.assertIn("Round 1 ✕ · 2 blockers", out["stages"])
        self.assertIn("3/3 tasks · QA round 1", out["count"])
        self.assertEqual(out["view"], "qa")
        for part in ("Auditors", "Blocking findings open", "Fixes", "Hard floor", "Exit check"):
            self.assertIn(part.upper(), out["panel"].upper())

    def test_stages_that_do_not_apply_are_not_drawn(self) -> None:
        out = self.render([["click", "#ph-construction"], ["text", "#stages", "stages"]])
        self.assertNotIn("Deploy", out["stages"])  # production deploy is not per milestone
        self.assertNotIn("Smoke", out["stages"])   # no local preview
        self.assertNotIn("does not apply", out["stages"])


# ------------------------------------------------------------------ item 14: the board in the user's language
# The text lint: board.js keeps no visible text outside the catalog (i18n/en.json), index.html marks every static text.


def js_literals(src: str) -> list[dict]:
    """String and template literals of a JS source (regex literals and comments skipped), outermost only."""
    i, n, out, prev = 0, len(src), [], ""
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i); i = n if j < 0 else j + 2; continue
        if c in "\"'":
            k = i + 1
            while k < n and src[k] != c:
                k += 2 if src[k] == "\\" else 1
            out.append({"start": i, "end": k + 1, "raw": src[i:k + 1]}); i = k + 1; prev = "s"; continue
        if c == "`":
            k, depth = i + 1, 0
            while k < n:
                if src[k] == "\\": k += 2; continue
                if src[k] == "`" and depth == 0: break
                if src.startswith("${", k): depth += 1; k += 2; continue
                if src[k] == "}" and depth: depth -= 1
                elif src[k] == "{" and depth: depth += 1
                k += 1
            out.append({"start": i, "end": k + 1, "raw": src[i:k + 1]}); i = k + 1; prev = "s"; continue
        if c == "/" and (prev in "(,=:[!&|?{};>~+-*%<\n" or re.search(r"\b(return|typeof|case)\s*$", src[max(0, i - 8):i])):
            k, cls = i + 1, False
            while k < n and (src[k] != "/" or cls):
                if src[k] == "\\": k += 1
                elif src[k] == "[": cls = True
                elif src[k] == "]": cls = False
                elif src[k] == "\n": break
                k += 1
            i = k + 1; prev = "r"; continue
        if not c.isspace():
            prev = c
        i += 1
    return out


def _template_text(raw: str) -> str:
    """The literal text of a string or template literal, ${...} parts removed (nested literals are checked on their own)."""
    if raw[0] != "`":
        return raw[1:-1]
    body, out, i, depth = raw[1:-1], [], 0, 0
    while i < len(body):
        if body[i] == "\\":
            i += 2; continue
        if body.startswith("${", i) and depth == 0:
            depth, i = 1, i + 2; continue
        if depth:
            depth += {"{": 1, "}": -1}.get(body[i], 0)
            i += 1; continue
        out.append(body[i]); i += 1
    return "".join(out)


def _inner_templates(raw: str) -> list[str]:
    """Literals nested inside the ${...} of a template."""
    if raw[0] != "`":
        return []
    found, body, i = [], raw[1:-1], 0
    while True:
        j = body.find("${", i)
        if j < 0:
            return found
        k, depth = j + 2, 1
        while k < len(body) and depth:
            depth += {"{": 1, "}": -1}.get(body[k], 0); k += 1
        found += [x["raw"] for x in js_literals(body[j + 2:k - 1])]
        i = k


TEXTY = re.compile(r"[A-Za-z]{2,}[\s,.:;!?()]+[A-Za-z]{2,}|^\s*[A-Z][a-z]{2,}")
TECH = re.compile(r"^\s*/(dev-kit|api|assets)[:/]|^[a-z0-9_-]+$|^(?=\S*-)[a-z0-9_-]+( [a-z0-9_-]+)*$|^[\w./-]+\.(md|json|js|css|html|svg)(#.*)?$|"
                  r"^[a-z_-]+:[a-z_-]*$|^[A-Z][a-z]+[A-Z]\w*$|^[#.\[](?! )|^(GATE|M|T|I|Q|P|R|F)[:-]?$|^\s*$|"
                  r"^(Escape|Enter|Home|End|Tab|Content-Type|X-Board-Token)$|^\(prefers-|^M[\d$ ,]|^\.dev/$")
VISIBLE_AT = re.compile(r'(?<![\w"-])(text|title|placeholder|"aria-label")\s*:\s*$|textContent\s*=\s*$|\btoast\(\s*$|\bfill\([^()]*,\s*$')
TECH_WORDS = {"min", "pid", "sha"}  # units and ids that read the same in every language
SYMBOL = re.compile(r"^[^A-Za-z]*$|^(M|T|R|I|Q|P|F|ADR)-?[\d.]*$")


def _lint_js(src: str, start_marker: str = "  const SVGNS") -> list[str]:
    """Visible literals outside the catalog: text-like literals that are not a tr()/N_()/plural() argument, and any
    literal with letters in a visible position (text:, title:, aria-label:, placeholder:, textContent =, toast)."""
    skip_until = src.index(start_marker)
    probs = []
    lits = js_literals(src)
    todo = [(x["raw"], x["start"], False) for x in lits if x["start"] >= skip_until]
    while todo:
        raw, at, in_class = todo.pop()
        before = src[max(0, at - 80):at]
        # a class list (class: "chip wait", or inside its template) is not text
        in_class = in_class or bool(re.search(r'(?<![\w"-])(class|cls|rel)\s*:\s*$|className\s*=\s*$', before))
        todo += [(r, src.find(r, at), in_class) for r in inner_templates(raw)]
        if in_class and re.fullmatch(r"[a-z0-9_ -]*", template_text(raw)):
            continue
        if re.search(r"\b(tr|N_|plural)\(\s*$|\bplural\([^()]*,\s*(\"[^\"]*\"\s*,\s*)?$", before):
            continue
        text = template_text(raw)
        line = src[src.rfind("\n", 0, at) + 1:src.find("\n", at)].strip()
        if "i18n-ok" in line:
            continue
        child = re.search(r"\b\w+\(\{[^{}]*\}\)\s*,\s*$|\}\s*\)?\s*,\s*$", before) and re.search(r"\bh\(", src[max(0, at - 400):at])
        words = re.findall(r"(?<![\w/.#:=?\[-])[a-z]{3,}(?![\w/.(=:-])", text) if "${" in raw or child else []
        if words and not in_class and not re.search(r"[/#\[=]|^\s*[.:]", text) and not TECH_WORDS.issuperset(words):
            probs.append(f"{src.count(chr(10), 0, at) + 1}: {raw[:70]} (word: {words[0]})")
        elif TEXTY.search(text) and not TECH.search(text.strip()):
            probs.append(f"{src.count(chr(10), 0, at) + 1}: {raw[:70]}")
        elif before and VISIBLE_AT.search(before) and re.search(r"[A-Za-z]", text) and not SYMBOL.match(text.strip()) \
                and not re.match(r"^[#.\[]|^\s*/(dev-kit|api)[:/]", text.strip()) \
                and not re.match(r"^\s*/dev-kit:", text):
            probs.append(f"{src.count(chr(10), 0, at) + 1}: {raw[:70]} (visible position)")
    return sorted(set(probs), key=lambda p: int(p.split(":")[0]))


def _js_keys(src: str) -> set[str]:
    """Catalog keys used by board.js: the literal first argument of tr() and N_()."""
    keys = set()
    for m in re.finditer(r"\b(?:tr|N_)\(\s*\"((?:[^\"\\]|\\.)*)\"", src):
        keys.add(json.loads(f'"{m.group(1)}"'))
    return keys


def _plural_nouns(src: str) -> set[str]:
    return set(m.group(1) for m in re.finditer(r"\bplural\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*?,\s*\"([^\"]+)\"", src))


lint_js, js_keys, plural_nouns, template_text, inner_templates = _lint_js, _js_keys, _plural_nouns, _template_text, _inner_templates


class _HtmlTexts(__import__("html.parser").parser.HTMLParser):
    """Static texts of index.html that are not marked for the catalog."""
    SKIP = ("script", "style", "code", "svg", "title")
    VOID = {"meta", "link", "br", "hr", "img", "input", "source", "col", "area", "base", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.missing: list[str] = []
        self.keys: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k, v in a.items():
            if k.startswith("data-i18n"):
                self.keys.add(v)
        if not any(t in self.SKIP for t, _ in self.stack) and tag not in self.SKIP:
            for k in ("title", "aria-label", "placeholder"):
                if a.get(k) and re.search(r"[A-Za-z]{2}", a[k]) and "__" not in a[k] and f"data-i18n-{k}" not in a and a.get("id") != "theme-btn":
                    self.missing.append(f"<{tag}> {k}={a[k]!r}")
        if tag not in self.VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop()[0] != tag:
            pass

    def handle_data(self, d):
        if not self.stack or not re.search(r"[A-Za-z]{2}", d) or any(t in self.SKIP for t, _ in self.stack):
            return
        a = self.stack[-1][1]
        if not ({"data-i18n", "data-i18n-once"} & set(a)):
            self.missing.append(f"<{self.stack[-1][0]}> text {d.strip()[:60]!r}")


def catalog(lang: str) -> dict:
    return json.loads((BOARD / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


PH = re.compile(r"\{(\w+)\}")


class TestBoardText(unittest.TestCase):
    def test_the_lint_catches_single_words(self) -> None:
        src = ("  const SVGNS = 1;\n  const a = h(\"span\", {}, h(\"i\", {}), \"running\");\n  const b = `${x} for ${y}`;\n"
               "  const c = `gate ${m.gate}`;\n  const d = `/api/x/${id}/cancel`;\n  const e = h(\"span\", { class: `chip ${x}` });\n")
        self.assertEqual([p.split(" (")[0] for p in lint_js(src)], ['2: "running"', "3: `${x} for ${y}`", "4: `gate ${m.gate}`"])

    def test_milestone_goal_leaves_out_its_fields(self) -> None:
        import dev_board
        self.assertEqual(dev_board.milestone_goals("## M1 — A\nGoal one.\n- exit_check: cmd: x\n\n### T-001 x\n"), {"M1": "Goal one."})

    def test_board_js_has_no_visible_text_outside_the_catalog(self) -> None:
        self.assertEqual(lint_js((BOARD / "board.js").read_text(encoding="utf-8")), [])

    def test_the_lint_catches_a_literal(self) -> None:
        src = 'const x = 1;\n  const SVGNS = "";\n  h("span", { text: "Waiting for you" }); h("b", { title: "ready" }); tr("Fine text");\n'
        self.assertEqual(len(lint_js(src)), 2)

    def test_index_html_marks_every_static_text(self) -> None:
        p = _HtmlTexts()
        p.feed((BOARD / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(p.missing, [])

    def test_every_key_is_in_en_and_every_en_key_in_pt_br(self) -> None:
        js = (BOARD / "board.js").read_text(encoding="utf-8")
        p = _HtmlTexts()
        p.feed((BOARD / "index.html").read_text(encoding="utf-8"))
        en, pt = catalog("en"), catalog("pt-BR")
        self.assertEqual(sorted((js_keys(js) | p.keys) - set(en["strings"])), [])
        self.assertEqual(sorted(plural_nouns(js) - set(en["plurals"])), [])
        self.assertEqual(sorted(set(en["strings"]) - set(pt["strings"])), [])
        self.assertEqual(sorted(set(en["plurals"]) - set(pt["plurals"])), [])
        for k, v in pt["strings"].items():
            self.assertEqual(set(PH.findall(v)), set(PH.findall(en["strings"].get(k, v))), k)
        for k, f in pt["plurals"].items():
            self.assertTrue({"one", "other"} <= set(f), k)
            self.assertTrue(all("{n}" in x for x in f.values()), k)


@unittest.skipUnless(HAS_PLAYWRIGHT, "node and Playwright are needed to render the board")
class TestBoardLanguageRendered(RenderBase):
    def test_pt_br_project_opens_in_portuguese_and_the_selector_switches_without_reload(self) -> None:
        st = self.state()
        st["language"] = "pt-BR"
        (self.dev / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.ds("start", "T-001")
        en, pt = catalog("en")["strings"], catalog("pt-BR")["strings"]
        out = self.render([["eval", "window.__marker = 1; document.documentElement.lang", "lang"], ["text", "body", "pt"],
                           ["click", "#menu-btn"], ["click", "#lang-switch [data-lang='en']"],
                           ["eval", "String(window.__marker) + ' ' + document.documentElement.lang", "after"], ["text", "body", "en"],
                           ["eval", "localStorage.getItem('board-lang')", "kept"]], locale="en-US")
        self.assertEqual(out["lang"], "pt-BR")
        for k in ("Construction", "Activity", "Requests", "Project lifecycle"):
            self.assertNotEqual(pt[k], en[k])
            self.assertIn(pt[k].upper(), out["pt"].upper())
        self.assertNotIn("Activity", out["pt"])
        self.assertEqual(out["after"], "1 en")  # the same page: no reload
        self.assertIn("Activity", out["en"])
        self.assertEqual(out["kept"], "en")


class TestExecutionTime(unittest.TestCase):
    """Finished work says how long it took: done task cards (and their details), closed milestones, released releases."""

    def test_board_shows_how_long_finished_work_took(self):
        js = (BOARD / "board.js").read_text(encoding="utf-8")
        self.assertIn('const taskTook = (t) => (t && t.status === "done" ? secsBetween(t.started_at, t.done_at) : null);', js)
        self.assertEqual(js.count('tr("took {v}", { v: dur(taskTook('), 2)  # task card and task details
        self.assertIn("m && isClosed(m) ? msTiming(m) : null", js)
        self.assertIn('if (!r || r.status !== "released") return null;', js)
        for use in ('tr(" · closed in {v}"', 'msTook(m) ? tr("took {v}"', 'tr(" in {v}", { v: rt.text })'):
            self.assertIn(use, js)
        for lang in ("en", "pt-BR"):
            cat = json.loads((BOARD / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["strings"]
            for k in ("took {v}", " · closed in {v}", " in {v}", "{v} d", "Execution time: from start to done"):
                self.assertIn(k, cat, lang)


if __name__ == "__main__":
    unittest.main()
