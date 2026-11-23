"""dev-kit 3.0, phase 5 (operations): release flags separate the deploy from the release, and a production health
check turns failures into one expedite issue (item 12).

Each acceptance criterion of the 3.0 specification for this item is one test (or a few) here.
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
sys.path.insert(0, str(SCRIPTS))


def task(n: int, files: str, flag: str | None = None, kind: str = "feature") -> str:
    return (f"### T-{n:03d} Step {n}\n- status: todo\n- deps: \n- type: {kind}\n- acceptance:\n  - AC-{n}: step {n} works\n"
            f"- test_notes: unit\n- files: {files}\n" + (f"- flag: {flag}\n" if flag else "") + "\n")


def plan(flags: bool) -> str:
    def ms(m: int, r: str) -> str:
        return (f"## M{m} — Part {m}\nPart {m}.\n\n" + task(2 * m - 1, f"src/a{m}.py", f"release_{r}" if flags else None)
                + task(2 * m, f"src/b{m}.py", kind="test"))
    return ("# Implementation plan — shop\n\n## R1 — First sale\n\n" + ms(1, "R1") + ms(2, "R1")
            + "## R2 — More\n\n" + ms(3, "R2") + ms(4, "R2") + "## R3 — Later\n\n" + ms(5, "R3"))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dev = self.root / ".dev"
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEV_KIT_NOW", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                                                                      "DEV_KIT_PARENT_SESSION")}
        self.env["DEV_KIT_NOW"] = "2026-11-23T12:00:00Z"
        self.ds("init", "--language", "en", "--project", "shop")

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

    def ship(self, rid: str, *ms: str, flag_on: bool = True) -> None:
        self.close(*ms)
        self.ds("release-submit", rid)
        self.ds("release-decide", rid, "--approve")
        if flag_on:
            self.ds("flag", "set", f"release_{rid}", "on")
        self.ds("release-record", "--version", f"1.{rid[1:]}.0", "--release", rid)


# ------------------------------------------------------------------ release flags
class TestReleaseFlags(Base):
    def setUp(self) -> None:
        super().setUp()
        self.ds("set", "autonomy.release_flags", '{"enabled": true, "provider": "env var FLAG_<NAME>"}')
        self.ds("set", "autonomy.production", '{"when": "per_milestone_flagged", "method": "compose"}')
        (self.dev / "plan.md").write_text(plan(flags=True), encoding="utf-8")
        self.out = self.ds("sync-plan").stdout

    def test_flags_need_a_provider_and_flagged_deploys_need_flags(self) -> None:
        self.ds("set", "autonomy.release_flags", '{"enabled": true, "provider": null}', expect=1)
        self.ds("set", "autonomy.release_flags", '{"enabled": false}', expect=1)  # production is per_milestone_flagged

    def test_sync_plan_creates_one_flag_per_release_off(self) -> None:
        self.assertIn("release flags created (off): release_R1, release_R2, release_R3", self.out)
        flags = self.state()["flags"]
        self.assertEqual({k: (v["release"], v["state"]) for k, v in flags.items()},
                         {"release_R1": ("R1", "off"), "release_R2": ("R2", "off"), "release_R3": ("R3", "off")})
        self.assertEqual(self.state()["tasks"]["T-005"]["flag"], "release_R2")
        self.assertNotIn("without `flag:", self.out)

    def test_a_feature_task_without_its_flag_is_a_warning(self) -> None:
        text = (self.dev / "plan.md").read_text(encoding="utf-8").replace("- flag: release_R2\n", "", 1)
        (self.dev / "plan.md").write_text(text.replace("- flag: release_R3\n", "- flag: release_R2\n"), encoding="utf-8")
        out = self.ds("sync-plan").stdout
        self.assertIn("T-005: feature task of R2 without `flag: release_R2`", out)
        self.assertIn("T-009: flag release_R2 is not the flag of its release (release_R3)", out)

    def test_m3_goes_to_production_with_release_r2_off_and_approving_r2_turns_it_on(self) -> None:
        self.ship("R1", "M1", "M2")
        self.close("M3")
        out = self.ds("deploy", "production", "--sha", "abc1234", "--milestone", "M3", "--status", "ok").stdout
        self.assertIn("release_R2 off", out)
        cur = self.state()["deploys"]["production"]["current"]
        self.assertEqual((cur["milestone"], cur["flag"]), ("M3", {"name": "release_R2", "state": "off"}))
        p = self.ds("flag", "set", "release_R2", "on", expect=1)  # not before its approval
        self.assertIn("turns on only after R2 is approved", p.stderr)
        self.close("M4")
        self.ds("release-submit", "R2")
        out = self.ds("release-decide", "R2", "--approve").stdout
        self.assertIn("turn release_R2 on in production (env var FLAG_<NAME>)", out)
        self.ds("flag", "set", "release_R2", "on")
        self.assertEqual(self.state()["flags"]["release_R2"]["state"], "on")

    def test_rollback_turns_the_flag_off(self) -> None:
        self.ship("R1", "M1", "M2")
        self.ds("flag", "set", "release_R1", "off", "--rollback", "--note", "checkout errors")
        f = self.state()["flags"]["release_R1"]
        self.assertEqual((f["state"], f["history"][-1]["event"], f["history"][-1]["note"]), ("off", "rollback", "checkout errors"))
        self.assertIn("release_R1: off", self.ds("flag", "list").stdout)

    def test_a_released_flag_gets_its_removal_task_in_the_next_release(self) -> None:
        self.ship("R1", "M1", "M2")
        s = self.state()
        tid = s["flags"]["release_R1"]["cleanup_task"]
        t = s["tasks"][tid]
        self.assertEqual((t["title"], t["type"], t["milestone"], t["source"]), ("Remove flag release_R1", "chore", "M3", "flag:release_R1"))
        self.assertIn(f"### {tid} Remove flag release_R1", (self.dev / "plan.md").read_text(encoding="utf-8"))

    def test_the_last_release_waits_for_a_next_one(self) -> None:
        self.ship("R1", "M1", "M2")
        self.ship("R2", "M3", "M4")
        self.ship("R3", "M5")
        self.assertEqual(self.state()["flags"]["release_R3"]["cleanup_task"], "pending")
        text = (self.dev / "plan.md").read_text(encoding="utf-8") + "## R4 — Next\n\n## M6 — Part 6\nPart 6.\n\n" + task(11, "src/a6.py", "release_R4")
        (self.dev / "plan.md").write_text(text, encoding="utf-8")
        out = self.ds("sync-plan").stdout
        self.assertIn("Remove flag release_R3 (its release is out)", out)
        tid = self.state()["flags"]["release_R3"]["cleanup_task"]
        self.assertEqual(self.state()["tasks"][tid]["milestone"], "M6")

    def test_board_shows_the_flags(self) -> None:
        import dev_board as db
        flags = db.build_state(self.root)["flags"]
        self.assertEqual([(f["name"], f["state"]) for f in flags], [("release_R1", "off"), ("release_R2", "off"), ("release_R3", "off")])


class TestFlagsOff(Base):
    def test_without_flags_nothing_changes(self) -> None:
        (self.dev / "plan.md").write_text(plan(flags=False), encoding="utf-8")
        out = self.ds("sync-plan").stdout
        self.assertNotIn("flag", out)
        self.assertNotIn("flags", self.state())
        self.ship("R1", "M1", "M2", flag_on=False)
        self.assertFalse(any(t.get("source", "") and str(t["source"]).startswith("flag:") for t in self.state()["tasks"].values()))
        self.ds("set", "autonomy.production", '{"when": "per_milestone_flagged", "method": "compose"}', expect=1)


# ------------------------------------------------------------------ production health
class TestProdHealth(Base):
    def setUp(self) -> None:
        super().setUp()
        self.ds("set", "autonomy.production", '{"when": "on_release", "method": "compose"}')
        self.flag = self.root / "healthy"
        self.ds("set", "autonomy.production.health", json.dumps({"command": f"test -e {self.flag}", "interval_min": 15}))

    def test_two_failures_make_a_single_expedite_issue(self) -> None:
        p = self.ds("prod-check", expect=1)
        self.assertIn("I-001 opened (expedite)", p.stdout)
        p = self.ds("prod-check", expect=1)
        self.assertIn("I-001 updated", p.stdout)
        iss = self.state()["issues"]
        self.assertEqual(list(iss), ["I-001"])
        self.assertEqual((iss["I-001"]["class"], iss["I-001"]["severity"], iss["I-001"]["failures"]), ("expedite", "high", 2))
        needs = json.loads(self.ds("backlog", "--json").stdout)["needs"]
        self.assertEqual([(x["kind"], x["issue"], x["failures"]) for x in needs if x["kind"] == "prod_health"], [("prod_health", "I-001", 2)])

    def test_recovery_clears_needs_you_and_a_closed_issue_is_not_reused(self) -> None:
        self.ds("prod-check", expect=1)
        self.flag.write_text("", encoding="utf-8")
        self.assertIn("prod-check: ok", self.ds("prod-check").stdout)
        self.assertEqual([x for x in json.loads(self.ds("backlog", "--json").stdout)["needs"] if x["kind"] == "prod_health"], [])
        self.ds("issue", "I-001", "--status", "done")
        self.flag.unlink()
        self.assertIn("I-002 opened", self.ds("prod-check", expect=1).stdout)

    def test_history_and_the_due_interval(self) -> None:
        self.ds("prod-check", expect=1)
        self.assertEqual(self.ds("prod-check", "--due").stdout.strip(), "prod-check: not due")
        self.env["DEV_KIT_NOW"] = "2026-11-23T12:16:00Z"
        self.ds("prod-check", "--due", expect=1)
        log = json.loads((self.dev / "run" / "prod-health.json").read_text(encoding="utf-8"))
        self.assertEqual((len(log["checks"]), log["streak"], log["last"]["ok"]), (2, 2, False))

    def test_a_url_check(self) -> None:
        self.ds("set", "autonomy.production.health", '{"command": null, "url": "http://127.0.0.1:9/health"}')
        p = self.ds("prod-check", "--json", expect=1)
        self.assertFalse(json.loads(p.stdout)["last"]["ok"])
        self.ds("set", "autonomy.production.health", '{"url": "ftp://x"}', expect=1)

    def test_no_check_configured(self) -> None:
        self.ds("set", "autonomy.production.health", '{"command": null}')
        self.assertIn("no production health check", self.ds("prod-check", expect=1).stderr)

    def test_board_stable_phase_shows_the_last_check(self) -> None:
        import dev_board as db
        self.assertIsNone(db.build_state(self.root)["prod_health"]["last"])
        self.ds("prod-check", expect=1)
        hc = db.build_state(self.root)["prod_health"]
        self.assertEqual((hc["last"]["ok"], hc["last"]["issue"], hc["interval_min"], len(hc["history"])), (False, "I-001", 15, 1))


sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_v3_board as tb  # noqa: E402  the board render helper (real server + Chromium)


@unittest.skipUnless(tb.HAS_PLAYWRIGHT, "node and Playwright are needed to render the board")
class TestHealthRendered(tb.RenderBase):
    def test_failing_check_shows_in_needs_you_and_in_stable(self) -> None:
        self.ds("set", "autonomy.release_flags", '{"enabled": true, "provider": "env var"}')
        self.ds("set", "autonomy.production", '{"when": "per_milestone_flagged", "method": "compose"}')
        self.ds("set", "autonomy.production.health", '{"command": "exit 3"}')
        self.ds("sync-plan")
        self.ds("prod-check", expect=1)
        out = self.render([["text", "#impediments", "needs"], ["click", "#ph-stable"], ["text", "#st-health", "health"],
                           ["text", "#st-prod", "prod"], ["text", "#st-prod-sub", "sub"]])
        self.assertIn("PRODUCTION IS FAILING ITS HEALTH CHECK", out["needs"].upper())  # titles are styled uppercase
        self.assertIn("I-001", out["needs"])
        self.assertIn("1 failed check", out["needs"])
        self.assertIn("✕ failing", out["health"])
        self.assertIn("EVERY 15 MIN · EXIT 3", out["health"].upper())
        self.assertIn("release_R1", out["prod"])
        self.assertIn("behind the release flag", out["sub"])


if __name__ == "__main__":
    unittest.main()
