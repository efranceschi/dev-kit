"""Tests for the Claude Code interface: dev_ui.py, dev_statusline.py, the hooks in dev_agent_hook.py and
dev_state.py next_command / notify (conventions.md §15).

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
STATE = CORE / "scripts" / "dev_state.py"
UI = CORE / "scripts" / "dev_ui.py"
LINE = CORE / "scripts" / "dev_statusline.py"
HOOK = CORE / "scripts" / "dev_agent_hook.py"

PLAN = """# Implementation plan — demo

## M1 — Walking skeleton
Ship a deployable skeleton.

### T-001 Project scaffold
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-0: test and lint run green
- test_notes: smoke test
- files: package.json
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.settings = self.root / ".claude" / "settings.local.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_py(self, script: Path, *args: str, stdin: str = "", expect: int = 0) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, "-I", str(script), *args], input=stdin, capture_output=True, text=True,
                           cwd=self.root, timeout=60)
        self.assertEqual(r.returncode, expect, r.stderr + r.stdout)
        return r

    def ds(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        return self.run_py(STATE, "--root", str(self.root), *args, expect=expect)

    def ui(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        return self.run_py(UI, "--root", str(self.root), *args, expect=expect)

    def init(self, phase: str = "implement", plan: bool = True) -> None:
        self.ds("init", "--project", "demo", "--phase", phase)
        if plan:
            (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
            self.ds("sync-plan")

    def state(self) -> dict:
        return json.loads((self.root / ".dev" / "state.json").read_text(encoding="utf-8"))

    def hook(self, payload: dict) -> str:
        return self.run_py(HOOK, stdin=json.dumps({"cwd": str(self.root), **payload})).stdout.strip()


class TestSettingsFile(Base):
    def test_apply_merges_and_remove_takes_only_ours(self) -> None:
        self.init()
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]},
                                             "spinnerTipsOverride": {"tips": ["my own tip"]}}), encoding="utf-8")
        self.ui("apply", "--tips", "--statusline")
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        tips = data["spinnerTipsOverride"]["tips"]
        self.assertEqual(tips[0], "my own tip")
        self.assertTrue(len(tips) > 5 and all(t.startswith("dev-kit: ") for t in tips[1:]))
        self.assertIn("dev_statusline.py", data["statusLine"]["command"])
        self.assertIn(".claude/settings.local.json", (self.root / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        ui = self.state()["autonomy"]["ui"]
        self.assertTrue(ui["offered"] and ui["spinner_tips"] and ui["statusline"])
        self.ui("apply", "--tips")  # idempotent: ours replaced, not duplicated
        self.assertEqual(len(json.loads(self.settings.read_text(encoding="utf-8"))["spinnerTipsOverride"]["tips"]), len(tips))
        self.ui("remove")
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data, {"permissions": {"allow": ["Bash(ls)"]}, "spinnerTipsOverride": {"tips": ["my own tip"]}})
        self.assertFalse(self.state()["autonomy"]["ui"]["title"])

    def test_translated_tips_and_foreign_status_line(self) -> None:
        self.init()
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "my-line.sh"}}), encoding="utf-8")
        tf = self.root / "tips.json"
        tf.write_text(json.dumps(["Pressione Tab\u0007 para aceitar", "  "]), encoding="utf-8")
        out = self.ui("apply", "--tips", "--tips-file", str(tf), "--statusline").stdout
        self.assertIn("already has its own", out)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["statusLine"]["command"], "my-line.sh")
        self.assertEqual(data["spinnerTipsOverride"]["tips"], ["dev-kit: Pressione Tab para aceitar"])
        self.assertFalse(self.state()["autonomy"]["ui"]["statusline"])
        self.ui("remove", "--statusline")
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["statusLine"]["command"], "my-line.sh")

    def test_broken_settings_are_never_overwritten(self) -> None:
        self.init()
        self.settings.parent.mkdir()
        self.settings.write_text("{ not json", encoding="utf-8")
        self.ui("apply", "--tips", expect=1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")

    def test_repair_and_decline(self) -> None:
        self.init()
        self.settings.parent.mkdir()
        old = {"type": "command", "command": 'python3 -I "/old/plugin/1.0/skills/core/scripts/dev_statusline.py"', "refreshInterval": 10}
        self.settings.write_text(json.dumps({"statusLine": old}), encoding="utf-8")
        self.assertIn("old path", self.ui("status").stdout)
        self.assertIn("updated", self.ui("repair").stdout)
        self.assertIn(str(LINE), json.loads(self.settings.read_text(encoding="utf-8"))["statusLine"]["command"])
        self.assertEqual(self.ui("repair").stdout, "")
        self.assertFalse(self.state()["autonomy"]["ui"]["offered"])
        self.ui("decline")
        self.assertTrue(self.state()["autonomy"]["ui"]["offered"])
        self.assertTrue(json.loads(self.ui("tips").stdout))


class TestStatusLineAndHooks(Base):
    def test_status_line(self) -> None:
        payload = json.dumps({"workspace": {"current_dir": str(self.root)}})
        self.assertEqual(self.run_py(LINE, stdin=payload).stdout, "")  # not a dev-kit project
        self.init()
        self.ds("review", "plan", "pass", "--score", "90")
        self.ds("start", "T-001")
        line = self.run_py(LINE, stdin=payload).stdout.strip()
        self.assertEqual(line, "dev-kit · implement · M1 0/1 · ▶ T-001 · next /dev-kit:implement")
        self.assertEqual(self.run_py(LINE, stdin="not json").stdout, "")

    def test_session_title_only_on_startup(self) -> None:
        self.init(phase="prd", plan=False)
        out = json.loads(self.hook({"hook_event_name": "SessionStart", "source": "startup", "session_id": "s1"}))
        self.assertEqual(out["hookSpecificOutput"]["sessionTitle"], "dev-kit · demo · prd")
        self.assertIn("/dev-kit:prd", out["systemMessage"])
        self.assertEqual(self.hook({"hook_event_name": "SessionStart", "source": "resume", "session_id": "s1"}), "")
        self.ds("set", "autonomy.ui.title", "false")
        self.assertEqual(self.hook({"hook_event_name": "SessionStart", "source": "startup", "session_id": "s2"}), "")
        self.assertEqual((self.root / ".dev" / "run" / "agents.jsonl").read_text(encoding="utf-8").count("session_start"), 3)

    def test_notifications_once_and_only_when_on(self) -> None:
        self.init()
        self.ds("notify", "hello")
        self.assertFalse((self.root / ".dev" / "run" / "notify.jsonl").exists())  # notify is off by default
        self.ds("set", "autonomy.ui.notify", "true")
        self.ds("block", "T-001", "--reason", "needs a key")
        self.ds("notify", "dev-kit: autopilot\x1b stopped")
        out = json.loads(self.hook({"hook_event_name": "Stop"}))
        self.assertIn("T-001 blocked", out["systemMessage"])
        self.assertEqual(out["terminalSequence"], "\x1b]9;dev-kit: autopilot  stopped\x07")
        self.assertEqual(self.hook({"hook_event_name": "Stop"}), "")  # queue cleared
        self.assertEqual(self.hook({"hook_event_name": "Stop", "cwd": tempfile.gettempdir()}), "")


class TestNextCommand(Base):
    def next(self) -> str:
        return self.ds("status", "--next").stdout.strip()

    def test_pipeline(self) -> None:
        self.init(phase="prd", plan=False)
        self.assertEqual(self.next(), "/dev-kit:prd")
        (self.root / ".dev" / "prd.md").write_text("# PRD\n", encoding="utf-8")
        self.ds("set", "phase", "architecture")
        self.assertEqual(self.next(), "/dev-kit:review prd")
        self.ds("review", "prd", "pass", "--score", "90")
        self.assertEqual(self.next(), "/dev-kit:architecture")
        (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")
        self.ds("set", "phase", "implement")
        self.assertEqual(self.next(), "/dev-kit:review plan")
        self.ds("review", "plan", "pass", "--score", "90")
        self.assertEqual(self.next(), "/dev-kit:implement")
        self.ds("start", "T-001")
        self.ds("done", "T-001")
        self.assertEqual(self.next(), "/dev-kit:qa M1")
        self.assertEqual(json.loads(self.ds("status", "--json").stdout)["next_command"], "/dev-kit:qa M1")

    def test_ui_setting_validation(self) -> None:
        self.init()
        st = self.state()
        st["autonomy"].pop("ui")  # a project created before kit 1.21
        (self.root / ".dev" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.ds("set", "autonomy.ui.notify", "true")
        self.assertEqual(self.state()["autonomy"]["ui"]["notify"], True)
        self.assertEqual(self.state()["autonomy"]["ui"]["title"], True)
        self.ds("set", "autonomy.ui.loud", "true", expect=1)
        self.ds("set", "autonomy.ui", '{"notify": "yes"}', expect=1)
        self.ds("init", "--autonomy-json", '{"ui": {"statusline": true}}')
        self.assertEqual(self.state()["autonomy"]["ui"]["notify"], True)  # merged, not reset


if __name__ == "__main__":
    unittest.main()
