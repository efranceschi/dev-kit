"""Tests for scripts/dev_diagram.py (the architecture diagram) and its place on the board and in the queue.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ["DEV_KIT_CLAUDE"] = __import__("shutil").which("true") or "/bin/true"

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dev_diagram as dg  # noqa: E402
import dev_worker as dw  # noqa: E402

SCRIPT = CORE / "scripts" / "dev_diagram.py"
SVG_NS = "{http://www.w3.org/2000/svg}"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / ".dev").mkdir()
        (self.root / ".dev" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_dg(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def write_model(self, m: dict) -> None:
        p = self.root / dg.MODEL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m), encoding="utf-8")


class TestModel(unittest.TestCase):
    def test_example_is_valid(self):
        clean, errors = dg.validate(dg.example())
        self.assertEqual(errors, [])
        self.assertEqual(len(clean["layers"]), 4)

    def test_errors_name_the_field(self):
        m = copy.deepcopy(dg.example())
        m["layers"][0]["nodes"][0]["kind"] = "spaceship"
        m["layers"][1]["nodes"][0]["id"] = "api"            # used twice
        m["edges"].append({"from": "web", "to": "nowhere"})
        m["edges"].append({"from": "db", "to": "db"})
        m["edges"].append({"from": "api", "to": "jobs", "style": "telepathy"})
        _, errors = dg.validate(m)
        text = "\n".join(errors)
        self.assertIn("layers[0].nodes[0].kind", text)
        self.assertIn("'api' is used twice", text)
        self.assertIn("no node 'nowhere'", text)
        self.assertIn("cannot point to itself", text)
        self.assertIn("edges[8].style", text)

    def test_high_level_only(self):
        m = {"title": "Big", "layers": [{"id": f"l{i}", "label": "L", "nodes": [{"id": f"n{i}-{j}", "label": "N"} for j in range(9)]}
                                         for i in range(9)]}
        _, errors = dg.validate(m)
        self.assertTrue(any("at most 8 (9)" in e for e in errors))
        self.assertTrue(any("at most 8 per layer" in e for e in errors))

    def test_layout_keeps_everything_inside_the_picture(self):
        m = copy.deepcopy(dg.example())
        m["edges"].append({"from": "user", "to": "db", "label": "far", "style": "data"})   # skips layers: the corridor
        m["edges"].append({"from": "api", "to": "jobs", "label": "beside"})
        m["edges"].append({"from": "db", "to": "mail", "label": "under"})                  # same layer, not neighbours
        clean, errors = dg.validate(m)
        self.assertEqual(errors, [])
        lay = dg.layout(clean)
        for e in lay["edges"]:
            for x, y in e["points"]:
                self.assertTrue(0 <= x <= lay["width"] and 0 <= y <= lay["height"], (e["from"], e["to"], x, y))
            for (x1, y1), (x2, y2) in zip(e["points"], e["points"][1:]):
                self.assertTrue(abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5, "right angles only")
        far = next(e for e in lay["edges"] if e["to"] == "db" and e["from"] == "user")
        self.assertGreater(max(x for x, _ in far["points"]), lay["lanes"][0]["x"] + lay["lanes"][0]["w"])


class TestRenderAndCheck(Base):
    def test_missing_then_current_then_stale(self):
        r = self.run_dg("check")
        self.assertEqual(r.returncode, 3)
        self.write_model(dg.example())
        r = self.run_dg("render", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["layers"], out["nodes"]), (4, 7))
        self.assertEqual(self.run_dg("check").returncode, 0)
        st = dg.status(self.root)
        self.assertTrue(st["exists"] and st["current"] and not st["stale"])
        # the model changes: the picture is no longer current
        m = dg.example()
        m["title"] = "Changed"
        self.write_model(m)
        self.assertEqual(self.run_dg("check").returncode, 4)
        self.run_dg("render")
        self.assertEqual(self.run_dg("check").returncode, 0)
        # the architecture changes: out of date until redrawn
        (self.root / ".dev" / "architecture.md").write_text("# Architecture\nA queue was added.\n", encoding="utf-8")
        r = self.run_dg("check", "--json")
        self.assertEqual(r.returncode, 4)
        self.assertTrue(json.loads(r.stdout)["stale"])

    def test_outputs_are_well_formed_svg_and_drawio(self):
        m = dg.example()
        m["title"] = "Shop <&> \"quotes\""
        m["layers"][1]["nodes"][0]["label"] = "Web & <app>"
        self.write_model(m)
        self.assertEqual(self.run_dg("render").returncode, 0)
        svg = ET.parse(self.root / dg.SVG).getroot()
        self.assertEqual(svg.tag, f"{SVG_NS}svg")
        self.assertEqual(len(svg.findall(f".//{SVG_NS}g[@class='node']")), 7)
        self.assertEqual(len(svg.findall(f".//{SVG_NS}path[@class='edge']")), 6)
        self.assertFalse(svg.findall(f".//{SVG_NS}script"))
        mx = ET.parse(self.root / dg.DRAWIO).getroot()
        self.assertEqual(mx.tag, "mxfile")
        cells = mx.findall(".//mxCell")
        self.assertEqual(sum(1 for c in cells if c.get("edge") == "1"), 6)
        self.assertEqual(sum(1 for c in cells if (c.get("style") or "").startswith("swimlane")), 4)
        web = next(c for c in cells if c.get("id") == "web")
        self.assertEqual(web.get("parent"), "lane-clients")
        self.assertIn("Web &amp; &lt;app&gt;", web.get("value"))

    def test_same_model_same_picture(self):
        self.write_model(dg.example())
        self.run_dg("render")
        a = (self.root / dg.SVG).read_text().split("\n", 1)[1]
        self.run_dg("render")
        self.assertEqual(a, (self.root / dg.SVG).read_text().split("\n", 1)[1])

    def test_invalid_model_writes_nothing(self):
        self.write_model({"title": "x", "layers": []})
        r = self.run_dg("render")
        self.assertEqual(r.returncode, 1)
        self.assertIn("layers", r.stderr)
        self.assertFalse((self.root / dg.SVG).exists())


class TestBoardAndQueue(Base):
    def test_the_queue_accepts_the_diagram_commands_only(self):
        ok = [c for c in ("/dev-kit:diagram", "/dev-kit:diagram update") if any(rx.match(c) for rx in dw.RUN_COMMANDS)]
        self.assertEqual(len(ok), 2)
        self.assertFalse(any(rx.match("/dev-kit:diagram update; rm -rf /") for rx in dw.RUN_COMMANDS))

    def test_board_serves_the_diagram_and_reports_it_in_the_state(self):
        from test_dev_board import BoardTest, request
        bt = BoardTest("test_start_twice_reuses_the_same_server")
        bt.setUp()
        try:
            bt.board("start", check=True)
            st, _ = request(bt.port, "GET", "/api/diagram")
            self.assertEqual(st, 404)
            st, body = request(bt.port, "GET", "/api/state")
            self.assertFalse(json.loads(body)["diagram"]["exists"])
            p = bt.root / dg.MODEL
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps(dg.example()), encoding="utf-8")
            subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(bt.root), "render"], check=True, capture_output=True)
            st, body = request(bt.port, "GET", "/api/diagram")
            self.assertEqual(st, 200)
            self.assertTrue(body.lstrip().startswith(b"<!-- dev-kit diagram"))
            st, body = request(bt.port, "GET", "/api/state")
            d = json.loads(body)["diagram"]
            self.assertTrue(d["exists"] and d["current"])
        finally:
            bt.tearDown()

    def test_board_page_has_the_button_next_to_map(self):
        html = (CORE / "shared" / "board" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="ph-map"'), html.index('id="ph-arch"'))
        self.assertLess(html.index('id="ph-arch"'), html.index('id="phases"'))
        js = (CORE / "shared" / "board" / "board.js").read_text(encoding="utf-8")
        self.assertIn('"/dev-kit:diagram update"', js)
        self.assertIn("/^\\/dev-kit:diagram(?: update)?$/", js)


class TestDocsMakeItMandatory(unittest.TestCase):
    def test_docs_skill_and_reviewer_require_the_diagram(self):
        skills = CORE.parent
        docs = (skills / "docs" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Architecture diagram (mandatory", docs)
        self.assertIn("dev-kit:diagram", docs)
        reviewer = (skills.parent / "agents" / "docs-reviewer.md").read_text(encoding="utf-8")
        self.assertIn("dev_diagram.py check", reviewer)


if __name__ == "__main__":
    unittest.main()
