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

# the board's server starts a headless `claude -p` worker for waiting requests: never the real one in a test
os.environ["DEV_KIT_CLAUDE"] = __import__("shutil").which("true") or "/bin/true"

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


def post(port: int, path: str, body: object, token: str | None, headers: dict | None = None) -> tuple[int, dict]:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"Content-Type": "application/json", "Content-Length": str(len(data)), "Origin": f"http://127.0.0.1:{port}",
         **({"X-Board-Token": token} if token else {}), **(headers or {})}
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", path, body=data, headers={"Host": f"127.0.0.1:{port}", **h})
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw)
    except json.JSONDecodeError:
        return r.status, {}


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie is gone for our purposes
        return not Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].startswith("Z")
    except OSError:
        return True


class CodeIdTest(unittest.TestCase):
    def test_code_id_covers_sibling_scripts(self):
        import dev_board as db
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, mock.patch.object(db, "SCRIPTS", Path(d)), \
                mock.patch.object(db, "ASSETS", Path(d) / "none"):
            sib = Path(d) / "dev_worker.py"
            sib.write_text("a = 1\n")
            before = db.code_id()
            self.assertEqual(before, db.code_id())
            sib.write_text("a = 2\n")
            self.assertNotEqual(before, db.code_id())


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
        for host in ("localhost:9000", "127.0.0.1:9000", "[::1]:9000", "LOCALHOST:9000", "localhost",
                     "192.168.68.121:9876", "10.0.0.5", "[fe80::1]:9000"):
            self.assertEqual(request(port, "GET", "/api/state", {"Host": host})[0], 200, host)
        for host in ("evil.example", "evil.example:9000", "localhost.evil.example:9000", "127.0.0.1.nip.io:9000",
                     "localhost:abc", "[::1]x", "", "192.168.68.121.evil.example:9876", "[192.168.1.1]:80",
                     "999.1.1.1:80", "localhost:70000"):
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
        self.assertIn("the kit was updated", r.stdout)
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

    # ------------------------------------------------------------------ --host (sharing on the network)

    def test_default_bind_is_loopback_and_needs_no_key(self):
        self.board("start", check=True)
        rec = self.record()
        self.assertEqual(rec["host"], "127.0.0.1")
        self.assertFalse(rec["exposed"])
        self.assertNotIn("access_urls", rec)
        self.assertEqual(request(rec["port"], "GET", "/api/state")[0], 200)

    def test_exposed_board_requires_the_access_key(self):
        r = self.board("start", "--host", "0.0.0.0", check=True)
        self.assertIn("exposed on 0.0.0.0", r.stdout)
        self.assertIn("keep the links private", r.stdout)
        rec = self.record()
        port, tok = rec["port"], rec["token"]
        self.assertTrue(rec["exposed"])
        for u in rec["access_urls"]:
            self.assertTrue(u.endswith(f":{port}/?key={tok}"), u)
        for path in ("/", "/api/state", "/api/events", "/assets/board.js"):
            self.assertEqual(request(port, "GET", path)[0], 401, path)
        self.assertEqual(request(port, "GET", "/api/ping")[0], 200)  # identity check used by start/stop
        self.assertEqual(request(port, "GET", "/api/state", {"Cookie": f"dkb_{port}=wrong"})[0], 401)
        # the key in the URL becomes an HttpOnly cookie and leaves the address bar
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", f"/?key={tok}")
        r = c.getresponse(); r.read(); c.close()
        self.assertEqual(r.status, 303)
        self.assertEqual(r.getheader("Location"), "/")
        cookie = r.getheader("Set-Cookie")
        self.assertIn(f"dkb_{port}={tok}", cookie)
        for flag in ("HttpOnly", "SameSite=Strict"):
            self.assertIn(flag, cookie)
        ok = {"Cookie": f"dkb_{port}={tok}"}
        self.assertEqual(request(port, "GET", "/api/state", ok)[0], 200)
        # with the key, host names are fine: a DNS-rebinding page never has the key
        self.assertEqual(request(port, "GET", "/api/state", {**ok, "Host": f"myserver.lan:{port}"})[0], 200)
        self.assertEqual(request(port, "GET", "/api/state", {"Host": f"myserver.lan:{port}"})[0], 401)
        self.assertIn("shared on the network", self.ds("status").stdout)
        self.assertIn("access link:", self.board("status").stdout)
        self.assertIn("stopped", self.board("stop", check=True).stdout)
        self.assertIsNone(self.record())

    def test_changing_host_restarts_and_plain_start_keeps_it(self):
        self.board("start", check=True)
        first = self.record()["pid"]
        r = self.board("start", "--host", "0.0.0.0", check=True)
        self.assertIn("listens on 127.0.0.1, not 0.0.0.0", r.stdout)
        self.assertIn("restarted:", r.stdout)
        self.assertFalse(alive(first))
        shared = self.record()["pid"]
        r = self.board("start", check=True)  # no --host: reuse the shared board as it is
        self.assertIn("already running", r.stdout)
        self.assertEqual(self.record()["pid"], shared)
        r = self.board("start", "--host", "127.0.0.1", check=True)
        self.assertIn("restarted:", r.stdout)
        self.assertFalse(self.record()["exposed"])
        self.assertEqual(len(self.board_pids()), 1)

    def test_host_must_be_an_ip_address(self):
        r = self.board("start", "--host", "myserver.lan")
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs an IP address", r.stderr)
        self.assertIsNone(self.record())

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

    # ------------------------------------------------------------------ requests to Claude Code

    def test_requests_need_token_origin_and_json(self):
        self.board("start", check=True)
        rec = self.record()
        port, tok = rec["port"], rec["token"]
        self.assertTrue(rec["actions"])
        body = {"action": "run", "args": {"command": "/dev-kit:implement"}}
        self.assertEqual(post(port, "/api/inbox", body, None)[0], 403)
        self.assertEqual(post(port, "/api/inbox", body, "wrong")[0], 403)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(post(port, "/api/inbox", b"not json", tok)[0], 400)
        self.assertEqual(post(port, "/api/inbox", {"action": "run", "args": {"command": "x" * 20000}}, tok)[0], 413)
        code, d = post(port, "/api/inbox", {"action": "run", "args": {"command": "/dev-kit:board stop"}}, tok)
        self.assertEqual(code, 422)
        self.assertIn("command is not one of", d["errors"][0])
        self.assertEqual(post(port, "/api/elsewhere", body, tok)[0], 404)
        self.assertFalse((self.root / ".dev" / "run" / "inbox" / "P-001.json").exists())
        code, d = post(port, "/api/inbox", body, tok)
        self.assertEqual((code, d["item"]["id"], d["item"]["status"]), (201, "P-001", "pending"))
        code, st = request(port, "GET", "/api/state")
        st = json.loads(st)
        self.assertEqual([x["id"] for x in st["inbox"]["open"]], ["P-001"])
        self.assertTrue(st["inbox"]["actions"])
        self.assertEqual(st["inbox"]["executor"]["state"], "offline")
        self.assertEqual(st["next"]["command"], "/dev-kit:interview")  # the demo project has no brief yet: conception · interview

    def test_request_writes_only_the_queue(self):
        dev = self.root / ".dev"
        before = {p: p.read_bytes() for p in dev.rglob("*") if p.is_file() and "run" not in p.relative_to(dev).parts}
        self.board("start", check=True)
        port, tok = self.record()["port"], self.record()["token"]
        self.assertEqual(post(port, "/api/inbox", {"action": "issue_new", "args": {"title": "Crash"}}, tok)[0], 201)
        self.assertEqual(post(port, "/api/inbox/P-001/cancel", {}, tok)[0], 200)
        self.assertEqual(post(port, "/api/inbox/P-001/cancel", {}, tok)[0], 409)
        self.assertEqual(post(port, "/api/inbox/P-404/cancel", {}, tok)[0], 404)
        code, d = post(port, "/api/worker/mode", {"paused": True}, tok)
        self.assertEqual((code, d["modes"]["paused"]), (200, True))
        self.assertEqual(post(port, "/api/worker/mode", {"paused": "yes"}, tok)[0], 422)
        after = {p: p.read_bytes() for p in dev.rglob("*") if p.is_file() and "run" not in p.relative_to(dev).parts}
        self.assertEqual(after, before)

    def test_plan_draft_is_checked_before_it_is_queued(self):
        self.board("start", check=True)
        port, tok = self.record()["port"], self.record()["token"]
        bad = {"action": "plan_draft", "args": {"ops": [{"op": "move_task", "task": "T-001", "milestone": "M1"}]}}
        code, d = post(port, "/api/inbox", bad, tok)  # T-001 is in progress
        self.assertEqual(code, 422)
        self.assertIn("only tasks not started can move", d["errors"][0])
        good = {"action": "plan_draft", "args": {"ops": [{"op": "new_milestone", "milestone": "M2", "title": "Next"},
                                                         {"op": "move_task", "task": "T-002", "milestone": "M2"}]}}
        state = (self.root / ".dev" / "state.json").read_bytes()
        self.assertEqual(post(port, "/api/inbox", good, tok)[0], 201)
        self.assertEqual((self.root / ".dev" / "state.json").read_bytes(), state)  # applied by Claude Code, not here

    def test_release_history_is_complete(self):
        state_file = self.root / ".dev" / "state.json"
        st = json.loads(state_file.read_text())
        st["release_state"] = {"R1": {"status": "awaiting_approval", "rounds": 3, "history": [
            {"at": f"2026-11-0{n}T10:00:00Z", "event": "rejected" if n % 2 else "submitted", "milestone": f"M{n}", "tasks": ["T-001"], "feedback": "secret text"}
            for n in range(1, 8)]}}
        state_file.write_text(json.dumps(st))
        self.board("start", check=True)
        d = json.loads(request(self.record()["port"], "GET", "/api/state")[1])
        hist = d["release_history"]["R1"]
        self.assertEqual(len(hist), 7)  # cycle.releases keeps the last five; the Releases tab shows all
        self.assertEqual(hist[0], {"event": "rejected", "at": "2026-11-01T10:00:00Z", "milestone": "M1", "tasks": ["T-001"]})
        self.assertNotIn("feedback", hist[0])

    def test_release_plan_draft_is_checked_before_it_is_queued(self):
        self.board("start", check=True)
        port, tok = self.record()["port"], self.record()["token"]
        # 3.0: the plan always has releases (sync-plan put every milestone in R1); an invalid grouping is refused
        for op, text in (({"op": "move_milestone", "milestone": "M1", "release": "R3"}, "R3"),
                         ({"op": "new_release", "release": "R2"}, "R2 would hold 0 milestones"),
                         ({"op": "drop_release", "release": "R1"}, "R1")):
            code, d = post(port, "/api/inbox", {"action": "plan_draft", "args": {"ops": [op]}}, tok)
            self.assertEqual(code, 422)
            self.assertTrue(any(text in e for e in d["errors"]), d["errors"])

    def test_approval_decisions(self):
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_worker as dw
        d = self.root / ".dev" / "run" / "approvals"
        aid = dw.request_approval(self.root, "Bash", "npm test", "P-001", "Bash(npm test:*)", 60)
        plain = dw.request_approval(self.root, "Write", "src/a.ts", "P-001", None, 60)
        self.board("start", check=True)
        port, tok = self.record()["port"], self.record()["token"]
        st = json.loads(request(port, "GET", "/api/state")[1])
        self.assertEqual(sorted(a["id"] for a in st["inbox"]["approvals"]), sorted([aid, plain]))
        self.assertEqual(next(a for a in st["inbox"]["approvals"] if a["id"] == aid)["rule"], "Bash(npm test:*)")
        self.assertEqual(post(port, f"/api/approvals/{aid}", {"decision": "always"}, tok)[0], 422)
        self.assertEqual(post(port, f"/api/approvals/{plain}", {"decision": "allow_session"}, tok)[0], 422)  # no rule to keep
        self.assertEqual(post(port, f"/api/approvals/{aid}", {"decision": "allow_session"}, tok)[0], 200)
        self.assertEqual((d / f"{aid}.decision").read_text(), "allow_session")
        self.assertEqual(post(port, f"/api/approvals/{aid}", {"decision": "deny"}, tok)[0], 409)
        self.assertEqual(post(port, "/api/approvals/A-11111111", {"decision": "deny"}, tok)[0], 404)

    def _permission_hook(self, wait_s="20", **payload):
        hook = CORE / "scripts" / "dev_agent_hook.py"
        body = {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": str(self.root), "tool_name": "Bash",
                "tool_input": {"command": "npm test -- --watch=false", "description": "Run the tests"}, **payload}
        proc = subprocess.Popen([sys.executable, "-I", str(hook)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "DEV_KIT_APPROVAL_WAIT_S": wait_s})
        proc.stdin.write(json.dumps(body))
        proc.stdin.close()
        return proc

    def _result(self, proc) -> dict:
        out = proc.stdout.read()
        proc.stdout.close()
        proc.wait(timeout=30)
        self.assertEqual(proc.returncode, 0)
        return json.loads(out)["hookSpecificOutput"]["decision"] if out.strip() else {}

    def _approval(self, port) -> dict:
        for _ in range(100):
            waiting = json.loads(request(port, "GET", "/api/state")[1])["inbox"]["approvals"]
            if waiting:
                return waiting[0]
            time.sleep(0.1)
        self.fail("the permission never reached the board")

    def test_permission_prompts_are_answered_on_the_board(self):
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_worker as dw
        suggestions = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test:*"}], "behavior": "allow",
                        "destination": "localSettings"},
                       {"type": "setMode", "mode": "bypassPermissions", "destination": "session"},
                       {"type": "addRules", "rules": [{"toolName": "Bash"}], "behavior": "deny", "destination": "userSettings"}]
        # no board request running: Claude Code's own prompt handles it (the hook says nothing, at once)
        self.assertEqual(self._result(self._permission_hook()), {})
        self.board("start", check=True)
        port, tok = self.record()["port"], self.record()["token"]
        dw.submit(self.root, "run", {"command": "/dev-kit:implement"})
        dw.claim(self.root, "claude-test", os.getpid())  # this test stands for the Claude Code process: the hook's parent
        # a question is never a permission
        self.assertEqual(self._result(self._permission_hook(tool_name="AskUserQuestion")), {})
        # allow for this session: only the allow rule Claude Code suggested, and only until the session ends
        proc = self._permission_hook(permission_suggestions=suggestions)
        a = self._approval(port)
        self.assertEqual((a["tool"], a["target"], a["request"], a["rule"]), ("Bash", "npm test -- --watch=false", "P-001", "Bash(npm test:*)"))
        self.assertEqual(post(port, f"/api/approvals/{a['id']}", {"decision": "allow_session"}, tok)[0], 200)
        self.assertEqual(self._result(proc), {"behavior": "allow", "updatedPermissions": [
            {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test:*"}], "behavior": "allow", "destination": "session"}]})
        self.assertEqual(json.loads(request(port, "GET", "/api/state")[1])["inbox"]["approvals"], [])
        # allow once
        proc = self._permission_hook(tool_name="Write", tool_input={"file_path": "src/a.ts", "content": "SECRET"})
        a = self._approval(port)
        self.assertEqual((a["tool"], a["target"], a["rule"]), ("Write", "src/a.ts", None))
        self.assertNotIn("SECRET", json.dumps(a))
        post(port, f"/api/approvals/{a['id']}", {"decision": "allow"}, tok)
        self.assertEqual(self._result(proc), {"behavior": "allow"})
        # deny
        proc = self._permission_hook()
        post(port, f"/api/approvals/{self._approval(port)['id']}", {"decision": "deny"}, tok)
        d = self._result(proc)
        self.assertEqual(d["behavior"], "deny")
        self.assertIn("Denied by the user on the dev-kit board (P-001)", d["message"])
        # nobody answers
        d = self._result(self._permission_hook(wait_s="1"))
        self.assertEqual(d["behavior"], "deny")
        self.assertIn("Nobody answered", d["message"])
        self.assertEqual(list((self.root / ".dev" / "run" / "approvals").iterdir()), [])
        # the request is cancelled on the board while the permission waits
        proc = self._permission_hook()
        self._approval(port)
        post(port, "/api/inbox/P-001/cancel", {}, tok)
        self.assertIn("P-001 was cancelled", self._result(proc)["message"])
        # the board is gone: back to Claude Code's own prompt
        self.board("stop")
        self.assertEqual(self._result(self._permission_hook()), {})

    def test_hook_trace_records_keys_never_values(self):
        hook = CORE / "scripts" / "dev_agent_hook.py"
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": str(self.root), "prompt": "SECRET prompt"}
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        subprocess.run([sys.executable, "-I", str(hook)], input=json.dumps(payload), text=True, check=True, env=env)
        trace = self.root / ".dev" / "run" / "hook-trace.jsonl"
        self.assertFalse(trace.exists())  # off unless asked for
        subprocess.run([sys.executable, "-I", str(hook)], input=json.dumps(payload), text=True, check=True,
                       env={**env, "DEV_KIT_HOOK_TRACE": "1"})
        rec = json.loads(trace.read_text().splitlines()[-1])
        self.assertEqual((rec["event"], rec["answered"]), ("UserPromptSubmit", False))
        self.assertIn("prompt", rec["payload_keys"])
        self.assertTrue(rec["parents"])
        self.assertNotIn("SECRET", trace.read_text())

    def test_question_options_reach_the_page(self):
        self.ds("add-question", "Which DB?", "--options", "Postgres|SQLite", "--recommended", "SQLite")
        self.board("start", check=True)
        q = json.loads(request(self.record()["port"], "GET", "/api/state")[1])["questions"][0]
        self.assertEqual((q["options"], q["recommended"]), (["Postgres", "SQLite"], "SQLite"))

    def test_actions_off_and_shared_board(self):
        self.board("start", "--actions", "off", check=True)
        rec = self.record()
        self.assertFalse(rec["actions"])
        code, d = post(rec["port"], "/api/inbox", {"action": "run", "args": {"command": "/dev-kit:docs"}}, rec["token"])
        self.assertEqual((code, d["error"]), (403, "actions off"))
        # asking for actions restarts a board started without them
        out = self.board("start", "--actions", "on", check=True).stdout
        self.assertIn("actions off", out)
        self.assertTrue(self.record()["actions"])
        self.board("stop")
        # shared with the network: still on (a single-user board; nobody gets in without the access key)
        out = self.board("start", "--host", "0.0.0.0", check=True).stdout
        rec = self.record()
        self.assertTrue(rec["actions"])
        self.assertIn("anyone with a link can also queue work", out)
        self.assertEqual(request(rec["port"], "GET", "/api/state")[0], 401)
        body = {"action": "run", "args": {"command": "/dev-kit:docs"}}
        self.assertEqual(post(rec["port"], "/api/inbox", body, "wrong")[0], 403)
        self.assertEqual(post(rec["port"], "/api/inbox", body, rec["token"])[0], 201)

    def test_trusted_host_names_for_a_reverse_proxy(self):
        self.board("start", check=True)
        self.assertEqual(request(self.record()["port"], "GET", "/api/state", {"Host": "board.example.com"})[0], 403)
        out = self.board("start", "--trusted-host", "Board.Example.com", check=True).stdout
        self.assertIn("the trusted host names changed", out)
        self.assertIn("trusted host names: board.example.com", out)
        rec = self.record()
        port, tok = rec["port"], rec["token"]
        self.assertEqual(request(port, "GET", "/api/state", {"Host": "board.example.com"})[0], 200)
        self.assertEqual(request(port, "GET", "/api/state", {"Host": "board.example.com:8443"})[0], 200)
        self.assertEqual(request(port, "GET", "/api/state", {"Host": "evil.example.com"})[0], 403)
        body = {"action": "run", "args": {"command": "/dev-kit:docs"}}
        # the proxy serves the page over https, and may keep the Host header or rewrite it to the local address
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "https://board.example.com", "Host": "board.example.com"})[0], 201)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "https://board.example.com"})[0], 201)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "https://evil.example.com"})[0], 403)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "https://board.example.com/x"})[0], 403)
        self.assertEqual(post(port, "/api/inbox", body, tok, {"Origin": "ftp://board.example.com"})[0], 403)
        # remembered for the project, until "none"
        self.board("stop")
        self.board("start", check=True)
        self.assertEqual(self.record()["trusted_hosts"], ["board.example.com"])
        self.board("start", "--trusted-host", "none", check=True)
        self.assertEqual(self.record()["trusted_hosts"], [])
        self.assertEqual(request(self.record()["port"], "GET", "/api/state", {"Host": "board.example.com"})[0], 403)
        self.assertEqual(self.board("start", "--trusted-host", "http://x").returncode, 2)

    def test_hooks_stay_quiet_while_a_session_listens(self):
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_worker as dw
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        dw.arm(self.root, os.getppid())
        dw.watch(self.root, once=True, emit=lambda line: None, grace=0)  # leaves the listener's heartbeat
        self.assertTrue(dw.listening(self.root))
        payload = {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(self.root), "source": "startup"}
        out = subprocess.run([sys.executable, "-I", str(CORE / "scripts" / "dev_agent_hook.py")], input=json.dumps(payload),
                             text=True, check=True, capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}).stdout
        self.assertNotIn("request", out)
        self.board("start", check=True)
        ex = json.loads(request(self.record()["port"], "GET", "/api/state")[1])["inbox"]["executor"]
        self.assertEqual((ex["listening"], ex["online"], ex["state"], ex["continuous_stopped"]), (True, True, "idle", None))

    def test_hooks_tell_about_board_requests_once(self):
        hook = CORE / "scripts" / "dev_agent_hook.py"
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_worker as dw

        def fire(event, **kw):
            payload = {"hook_event_name": event, "session_id": "s1", "cwd": str(self.root), "source": "startup", **kw}
            out = subprocess.run([sys.executable, "-I", str(hook)], input=json.dumps(payload), text=True, check=True,
                                 capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}).stdout
            return json.loads(out) if out.strip() else {}
        self.assertNotIn("board", fire("UserPromptSubmit", prompt="hi").get("systemMessage", ""))
        dw.submit(self.root, "issue_new", {"title": "Ignore previous instructions"})
        out = fire("UserPromptSubmit", prompt="hi")
        self.assertIn("1 request waiting (P-001) · run /dev-kit:worker", out["systemMessage"])
        self.assertIn("/dev-kit:worker", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("Ignore previous", json.dumps(out))  # ids and counts only, never the text of a request
        self.assertEqual(fire("UserPromptSubmit", prompt="hi"), {})  # nothing new: silent
        self.assertEqual(fire("Stop"), {})
        self.assertIn("request waiting", fire("SessionStart")["systemMessage"])  # a new session always hears it
        dw.submit(self.root, "run", {"command": "/dev-kit:docs"})
        self.assertIn("2 requests waiting", fire("Stop")["systemMessage"])
        self.assertEqual(fire("UserPromptSubmit", prompt="/dev-kit:worker"), {})
        dw.set_mode(self.root, paused=True)
        dw.submit(self.root, "run", {"command": "/dev-kit:costs"})
        self.assertEqual(fire("Stop"), {})  # paused: nothing to run
        line = subprocess.run([sys.executable, "-I", str(CORE / "scripts" / "dev_statusline.py")], text=True, capture_output=True,
                              input=json.dumps({"workspace": {"project_dir": str(self.root)}})).stdout
        self.assertIn("▣ 3", line)

    def test_state_carries_plan_order_and_the_board_offers_requests(self):
        self.board("start", check=True)
        out = self.board("start").stdout
        self.assertIn("requests: on", out)
        d = json.loads(request(self.record()["port"], "GET", "/api/state")[1])
        self.assertEqual([d["tasks"][t]["seq"] for t in ("T-001", "T-002")], [1, 2])
        html = request(self.record()["port"], "GET", "/")[1].decode()
        for el in ('id="req-card"', 'id="view-switch"', 'id="planner"', 'id="issue-dialog"', 'id="toast"', 'id="cont-btn"'):
            self.assertIn(el, html)
        # the lane tabs are the page's navigation (3.1: the lanes of the flow diagram, plus the map); one panel per lane
        self.assertIn('id="phases" role="tablist"', html)
        self.assertIn('id="ph-map"', html)
        for ph in ("conception", "planning", "construction", "releases", "stable"):
            self.assertIn(f'id="phase-{ph}" role="tabpanel"', html)
        # Needs you, requests and activity are drawers outside every panel
        main = html[html.index('<main'):html.index('</main>')]
        for el in ('id="impediments"', 'id="req-card"', 'id="feed"', 'id="needs-dialog"'):
            self.assertNotIn(el, main)
            self.assertIn(el, html)
        self.assertIn('id="needs-btn"', html[:html.index('<main')])
        # construction: the milestone's strip (picker and stages), then the work area; the metrics are a modal
        cons = html[html.index('id="phase-construction"'):html.index('id="phase-releases"')]
        for el in ('id="tabs"', 'id="stages"', 'id="board-card"', 'id="tab-tasks"', 'id="tab-qa"', 'id="metrics-btn"'):
            self.assertIn(el, cons)
        metrics = html[html.index('id="metrics-dialog"'):]
        for el in ('id="ins-burndown"', 'id="ins-velocity"', 'id="ins-gates"'):
            self.assertIn(el, metrics)
        for el in ('id="ins-quality"', 'id="ins-backlog"', 'class="card insights"', 'id="tab-plan"', 'id="train-card"', 'id="cons-nav"'):
            self.assertNotIn(el, html)
        # the plan view has a screen of its own, opened from Planning
        self.assertIn('id="planner"', html[html.index('id="phase-replan"'):html.index('id="phase-construction"')])
        self.assertEqual(request(self.record()["port"], "GET", "/assets/favicon-alert.svg")[0], 200)  # the tab's "needs you" icon
        releases = html[html.index('id="phase-releases"'):html.index('id="phase-stable"')]
        for el in ('id="rel-strip"', 'id="rel-tiles"'):
            self.assertIn(el, releases)
        for el in ('id="board-card"', 'id="tabs"', 'id="stages"'):
            self.assertNotIn(el, releases)

    def test_state_endpoint_is_read_only_and_complete(self):
        state_file = self.root / ".dev" / "state.json"
        before = state_file.read_bytes()
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/state")
        self.assertEqual(code, 200)
        d = json.loads(body)
        for key in ("project", "phase", "step", "cycle", "progress", "milestones", "tasks", "next", "reviews", "quality",
                    "backlog", "questions", "log", "current_milestone", "board", "kit", "decisions", "releases", "release_history", "production",
                    "artifacts"):
            self.assertIn(key, d)
        self.assertEqual([p["key"] for p in d["cycle"]["phases"]], ["conception", "planning", "construction", "stable"])  # Releases is not a phase
        self.assertRegex(d["kit"], r"^\d+\.\d+\.\d+")
        self.assertEqual(d["milestones"][0]["goal"], "Ship a deployable skeleton.")
        self.assertEqual(d["tasks"]["T-001"]["status"], "in_progress")
        self.assertNotIn("token", d["board"])
        self.assertEqual(d["lifecycle"], {"local_deploy": "off", "deploy_when": "none", "max_fix_rounds": 3})
        self.assertEqual([p["key"] for p in d["cycle"]["phases"]], ["conception", "planning", "construction", "stable"])
        self.assertEqual((d["phase"], d["step"]), ("conception", "interview"))  # no brief yet
        self.assertEqual([x["key"] for x in d["cycle"]["phases"][2]["steps"]], ["milestones", "release"])
        self.assertIsNone(d["milestones"][0]["deploy"])
        self.assertEqual((d["releases"], d["production"]), ([], None))
        self.assertEqual(set(d["artifacts"]), {"interview", "prd", "architecture", "ux", "ui", "plan"})
        self.assertEqual(state_file.read_bytes(), before)

    def test_release_decision_only_for_a_release_waiting_for_approval(self):
        mod = self._mod()
        plan = PLAN.replace("## M1", "## R1 — First\n\n## M1", 1)
        (self.root / ".dev" / "plan.md").write_text(plan, encoding="utf-8")
        self.ds("sync-plan")
        d = mod.build_state(self.root)
        self.assertEqual([(r["id"], r["status"]) for r in d["cycle"]["releases"]], [("R1", "in_progress")])
        self.assertEqual(d["milestones"][0]["release"], "R1")
        self.assertIn("not waiting for your approval", mod.release_decision_errors(self.root, {"release": "R1", "decision": "approve"})[0])
        for tid in [t for t, v in json.loads((self.root / ".dev" / "state.json").read_text())["tasks"].items()]:
            self.ds("done", tid, "--force")
        self.ds("gate", d["milestones"][0]["id"], "passed", "--score", "90")
        self.ds("release-submit", "R1")
        self.assertEqual(mod.release_decision_errors(self.root, {"release": "R1", "decision": "approve"}), [])
        sys.path.insert(0, str(CORE / "scripts"))
        import dev_worker as dw
        dw.submit(self.root, "release_decision", {"release": "R1", "decision": "approve"})
        self.assertIn("already queued", mod.release_decision_errors(self.root, {"release": "R1", "decision": "approve"})[0])

    def test_markdown_documents_of_dev_only(self):
        mod = self._mod()
        dev = self.root / ".dev"
        (dev / "prd.md").write_text("# PRD\n\n| AC | Text |\n|---|---|\n| AC-1 | x |\n", encoding="utf-8")
        (dev / "qa" / "M1").mkdir(parents=True)
        (dev / "qa" / "M1" / "report.md").write_text("# QA M1\n", encoding="utf-8")
        (dev / "notes.txt").write_text("x", encoding="utf-8")
        (self.root / "outside.md").write_text("secret", encoding="utf-8")
        (dev / "link.md").symlink_to(self.root / "outside.md")
        (dev / "run").mkdir(exist_ok=True)
        (dev / "run" / "scratch.md").write_text("x", encoding="utf-8")
        code, d = mod.doc_detail(self.root, "prd.md")
        self.assertEqual((code, d["path"]), (200, "prd.md"))
        self.assertIn("| AC-1 | x |", d["text"])
        self.assertEqual(mod.doc_detail(self.root, ".dev/qa/M1/report.md")[1]["path"], "qa/M1/report.md")
        for bad, want in (("../outside.md", 400), ("/etc/passwd", 400), ("link.md", 400), ("notes.txt", 400),
                          ("missing.md", 404), ("qa/../../outside.md", 400), ("prd.md\x00", 400), ("", 400)):
            self.assertEqual(mod.doc_detail(self.root, bad)[0], want, bad)
        docs = mod.build_state(self.root)["docs"]
        self.assertIn("prd.md", docs)
        self.assertIn("qa/M1/report.md", docs)
        self.assertNotIn("run/scratch.md", docs)
        self.assertNotIn("link.md", docs)
        # over HTTP, behind the same access check as /api/task
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/doc?path=qa%2FM1%2Freport.md")
        self.assertEqual((code, json.loads(body)["text"]), (200, "# QA M1\n"))
        self.assertEqual(request(port, "GET", "/api/doc?path=..%2Foutside.md")[0], 400)

    def test_decisions_are_listed_newest_first_without_the_template_placeholder(self):
        mod = self._mod()
        text = ("### ADR-001 — {{first decision}}\n- date: {{date}} · status: accepted · source: interview\n"
                "### ADR-001 — Use SQLite\n- date: 2026-01-02 · status: superseded by ADR-003 · source: interview\n"
                "- category: library_choice\n### ADR-002 — Tokens in cookies (auto)\n- date: 2026-01-05 · status: accepted · source: auto\n"
                "### ADR-003 — Use Postgres\n- status: accepted\n")
        out = mod.decisions_list(text)
        self.assertEqual([d["id"] for d in out], ["ADR-003", "ADR-002", "ADR-001"])
        self.assertEqual(out[2], {"id": "ADR-001", "title": "Use SQLite", "status": "superseded by ADR-003", "date": "2026-01-02"})
        self.assertEqual((out[0]["status"], out[0]["date"]), ("accepted", None))

    def test_production_and_releases_reach_the_board(self):
        mod = self._mod()
        self.assertIsNone(mod.build_state(self.root)["production"])
        self.ds("deploy", "production", "--sha", "a" * 40, "--status", "ok")
        self.ds("deploy", "production", "--sha", "b" * 40, "--status", "failed")
        d = mod.build_state(self.root)
        self.assertEqual((d["production"]["current"]["sha"], d["production"]["last"]["status"]), ("a" * 40, "failed"))

    def test_milestone_deploy_is_the_latest_production_record_of_that_milestone(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dev_board", BOARD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        m1 = mod.build_state(self.root)["milestones"][0]["id"]
        self.ds("deploy", "production", "--sha", "a" * 40, "--status", "failed", "--milestone", m1)
        self.ds("deploy", "production", "--sha", "b" * 40, "--status", "ok", "--milestone", m1)
        self.ds("deploy", "production", "--sha", "c" * 40, "--status", "ok")
        d = mod.build_state(self.root)
        self.assertEqual(d["milestones"][0]["deploy"]["status"], "ok")
        self.assertEqual(d["milestones"][0]["deploy"]["sha"], "b" * 40)

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
        # the subagent's own transcript path: derived on start (with or without the agent- prefix), given on stop
        fire("SubagentStart", agent_id="agent-b1", agent_type="dev-kit:implementer", transcript_path="/h/.claude/projects/p/s1.jsonl")
        fire("SubagentStart", agent_id="b2", agent_type="dev-kit:implementer", transcript_path="/h/.claude/projects/p/s1.jsonl")
        fire("SubagentStop", agent_id="b2", agent_type="dev-kit:implementer", agent_transcript_path="/etc/passwd")
        recs = [json.loads(x) for x in (self.root / ".dev" / "run" / "agents.jsonl").read_text().splitlines()]
        self.assertEqual([r.get("transcript") for r in recs[-3:]],
                         ["/h/.claude/projects/p/s1/subagents/agent-b1.jsonl", "/h/.claude/projects/p/s1/subagents/agent-b2.jsonl", None])

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dev_board", BOARD)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(BOARD.parent))
        spec.loader.exec_module(mod)
        return mod

    def _hook(self, event, agent_id, agent, ago_s=0, transcript=None):
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        run = self.root / ".dev" / "run"
        run.mkdir(exist_ok=True)
        rec = {"ts": ts, "event": event, "session": "s1", "agent_id": agent_id, "agent": agent}
        if transcript:
            rec["transcript"] = str(transcript)
        with (run / "agents.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")

    def _transcript(self, agent_id, prompt=None):
        """Path of a fake subagent transcript; written only when a prompt is given (blocks form, as Claude Code does)."""
        p = self.root / "cc" / "s1" / "subagents" / f"agent-{agent_id}.jsonl"
        if prompt is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}})
                         + "\n" + json.dumps({"type": "assistant", "message": {"content": "Scope: T-099"}}) + "\n")
        return p

    def test_agents_link_by_the_scope_line_of_their_prompt(self):
        """Two implementers started together, spawns logged without scope: only the prompt can tell them apart."""
        mod = self._mod()
        self.ds("start", "T-002", "--force")
        self._hook("session_start", "", "")
        for _ in range(3):
            self.ds("event", "agent_spawn", "--set", "agent=implementer")
        self._hook("agent_start", "a1", "dev-kit:implementer", transcript=self._transcript("a1", "Task: T-002 — x\nScope: T-002\n"))
        self._hook("agent_start", "a2", "dev-kit:implementer", transcript=self._transcript("a2", "Task: T-001\nScope: T-001"))
        self._hook("agent_start", "a3", "dev-kit:implementer", transcript=self._transcript("a3"))  # not written yet
        tasks = {t: {"status": "in_progress"} for t in ("T-001", "T-002", "T-003")}
        live = mod.live_agents(self.root, None, tasks)["active"]
        self.assertEqual(sorted((x["node"], x["linked_by"]) for x in live[:2]), [("T-001", "id"), ("T-002", "id")])
        # the third falls back to the task rule: the one in-progress task with no agent
        self.assertEqual((live[2]["node"], live[2]["linked_by"]), ("T-003", "task"))
        self._transcript("a3", "Scope: M1")
        self.assertEqual(mod.live_agents(self.root, None, tasks)["active"][2]["node"], "GATE:M1")
        # nothing from the transcript reaches /api/state
        self.assertNotIn("transcript", json.dumps(mod.build_state(self.root)["agents"]))

    def test_spawn_without_scope_never_links_by_time_to_nothing(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        # written directly: dev_state would fill the scope in (one task in progress)
        tel = self.root / ".dev" / "telemetry.jsonl"
        sess = json.loads(tel.read_text().splitlines()[-1]).get("session") if tel.exists() else None
        from datetime import datetime, timezone
        with tel.open("a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": "agent_spawn",
                                "session": sess, "agent": "implementer"}) + "\n")
        self._hook("agent_start", "a1", "dev-kit:implementer")
        tasks = {"T-001": {"status": "in_progress"}}
        self.assertEqual([(x["node"], x["linked_by"]) for x in mod.live_agents(self.root, None, tasks)["active"]],
                         [("T-001", "task")])
        self.assertEqual([(x["node"], x["linked_by"]) for x in mod.live_agents(self.root)["active"]], [(None, None)])

    def test_unscoped_spawn_without_hooks_links_to_the_task_and_closes(self):
        mod = self._mod()
        tel = self.root / ".dev" / "telemetry.jsonl"
        sess = json.loads(tel.read_text().splitlines()[-1]).get("session")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tel.open("a") as f:
            f.write(json.dumps({"ts": now, "event": "agent_spawn", "session": sess, "agent": "implementer"}) + "\n")
        tasks = {"T-001": {"status": "in_progress"}}
        self.assertEqual([(x["node"], x["linked_by"]) for x in mod.live_agents(self.root, None, tasks)["active"]],
                         [("T-001", "task")])
        with tel.open("a") as f:
            f.write(json.dumps({"ts": now, "event": "agent_end", "session": sess, "agent": "implementer", "status": "ok"}) + "\n")
        self.assertEqual(mod.live_agents(self.root, None, tasks)["active"], [])

    def test_agent_colors_match_claude_code_and_the_board(self):
        mod = self._mod()
        roles = mod.agent_roles()
        self.assertEqual(len(roles), 17)
        self.assertEqual({r["color"] for r in roles.values()} - set(mod.AGENT_COLORS), set())
        self.assertEqual(roles["architect"]["color"], "purple")
        self.assertEqual(roles["implementer"]["color"], "green")
        css = (CORE / "shared" / "board" / "board.css").read_text()
        for c in mod.AGENT_COLORS:
            self.assertEqual(css.count(f"--ag-{c}:"), 3, c)  # dark, light by preference, light by switch
            self.assertIn(f".agent-dot.ag-{c} ", css)

    def test_live_agents_from_skill_log_without_hooks(self):
        mod = self._mod()
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-002", "--set", "slot=1")
        self.ds("event", "agent_spawn", "--set", "agent=code-reviewer", "--set", "scope=M1", "--set", "slot=2")
        self.ds("event", "agent_spawn", "--set", "agent=security-auditor", "--set", "scope=M1", "--set", "slot=3")
        self.ds("event", "agent_end", "--set", "agent=security-auditor", "--set", "scope=M1", "--set", "slot=3",
                "--set", "status=ok", "--set", "duration_s=40")
        a = mod.live_agents(self.root)
        self.assertFalse(a["hooks"])
        self.assertEqual(sorted((x["agent"], x["node"]) for x in a["active"]),
                         [("code-reviewer", "GATE:M1"), ("implementer", "T-002")])

    def test_live_agents_hooks_link_only_when_unambiguous(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-002", "--set", "slot=1")
        self._hook("agent_start", "a1", "dev-kit:implementer")
        self._hook("agent_start", "a2", "Explore")
        a = {x["agent"]: x for x in mod.live_agents(self.root)["active"]}
        self.assertTrue(mod.live_agents(self.root)["hooks"])
        self.assertEqual(a["implementer"]["node"], "T-002")
        self.assertIsNone(a["Explore"]["node"])
        # a second implementer in the same window (implement --parallel): two agents for two spawns, paired as a batch
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-001", "--set", "slot=2", "--set", "round=1")
        self._hook("agent_start", "a3", "dev-kit:implementer")
        impl = [x for x in mod.live_agents(self.root)["active"] if x["agent"] == "implementer"]
        self.assertEqual(sorted(x["node"] for x in impl), ["T-001", "T-002"])
        self.assertEqual({x["linked_by"] for x in impl}, {"batch"})
        # stopped hook agents leave the running set; a new one still sees two open spawns, so it stays unlinked
        self._hook("agent_stop", "a1", "dev-kit:implementer")
        self._hook("agent_stop", "a3", "dev-kit:implementer")
        self._hook("agent_start", "a4", "dev-kit:implementer")
        late = [x for x in mod.live_agents(self.root)["active"] if x["agent"] == "implementer"]
        self.assertEqual([x["node"] for x in late], [None])

    def test_late_auditor_links_by_type_or_by_the_open_qa_run(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        # the skill logged the spawn when it planned the batch; the heavy auditor really started 5 minutes apart
        self.ds("event", "agent_spawn", "--set", "agent=a11y-auditor", "--set", "scope=M1", "--set", "slot=4")
        self._hook("agent_start", "h1", "dev-kit:a11y-auditor", ago_s=300)
        a = {x["agent"]: x for x in mod.live_agents(self.root)["active"]}
        self.assertEqual((a["a11y-auditor"]["node"], a["a11y-auditor"]["linked_by"]), ("GATE:M1", "type"))
        # no spawn at all, but qa is running on M1: an auditor belongs to that gate, an implementer does not
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        self._hook("agent_start", "h2", "dev-kit:copy-reviewer")
        self._hook("agent_start", "h3", "dev-kit:implementer")
        live = mod.live_agents(self.root)
        a = {x["agent"]: x for x in live["active"]}
        self.assertEqual((a["copy-reviewer"]["node"], a["copy-reviewer"]["linked_by"]), ("GATE:M1", "qa_run"))
        self.assertIsNone(a["implementer"]["node"])
        self.assertEqual([(r["skill"], r["scope"]) for r in live["runs"]], [("qa", "M1")])
        # the run ends: nothing is inferred any more
        self.ds("event", "skill_end", "--set", "skill=qa", "--set", "scope=M1", "--set", "status=ok")
        self.assertEqual(mod.live_agents(self.root)["runs"], [])

    def test_a_finished_qa_run_takes_its_unclosed_auditors_with_it(self):
        mod = self._mod()
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        self.ds("event", "agent_spawn", "--set", "agent=a11y-auditor", "--set", "scope=M1", "--set", "slot=1")
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-002", "--set", "slot=2")
        self.assertEqual(len(mod.live_agents(self.root)["active"]), 2)
        self.ds("event", "skill_end", "--set", "skill=qa", "--set", "scope=M1", "--set", "status=ok")
        self.assertEqual([x["agent"] for x in mod.live_agents(self.root)["active"]], ["implementer"])

    def test_qa_run_without_scope_uses_the_milestone_waiting_for_its_gate(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "args_kind=milestone")
        self._hook("agent_start", "h1", "dev-kit:spec-tracer")
        self.assertIsNone(mod.live_agents(self.root)["active"][0]["node"])
        self.assertEqual(mod.live_agents(self.root, "M1")["active"][0]["node"], "GATE:M1")

    def test_parallel_implementers_link_to_their_tasks(self):
        """implement --parallel 2: the skill logs both spawns, prepares the briefs, and the agents start a minute
        later, together. Neither the time rule nor the type rule can tell them apart; the batch rule pairs them."""
        mod = self._mod()
        self.ds("start", "T-002", "--force")
        self._hook("session_start", "", "")
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-001", "--set", "slot=1")
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-002", "--set", "slot=2")
        self._hook("agent_start", "a1", "dev-kit:implementer", ago_s=-90)
        self._hook("agent_start", "a2", "dev-kit:implementer", ago_s=-90)
        tasks = {t: {"status": "in_progress", "started_at": None} for t in ("T-001", "T-002")}
        impl = mod.live_agents(self.root, None, tasks)["active"]
        self.assertEqual(sorted(x["node"] for x in impl), ["T-001", "T-002"])
        self.assertEqual({x["linked_by"] for x in impl}, {"batch"})
        # the same through /api/state: each running task carries one implementer, none is left "not linked"
        d = mod.build_state(self.root)
        self.assertEqual(sorted(a["node"] for a in d["agents"]["active"]), ["T-001", "T-002"])

    def test_spawn_of_a_finished_task_does_not_block_the_link(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        # T-002's agent_end was never logged; T-002 is done since
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-002", "--set", "slot=1")
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-001", "--set", "slot=2")
        self._hook("agent_start", "a1", "dev-kit:implementer")
        tasks = {"T-001": {"status": "in_progress"}, "T-002": {"status": "done"}}
        self.assertEqual([x["node"] for x in mod.live_agents(self.root)["active"]], [None])
        self.assertEqual([(x["node"], x["linked_by"]) for x in mod.live_agents(self.root, None, tasks)["active"]],
                         [("T-001", "time")])

    def test_unlogged_implementers_link_to_the_tasks_in_progress(self):
        mod = self._mod()
        self.ds("start", "T-002", "--force")
        self._hook("session_start", "", "")
        self._hook("agent_start", "a1", "dev-kit:implementer")
        self._hook("agent_start", "a2", "dev-kit:implementer")
        self._hook("agent_start", "a3", "Explore")
        tasks = {"T-001": {"status": "in_progress", "started_at": "2026-01-01T00:00:00Z"},
                 "T-002": {"status": "in_progress", "started_at": "2026-01-01T00:00:05Z"}}
        live = {x["agent"]: [] for x in mod.live_agents(self.root, None, tasks)["active"]}
        for x in mod.live_agents(self.root, None, tasks)["active"]:
            live[x["agent"]].append((x["node"], x["linked_by"]))
        self.assertEqual(sorted(live["implementer"]), [("T-001", "task"), ("T-002", "task")])
        self.assertEqual(live["Explore"], [(None, None)])
        # three implementers for two tasks: no guess
        self._hook("agent_start", "a4", "dev-kit:implementer")
        self.assertEqual({x["node"] for x in mod.live_agents(self.root, None, tasks)["active"]}, {None})

    def test_type_link_stays_off_when_spawns_of_that_type_point_to_different_nodes(self):
        mod = self._mod()
        self._hook("session_start", "", "")
        self.ds("event", "agent_spawn", "--set", "agent=code-reviewer", "--set", "scope=M1", "--set", "slot=1")
        self.ds("event", "agent_spawn", "--set", "agent=code-reviewer", "--set", "scope=T-002", "--set", "slot=2")
        self._hook("agent_start", "h1", "dev-kit:code-reviewer", ago_s=300)
        self.assertIsNone(mod.live_agents(self.root)["active"][0]["node"])

    def test_qa_detail_rounds_scores_and_running_auditors(self):
        mod = self._mod()
        self.ds("done", "T-001")
        self.ds("start", "T-002"); self.ds("done", "T-002")
        self.ds("gate", "M1", "pending", "--score", "89", "--count-run", "--note", "copy and spec below 75")
        qa = self.root / ".dev" / "qa" / "M1"
        qa.mkdir(parents=True)
        (qa / "scores.json").write_text(json.dumps({"overall": 89, "cutoff": 85, "verdict": "fail", "blockers": [],
            "dimensions": {"copy": {"score": 50, "min": 75, "ok": False}, "code": {"score": 95, "min": 75, "ok": True},
                           "spec": {"score": 72, "min": 75, "ok": False}}}))
        self.ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M1")
        for agent in ("code-reviewer", "a11y-auditor"):
            self.ds("event", "agent_spawn", "--set", f"agent={agent}", "--set", "scope=M1", "--set", "slot=1")
        self.ds("event", "agent_end", "--set", "agent=code-reviewer", "--set", "scope=M1", "--set", "slot=1",
                "--set", "status=ok", "--json", '{"findings": {"medium": 2}}')
        d = mod.build_state(self.root)
        q = d["milestones"][0]["qa"]
        self.assertEqual(q["runs"], 1)
        self.assertEqual([(r["n"], r["value"], r["score"]) for r in q["history"]], [(1, "pending", 89)])
        self.assertEqual(q["last"]["below"], [{"dimension": "copy", "score": 50, "min": 75}, {"dimension": "spec", "score": 72, "min": 75}])
        self.assertEqual(q["round"]["n"], 2)
        self.assertEqual([x["agent"] for x in q["round"]["done"]], ["code-reviewer"])
        self.assertEqual(q["round"]["spawned"], 2)
        texts = [r["text"] for r in d["log"] if r.get("kind") == "live"]
        self.assertIn("a11y-auditor started (accessibility audit) · QA gate of M1", texts)
        self.assertIn("code-reviewer finished · QA gate of M1 · 2 medium", texts)
        self.assertIn("/dev-kit:qa started (M1)", texts)

    def test_every_agent_has_a_short_role(self):
        mod = self._mod()
        agents = sorted(p.stem for p in mod.AGENTS_DIR.glob("*.md"))
        self.assertTrue(agents)
        self.assertEqual([a for a in agents if a not in mod.AGENT_ROLE], [])
        self.assertTrue(all(v["role"] and v["about"] for v in mod.AGENT_ROLES.values()))

    def test_graph_endpoint_is_gone(self):
        self.board("start", check=True)
        port = self.record()["port"]
        self.assertEqual(request(port, "GET", "/api/graph?m=M1")[0], 404)
        self.assertNotIn(b"/api/graph", request(port, "GET", "/assets/board.js")[1])

    def test_task_endpoint(self):
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/task?id=T-001")
        self.assertEqual(code, 200)
        d = json.loads(body)
        self.assertEqual(d["id"], "T-001")
        for k in ("acceptance", "deps", "blocks", "files", "log", "commit_sha"):
            self.assertIn(k, d)
        self.assertEqual(request(port, "GET", "/api/task?id=bad")[0], 400)
        self.assertEqual(request(port, "GET", "/api/task?id=T-999")[0], 404)
        self.assertEqual(request(port, "GET", "/api/task?id=T-001", {"Host": "evil.example"})[0], 403)

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


class TestNoStateProjects(unittest.TestCase):
    """Outside a dev-kit project the hook and the board must leave no trace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".dev").mkdir()  # an unrelated tool's .dev/ folder, no state.json

    def tearDown(self):
        self.tmp.cleanup()

    def test_hook_ignores_dev_folder_without_state(self):
        hook = CORE / "scripts" / "dev_agent_hook.py"
        payload = {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(self.root)}
        subprocess.run([sys.executable, "-I", str(hook)], input=json.dumps(payload), text=True, check=True,
                       capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)})
        self.assertFalse((self.root / ".dev" / "run").exists())

    def test_stop_and_status_do_not_create_run_dir(self):
        for args in (["stop"], ["status"], ["status", "--json"]):
            p = subprocess.run([sys.executable, "-I", str(BOARD), "--root", str(self.root), *args],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("not running" if "--json" not in args else '"running": false', p.stdout)
        self.assertFalse((self.root / ".dev" / "run").exists())
