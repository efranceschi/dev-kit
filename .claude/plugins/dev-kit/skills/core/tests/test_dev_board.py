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
        self.assertEqual(d["lifecycle"], {"local_deploy": "off", "deploy_when": "none", "max_fix_rounds": 3})
        self.assertIsNone(d["milestones"][0]["deploy"])
        self.assertEqual(state_file.read_bytes(), before)

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
