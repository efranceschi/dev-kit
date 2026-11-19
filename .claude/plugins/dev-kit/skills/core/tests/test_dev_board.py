"""Tests for scripts/dev_board.py: single instance, stale records, security of the shutdown, read-only data.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
STATE = CORE / "scripts" / "dev_state.py"
BOARD = CORE / "scripts" / "dev_board.py"

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

### T-002 Login form
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-1: invalid email shows inline error
- test_notes: unit
- files: src/a.ts
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def request(port: int, method: str, path: str, headers: dict | None = None) -> tuple[int, bytes]:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    c.putrequest(method, path, skip_host=True)
    for k, v in h.items():
        c.putheader(k, v)
    c.endheaders()
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie is gone for our purposes
        return not Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].startswith("Z")
    except OSError:
        return True


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.ds("init", "--project", "demo", "--language", "en")
        (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
        self.ds("sync-plan")
        self.ds("start", "T-001")
        self.port = free_port()

    def tearDown(self):
        self.board("stop")
        self.tmp.cleanup()

    def ds(self, *args):
        return subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                              capture_output=True, text=True, check=True)

    def board(self, *args, check=False):
        extra = ["--no-open", "--port", str(self.port)] if args and args[0] == "start" else []
        return subprocess.run([sys.executable, "-I", str(BOARD), "--root", str(self.root), *args, *extra],
                              capture_output=True, text=True, check=check, timeout=30)

    def record(self) -> dict | None:
        p = self.root / ".dev" / "run" / "board.json"
        return json.loads(p.read_text()) if p.exists() else None

    def board_pids(self) -> list[int]:
        out = []
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                try:
                    cmd = (d / "cmdline").read_bytes().split(b"\0")
                except OSError:
                    continue
                args = [c.decode() for c in cmd if c]
                if any(a.endswith("dev_board.py") for a in args) and "serve" in args and str(self.root) in args:
                    if alive(int(d.name)):
                        out.append(int(d.name))
        return out

    # ------------------------------------------------------------------ single instance

    def test_start_twice_reuses_the_same_server(self):
        r1 = self.board("start", check=True)
        self.assertIn("started:", r1.stdout)
        pid = self.record()["pid"]
        r2 = self.board("start", check=True)
        self.assertIn("already running", r2.stdout)
        self.assertIn("no new tab", r2.stdout)
        self.assertEqual(self.record()["pid"], pid)
        self.assertEqual(self.board_pids(), [pid])
        self.assertEqual((self.root / ".dev" / "run" / ".gitignore").read_text(), "*\n")

    def test_parallel_starts_leave_one_server(self):
        outs = []
        threads = [threading.Thread(target=lambda: outs.append(self.board("start").stdout)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum("started:" in o for o in outs), 1, outs)
        self.assertEqual(len(self.board_pids()), 1)

    def test_stale_record_with_dead_pid_is_replaced(self):
        run = self.root / ".dev" / "run"
        run.mkdir(parents=True, exist_ok=True)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        (run / "board.json").write_text(json.dumps({"pid": dead.pid, "port": self.port, "token": "x", "url": "u"}))
        r = self.board("start", check=True)
        self.assertIn("started:", r.stdout)
        self.assertNotEqual(self.record()["pid"], dead.pid)

    def test_record_pointing_to_another_process_is_not_trusted(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            run = self.root / ".dev" / "run"
            run.mkdir(parents=True, exist_ok=True)
            (run / "board.json").write_text(json.dumps({"pid": other.pid, "port": self.port, "token": "x", "url": "u"}))
            self.assertIn("not running", self.board("stop", check=True).stdout)
            self.assertTrue(alive(other.pid), "stop must never kill a process that is not the board")
            r = self.board("start", check=True)
            self.assertIn("started:", r.stdout)
            self.assertNotEqual(self.record()["pid"], other.pid)
        finally:
            other.kill()
            other.wait()

    # ------------------------------------------------------------------ stop and shutdown security

    def test_stop_when_not_running_is_ok(self):
        r = self.board("stop", check=True)
        self.assertIn("not running", r.stdout)

    def test_stop_kills_server_and_removes_record(self):
        self.board("start", check=True)
        pid = self.record()["pid"]
        r = self.board("stop", check=True)
        self.assertIn("stopped", r.stdout)
        self.assertIsNone(self.record())
        self.assertFalse(alive(pid))
        self.assertIn("not running", self.board("status").stdout)

    def test_shutdown_requires_token_host_and_origin(self):
        self.board("start", check=True)
        rec = self.record()
        port, tok = rec["port"], rec["token"]
        self.assertEqual(request(port, "POST", "/api/shutdown")[0], 403)
        self.assertEqual(request(port, "POST", "/api/shutdown", {"X-Board-Token": "wrong"})[0], 403)
        self.assertEqual(request(port, "POST", "/api/shutdown", {"X-Board-Token": tok, "Origin": "http://evil.example"})[0], 403)
        self.assertEqual(request(port, "POST", "/api/shutdown", {"X-Board-Token": tok, "Host": "evil.example"})[0], 403)
        self.assertEqual(request(port, "GET", "/api/state", {"Host": "evil.example"})[0], 403)
        self.assertTrue(alive(rec["pid"]))
        code, _ = request(port, "POST", "/api/shutdown", {"X-Board-Token": tok, "Origin": f"http://127.0.0.1:{port}"})
        self.assertEqual(code, 202)
        for _ in range(50):
            if not alive(rec["pid"]) and self.record() is None:
                break
            time.sleep(0.1)
        self.assertFalse(alive(rec["pid"]))
        self.assertIsNone(self.record())

    def test_ssh_tunnel_on_another_local_port_is_accepted(self):
        """ssh -L 9000:127.0.0.1:<port> makes the browser send Host: localhost:9000 (or 127.0.0.1:9000, [::1]:9000)."""
        self.board("start", check=True)
        rec = self.record()
        port, tok = rec["port"], rec["token"]
        for host in ("localhost:9000", "127.0.0.1:9000", "[::1]:9000", "LOCALHOST:9000", "localhost"):
            self.assertEqual(request(port, "GET", "/api/state", {"Host": host})[0], 200, host)
        for host in ("evil.example", "evil.example:9000", "localhost.evil.example:9000", "127.0.0.1.nip.io:9000",
                     "localhost:abc", "[::1]x", ""):
            self.assertEqual(request(port, "GET", "/api/state", {"Host": host})[0], 403, host)
        # Origin must match the Host the browser used
        self.assertEqual(request(port, "POST", "/api/shutdown",
                                 {"Host": "localhost:9000", "X-Board-Token": tok, "Origin": "http://localhost:8000"})[0], 403)
        self.assertIn("refused Host header", (self.root / ".dev" / "run" / "board.log").read_text())
        code, _ = request(port, "POST", "/api/shutdown",
                          {"Host": "localhost:9000", "X-Board-Token": tok, "Origin": "http://localhost:9000"})
        self.assertEqual(code, 202)

    def test_server_from_older_code_is_restarted_not_reused(self):
        """After a plugin update the old server must not keep answering with the old rules."""
        self.board("start", check=True)
        old = self.record()
        rec = dict(old, code="older-version")
        (self.root / ".dev" / "run" / "board.json").write_text(json.dumps(rec))
        r = self.board("start", check=True)
        self.assertIn("another version of the kit", r.stdout)
        self.assertIn("restarted:", r.stdout)
        new = self.record()
        self.assertNotEqual(new["pid"], old["pid"])
        self.assertFalse(alive(old["pid"]))
        self.assertEqual(self.board_pids(), [new["pid"]])
        self.assertIn("already running", self.board("start", check=True).stdout)

    def test_forbidden_host_reply_explains_itself(self):
        self.board("start", check=True)
        code, body = request(self.record()["port"], "GET", "/", {"Host": "myserver.lan:8765"})
        self.assertEqual(code, 403)
        d = json.loads(body)
        self.assertEqual(d["host"], "myserver.lan:8765")
        self.assertIn("localhost", d["hint"])

    def test_static_files_are_whitelisted(self):
        self.board("start", check=True)
        port = self.record()["port"]
        self.assertEqual(request(port, "GET", "/../../scripts/dev_state.py")[0], 404)
        self.assertEqual(request(port, "GET", "/assets/../board.json")[0], 404)
        code, body = request(port, "GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(self.record()["token"].encode(), body)
        self.assertNotIn(b"__BOARD_TOKEN__", body)

    # ------------------------------------------------------------------ data

    def test_state_endpoint_is_read_only_and_complete(self):
        state_file = self.root / ".dev" / "state.json"
        before = state_file.read_bytes()
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/state")
        self.assertEqual(code, 200)
        d = json.loads(body)
        for key in ("project", "phase", "phases", "progress", "milestones", "tasks", "next", "reviews", "quality",
                    "backlog", "questions", "log", "current_milestone", "board"):
            self.assertIn(key, d)
        self.assertEqual(d["milestones"][0]["goal"], "Ship a deployable skeleton.")
        self.assertEqual(d["tasks"]["T-001"]["status"], "in_progress")
        self.assertNotIn("token", d["board"])
        self.assertEqual(state_file.read_bytes(), before)

    def test_agents_disabled_until_a_hook_fires_then_live(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dev_board", BOARD)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(BOARD.parent))
        spec.loader.exec_module(mod)
        self.assertEqual(mod.agents_data(self.root), {"hooks": False, "active": [], "recent": []})
        hook = CORE / "scripts" / "dev_agent_hook.py"

        def fire(event, **kw):
            payload = {"hook_event_name": event, "session_id": "s1", "cwd": str(self.root), "prompt": "SECRET", **kw}
            subprocess.run([sys.executable, "-I", str(hook)], input=json.dumps(payload), text=True, check=True,
                           capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)})
        fire("SessionStart")
        self.assertTrue(mod.agents_data(self.root)["hooks"])
        fire("SubagentStart", agent_id="a1", agent_type="dev-kit:code-reviewer")
        fire("SubagentStart", agent_id="a2", agent_type="dev-kit:security-auditor")
        fire("SubagentStop", agent_id="a1", agent_type="dev-kit:code-reviewer")
        d = mod.agents_data(self.root)
        self.assertEqual([a["agent_id"] for a in d["active"]], ["a2"])
        self.assertEqual(d["recent"][0]["agent"], "dev-kit:code-reviewer")
        self.assertNotIn("SECRET", (self.root / ".dev" / "run" / "agents.jsonl").read_text())

    def test_status_line_in_dev_state(self):
        self.board("start", check=True)
        out = self.ds("status").stdout
        self.assertIn("Board: http://127.0.0.1:", out)
        self.board("stop", check=True)
        self.assertNotIn("Board:", self.ds("status").stdout)

    def test_start_without_state_exits_2(self):
        with tempfile.TemporaryDirectory() as empty:
            r = subprocess.run([sys.executable, "-I", str(BOARD), "--root", empty, "start", "--no-open"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
