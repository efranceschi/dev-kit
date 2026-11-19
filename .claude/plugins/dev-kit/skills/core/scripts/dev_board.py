#!/usr/bin/env python3
"""dev_board.py - local, read-only Scrum board for a dev-kit project, served on 127.0.0.1.

Standard library only. Run with: python3 -I dev_board.py [--root DIR] <subcommand>

Subcommands
  start   start the board (or reuse the one already running) and open the default browser
          --port N (preferred port, default 8765; falls back to a free one) · --no-open · --open (force a tab
          even when the board was already running) · --idle-min N (auto-stop after N idle minutes, default 120)
          · --host IP (listen address, default 127.0.0.1; 0.0.0.0 or :: shares it with the network, see below;
          a running board on another address is restarted)
  stop    stop the board of this project (token-authenticated shutdown, then SIGTERM, then SIGKILL)
  status  print whether the board is running, its URL and PID (--json)
  serve   internal: the server process itself (spawned by start)

One board per project: .dev/run/board.json holds {pid, port, token, url, root, started_at}; a lock file
(.dev/run/board.lock) serialises concurrent starts. A recorded PID only counts as the board when the process
is alive, its command line is this script serving this root, and /api/ping on the port answers with the
same token fingerprint. Anything else is a stale record and is removed.

The server never writes to .dev/ except its own files in .dev/run/ and needs the per-run token to shut down.
By default it binds 127.0.0.1 and answers Host headers that are localhost or an IP literal (tunnels, forwards),
refusing host names (DNS rebinding). With --host on a non-loopback address the board is "exposed": every
request except /api/ping needs the access key (the per-run token) from ?key= - traded for an HttpOnly,
SameSite=Strict cookie - so host names are accepted there. It is plain HTTP: for trusted networks only.

Exit codes: 0 ok · 1 error · 2 no dev-kit state in the project
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import http.cookies
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # -I drops the script dir
import dev_state as ds  # noqa: E402

ASSETS = SCRIPTS.parent / "shared" / "board"
STATIC = {"/": "index.html", "/index.html": "index.html", "/assets/board.css": "board.css",
          "/assets/board.js": "board.js", "/assets/favicon.svg": "favicon.svg"}
DEFAULT_PORT = 8765
# Identity of this code: a running server whose record carries another value was started by an older copy
# of the kit (e.g. before a plugin update) and is restarted by `start` instead of reused.
CODE_ID = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()[:12]
WATCHED = ("state.json", "log.md", "open-questions.md", "costs/summary.json", "plan.md", "run/agents.jsonl",
           "telemetry.jsonl", "plan-baseline.json")
KIT_VERSION = ds.tel.kit_version()  # read once: it is the version of the code this server is actually running
AGENT_STALE_S = 3600
LINK_WINDOW_S = 30  # a hook start and a skill spawn of the same agent type this close may be the same agent
AGENTS_DONE = 8  # a start with no stop after this long is treated as lost, not running
AGENT_RECENT = 10
LOG_TAIL = 25


# --------------------------------------------------------------------------- record and identity

def run_dir(root: Path) -> Path:
    return root / ".dev" / "run"


def ensure_run_dir(root: Path) -> None:
    """Create .dev/run/ with a .gitignore so the token and logs are never committed."""
    run_dir(root).mkdir(parents=True, exist_ok=True)
    gi = run_dir(root) / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")


def record_path(root: Path) -> Path:
    return run_dir(root) / "board.json"


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def read_record(root: Path) -> dict | None:
    try:
        rec = json.loads(record_path(root).read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) and isinstance(rec.get("pid"), int) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_record(root: Path, rec: dict) -> None:
    ensure_run_dir(root)
    tmp = record_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)  # holds the shutdown token
    os.replace(tmp, record_path(root))


def remove_record(root: Path, pid: int | None = None) -> None:
    """Remove board.json; with pid, only if the record still belongs to that process."""
    if pid is not None:
        rec = read_record(root)
        if rec and rec.get("pid") != pid:
            return
    record_path(root).unlink(missing_ok=True)


def is_board_process(pid: int, root: Path) -> bool:
    if not ds._alive(pid):
        return False
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return True  # no /proc (macOS): trust the ping check
    args = [c.decode("utf-8", "replace") for c in cmd if c]
    return any(a.endswith("dev_board.py") for a in args) and "serve" in args and str(root) in args


def parse_bind(host: str) -> str:
    """Validate --host: an IP address to listen on (0.0.0.0 / :: = every interface). Names are refused."""
    h = host.strip().strip("[]").lower()
    if h == "localhost":
        return "127.0.0.1"
    try:
        return ipaddress.ip_address(h).compressed
    except ValueError:
        raise argparse.ArgumentTypeError(f"--host needs an IP address such as 127.0.0.1 or 0.0.0.0, not {host!r}")


def is_exposed(bind_host: str) -> bool:
    return not ipaddress.ip_address(bind_host).is_loopback


def connect_addr(bind_host: str) -> str:
    """Address this machine uses to reach the server (ping, stop, local browser)."""
    return {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(bind_host, bind_host)


def hostport(addr: str, port: int) -> str:
    return f"[{addr}]:{port}" if ":" in addr else f"{addr}:{port}"


def lan_addresses(bind_host: str) -> list[str]:
    """Addresses other machines can use: the bound IP, or this machine's non-loopback IPs for 0.0.0.0 / ::."""
    if bind_host not in ("0.0.0.0", "::"):
        return [bind_host]
    found: set[str] = set()
    for probe in ("192.0.2.1", "10.255.255.255"):  # UDP connect sends nothing; it only selects the outgoing interface
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.connect((probe, 9))
                found.add(u.getsockname()[0])
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in found if not ipaddress.ip_address(ip).is_loopback)


def ping(port: int, timeout: float = 1.0, addr: str = "127.0.0.1") -> dict | None:
    try:
        c = http.client.HTTPConnection(addr, port, timeout=timeout)
        c.request("GET", "/api/ping", headers={"Host": hostport(addr, port)})
        r = c.getresponse()
        body = r.read()
        c.close()
        return json.loads(body) if r.status == 200 else None
    except (OSError, ValueError):
        return None


def live_record(root: Path) -> dict | None:
    """The record if it describes this project's running board; None otherwise (stale records are removed)."""
    rec = read_record(root)
    if not rec:
        return None
    ok = (is_board_process(rec["pid"], root)
          and (p := ping(int(rec.get("port", 0)), addr=str(rec.get("connect", "127.0.0.1")))) is not None
          and p.get("app") == "dev-kit-board" and p.get("fingerprint") == fingerprint(str(rec.get("token", ""))))
    if not ok:
        remove_record(root)
        return None
    return rec


class Lock:
    def __init__(self, root: Path):
        ensure_run_dir(root)
        self.f = open(run_dir(root) / "board.lock", "a+")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


# --------------------------------------------------------------------------- data for the UI

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def milestone_goals(plan: str) -> dict:
    """First paragraph after each '## Mn — title' heading of plan.md."""
    goals, cur, buf = {}, None, []
    for line in plan.splitlines():
        h = line.strip()
        if h.startswith("## "):
            if cur and buf:
                goals[cur] = " ".join(buf)
            head = h[3:].split()
            cur = head[0] if head and head[0][:1] == "M" and head[0][1:].isdigit() else None
            buf = []
        elif h.startswith("#"):
            if cur and buf:
                goals[cur] = " ".join(buf)
            cur, buf = None, []
        elif cur:
            if h:
                buf.append(h)
            elif buf:
                goals[cur] = " ".join(buf)
                cur, buf = None, []
    if cur and buf:
        goals[cur] = " ".join(buf)
    return goals


def open_questions(text: str) -> list[dict]:
    out, cols, in_open = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_open = s.lower() == "## open"
            cols = []
            continue
        if not in_open or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cols:
            cols = [c.lower() for c in cells]
            continue
        if cells and cells[0].startswith("Q-"):
            row = dict(zip(cols, cells))
            out.append({"id": cells[0], "question": row.get("question", ""), "assumption": row.get("assumption used", ""),
                        "by": row.get("raised by", ""), "date": row.get("date", "")})
    return out


def log_tail(text: str, n: int = LOG_TAIL) -> list[dict]:
    rows = []
    for line in [ln for ln in text.splitlines() if ln.startswith("- ")][-n:]:
        parts = line[2:].split(" ", 1)
        rows.append({"at": parts[0], "text": parts[1] if len(parts) > 1 else ""})
    return rows[::-1]


def _ts(v: object) -> float:
    try:
        return datetime.strptime(str(v), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def agents_data(root: Path) -> dict:
    """Live agents from the hook log. `hooks` is true only once a hook has actually fired in this project,
    i.e. the environment runs plugin hooks; otherwise the panel is shown as disabled."""
    path = root / ".dev" / "run" / "agents.jsonl"
    recs = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict) and r.get("event") in ("session_start", "agent_start", "agent_stop"):
                recs.append(r)
    except OSError:
        pass
    if not recs:
        return {"hooks": False, "active": [], "recent": []}
    session = next((r.get("session") for r in reversed(recs) if r["event"] == "session_start"), None)
    now = time.time()
    running: dict[str, dict] = {}
    recent: list[dict] = []
    for r in recs:
        aid = r.get("agent_id") or ""
        if r["event"] == "agent_start" and aid:
            running[aid] = r
        elif r["event"] == "agent_stop" and aid:
            st = running.pop(aid, None)
            dur = max(0, round(_ts(r.get("ts")) - _ts(st.get("ts")))) if st else None
            recent.append({"agent": r.get("agent") or (st or {}).get("agent") or "agent", "agent_id": aid,
                           "started_at": (st or {}).get("ts"), "ended_at": r.get("ts"), "duration_s": dur})
    active = [{"agent": r.get("agent") or "agent", "agent_id": aid, "started_at": r.get("ts")}
              for aid, r in running.items()
              if now - _ts(r.get("ts")) < AGENT_STALE_S and (session is None or r.get("session") == session)]
    return {"hooks": True, "active": active, "recent": recent[-AGENT_RECENT:][::-1]}


_EVENTS_CACHE: dict = {}


def _task_events(root: Path) -> list[dict]:
    """Validated telemetry events, re-read only when the file changes (read_events re-validates every line)."""
    path = root / ".dev" / "telemetry.jsonl"
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return []
    hit = _EVENTS_CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    events, _ = ds.tel.read_events(root / ".dev")
    _EVENTS_CACHE[str(path)] = (key, events)
    return events


AC_LINE_RE = re.compile(r"^\s*[-*]\s*\**(AC-\d+)\**\s*(?:\[[^\]]*\])?\s*:\s*(.+)$")
TASK_ID_RE = re.compile(r"T-\d{1,5}")
SHA_RE = re.compile(r"[0-9a-f]{7,40}")


def _commit_info(root: Path, sha: object) -> dict | None:
    """Subject, date and changed files of a task's commit; None when there is no commit or git cannot show it."""
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        return None
    try:
        r = subprocess.run(["git", "show", "--stat=120", "--format=%H%x09%an%x09%aI%x09%s", sha], cwd=root,
                           capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    lines = r.stdout.splitlines()
    head = lines[0].split("\t", 3)
    if len(head) < 4:
        return None
    files = [ln.strip() for ln in lines[1:] if ln.strip()]
    return {"sha": head[0], "author": head[1], "date": head[2], "subject": head[3],
            "files": files[:-1][:40], "summary": files[-1] if files else ""}


def task_detail(root: Path, tid: str) -> dict | None:
    """Everything the kit keeps about one task, resolved on demand (the board state only carries the card)."""
    store = ds.Store(root)
    if not store.exists():
        return None
    try:
        store.load()
    except SystemExit:
        return None
    t = store.tasks().get(tid)
    if t is None:
        return None
    prd = {}
    for line in _read(store.dev / "prd.md").splitlines():
        m = AC_LINE_RE.match(line)
        if m:
            prd.setdefault(m.group(1), m.group(2).strip())
    acs = []
    for a in t.get("acceptance") or []:
        m = re.match(r"(AC-\d+)\s*(?:\[[^\]]*\])?\s*:?\s*(.*)", str(a))
        acs.append({"id": m.group(1) if m else None, "text": str(a),
                    "prd": prd.get(m.group(1)) if m and prd.get(m.group(1)) not in (None, (m.group(2) or "").strip()) else None})
    tasks = store.tasks()
    deps = [{"id": d, "title": tasks.get(d, {}).get("title"), "status": tasks.get(d, {}).get("status", "unknown")}
            for d in t.get("deps") or []]
    blocks = [{"id": k, "title": v.get("title"), "status": v.get("status")}
              for k, v in tasks.items() if tid in (v.get("deps") or []) and v.get("status") != "dropped"]
    issue = None
    src = t.get("source")
    if isinstance(src, str) and src.startswith("issue:"):
        i = (store.state.get("issues") or {}).get(src[6:])
        if i:
            issue = {"id": src[6:], **{k: i.get(k) for k in ("title", "type", "class", "severity", "status", "note", "affects", "origin")}}
    pat = re.compile(rf"\b{re.escape(tid)}\b")
    log = [r for r in log_tail(_read(store.dev / "log.md"), 100000) if pat.search(r["text"])]
    events = [{"ts": e.get("ts"), "transition": e.get("transition")} for e in _task_events(root)
              if e.get("event") == "task" and e.get("task") == tid]
    return {"ok": True, "id": tid, **{k: t.get(k) for k in ("title", "milestone", "type", "status", "lane", "source", "test_notes",
                                                           "blocked_reason", "started_at", "done_at")},
            "files": t.get("files") or [], "acceptance": acs, "deps": deps, "blocks": blocks, "issue": issue,
            "commit": _commit_info(root, t.get("commit")), "commit_sha": t.get("commit"),
            "log": log[:30], "events": events[-30:]}


def graph_data(root: Path, milestone: str) -> dict | None:
    """Execution graph of one milestone: the initial plan (baseline) plus what really happened.

    Nodes are tasks (plus stubs for dependencies in other milestones and a Gate sink); edges are dependencies;
    loops are failures that leave and re-enter the same node (block, restart, failed QA run); `parallel` lists
    groups of tasks whose execution intervals overlapped."""
    store = ds.Store(root)
    if not store.exists():
        return None
    try:
        store.load()
    except SystemExit:
        return None
    if milestone not in store.milestones():
        return None
    tasks = store.tasks()
    try:
        base = json.loads((store.dev / "plan-baseline.json").read_text(encoding="utf-8"))
        if not isinstance(base, dict):
            base = {}
    except (OSError, json.JSONDecodeError):
        base = {}
    has_base = bool(base)
    now = time.time()
    hist: dict[str, list[tuple[str, str]]] = {}
    gate_runs = []
    for e in _task_events(root):
        if e.get("event") == "task" and e.get("task") and e.get("transition"):
            hist.setdefault(e["task"], []).append((e.get("ts"), e["transition"]))
        elif e.get("event") == "gate" and e.get("scope") == milestone and e.get("value") == "pending" and (e.get("qa_runs") or 0) > 0:
            gate_runs.append({"at": e.get("ts"), "score": e.get("score"), "run": e.get("qa_runs")})

    done_by: dict[str, list[dict]] = {}
    for e in _task_events(root):
        if e.get("event") == "agent_end":
            node = _node_of(e.get("scope"))
            if node:
                f = e.get("findings") if isinstance(e.get("findings"), dict) else {}
                done_by.setdefault(node, []).append({"agent": _short(e.get("agent")), "at": e.get("ts"), "status": e.get("status"),
                                                     "duration_s": e.get("duration_s"), "findings": sum(v for v in f.values() if isinstance(v, (int, float))) if f else None})
    mine = {tid: t for tid, t in tasks.items() if t.get("milestone") == milestone and t.get("status") != "dropped"}
    nodes, edges, loops, spans = {}, [], [], {}

    def planned(tid: str, t: dict) -> bool:
        if has_base:
            return tid in base
        return t.get("type") != "fix" and not str(t.get("source") or "").startswith("issue:")

    for tid, t in sorted(mine.items(), key=lambda kv: int(kv[0][2:])):
        h = hist.get(tid, [])
        attempts = sum(1 for _, tr in h if tr == "start")
        blocks = sum(1 for _, tr in h if tr == "block")
        intervals, cur, prev = [], None, None
        for ts_, tr in h:
            if tr == "start":
                if cur is not None:
                    intervals.append([cur, ts_])
                    loops.append({"task": tid, "kind": "restart", "at": ts_})
                elif prev in ("done",):
                    loops.append({"task": tid, "kind": "restart", "at": ts_})
                cur = ts_
            elif tr in ("done", "block") and cur is not None:
                intervals.append([cur, ts_])
                cur = None
                if tr == "block":
                    loops.append({"task": tid, "kind": "block", "at": ts_})
            elif tr == "block":
                loops.append({"task": tid, "kind": "block", "at": ts_})
            prev = tr
        if cur is not None and t.get("status") == "in_progress":
            intervals.append([cur, None])
        spans[tid] = [(_ts(a), _ts(b) if b else now) for a, b in intervals]
        nodes[tid] = {"id": tid, "title": t.get("title"), "type": t.get("type"), "status": t.get("status"),
                      "lane": t.get("lane"), "planned": planned(tid, t), "added": has_base and tid not in base or not planned(tid, t),
                      "external": False, "attempts": attempts, "blocks": blocks, "intervals": intervals,
                      "history": [[a, b] for a, b in h[-24:]], "agents_done": done_by.get(tid, [])[-AGENTS_DONE:]}
    # dependency edges: current deps, compared with the baseline when there is one
    sinks = set(mine)
    for tid, t in mine.items():
        cur_deps = set(t.get("deps") or [])
        old_deps = set((base.get(tid) or {}).get("deps") or []) if has_base and tid in base else cur_deps
        for d in sorted(cur_deps | old_deps):
            if d not in tasks:
                continue
            kind = "planned" if d in cur_deps and d in old_deps else ("added" if d in cur_deps else "removed")
            if d not in nodes:
                dt = tasks[d]
                nodes[d] = {"id": d, "title": dt.get("title"), "type": dt.get("type"), "status": dt.get("status"),
                            "lane": None, "planned": True, "added": False, "external": True, "milestone": dt.get("milestone"),
                            "attempts": 0, "blocks": 0, "intervals": [], "history": [], "agents_done": []}
            edges.append({"from": d, "to": tid, "kind": kind})
            if kind != "removed":
                sinks.discard(d)
    m = store.milestones()[milestone]
    nodes["GATE"] = {"id": "GATE", "title": f"QA gate {milestone}", "type": "gate", "status": m.get("gate", "pending"),
                     "score": m.get("score"), "qa_runs": m.get("qa_runs", 0), "planned": True, "added": False,
                     "external": False, "attempts": 0, "blocks": 0, "intervals": [], "history": [],
                     "agents_done": done_by.get(f"GATE:{milestone}", [])[-AGENTS_DONE:]}
    fixes = [tid for tid, n in nodes.items() if tid in mine and n["added"] and mine[tid].get("type") == "fix"]
    for tid in sorted(sinks):
        if tid not in fixes:
            edges.append({"from": tid, "to": "GATE", "kind": "planned"})
    for tid in fixes:  # out and back: the gate sends work to the fix task and the fix returns to the gate
        edges.append({"from": "GATE", "to": tid, "kind": "fix"})
        edges.append({"from": tid, "to": "GATE", "kind": "fix"})
    for r in gate_runs:
        loops.append({"task": "GATE", "kind": "gate", "at": r["at"], "score": r["score"], "run": r["run"]})
    # parallel groups: connected components of overlapping execution intervals
    ids = [t for t in spans if spans[t]]
    parent = {t: t for t in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a_ in enumerate(ids):
        for b_ in ids[i + 1:]:
            if any(s1 < e2 and s2 < e1 for s1, e1 in spans[a_] for s2, e2 in spans[b_]):
                parent[find(a_)] = find(b_)
    groups: dict[str, list[str]] = {}
    for t_ in ids:
        groups.setdefault(find(t_), []).append(t_)
    return {"ok": True, "milestone": milestone, "baseline": has_base, "nodes": list(nodes.values()), "edges": edges,
            "loops": loops, "parallel": [sorted(g, key=lambda x: int(x[2:])) for g in groups.values() if len(g) > 1],
            "generated_at": ds.now()}


def _short(agent: object) -> str:
    return str(agent or "agent").removeprefix("dev-kit:")


def _node_of(scope: object) -> str | None:
    s = str(scope or "")
    if re.fullmatch(r"T-\d{1,5}", s):
        return s
    if re.fullmatch(r"M\d{1,3}", s):
        return f"GATE:{s}"
    return None


def open_spawns(events: list[dict], now: float) -> list[dict]:
    """agent_spawn events logged by the skills that have no matching agent_end yet (and are not stale)."""
    open_: list[dict] = []
    for e in events:
        ev = e.get("event")
        if ev == "agent_spawn":
            open_.append({"agent": _short(e.get("agent")), "scope": e.get("scope"), "slot": e.get("slot"),
                          "session": e.get("session"), "started_at": e.get("ts")})
        elif ev == "agent_end":
            ag, sc, sl, se = _short(e.get("agent")), e.get("scope"), e.get("slot"), e.get("session")
            match = [o for o in open_ if o["session"] == se and o["agent"] == ag and o["scope"] == sc and o["slot"] == sl] \
                or [o for o in open_ if o["session"] == se and o["agent"] == ag and o["scope"] == sc]
            if match:
                open_.remove(match[-1])
    return [o for o in open_ if now - _ts(o["started_at"]) < AGENT_STALE_S]


def live_agents(root: Path) -> dict:
    """Running agents and the graph node each one works on.

    Skills log agent_spawn/agent_end with a scope (task or milestone) in telemetry; plugin hooks, where the
    environment runs them, log exact start/stop of every agent but without the task. With hooks, the running set
    is the hook set and an agent gets a node only when exactly one skill spawn of the same type started within
    LINK_WINDOW_S of it and vice versa; any ambiguity leaves it without a node (better none than a wrong one).
    Without hooks, the open skill spawns are the running set."""
    now = time.time()
    spawns = open_spawns(_task_events(root), now)
    hooks = agents_data(root)
    if not hooks["hooks"]:
        active = [{"agent": o["agent"], "started_at": o["started_at"], "node": _node_of(o["scope"]), "slot": o["slot"]}
                  for o in spawns]
        return {"hooks": False, "active": active}
    near = lambda h, o: h["agent"] == o["agent"] and abs(_ts(h["started_at"]) - _ts(o["started_at"])) <= LINK_WINDOW_S  # noqa: E731
    hs = [{"agent": _short(h["agent"]), "started_at": h["started_at"]} for h in hooks["active"]]
    active = []
    for h in hs:
        cands = [o for o in spawns if near(h, o)]
        node = slot = None
        if len(cands) == 1 and sum(1 for x in hs if near(x, cands[0])) == 1:
            node, slot = _node_of(cands[0]["scope"]), cands[0]["slot"]
        active.append({"agent": h["agent"], "started_at": h["started_at"], "node": node, "slot": slot})
    return {"hooks": True, "active": active}


def build_state(root: Path, board: dict | None = None) -> dict:
    store = ds.Store(root)
    if not store.exists():
        return {"ok": False, "error": "no_state", "message": f"No dev-kit state in {root}. Run /dev-kit:start."}
    try:
        store.load()  # read-only from here on: never call store.save()
    except SystemExit:
        return {"ok": False, "error": "corrupt_state", "message": "state.json could not be read (it may be mid-write)."}
    s = store.state
    goals = milestone_goals(_read(store.dev / "plan.md"))
    tasks = {}
    for tid, t in sorted(store.tasks().items(), key=lambda kv: int(kv[0][2:])):
        if t.get("status") == "dropped":
            continue  # removed by a replan: history only, not on the board
        tasks[tid] = {k: t.get(k) for k in ("title", "milestone", "type", "status", "lane", "deps", "commit",
                                            "blocked_reason", "started_at", "done_at", "source")}
        tasks[tid]["acceptance"] = len(t.get("acceptance") or [])
    milestones = []
    for m in store.milestone_order():
        info = store.milestones()[m]
        milestones.append({"id": m, "title": info.get("title"), "goal": goals.get(m, ""), "gate": info.get("gate", "pending"),
                           "score": info.get("score"), "qa_runs": info.get("qa_runs", 0), "passed_at": info.get("passed_at"),
                           "preview": info.get("preview"),
                           "tasks": [tid for tid, t in tasks.items() if t["milestone"] == m]})
    nxt, why = ds.pick_next(store, None)
    try:
        backlog = ds.backlog_data(store)
    except Exception as e:  # noqa: BLE001 - the board must keep rendering
        backlog = {"error": str(e)}
    costs = None
    cs = store.dev / "costs" / "summary.json"
    if cs.exists():
        try:
            costs = json.loads(cs.read_text(encoding="utf-8")).get("total")
        except (OSError, json.JSONDecodeError):
            costs = None
    return {
        "ok": True,
        "project": s.get("project") or root.name,
        "phase": s.get("phase"), "phases": ds.PHASES, "language": s.get("language"),
        "created_at": s.get("created_at"), "updated_at": s.get("updated_at"),
        "autonomy": (s.get("autonomy") or {}).get("level"),
        "brownfield": ({k: (s.get("brownfield") or {}).get(k) for k in ("mode", "baseline_ref", "first_milestone")}
                       if s.get("brownfield") else None),
        "stack": {k: v for k, v in (s.get("stack") or {}).items() if k != "detected_from" and v},
        "progress": store.progress(),
        "current_milestone": ds.current_milestone(store),
        "next": {"task": nxt, "reason": why},
        "milestones": milestones, "tasks": tasks,
        "reviews": s.get("reviews") or {},
        "quality": ds.quality_cfg(store),
        "backlog": backlog,
        "questions": open_questions(_read(store.dev / "open-questions.md")),
        "log": log_tail(_read(store.dev / "log.md")),
        "costs": costs,
        "agents": live_agents(root),
        "kit": KIT_VERSION,
        "board": {k: board.get(k) for k in ("pid", "port", "url", "started_at", "host", "exposed")} if board else None,
        "generated_at": ds.now(),
    }


def signature(root: Path) -> tuple:
    dev = root / ".dev"
    out = []
    for name in WATCHED:
        try:
            st = (dev / name).stat()
            out.append((name, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((name, 0, 0))
    return tuple(out)


# --------------------------------------------------------------------------- server

def allowed_host(host: str) -> bool:
    """Host headers the board answers: 'localhost' or any IP literal (127.0.0.1, [::1], 192.168.x.y...),
    with or without a numeric port. Any other name is refused.

    The threat is DNS rebinding: a malicious site points its own domain name at this machine and reads the
    board from its page. That only works with a domain name in the Host header; a page whose URL is a raw IP
    is a different origin from any attacker site. IP literals are therefore safe to accept, and they are what
    the browser sends through SSH tunnels, editor port forwarding or a LAN forward (ssh -L 0.0.0.0:...).
    The server itself still binds 127.0.0.1 only: reaching it from another machine needs such a forward."""
    host = host.strip().lower()
    if host.startswith("["):
        name, _, rest = host.partition("]")
        name, port = name[1:], rest[1:] if rest.startswith(":") else (None if not rest else "x")
        v6_only = True
    else:
        name, _, port = host.partition(":")
        port = port if ":" in host else None
        v6_only = False
    if port is not None and not (port.isdigit() and 0 < int(port) < 65536):
        return False
    if name == "localhost" and not v6_only:
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return (ip.version == 6) == v6_only


class Board(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, root: Path, token: str, idle_s: int):
        super().__init__(addr, Handler)
        self.root, self.token, self.idle_s = root, token, idle_s
        self.exposed = is_exposed(addr[0])  # listening beyond loopback: every request needs the access key
        self.record: dict = {}
        self.stopping = threading.Event()
        self.last_activity = time.monotonic()
        self.clients = 0
        self.lock = threading.Lock()

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def stop(self) -> None:
        if not self.stopping.is_set():
            self.stopping.set()
            threading.Thread(target=self.shutdown, daemon=True).start()


class Board6(Board):
    address_family = socket.AF_INET6


class Handler(BaseHTTPRequestHandler):
    server: Board
    server_version = "dev-kit-board"
    sys_version = ""

    def log_message(self, fmt, *args):  # quiet: errors only
        pass

    def _host_ok(self) -> bool:
        """localhost or an IP address, on any port (tunnels and forwards may change both); see allowed_host."""
        host = self.headers.get("Host", "")
        if allowed_host(host) or self.server.exposed:  # exposed: the access key protects instead (a rebinding page never has it)
            return True
        print(f"refused Host header {host[:80]!r} (only localhost or an IP address are accepted)", file=sys.stderr, flush=True)
        return False

    def _cookie_name(self) -> str:
        return f"dkb_{self.server.server_address[1]}"

    def _key_from_query(self) -> str:
        q = self.path.partition("?")[2]
        return next((v[4:] for v in q.split("&") if v.startswith("key=")), "")

    def _authorized(self) -> bool:
        """Loopback-only boards need no key. Exposed ones need the access key, by cookie or ?key=."""
        if not self.server.exposed:
            return True
        tok = self.server.token
        if self._key_from_query() and secrets.compare_digest(self._key_from_query(), tok):
            return True
        try:
            jar = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return False
        c = jar.get(self._cookie_name())
        return bool(c) and secrets.compare_digest(c.value, tok)

    def _deny(self, path: str):
        print(f"refused unauthenticated request for {path[:60]!r} from {self.client_address[0]}", file=sys.stderr, flush=True)
        if path.startswith("/api/"):
            return self._json(401, {"ok": False, "error": "access key required",
                                    "hint": "open the access link printed by /dev-kit:board (or /dev-kit:board status)"})
        body = (b"<!doctype html><meta charset=utf-8><title>dev-kit board</title>"
                b"<body style=\"font:16px system-ui;margin:15vh auto;max-width:36em;padding:0 1em\">"
                b"<h1>Access link required</h1><p>This board is shared on the network and only opens with its access "
                b"link. Run <code>/dev-kit:board status</code> on the machine that runs it to see the link.</p>")
        self._send(401, body, "text/html; charset=utf-8")

    def _origin_ok(self) -> bool:
        """POSTs must come from the page itself: Origin, when sent, is the same origin the browser used."""
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() == f"http://{self.headers.get('Host', '')}".lower()

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj: object):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        self.server.touch()
        if not self._host_ok():
            return self._json(403, {"ok": False, "error": "forbidden host", "host": self.headers.get("Host", "")[:80],
                                    "hint": "open the board by IP address or localhost, e.g. http://127.0.0.1:<port>/ or "
                                            "http://<machine IP>:<port>/; host names are refused (DNS rebinding protection)"})
        path = self.path.split("?", 1)[0]
        if path == "/api/ping":
            return self._json(200, {"ok": True, "app": "dev-kit-board", "pid": os.getpid(),
                                    "fingerprint": fingerprint(self.server.token)})
        if not self._authorized():
            return self._deny(path)
        if self.server.exposed and self._key_from_query() and path in ("/", "/index.html"):
            # trade the key in the URL for a cookie, so it leaves the address bar and the history
            return self._send(303, b"", "text/plain", {
                "Location": "/",
                "Set-Cookie": f"{self._cookie_name()}={self.server.token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400"})
        if path == "/api/state":
            return self._json(200, build_state(self.server.root, self.server.record))
        if path == "/api/graph":
            q = self.path.partition("?")[2]
            ms = next((v[2:] for v in q.split("&") if v.startswith("m=")), "")
            if not re.fullmatch(r"M\d{1,3}", ms):
                return self._json(400, {"ok": False, "error": "bad milestone"})
            g = graph_data(self.server.root, ms)
            return self._json(200 if g else 404, g or {"ok": False, "error": "unknown milestone"})
        if path == "/api/task":
            q = self.path.partition("?")[2]
            tid = next((v[3:] for v in q.split("&") if v.startswith("id=")), "")
            if not TASK_ID_RE.fullmatch(tid):
                return self._json(400, {"ok": False, "error": "bad task id"})
            d = task_detail(self.server.root, tid)
            return self._json(200 if d else 404, d or {"ok": False, "error": "unknown task"})
        if path == "/api/events":
            return self._events()
        name = STATIC.get(path)
        if not name:
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            body = (ASSETS / name).read_bytes()
        except OSError:
            return self._json(500, {"ok": False, "error": f"missing asset {name}"})
        if name == "index.html":
            body = body.replace(b"__BOARD_TOKEN__", self.server.token.encode())
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith(("javascript", "svg+xml")):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype)

    do_HEAD = do_GET

    def do_POST(self):
        self.server.touch()
        if not self._host_ok() or not self._origin_ok():
            return self._json(403, {"ok": False, "error": "forbidden origin"})
        path = self.path.split("?", 1)[0]
        if path != "/api/shutdown":
            return self._json(404, {"ok": False, "error": "not found"})
        if not secrets.compare_digest(self.headers.get("X-Board-Token", ""), self.server.token):
            return self._json(403, {"ok": False, "error": "bad token"})
        self._json(202, {"ok": True, "stopping": True})
        self.server.stop()

    def _events(self):
        srv = self.server
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        with srv.lock:
            srv.clients += 1
        try:
            last = signature(srv.root)
            beat = time.monotonic()
            self.wfile.write(b"retry: 2000\nevent: hello\ndata: {}\n\n")
            self.wfile.flush()
            while not srv.stopping.wait(1.0):
                sig = signature(srv.root)
                if sig != last:
                    last = sig
                    self.wfile.write(b"event: change\ndata: {}\n\n")
                    self.wfile.flush()
                elif time.monotonic() - beat > 15:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    beat = time.monotonic()
                srv.touch()
            self.wfile.write(b"event: bye\ndata: {}\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with srv.lock:
                srv.clients -= 1


def bind(host: str, port: int, root: Path, token: str, idle_s: int) -> Board:
    cls = Board6 if ":" in host else Board
    try:
        return cls((host, port), root, token, idle_s)
    except OSError:
        return cls((host, 0), root, token, idle_s)


def cmd_serve(root: Path, a: argparse.Namespace) -> int:
    token = os.environ.pop("DEV_BOARD_TOKEN", "") or secrets.token_urlsafe(24)
    host = a.host or "127.0.0.1"
    srv = bind(host, a.port, root, token, a.idle_min * 60)
    port = srv.server_address[1]
    conn = connect_addr(host)
    url = f"http://{hostport(conn, port)}/"
    srv.record = {"pid": os.getpid(), "port": port, "token": token, "url": url, "root": str(root),
                  "host": host, "connect": conn, "exposed": srv.exposed,
                  "code": CODE_ID, "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if srv.exposed:
        srv.record["open_url"] = f"{url}?key={token}"
        srv.record["access_urls"] = [f"http://{hostport(ip, port)}/?key={token}" for ip in lan_addresses(host)]
    write_record(root, srv.record)

    def on_signal(signum, frame):
        srv.stop()
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGHUP, on_signal)

    def watchdog():
        while not srv.stopping.wait(30):
            if srv.idle_s > 0 and srv.clients == 0 and time.monotonic() - srv.last_activity > srv.idle_s:
                print(f"idle for {srv.idle_s // 60} min: stopping", flush=True)
                srv.stop()
            if read_record(root) is None or (read_record(root) or {}).get("pid") != os.getpid():
                srv.stop()  # record removed or taken over: this server is no longer the board
    threading.Thread(target=watchdog, daemon=True).start()
    print(f"serving {url} on {host} for {root} (pid {os.getpid()})" + (" · exposed: access key required" if srv.exposed else ""), flush=True)
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        srv.server_close()
        remove_record(root, os.getpid())
        print("stopped", flush=True)
    return 0


# --------------------------------------------------------------------------- start / stop / status

def open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:  # noqa: BLE001
        return False


def cmd_start(root: Path, a: argparse.Namespace) -> int:
    if not (root / ".dev" / "state.json").exists():
        print(f"no dev-kit state at {root / '.dev' / 'state.json'}; run /dev-kit:start first", file=sys.stderr)
        return 2
    with Lock(root):
        rec = live_record(root)
        restarted = False
        why = None
        if rec and rec.get("code") != CODE_ID:
            why = "the running board was started by another version of the kit"
        elif rec and a.host and rec.get("host", "127.0.0.1") != a.host:
            why = f"the running board listens on {rec.get('host', '127.0.0.1')}, not {a.host}"
        if why:
            code, msg = stop_locked(root)  # replace it rather than reuse it
            print(f"{why}; {msg}")
            if code:
                return code
            rec, restarted = None, True
        if rec:
            opened = open_browser(rec.get("open_url") or rec["url"]) if a.open else False
            print(f"already running: {rec['url']} (pid {rec['pid']})" +
                  (" · opened a new tab" if opened else " · no new tab opened (use --open to force one)"))
            print_exposure(rec)
            return 0
        log = open(run_dir(root) / "board.log", "a", encoding="utf-8")
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--root", str(root), "serve",
               "--port", str(a.port), "--idle-min", str(a.idle_min), "--host", a.host or "127.0.0.1"]
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(root),
                                start_new_session=True, close_fds=True)
        log.close()
        deadline = time.monotonic() + 8
        rec = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            r = read_record(root)
            if r and r.get("pid") == proc.pid and ping(int(r["port"]), 0.5, str(r.get("connect", "127.0.0.1"))):
                rec = r
                break
            time.sleep(0.1)
        if not rec:
            if proc.poll() is None:
                proc.terminate()
            print(f"the board did not start; see {run_dir(root) / 'board.log'}", file=sys.stderr)
            return 1
    opened = False if a.no_open else open_browser(rec.get("open_url") or rec["url"])
    print(f"{'restarted' if restarted else 'started'}: {rec['url']} (pid {rec['pid']})" +
          (" · opened in the default browser" if opened else " · open the URL in your browser"))
    print_exposure(rec)
    return 0


def print_exposure(rec: dict) -> None:
    """For a board listening beyond loopback: the access links and the warning that goes with them."""
    if not rec.get("exposed"):
        return
    print(f"exposed on {rec.get('host')} port {rec['port']}: plain HTTP, anyone with an access link can see the board and stop it")
    for u in rec.get("access_urls") or []:
        print(f"access link: {u}")
    if not rec.get("access_urls"):
        print(f"access link: http://<this machine's IP>:{rec['port']}/?key={rec['token']}")
    print("keep the links private; restart without --host (or --host 127.0.0.1) to stop sharing")


def cmd_stop(root: Path, a: argparse.Namespace) -> int:
    if not run_dir(root).is_dir():  # nothing was ever started here: do not create .dev/run/ just to say so
        print("not running")
        return 0
    with Lock(root):
        code, msg = stop_locked(root)
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


def stop_locked(root: Path) -> tuple[int, str]:
    """Stop this project's board; the caller holds the lock. Returns (exit code, message)."""
    rec = read_record(root)
    if not rec:
        return 0, "not running"
    pid = rec["pid"]
    if not is_board_process(pid, root):
        remove_record(root)
        return 0, f"not running (removed a stale record for pid {pid})"
    try:
        addr = str(rec.get("connect", "127.0.0.1"))
        c = http.client.HTTPConnection(addr, int(rec["port"]), timeout=2)
        c.request("POST", "/api/shutdown", body=b"",
                  headers={"Host": hostport(addr, int(rec["port"])), "X-Board-Token": str(rec.get("token", ""))})
        c.getresponse().read()
        c.close()
    except OSError:
        pass
    for sig, wait in ((None, 3.0), (signal.SIGTERM, 2.0), (signal.SIGKILL, 1.0)):
        if sig is not None and ds._alive(pid):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        end = time.monotonic() + wait
        while time.monotonic() < end and ds._alive(pid) and not _zombie(pid):
            time.sleep(0.1)
        if not ds._alive(pid) or _zombie(pid):
            break
    remove_record(root)
    if ds._alive(pid) and not _zombie(pid):
        return 1, f"could not stop pid {pid}"
    return 0, f"stopped (pid {pid})"


def _zombie(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].startswith("Z")
    except (OSError, IndexError):
        return False


def cmd_status(root: Path, a: argparse.Namespace) -> int:
    if not run_dir(root).is_dir():
        rec = None
    else:
        with Lock(root):
            rec = live_record(root)
    out = {"running": bool(rec), **({k: rec.get(k) for k in ("url", "pid", "port", "started_at", "host", "exposed", "access_urls")}
                                    if rec else {})}
    if a.json:
        print(json.dumps(out))
    elif rec:
        print(f"running: {rec['url']} (pid {rec['pid']}, since {rec['started_at']})")
        print_exposure(rec)
    else:
        print("not running")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev_board.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: walk up from cwd to find .dev/state.json, else cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("start", "serve"):
        s = sub.add_parser(name)
        s.add_argument("--port", type=int, default=DEFAULT_PORT)
        s.add_argument("--idle-min", type=int, default=120, help="stop after N minutes with no open tab (0 = never)")
        s.add_argument("--host", type=parse_bind, default=None,
                       help="IP address to listen on (default 127.0.0.1). 0.0.0.0 or :: shares the board with the "
                            "network: every request then needs the access key printed at start")
        if name == "start":
            g = s.add_mutually_exclusive_group()
            g.add_argument("--no-open", action="store_true", help="do not open a browser tab")
            g.add_argument("--open", action="store_true", help="open a tab even if the board was already running")
    sub.add_parser("stop")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    root = ds.find_root(a.root)
    return {"start": cmd_start, "serve": cmd_serve, "stop": cmd_stop, "status": cmd_status}[a.cmd](root, a)


if __name__ == "__main__":
    sys.exit(main())
