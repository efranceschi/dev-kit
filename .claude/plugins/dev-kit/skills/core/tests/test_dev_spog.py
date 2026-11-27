#!/usr/bin/env python3
"""/dev-kit:spog: the machine-wide list of projects, the state of each one (waiting, running, idle), the sessions the
hooks record, the read-only server and its page's text."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DEV_KIT_HOME", tempfile.mkdtemp(prefix="dk-home-"))  # never the real ~/.dev-kit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v3_board import BOARD, SCRIPTS, Base, _HtmlTexts, catalog, js_keys, lint_js, plural_nouns  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
import dev_spog as sp  # noqa: E402

SPOG = SCRIPTS / "dev_spog.py"
HOOK = SCRIPTS / "dev_agent_hook.py"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class SpogBase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.home = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("DEV_KIT_HOME")
        os.environ["DEV_KIT_HOME"] = self.home.name
        self.env["DEV_KIT_HOME"] = self.home.name

    def tearDown(self) -> None:
        os.environ["DEV_KIT_HOME"] = self.old_home or ""
        self.home.cleanup()
        super().tearDown()

    def sp(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, "-I", str(SPOG), *args], capture_output=True, text=True, cwd=self.root, env=self.env)
        if expect is not None:
            self.assertEqual(p.returncode, expect, msg=f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def hook(self, payload: dict, **env: str) -> None:
        p = subprocess.run([sys.executable, "-I", str(HOOK)], input=json.dumps({"session_id": "s1", "cwd": str(self.root), **payload}),
                           capture_output=True, text=True, env={**self.env, "CLAUDE_PROJECT_DIR": str(self.root), **env})
        self.assertEqual(p.returncode, 0)

    def session(self) -> dict | None:
        f = self.dev / "run" / "sessions" / "s1.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


class TestRegistry(SpogBase):
    def test_register_list_and_forget(self) -> None:
        self.assertTrue(sp.register(self.root))
        self.assertTrue(sp.register(self.root))  # again: still one entry, added_at kept
        reg = sp.read_registry()
        self.assertEqual(list(reg), [str(self.root.resolve())])
        self.assertEqual(reg[str(self.root.resolve())]["name"], "shop")
        with tempfile.TemporaryDirectory() as other:
            self.assertFalse(sp.register(Path(other)))  # not a dev-kit project
        self.assertEqual(sp.forget([str(self.root)]), [str(self.root.resolve())])
        self.assertEqual(sp.read_registry(), {})

    def test_a_project_whose_folder_is_gone_stays_greyed_until_forgotten(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            gone = Path(t) / "gone"
            (gone / ".dev").mkdir(parents=True)
            (gone / ".dev" / "state.json").write_text("{}", encoding="utf-8")
            sp.register(gone)
            other = Path(t) / "other"
            (other / ".dev").mkdir(parents=True)
            (other / ".dev" / "state.json").write_text("{}", encoding="utf-8")
            sp.register(other)
            (other / ".dev" / "state.json").unlink()
        sp.register(self.root)
        views = {Path(v["path"]).name: v["status"] for v in sp.overview(sp.Views())["projects"]}
        self.assertEqual(views["gone"], "missing")
        self.assertEqual(views["other"], "missing")  # the whole temp folder went away
        out = self.sp("list").stdout
        self.assertIn("missing", out)
        self.assertIn("forgot", self.sp("forget", "--missing").stdout)
        self.assertEqual(list(sp.read_registry()), [str(self.root.resolve())])

    def test_a_folder_without_state_reads_as_not_a_project(self) -> None:
        sp.register(self.root)
        (self.dev / "state.json").rename(self.dev / "state.bak")
        self.assertEqual(sp.project_view(str(self.root.resolve()))["status"], "not_project")

    def test_starting_the_board_registers_the_project(self) -> None:
        board = subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_board.py"), "--root", str(self.root), "start", "--no-open",
                                "--port", "0"], capture_output=True, text=True, env=self.env)
        try:
            self.assertEqual(board.returncode, 0, board.stderr)
            self.assertIn(str(self.root.resolve()), sp.read_registry())
            v = sp.project_view(str(self.root.resolve()))
            self.assertTrue(v["board"]["url"].startswith("http://127.0.0.1:"))
        finally:
            subprocess.run([sys.executable, "-I", str(SCRIPTS / "dev_board.py"), "--root", str(self.root), "stop"],
                           capture_output=True, env=self.env)


class TestProjectState(SpogBase):
    def test_idle_then_running_then_waiting(self) -> None:
        path = str(self.root.resolve())
        v = sp.project_view(path)
        self.assertEqual((v["status"], v["needs_total"]), ("idle", 0))
        self.assertIn(v["phase"], ("conception", "planning", "construction", "stable"))
        self.assertTrue(v["since"])
        self.env.pop("DEV_KIT_NOW")  # a run started two days ago would count as abandoned
        self.ds("event", "skill_start", "--set", "skill=implement", "--set", "args_kind=run")
        v = sp.project_view(path)
        self.assertEqual(v["status"], "running")
        self.assertEqual(v["runs"], [{"skill": "implement", "scope": None}])
        self.ds("add-question", "Which payment provider?", "--assumption", "Stripe")
        v = sp.project_view(path)
        self.assertEqual(v["status"], "waiting")
        self.assertTrue(v["running"])
        q = next(g for g in v["needs"] if g["kind"] == "question")
        self.assertEqual((q["n"], q["items"][0]["text"]), (1, "Which payment provider?"))

    def test_the_spog_and_board_runs_do_not_count_as_running(self) -> None:
        self.env.pop("DEV_KIT_NOW")
        self.ds("event", "skill_start", "--set", "skill=spog", "--set", "args_kind=start")
        self.assertEqual(sp.project_view(str(self.root.resolve()))["status"], "idle")

    def test_needs_follow_the_board_order_and_cap_the_items(self) -> None:
        st = {"tasks": {f"T-{i:03d}": {"title": f"t{i}", "status": "blocked", "blocked_reason": "waits on Q-001"} for i in range(1, 6)},
              "backlog": {"needs": [{"kind": "checkpoint", "target": "plan", "title": "Confirm plan"},
                                    {"kind": "prod_health", "issue": "I-001", "detail": "500 on /"}], "hotfix_open": []},
              "cycle": {"releases": [{"id": "R1", "title": "First", "status": "awaiting_approval"}]},
              "questions": [{"id": "Q-001", "question": "Which?"}], "milestones": [], "denied": [], "agents": {}}
        sess = [{"state": "waiting", "why": "permission", "tool": "Bash", "since": "2026-11-25T10:00:00Z"}]
        got = sp.needs(st, sess)
        self.assertEqual([g["kind"] for g in got],
                         ["session_permission", "prod_health", "release_approval", "checkpoint", "blocked", "question"])
        blocked = next(g for g in got if g["kind"] == "blocked")
        self.assertEqual((blocked["n"], len(blocked["items"])), (5, sp.ITEMS_SHOWN))
        self.assertEqual(blocked["items"][0], {"id": "T-001", "text": "waits on Q-001"})

    def test_waiting_projects_come_first(self) -> None:
        vs = [{"name": "b", "status": "idle", "last_activity": "2026-11-25T10:00:00Z"},
              {"name": "a", "status": "missing"},
              {"name": "c", "status": "waiting", "needs_total": 1},
              {"name": "d", "status": "waiting", "needs_total": 4},
              {"name": "e", "status": "running"},
              {"name": "f", "status": "idle", "last_activity": "2026-11-25T11:00:00Z"}]
        self.assertEqual([v["name"] for v in sp.sort_views(vs)], ["d", "c", "e", "f", "b", "a"])


class TestSessions(SpogBase):
    def test_the_hooks_record_what_the_session_is_doing(self) -> None:
        self.hook({"hook_event_name": "SessionStart", "source": "startup"})
        self.assertEqual(self.session()["state"], "idle")
        self.hook({"hook_event_name": "UserPromptSubmit", "prompt": "secret words"})
        s = self.session()
        self.assertEqual((s["state"], s["why"]), ("working", None))
        self.assertNotIn("secret", json.dumps(s))  # only ids, the state and a tool name are kept
        self.hook({"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "Claude needs your permission to use Bash"})
        s = self.session()
        self.assertEqual((s["state"], s["why"]), ("waiting", "permission"))
        v = sp.project_view(str(self.root.resolve()))
        self.assertEqual(v["status"], "waiting")
        self.assertEqual(v["needs"][0]["kind"], "session_permission")
        self.hook({"hook_event_name": "PostToolUse", "tool_name": "Bash"})
        self.assertEqual(self.session()["state"], "working")
        self.assertEqual(sp.project_view(str(self.root.resolve()))["status"], "running")
        self.hook({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_input": {}})
        self.assertEqual((self.session()["state"], self.session()["why"]), ("waiting", "question"))
        self.hook({"hook_event_name": "Stop"})
        self.assertEqual(self.session()["state"], "idle")
        self.assertEqual(sp.project_view(str(self.root.resolve()))["status"], "idle")
        self.hook({"hook_event_name": "SessionEnd"})
        self.assertIsNone(self.session())

    def test_an_older_claude_code_without_notification_type(self) -> None:
        self.hook({"hook_event_name": "Notification", "message": "Claude needs your permission to use Edit"})
        self.assertEqual(self.session()["why"], "permission")
        self.hook({"hook_event_name": "Notification", "notification_type": "idle_prompt", "message": "Claude is waiting for your input"})
        self.assertEqual(self.session()["why"], "permission")  # idle_prompt says nothing new

    def test_a_round_child_records_no_session(self) -> None:
        self.hook({"hook_event_name": "UserPromptSubmit"}, DEV_KIT_ROUND_ID="r1")
        self.assertIsNone(self.session())

    def test_a_stale_session_is_left_out(self) -> None:
        d = self.dev / "run" / "sessions"
        d.mkdir(parents=True)
        old = iso(datetime.now(timezone.utc) - timedelta(hours=13))
        (d / "old.json").write_text(json.dumps({"session": "old", "state": "waiting", "why": "permission", "since": old, "at": old}))
        self.assertEqual(sp.sessions(self.root), [])

    def test_the_hooks_file_wires_the_session_events(self) -> None:
        hooks = json.loads((SCRIPTS.parents[2] / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for ev in ("UserPromptSubmit", "PostToolUse", "Notification", "SessionEnd", "Stop"):
            self.assertIn("dev_agent_hook.py", json.dumps(hooks[ev]), ev)
        self.assertIn("AskUserQuestion", hooks["PreToolUse"][0]["matcher"])
        self.assertIn("permission_prompt", hooks["Notification"][0]["matcher"])


class TestServer(SpogBase):
    def test_start_serve_read_only_and_stop(self) -> None:
        out = self.sp("start", "--no-open", "--port", "0", "--register", str(self.root)).stdout
        try:
            self.assertIn("started: http://127.0.0.1:", out)
            self.assertIn("1 project(s)", out)
            rec = sp.read_record()
            port = rec["port"]
            self.assertIn("already running", self.sp("start", "--no-open").stdout)

            def get(path: str, host: str | None = None) -> tuple[int, bytes]:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("GET", path, headers={"Host": host or f"127.0.0.1:{port}"})
                r = c.getresponse()
                body = r.read()
                c.close()
                return r.status, body
            code, body = get("/api/projects")
            self.assertEqual(code, 200)
            d = json.loads(body)
            self.assertEqual([p["name"] for p in d["projects"]], ["shop"])
            self.assertNotIn(rec["token"], body.decode())
            code, page = get("/")
            self.assertEqual(code, 200)
            self.assertIn(b'id="projects"', page)
            self.assertNotIn(b"__BOARD_I18N__", page)
            for asset in ("/assets/spog.js", "/assets/spog.css", "/assets/board.css"):
                self.assertEqual(get(asset)[0], 200, asset)
            self.assertEqual(get("/api/projects", host="evil.example:80")[0], 403)  # DNS rebinding
            self.assertEqual(get("/api/state")[0], 404)
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("POST", "/api/shutdown", body=b"", headers={"Host": f"127.0.0.1:{port}", "X-Board-Token": "wrong"})
            self.assertEqual(c.getresponse().status, 403)
            c.close()
            self.assertIn("running:", self.sp("status").stdout)
        finally:
            self.assertIn("stopped", self.sp("stop").stdout)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and sp.read_record():
            time.sleep(0.1)
        self.assertIn("not running", self.sp("status").stdout)


class TestSpogText(unittest.TestCase):
    def test_spog_js_has_no_visible_text_outside_the_catalog(self) -> None:
        self.assertEqual(lint_js((BOARD / "spog.js").read_text(encoding="utf-8"), "  const STATUS_LABEL"), [])

    def test_spog_html_marks_every_static_text(self) -> None:
        p = _HtmlTexts()
        p.feed((BOARD / "spog.html").read_text(encoding="utf-8"))
        self.assertEqual(p.missing, [])

    def test_every_spog_key_is_in_both_catalogs(self) -> None:
        js = (BOARD / "spog.js").read_text(encoding="utf-8")
        p = _HtmlTexts()
        p.feed((BOARD / "spog.html").read_text(encoding="utf-8"))
        en, pt = catalog("en"), catalog("pt-BR")
        self.assertEqual(sorted((js_keys(js) | p.keys) - set(en["strings"])), [])
        self.assertEqual(sorted((js_keys(js) | p.keys) - set(pt["strings"])), [])
        self.assertEqual(sorted(plural_nouns(js) - set(en["plurals"]) - set(pt["plurals"])), [])

    def test_the_page_names_itself_and_has_a_sound_alert_with_ack_and_mute(self) -> None:
        html = (BOARD / "spog.html").read_text(encoding="utf-8")
        js = (BOARD / "spog.js").read_text(encoding="utf-8")
        self.assertIn('<h1 data-i18n="Single Pane of Glass">', html)
        self.assertIn("Single Pane of Glass", catalog("pt-BR")["strings"]["Single Pane of Glass"])
        self.assertNotEqual(catalog("pt-BR")["strings"]["Single Pane of Glass"], "Single Pane of Glass")  # translated
        for el in ('id="ack-btn"', 'id="sound-btn"', 'id="sound-every"', 'id="sound-test"'):
            self.assertIn(el, html)
        for code in ("function chime()", "function ack()", "function settleAcks()", "everyMin * 60000", '"spog-sound"'):
            self.assertIn(code, js)

    def test_every_need_kind_has_a_label(self) -> None:
        js = (BOARD / "spog.js").read_text(encoding="utf-8")
        for k in sp.NEED_KINDS:
            self.assertIn(f"{k}: N_(", js, k)


if __name__ == "__main__":
    unittest.main()
