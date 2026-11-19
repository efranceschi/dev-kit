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

    def test_state_endpoint_is_read_only_and_complete(self):
        state_file = self.root / ".dev" / "state.json"
        before = state_file.read_bytes()
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/state")
        self.assertEqual(code, 200)
        d = json.loads(body)
        for key in ("project", "phase", "phases", "progress", "milestones", "tasks", "next", "reviews", "quality",
                    "backlog", "questions", "log", "current_milestone", "board", "kit"):
            self.assertIn(key, d)
        self.assertRegex(d["kit"], r"^\d+\.\d+\.\d+")
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

    def test_graph_baseline_loops_fix_gate_and_parallel(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dev_board", BOARD)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(BOARD.parent))
        spec.loader.exec_module(mod)
        base_file = self.root / ".dev" / "plan-baseline.json"
        base = json.loads(base_file.read_text())
        self.assertEqual(sorted(base), ["T-001", "T-002"])
        self.ds("block", "T-001", "--reason", "boom")
        self.ds("unblock", "T-001")
        self.ds("start", "T-001")
        self.ds("start", "T-002", "--force")  # overlaps with T-001 -> parallel
        self.ds("add-task", "--milestone", "M1", "--title", "Fix lint", "--type", "fix", "--source", "qa")
        self.ds("gate", "M1", "pending", "--score", "60", "--count-run")
        (self.root / ".dev" / "plan.md").write_text(PLAN.replace("Project scaffold", "Renamed"), encoding="utf-8")
        self.ds("sync-plan")
        self.assertEqual(json.loads(base_file.read_text()), base)  # first write wins, fix task never enters it
        g = mod.graph_data(self.root, "M1")
        nodes = {n["id"]: n for n in g["nodes"]}
        self.assertTrue(g["baseline"])
        self.assertEqual(nodes["T-001"]["blocks"], 1)
        self.assertEqual(nodes["T-001"]["attempts"], 2)
        self.assertTrue(nodes["T-003"]["added"] and not nodes["T-003"]["planned"])
        kinds = {(l["task"], l["kind"]) for l in g["loops"]}
        self.assertIn(("T-001", "block"), kinds)
        self.assertIn(("GATE", "gate"), kinds)
        self.assertEqual(g["parallel"], [["T-001", "T-002"]])
        fix_edges = {(e["from"], e["to"]) for e in g["edges"] if e["kind"] == "fix"}
        self.assertEqual(fix_edges, {("GATE", "T-003"), ("T-003", "GATE")})
        self.assertIsNone(mod.graph_data(self.root, "M9"))

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dev_board", BOARD)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(BOARD.parent))
        spec.loader.exec_module(mod)
        return mod

    def _hook(self, event, agent_id, agent, ago_s=0):
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        run = self.root / ".dev" / "run"
        run.mkdir(exist_ok=True)
        with (run / "agents.jsonl").open("a") as f:
            f.write(json.dumps({"ts": ts, "event": event, "session": "s1", "agent_id": agent_id, "agent": agent}) + "\n")

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
        gate = next(n for n in mod.graph_data(self.root, "M1")["nodes"] if n["id"] == "GATE")
        self.assertEqual(gate["agents_done"][-1]["agent"], "security-auditor")
        self.assertEqual(gate["agents_done"][-1]["duration_s"], 40)

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
        # a second implementer starting in the same window makes both ambiguous: no node for either
        self.ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "scope=T-001", "--set", "slot=2", "--set", "round=1")
        self._hook("agent_start", "a3", "dev-kit:implementer")
        nodes = [x["node"] for x in mod.live_agents(self.root)["active"] if x["agent"] == "implementer"]
        self.assertEqual(nodes, [None, None])
        # stopped hook agents leave the running set; a new one still sees two open spawns, so it stays unlinked
        self._hook("agent_stop", "a1", "dev-kit:implementer")
        self._hook("agent_stop", "a3", "dev-kit:implementer")
        self._hook("agent_start", "a4", "dev-kit:implementer")
        late = [x for x in mod.live_agents(self.root)["active"] if x["agent"] == "implementer"]
        self.assertEqual([x["node"] for x in late], [None])

    def test_graph_endpoint(self):
        self.board("start", check=True)
        port = self.record()["port"]
        code, body = request(port, "GET", "/api/graph?m=M1")
        self.assertEqual(code, 200)
        self.assertIn("T-001", [n["id"] for n in json.loads(body)["nodes"]])
        self.assertEqual(request(port, "GET", "/api/graph?m=bad")[0], 400)
        self.assertEqual(request(port, "GET", "/api/graph?m=M9")[0], 404)
        self.assertEqual(request(port, "GET", "/api/graph?m=M1", {"Host": "evil.example"})[0], 403)

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
