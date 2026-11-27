"""dev_journey.py: the project's journey rebuilt from .dev/ (log.md, telemetry.jsonl, state.json), the same way every time."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dev_journey as jr  # noqa: E402

LOG = """# Log
- 2026-11-02T09:00:00+00:00 init created (phase=conception, language=en)
- 2026-11-02T12:00:00+00:00 artifact mark prd, architecture
- 2026-11-02T13:00:00+00:00 review prd pass score=94
- 2026-11-04T09:00:00+00:00 sync-plan +1 milestones, +2 tasks, ~0 updated
- 2026-11-04T12:00:00+00:00 checkpoint plan confirm by user
- 2026-11-05T09:00:00+00:00 start T-001 Skeleton tier=balanced arm=sonnet/medium
- 2026-11-05T09:40:00+00:00 done T-001 commit=ab418bf
- 2026-11-05T10:00:00+00:00 start T-002 Sign-in tier=quality arm=opus/high
- 2026-11-05T10:20:00+00:00 block T-002: needs the OAuth keys
- 2026-11-05T11:00:00+00:00 unblock T-002
- 2026-11-05T11:05:00+00:00 start T-002 Sign-in tier=quality arm=opus/high
- 2026-11-05T11:45:00+00:00 done T-002 commit=753dfc3
- 2026-11-05T15:01:00+00:00 gate M1 pending score=81 (search misses accents)
- 2026-11-05T16:00:00+00:00 gate M1 passed score=100
- 2026-11-05T17:00:00+00:00 release 1.0.0 (v1.0.0): M1
- 2026-11-06T09:00:00+00:00 add-question Q-001 (implement): One list or many?
- 2026-11-06T09:30:00+00:00 cleanup killed=0 stale_files=0 skipped=0
"""


def tel(ts: str, event: str, **kw) -> str:
    return json.dumps({"v": 1, "ts": ts, "session": "s1", "kit": "3.26.0", "event": event, **kw})


TELEMETRY = [
    tel("2026-11-05T08:55:00Z", "skill_start", skill="implement", scope="M1"),
    tel("2026-11-05T09:01:00Z", "agent_spawn", agent="implementer", model="sonnet", effort="medium", scope="T-001", slot=1),
    # out of file order on purpose: the journey pairs in time order
    tel("2026-11-05T09:39:00Z", "agent_end", agent="implementer", model="sonnet", effort="medium", scope="T-001", slot=1, tokens=21000),
    tel("2026-11-05T11:50:00Z", "skill_end", skill="implement", scope="M1", status="ok"),
    tel("2026-11-05T09:30:00Z", "skill_start", skill="board"),
    tel("2026-11-01T09:00:00Z", "skill_start", skill="prd"),
]


class JourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        dev = self.root / ".dev"
        (dev / "costs").mkdir(parents=True)
        (dev / "log.md").write_text(LOG, encoding="utf-8")
        (dev / "telemetry.jsonl").write_text("\n".join(TELEMETRY) + "\n", encoding="utf-8")
        (dev / "state.json").write_text(json.dumps({
            "version": 3, "project": "demo", "created_at": "2026-11-02T09:00:00+00:00",
            "milestones": {"M1": {"title": "Skeleton", "gate": "passed", "release": "R1", "qa_runs": 2, "passed_at": "2026-11-05T16:00:00+00:00"}},
            "tasks": {"T-001": {"title": "Skeleton", "milestone": "M1", "status": "done"},
                      "T-002": {"title": "Sign-in", "milestone": "M1", "status": "done"}},
            "releases": [{"version": "1.0.0", "tag": "v1.0.0", "milestones": ["M1"], "at": "2026-11-05T17:00:00+00:00", "release": "R1"}],
        }), encoding="utf-8")
        (dev / "costs" / "milestones.json").write_text(json.dumps({"milestones": {"M1": {"usd": 1.5, "tokens": 9000}}}), encoding="utf-8")
        os.environ["DEV_KIT_NOW"] = "2026-11-07T00:00:00Z"
        self.j = jr.build(self.root)

    def tearDown(self) -> None:
        os.environ.pop("DEV_KIT_NOW", None)
        self.tmp.cleanup()

    def kinds(self, k: str) -> list[dict]:
        return [it for it in self.j["items"] if it["k"] == k]

    def test_task_runs_are_bars_from_start_to_their_end(self) -> None:
        runs = self.kinds("task")
        self.assertEqual([(r["r"], r["s"]) for r in runs], [("T-001", "done"), ("T-002", "blocked"), ("T-002", "done")])
        self.assertEqual(runs[0]["e"] - runs[0]["t"], 40 * 60)
        self.assertEqual(runs[0]["v"]["commit"], "ab418bf")
        self.assertEqual(runs[0]["m"], "M1")
        self.assertEqual(len(self.kinds("task_blocked")), 1)

    def test_lanes_follow_the_flow(self) -> None:
        lane = {it["k"] + ":" + it.get("r", ""): it["l"] for it in self.j["items"]}
        self.assertEqual(lane["artifact:prd"], "conception")
        self.assertEqual(lane["review:prd"], "conception")
        self.assertEqual(lane["checkpoint:plan"], "planning")
        self.assertEqual(lane["plan_sync:"], "planning")
        self.assertEqual(lane["gate:M1"], "construction")
        self.assertEqual(lane["released:1.0.0"], "releases")
        self.assertEqual(lane["question_open:Q-001"], "inbox")

    def test_technical_lines_and_viewer_skills_are_left_out(self) -> None:
        self.assertFalse([it for it in self.j["items"] if "cleanup" in json.dumps(it)])
        self.assertFalse([it for it in self.kinds("skill") if it["v"]["skill"] == "board"])

    def test_skill_runs_and_agents_are_paired(self) -> None:
        impl = [it for it in self.kinds("skill") if it["v"]["skill"] == "implement"][0]
        self.assertEqual((impl["s"], impl["l"], impl["m"]), ("ok", "construction", "M1"))
        ag = self.kinds("agent")[0]
        self.assertEqual((ag["s"], ag["m"], ag["v"]["tokens"]), ("ok", "M1", 21000))
        stale = [it for it in self.kinds("skill") if it["v"]["skill"] == "prd"][0]
        self.assertEqual(stale["s"], "no_end")  # a start with no end, days old: not running

    def test_bands_carry_duration_and_cost(self) -> None:
        m1 = self.j["milestones"][0]
        self.assertEqual((m1["id"], m1["status"], m1["usd"], m1["tasks"]), ("M1", "done", 1.5, 2))
        r1 = self.j["releases"][0]
        self.assertEqual((r1["id"], r1["status"], r1["version"], r1["usd"]), ("R1", "released", "1.0.0", 1.5))
        self.assertGreater(r1["to"], r1["from"])

    def test_the_same_files_give_the_same_journey(self) -> None:
        self.assertEqual(json.dumps(jr.build(self.root), sort_keys=True), json.dumps(self.j, sort_keys=True))

    def test_the_board_serves_it_and_rebuilds_only_when_a_file_changes(self) -> None:
        import dev_board
        first = dev_board.journey_data(self.root)
        self.assertTrue(first["ok"])
        self.assertEqual(len(dev_board.journey_data(self.root)["items"]), len(first["items"]))
        with (self.root / ".dev" / "log.md").open("a", encoding="utf-8") as f:
            f.write("- 2026-11-06T10:00:00+00:00 answer-question Q-001: one list\n")
        self.assertEqual(len(dev_board.journey_data(self.root)["items"]), len(first["items"]) + 1)

    def test_command_line(self) -> None:
        env = dict(os.environ)
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_journey.py"), "--root", str(self.root), "build", "--json"],
                           capture_output=True, text=True, env=env, check=True)
        self.assertEqual(json.loads(p.stdout)["counts"]["tasks"], len([it for it in self.j["items"] if it["c"] == "tasks"]))
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_journey.py"), "--root", self.tmp.name + "/none", "build"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
