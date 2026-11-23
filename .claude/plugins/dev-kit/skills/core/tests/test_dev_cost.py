"""Tests for dev_cost.py (token usage and estimated cost per stage). Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
STATE = SCRIPTS / "dev_state.py"
COST = SCRIPTS / "dev_cost.py"
SECRET = "Pflaumenkuchen-secret-content"


def line(rid: str, model: str, ts: str, inp=0, out=0, w5=0, w1=0, cr=0, sid="s1", block=0, agent_id=None, speed="standard") -> str:
    rec = {
        "type": "assistant", "requestId": rid, "timestamp": ts, "sessionId": sid, "isSidechain": agent_id is not None,
        "agentId": agent_id,
        "message": {"model": model, "content": [{"type": "text", "text": f"{SECRET} block {block}"}],
                    "usage": {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": w5 + w1,
                              "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
                              "cache_read_input_tokens": cr, "speed": speed}},
    }
    return json.dumps(rec) + "\n"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        self.tdir = Path(self.tmp.name) / "transcripts"
        (self.tdir / "s1" / "subagents").mkdir(parents=True)
        self.sh(STATE, "init", "--project", "demo")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def sh(self, script: Path, *args: str, expect: int = 0, at: str | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "DEV_KIT_NOW"}
        if at:
            env["DEV_KIT_NOW"] = at  # pinned clock: the script measures skill durations itself
        proc = subprocess.run([sys.executable, "-I", str(script), "--root", str(self.root), *args],
                              capture_output=True, text=True, cwd=self.root, env=env)
        self.assertEqual(proc.returncode, expect, msg=f"{args}\n{proc.stdout}\n{proc.stderr}")
        return proc

    def report(self, *extra: str) -> dict:
        return json.loads(self.sh(COST, "report", "--json", "--all", "--transcripts", str(self.tdir), *extra).stdout)

    def write_main(self, text: str) -> None:
        (self.tdir / "s1.jsonl").write_text(text, encoding="utf-8")

    def write_sub(self, aid: str, agent_type: str, text: str) -> None:
        d = self.tdir / "s1" / "subagents"
        (d / f"agent-{aid}.jsonl").write_text(text, encoding="utf-8")
        (d / f"agent-{aid}.meta.json").write_text(json.dumps({"agentType": agent_type, "description": SECRET}), encoding="utf-8")


class TestIngest(Base):
    def test_dedupe_synthetic_and_idempotent(self) -> None:
        self.write_main(
            line("r1", "claude-sonnet-5-5", "2026-11-18T10:00:00Z", inp=100, out=10, block=0) +
            line("r1", "claude-sonnet-5-5", "2026-11-18T10:00:01Z", inp=100, out=50, block=1) +
            line("r1", "claude-sonnet-5-5", "2026-11-18T10:00:02Z", inp=100, out=80, block=2) +
            line("r2", "<synthetic>", "2026-11-18T10:01:00Z", inp=5))
        self.sh(COST, "ingest", "--transcripts", str(self.tdir))
        self.sh(COST, "ingest", "--transcripts", str(self.tdir))
        usage = (self.root / ".dev" / "costs" / "usage.jsonl").read_text(encoding="utf-8")
        recs = [json.loads(x) for x in usage.splitlines()]
        self.assertEqual(len(recs), 1)                    # 3 lines of one request + 1 synthetic -> 1 record
        self.assertEqual((recs[0]["input"], recs[0]["output"]), (100, 80))   # last line wins
        self.assertNotIn(SECRET, usage)
        self.assertTrue((self.root / ".dev" / "costs" / "prices.json").exists())

    def test_pricing(self) -> None:
        self.write_main(line("r1", "claude-sonnet-5-5", "2026-11-18T10:00:00Z", inp=1_000_000, out=1_000_000) +
                        line("r2", "claude-sonnet-5-5", "2026-11-18T10:00:05Z", cr=1_000_000) +
                        line("r3", "claude-opus-5-5", "2026-11-18T10:00:06Z", w5=1_000_000, w1=1_000_000) +
                        line("r4", "claude-opus-5-5", "2026-11-18T10:00:07Z", out=1_000_000, speed="fast"))
        rep = self.report("--by", "model")
        by = {r["key"]: r for r in rep["rows"]}
        self.assertAlmostEqual(by["claude-sonnet-5-5"]["usd"], 12.10)   # 2 + 10 + cache read 0.10
        self.assertAlmostEqual(by["claude-opus-5-5"]["usd"], 4 * 1.25 + 4 * 2 + 20 * 2)  # writes 5m/1h + fast output
        self.assertTrue(rep["total"]["usd_complete"])

    def test_unknown_model_keeps_tokens(self) -> None:
        self.write_main(line("r1", "claude-future-9", "2026-11-18T10:00:00Z", inp=500, out=7))
        rep = self.report("--by", "model")
        self.assertEqual(rep["rows"][0]["input"], 500)
        self.assertFalse(rep["total"]["usd_complete"])
        self.assertTrue(any("no price for: claude-future-9" in w for w in rep["warnings"]))
        self.assertIn("*", self.sh(COST, "report", "--all", "--by", "model", "--transcripts", str(self.tdir)).stdout)

    def test_placeholder_and_long_request_ids_stay_distinct(self) -> None:
        def rec(rid, mid, uuid, out):
            r = json.loads(line(rid, "claude-sonnet-5-5", "2026-11-18T10:00:00Z", out=out))
            r["message"]["id"], r["uuid"] = mid, uuid
            return json.dumps(r) + "\n"
        long_id = "gw/" + "x" * 90
        self.write_main(rec("unknown", "msg_a", "u1", 1) + rec("unknown", "msg_b", "u2", 2) +
                        rec("", None, "u3", 3) + rec(long_id, None, "u4", 4) + rec(long_id + "y", None, "u5", 5))
        rep = self.report()
        self.assertEqual(rep["total"]["requests"], 5)
        self.assertEqual(rep["total"]["output"], 15)

    def test_gateway_model_names_are_priced(self) -> None:
        self.write_main(line("r1", "system.ai.claude-opus-5-5", "2026-11-18T10:00:00Z", out=1_000_000) +
                        line("r2", "us.anthropic.claude-sonnet-5-5-v1:0", "2026-11-18T10:00:01Z", out=1_000_000) +
                        line("r3", "system.ai.opus-next", "2026-11-18T10:00:02Z", out=1_000_000))
        rep = self.report("--by", "model")
        by = {r["key"]: r for r in rep["rows"]}
        self.assertAlmostEqual(by["claude-opus-5-5"]["usd"], 20)        # prefix stripped at ingest
        self.assertAlmostEqual(by["claude-sonnet-5-5"]["usd"], 10)      # provider prefix and -v1:0 stripped
        self.assertAlmostEqual(by["system.ai.opus-next"]["usd"], 20)    # family fallback: first opus listed
        self.assertTrue(rep["total"]["usd_complete"])
        self.assertTrue(any("priced as claude-opus-5-5" in w for w in rep["warnings"]))


class TestTime(Base):
    def test_time_by_agent_and_skill_with_ledger_reuse(self) -> None:
        self.write_sub("a1", "implementer", line("q1", "claude-sonnet-5-5", "2026-11-18T10:00:00Z", agent_id="a1") +
                       line("q2", "claude-sonnet-5-5", "2026-11-18T10:20:00Z", agent_id="a1"))
        self.write_sub("a2", "implementer", line("q3", "claude-sonnet-5-5", "2026-11-18T11:00:00Z", agent_id="a2") +
                       line("q4", "claude-sonnet-5-5", "2026-11-18T11:10:00Z", agent_id="a2"))
        self.write_sub("a3", "test-auditor", line("q5", "claude-sonnet-5-5", "2026-11-18T12:00:00Z", agent_id="a3") +
                       line("q6", "claude-sonnet-5-5", "2026-11-18T12:30:00Z", agent_id="a3"))
        self.sh(STATE, "event", "skill_start", "--set", "skill=qa", at="2026-11-18T12:00:00Z")
        self.sh(STATE, "event", "skill_end", "--set", "skill=qa", "--set", "status=ok", at="2026-11-18T12:40:00Z")
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("x = 1\n")
        self.sh(STATE, "ledger", "plan", "--prefix", "audit:code", "--files", "src/a.py")
        rep = json.loads(self.sh(COST, "report", "--time", "--all", "--json", "--transcripts", str(self.tdir)).stdout)
        rows = {(r["kind"], r["name"]): r for r in rep["rows"]}
        imp = rows[("agent", "implementer")]
        self.assertEqual((imp["runs"], imp["avg_min"], imp["max_min"]), (2, 15.0, 20.0))
        self.assertEqual(rows[("skill", "qa")]["total_min"], 40.0)
        self.assertAlmostEqual(imp["share"], 30 / 100 * 100, places=1)  # 30 of 100 minutes
        self.assertEqual(rep["reuse"]["audit:code"]["review"], 1)
        self.assertIn("implementer", self.sh(COST, "report", "--time", "--all", "--transcripts", str(self.tdir)).stdout)


class TestAttribution(Base):
    def ev(self, *args: str) -> None:
        self.sh(STATE, "event", *args)

    def test_stage_windows_and_subagents(self) -> None:
        tl = self.root / ".dev" / "telemetry.jsonl"
        rows = [("2026-11-18T09:00:00Z", "skill_start", "qa"), ("2026-11-18T09:30:00Z", "skill_end", "qa"),
                ("2026-11-18T10:00:00Z", "skill_start", "implement"), ("2026-11-18T11:00:00Z", "skill_end", "implement")]
        with tl.open("a", encoding="utf-8") as f:
            for ts, ev, skill in rows:
                f.write(json.dumps({"v": 1, "ts": ts, "session": "abcd1234", "kit": "1", "event": ev, "skill": skill}) + "\n")
        self.write_main(line("m1", "claude-opus-5-5", "2026-11-18T09:10:00Z", out=100) +
                        line("m2", "claude-opus-5-5", "2026-11-18T10:10:00Z", out=200) +
                        line("m3", "claude-opus-5-5", "2026-11-18T12:00:00Z", out=300))
        self.write_sub("a1", "dev-kit:code-reviewer", line("x1", "claude-sonnet-5-5", "2026-11-18T09:05:00Z", out=10, agent_id="a1") +
                       line("x2", "claude-sonnet-5-5", "2026-11-18T09:40:00Z", out=20, agent_id="a1"))   # started in qa
        self.write_sub("a2", "dev-kit:implementer", line("y1", "claude-sonnet-5-5", "2026-11-18T08:00:00Z", out=40, agent_id="a2"))
        rep = self.report()
        by = {r["key"]: r for r in rep["rows"]}
        self.assertEqual(by["qa"]["output"], 100 + 10 + 20)
        self.assertEqual(by["implement"]["output"], 200 + 40)
        self.assertEqual(by["orchestration"]["output"], 300)
        agents = {r["key"]: r for r in self.report("--by", "agent")["rows"]}
        self.assertEqual(agents["dev-kit:code-reviewer"]["requests"], 2)
        self.assertEqual(agents["main"]["requests"], 3)

    def test_csv_and_status(self) -> None:
        self.write_main(line("r1", "claude-sonnet-5-5", "2026-11-18T10:00:00Z", inp=10, out=20, w5=30, w1=40, cr=50))
        self.sh(COST, "export", "--all", "--stamp", "20261118-120000", "--transcripts", str(self.tdir))
        self.sh(COST, "export", "--all", "--stamp", "20261118-120000", "--transcripts", str(self.tdir))
        files = sorted((self.root / ".dev" / "costs").glob("tokens-*.csv"))
        self.assertEqual([f.name for f in files], ["tokens-20261118-120000-2.csv", "tokens-20261118-120000.csv"])
        rows = list(csv.DictReader(files[0].open(encoding="utf-8")))
        self.assertEqual((rows[0]["input"], rows[0]["output"], rows[0]["cache_write_5m"], rows[0]["cache_write_1h"], rows[0]["cache_read"]),
                         ("10", "20", "30", "40", "50"))
        self.report()
        self.assertIn("Cost (est., API-equivalent): US$", self.sh(STATE, "status").stdout)

    def test_no_transcripts_falls_back_to_skill_tokens(self) -> None:
        self.ev("agent_end", "--set", "agent=code-reviewer", "--set", "scope=M1", "--set", "tokens=1234")
        rep = json.loads(self.sh(COST, "report", "--json", "--all", "--transcripts", str(self.tdir / "missing")).stdout)
        self.assertEqual(rep["source"], "skills (partial)")
        self.assertEqual(rep["total"]["input"], 1234)
        self.assertTrue(any(w.startswith("partial") for w in rep["warnings"]))


class TestByMilestone(Base):
    """Usage is spent on the milestone of the task in progress, or of its QA window (the board's velocity reads it)."""

    def setUp(self) -> None:
        super().setUp()
        sp = self.root / ".dev" / "state.json"
        st = json.loads(sp.read_text(encoding="utf-8"))
        st["milestones"] = {"M1": {"title": "One", "gate": "passed", "passed_at": "2026-11-18T12:00:00+00:00"},
                            "M2": {"title": "Two", "gate": "pending"}}
        st["tasks"] = {
            "T-001": {"title": "a", "milestone": "M1", "status": "done", "started_at": "2026-11-18T09:00:00+00:00", "done_at": "2026-11-18T10:00:00+00:00"},
            "T-002": {"title": "b", "milestone": "M1", "status": "done", "started_at": "2026-11-18T09:30:00+00:00", "done_at": "2026-11-18T11:00:00+00:00"},
            "T-003": {"title": "c", "milestone": "M2", "status": "in_progress", "started_at": "2026-11-18T13:00:00+00:00", "done_at": None},
        }
        sp.write_text(json.dumps(st), encoding="utf-8")

    def test_rows_go_to_the_running_task_or_the_qa_window(self) -> None:
        self.write_main(line("a", "claude-opus-5-5", "2026-11-18T09:45:00Z", out=100) +   # T-001 and T-002 run: M1
                        line("b", "claude-opus-5-5", "2026-11-18T11:30:00Z", out=200) +   # QA window of M1
                        line("c", "claude-opus-5-5", "2026-11-18T12:30:00Z", out=300) +   # between milestones: none
                        line("d", "claude-opus-5-5", "2026-11-18T13:30:00Z", out=400))    # T-003 runs: M2
        by = {r["key"]: r for r in self.report("--by", "milestone")["rows"]}
        self.assertEqual((by["M1"]["output"], by["M2"]["output"], by["other"]["output"]), (300, 400, 300))
        ms = json.loads((self.root / ".dev" / "costs" / "milestones.json").read_text(encoding="utf-8"))["milestones"]
        self.assertEqual((ms["M1"]["tokens"], ms["M2"]["tokens"]), (300, 400))
        self.assertGreater(ms["M1"]["usd"], 0)
        self.assertFalse(ms["M1"]["partial"])
        self.sh(COST, "ingest", "--transcripts", str(self.tdir))  # ingest refreshes it too
        self.assertIn("M2", json.loads((self.root / ".dev" / "costs" / "milestones.json").read_text(encoding="utf-8"))["milestones"])

    def test_without_transcripts_the_skill_tokens_per_scope(self) -> None:
        self.sh(STATE, "event", "agent_end", "--set", "agent=implementer", "--set", "scope=T-003", "--set", "tokens=500")
        self.sh(STATE, "event", "agent_end", "--set", "agent=code-reviewer", "--set", "scope=M1", "--set", "tokens=70")
        self.sh(COST, "ingest", "--transcripts", str(self.tdir / "missing"))
        ms = json.loads((self.root / ".dev" / "costs" / "milestones.json").read_text(encoding="utf-8"))["milestones"]
        self.assertEqual((ms["M2"]["tokens"], ms["M1"]["tokens"], ms["M2"]["partial"], ms["M2"]["usd"]), (500, 70, True, 0.0))


if __name__ == "__main__":
    unittest.main()
