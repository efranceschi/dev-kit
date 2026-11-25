"""3.14.0 - the board at scale: lean live updates, the timeline (newest first, the past folded) and grouped lists.

The stress projects of docs/demo/stress/ measure the limits by hand; these tests keep the mechanisms in place.
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v3_board import BOARD, HAS_PLAYWRIGHT, SCRIPTS, Base, RenderBase  # noqa: E402

sys.path.insert(0, str(SCRIPTS))


def release(t: Base, r: str, version: str) -> None:
    review = t.dev / "releases" / r / "review.md"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(f"# Release {r}\n\n## Summary\nx\n", encoding="utf-8")
    t.ds("release-submit", r, "--review", f".dev/releases/{r}/review.md")
    t.ds("release-decide", r, "--approve")
    t.ds("release-record", "--version", version, "--release", r)


class TestLeanState(Base):
    def test_snapshot_drops_what_the_board_never_reads(self) -> None:
        self.ds("start", "T-001")
        import dev_board
        st = dev_board.build_state(self.root)
        self.assertNotIn("tasks", st["backlog"])  # the task list already travels once, in "tasks"
        for t in st["tasks"].values():
            self.assertFalse([k for k, v in t.items() if v in (None, [], "")], t)
        self.assertEqual(st["denied_total"], 0)

    def test_state_is_compact_and_gzipped_when_the_browser_accepts_it(self) -> None:
        board = SCRIPTS / "dev_board.py"
        env = {k: v for k, v in self.env.items() if k != "DEV_KIT_NOW"}
        subprocess.run([sys.executable, "-I", str(board), "--root", str(self.root), "start", "--no-open", "--port", "0"],
                       capture_output=True, text=True, env=env, check=True, timeout=60)
        try:
            url = json.loads((self.dev / "run" / "board.json").read_text(encoding="utf-8"))["url"]
            req = urllib.request.Request(url + "api/state", headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=20) as r:
                self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
                body = gzip.decompress(r.read()).decode("utf-8")
            self.assertTrue(json.loads(body)["ok"])
            self.assertNotIn('": ', body[:400])  # compact separators
            with urllib.request.urlopen(url + "api/state", timeout=20) as r:  # no Accept-Encoding: plain JSON
                self.assertIsNone(r.headers.get("Content-Encoding"))
                self.assertTrue(json.loads(r.read())["ok"])
        finally:
            subprocess.run([sys.executable, "-I", str(board), "--root", str(self.root), "stop"], capture_output=True, env=env, timeout=60)


class TestScaleSource(unittest.TestCase):
    """Cheap checks on the page source, run everywhere (the rendered checks need Playwright)."""

    js = (BOARD / "board.js").read_text(encoding="utf-8")

    def test_one_timeline_feeds_the_selectors_and_the_roadmap(self) -> None:
        self.assertGreaterEqual(self.js.count("tlEntries("), 4)  # defined, milestones selector, releases selector, roadmap
        self.assertIn("const TL_PAST = 2", self.js)

    def test_redraw_is_skipped_when_nothing_changed(self) -> None:
        self.assertIn("same === lastText", self.js)

    def test_charts_keep_a_window_and_the_agent_line_a_cap(self) -> None:
        self.assertIn("const VEL_WINDOW = 12", self.js)
        self.assertIn("const CHIP_CAP = 3", self.js)

    def test_the_kit_ships_the_stress_tools(self) -> None:
        demo = BOARD.parents[3] / "docs" / "demo" / "stress"
        self.assertTrue((demo / "build_stress.py").is_file())
        self.assertTrue((demo / "stress.js").is_file())


@unittest.skipUnless(HAS_PLAYWRIGHT, "node and Playwright are needed to render the board")
class TestTimelineRendered(RenderBase):
    def test_newest_first_with_the_released_past_folded(self) -> None:
        self.close("M1", "M2", "M3")
        release(self, "R1", "1.0.0")
        self.ds("start", "T-007")
        out = self.render([
            ["click", "#ph-construction"],
            ["eval", "[...document.querySelectorAll('#tabs .sel-group')].map((g) => g.innerText.replace(/\\s+/g, ' ').trim())", "groups"],
            ["click", "#ph-planning"],
            ["eval", "[...document.querySelectorAll('.road > li')].map((li) => li.innerText.replace(/\\s+/g, ' ').trim().slice(0, 12))", "road"],
        ])
        groups = out["groups"]
        self.assertTrue(groups[0].startswith("R2"), groups)
        self.assertLess(groups[0].index("M5"), groups[0].index("M4"))  # newest first
        self.assertTrue(any(g.startswith("R1") and "1.0.0" in g and "M1" not in g for g in groups), groups)  # R1 folded
        road = out["road"]
        self.assertTrue(road[0].startswith("R2"), road)
        self.assertLess(road.index(next(x for x in road if x.startswith("✓ M4") or "M4" in x)),
                        road.index(next(x for x in road if "R1" in x)))

    def test_needs_you_groups_blocked_tasks_by_reason_and_folds_after_two(self) -> None:
        for t in ("T-001", "T-002", "T-003"):
            self.ds("block", t, "--reason", "waiting for the API key")
        for i in range(3):
            self.ds("add-question", f"Question {i}?", "--skill", "implement")
        for i in range(5):
            self.ds("add-issue", "--type", "bug", "--title", f"Issue {i}", "--severity", "low", expect=None)
        out = self.render([
            ["click", "#needs-btn"],
            ["eval", "[...document.querySelectorAll('#impediments details.fold-list')].map((d) => d.open)", "open"],
            ["eval", "[...document.querySelectorAll('#impediments .group-head')].map((x) => x.innerText.replace(/\\s+/g, ' ').trim())", "heads"],
            ["key", "Escape"], ["click", "#act-btn"],
            ["text", "#feed", "feed"],
        ])
        self.assertEqual(out["open"][:2], [True, True])
        self.assertTrue(all(not o for o in out["open"][2:]), out["open"])
        self.assertIn("waiting for the API key 3", out["heads"])
        self.assertRegex(out["feed"], r"\d+ more like this")


if __name__ == "__main__":
    unittest.main()
