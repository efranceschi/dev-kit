#!/usr/bin/env python3
"""dev_spog.py - one local page for every dev-kit project on this machine (single pane of glass), on 127.0.0.1.

Standard library only. Run with: python3 -I dev_spog.py <subcommand>

Subcommands
  start     start the page (or reuse the one already running) and open the default browser
            --port N (preferred port, default 8790; falls back to a free one) · --no-open · --open (force a tab even
            when it was already running) · --idle-min N (auto-stop after N idle minutes, default 240; 0 = never)
            · --register DIR (add that project to the list first, when it is a dev-kit project)
  stop      stop it (token-authenticated shutdown, then SIGTERM, then SIGKILL)
  status    whether it is running, its URL and PID (--json)
  list      the registered projects and how each one stands (--json): what the page shows, without a server
  register  add a project to the list: --root DIR (default: walk up from cwd to find .dev/state.json)
  forget    remove projects from the list: PATH ... or --missing (every project whose folder or .dev/state.json is gone)
  serve     internal: the server process itself (spawned by start)

The list of projects is ~/.dev-kit/projects.json (DEV_KIT_HOME moves ~/.dev-kit, for tests). A project joins it
when /dev-kit:board starts its board (dev_board.py start) or when /dev-kit:spog runs inside it; it leaves only with
`forget`. A registered project whose folder was deleted or moved, or that no longer has .dev/state.json, stays on the
page, greyed, with the command that forgets it.

For each project the page shows its state - waiting for you, running, or idle, and since when - and what needs you:
the same items as the board's Needs you, plus a Claude Code session of the project waiting on a permission prompt or a
question (`.dev/run/sessions/<session>.json`, written by the optional hooks in dev_agent_hook.py; without the hooks
that part is just missing). "Running" is a skill run with no end yet, an agent at work, a headless round or a session
working on a turn.

Read-only: it reads each project's .dev/ and writes only ~/.dev-kit/ (projects.json, projects.lock, and run/spog.json,
spog.lock, spog.log). It never changes a project and never starts Claude Code. Its only POST is /api/shutdown, with the
per-run token (X-Board-Token). It binds 127.0.0.1 only and answers Host headers that are localhost or an IP literal
(DNS rebinding protection), like the board.

Exit codes: 0 ok · 1 error
"""
from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # -I drops the script dir
import dev_board as db  # noqa: E402
import dev_state as ds  # noqa: E402

APP = "dev-kit-spog"
DEFAULT_PORT = 8790
STATIC = {"/": "spog.html", "/index.html": "spog.html", "/assets/board.css": "board.css", "/assets/spog.css": "spog.css",
          "/assets/spog.js": "spog.js", "/assets/favicon.svg": "favicon.svg", "/assets/favicon-alert.svg": "favicon-alert.svg"}
CACHE_S = 30        # a project's view is rebuilt when its files change, or at least this often (runs go stale by time)
SESSION_STALE_S = 12 * 3600  # a session with no hook event for this long is treated as closed
ITEMS_SHOWN = 3     # rows per kind of need on a project card (the rest are counted)
# the order that costs most to leave waiting, as in the board's Needs you; a live session waiting comes first
NEED_KINDS = ("session_permission", "session_question", "prod_health", "release_approval", "qa_exhausted", "checkpoint",
              "hotfix", "blocked", "question", "issue_queue", "debt", "lesson", "denied")
CODE_ID = db.CODE_ID


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- the list of projects

def home() -> Path:
    return Path(os.environ.get("DEV_KIT_HOME") or Path.home() / ".dev-kit").expanduser()


def registry_path() -> Path:
    return home() / "projects.json"


class _FileLock:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a+")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def read_registry() -> dict:
    """{path: {name, added_at, seen_at}}; an unreadable file reads as empty (the next register rewrites it)."""
    try:
        d = json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    p = d.get("projects") if isinstance(d, dict) else None
    return {k: v for k, v in p.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(p, dict) else {}


def _write_registry(projects: dict) -> None:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "projects": projects}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def register(root: Path) -> bool:
    """Add (or refresh) a dev-kit project in the list. False when root is not a dev-kit project."""
    root = Path(root).resolve()
    if not (root / ".dev" / "state.json").is_file():
        return False
    try:
        name = json.loads((root / ".dev" / "state.json").read_text(encoding="utf-8")).get("project") or root.name
    except (OSError, ValueError, AttributeError):
        name = root.name
    with _FileLock(home() / "projects.lock"):
        projects = read_registry()
        cur = projects.get(str(root)) or {}
        projects[str(root)] = {"name": str(name)[:120], "added_at": cur.get("added_at") or now_iso(), "seen_at": now_iso()}
        _write_registry(projects)
    return True


def register_quietly(root: Path) -> None:
    """For the board: registering must never stop it from starting."""
    try:
        register(root)
    except Exception:  # noqa: BLE001
        pass


def forget(paths: list[str], missing: bool = False) -> list[str]:
    """Remove the given paths (as listed, or resolved), or with missing every project that is gone. Returns them."""
    with _FileLock(home() / "projects.lock"):
        projects = read_registry()
        drop = []
        for k in list(projects):
            gone = not (Path(k) / ".dev" / "state.json").is_file()
            if (missing and gone) or k in paths or any(str(Path(p).expanduser().resolve()) == k for p in paths):
                drop.append(k)
                projects.pop(k)
        if drop:
            _write_registry(projects)
    return drop


# --------------------------------------------------------------------------- the view of one project

def _ts(v: object) -> float:
    return db._ts(v)


def sessions(root: Path, now: float | None = None) -> list[dict]:
    """The project's Claude Code sessions as the hooks last saw them (working, waiting, idle), newest first; closed
    and stale ones are left out."""
    now = now or time.time()
    out = []
    d = root / ".dev" / "run" / "sessions"
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(s, dict) or s.get("state") not in ("working", "waiting", "idle"):
            continue
        if now - _ts(s.get("at")) > SESSION_STALE_S:
            continue
        out.append({k: s.get(k) for k in ("session", "state", "why", "since", "at", "tool")})
    return sorted(out, key=lambda s: _ts(s.get("at")), reverse=True)


def _item(id_: object = None, text: object = None, since: object = None) -> dict:
    return {k: v for k, v in (("id", id_), ("text", str(text)[:160] if text else None), ("since", since)) if v}


def needs(st: dict, sess: list[dict]) -> list[dict]:
    """What needs the user in one project: the board's Needs you (same rules as renderImpediments in board.js), plus
    sessions waiting on a permission or a question. [{kind, n, items: [{id, text, since}]}] in NEED_KINDS order."""
    tasks = st.get("tasks") or {}
    groups: dict[str, list[dict]] = {k: [] for k in NEED_KINDS}
    for s in sess:
        if s["state"] == "waiting":
            groups["session_permission" if s.get("why") == "permission" else "session_question"].append(
                _item(None, s.get("tool"), s.get("since")))
    b = st.get("backlog") or {}
    for n in b.get("needs") or []:
        k = n.get("kind")
        if k == "prod_health":
            groups["prod_health"].append(_item(n.get("issue"), n.get("detail") or n.get("target"), n.get("since")))
        elif k == "checkpoint":
            groups["checkpoint"].append(_item(n.get("target"), n.get("title"), n.get("since")))
        elif k == "debt_over_cap":
            groups["debt"].append(_item(None, f"{n.get('total')} / {n.get('cap_total')}"))
        elif k == "lesson":
            groups["lesson"].append(_item(n.get("agent") or n.get("id"), n.get("text") or n.get("lesson")))
        else:
            groups["issue_queue"].append(_item(n.get("issue") or n.get("milestone"), None))
    for r in (st.get("cycle") or {}).get("releases") or []:
        if r.get("status") == "awaiting_approval":
            groups["release_approval"].append(_item(r.get("id"), r.get("title"), r.get("submitted_at")))
    is_fix = lambda t: t.get("type") == "fix" and bool(t.get("source")) and not str(t.get("source")).startswith("release:")  # noqa: E731
    lc = st.get("lifecycle") or {}
    for m in st.get("milestones") or []:
        if m.get("gate") in ("passed", "skipped"):
            continue
        ts = [tasks[t] for t in m.get("tasks") or [] if t in tasks]
        fixes = [t for t in ts if is_fix(t)]
        qa = m.get("qa") or {}
        running = bool(qa.get("round")) or any(a.get("node") == f"GATE:{m['id']}" for a in (st.get("agents") or {}).get("active") or [])
        active = [t for t in fixes if t.get("status") in ("todo", "in_progress")]
        cap = m.get("max_fix_rounds") or lc.get("max_fix_rounds") or 3
        runs = qa.get("runs", m.get("qa_runs") or 0)
        if not running and not active and (runs > cap or any(t.get("status") == "blocked" for t in fixes)):
            groups["qa_exhausted"].append(_item(m["id"], m.get("title")))
    hot = [t for t in b.get("hotfix_open") or [] if (tasks.get(t) or {}).get("status") not in ("done", "dropped")]
    groups["hotfix"] = [_item(t, (tasks.get(t) or {}).get("title")) for t in hot]
    for tid, t in tasks.items():
        held_by_qa = is_fix(t) and "rounds_exhausted" in str(t.get("blocked_reason") or "")
        if t.get("status") == "blocked" and not held_by_qa and t.get("lane") != "hotfix":
            groups["blocked"].append(_item(tid, t.get("blocked_reason") or t.get("title")))
    groups["question"] = [_item(q.get("id"), q.get("question"), q.get("date")) for q in st.get("questions") or []]
    groups["denied"] = [_item(d.get("agent"), f"{d.get('tool')}: {d.get('target')}") for d in st.get("denied") or []]
    out = []
    for k in NEED_KINDS:
        items = groups[k]
        n = st.get("denied_total") or len(items) if k == "denied" and items else len(items)
        if n:
            out.append({"kind": k, "n": n, "items": items[:ITEMS_SHOWN]})
    return out


def _last_activity(root: Path) -> str | None:
    """The newest change among the files the board watches and the sessions: when the project last moved."""
    best = 0.0
    dev = root / ".dev"
    for name in db.WATCHED:
        try:
            best = max(best, (dev / name).stat().st_mtime)
        except OSError:
            pass
    d = dev / "run" / "sessions"
    for f in d.glob("*.json") if d.is_dir() else []:
        try:
            best = max(best, f.stat().st_mtime)
        except OSError:
            pass
    return datetime.fromtimestamp(best, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if best else None


def project_view(path: str, entry: dict | None = None) -> dict:
    """How one registered project stands, for its card."""
    entry = entry or {}
    root = Path(path)
    base = {"path": path, "name": entry.get("name") or root.name}
    if not root.is_dir():
        return {**base, "status": "missing"}
    if not (root / ".dev" / "state.json").is_file():
        return {**base, "status": "not_project"}
    rec = db.read_record(root)
    board = None
    if rec and ds._alive(rec.get("pid")):
        board = {"url": None if rec.get("exposed") else rec.get("url"), "exposed": bool(rec.get("exposed"))}
    st = db.build_state(root, None)
    if not st.get("ok"):
        return {**base, "status": "unreadable", "error": st.get("error"), "board": board}
    sess = sessions(root)
    ag = st.get("agents") or {}
    runs = [r for r in ag.get("runs") or [] if r.get("skill") not in ("board", "spog", "status", "help", "debug")]
    round_ = db.round_view(root)
    starts = [r.get("started_at") for r in runs] + [a.get("started_at") for a in ag.get("active") or []]
    starts += [s.get("since") for s in sess if s["state"] == "working"]
    if round_:
        starts.append(round_.get("since"))
    running = bool(runs or ag.get("active") or round_ or any(s["state"] == "working" for s in sess))
    need = needs(st, sess)
    total = sum(g["n"] for g in need)
    last = _last_activity(root)
    if total:
        status = "waiting"
        waits = [i["since"] for g in need for i in g["items"] if len(str(i.get("since") or "")) > 10]  # a bare date says too little
        since = min(waits, key=_ts) if waits else last
    elif running:
        status, since = "running", min((s for s in starts if s), key=_ts, default=last)
    else:
        status, since = "idle", last
    cur = st.get("current_milestone")
    ms = next((m for m in st.get("milestones") or [] if m.get("id") == cur), None)
    mt = [st["tasks"][t] for t in (ms or {}).get("tasks") or [] if t in st.get("tasks", {})]
    return {**base, "name": st.get("project") or base["name"], "status": status, "since": since, "running": running,
            "needs": need, "needs_total": total, "phase": st.get("phase"), "step": st.get("step"),
            "milestone": {"id": cur, "title": ms.get("title"), "done": sum(1 for t in mt if t.get("status") == "done"),
                          "total": len(mt)} if ms else None,
            "autopilot": any(r.get("skill") == "autopilot" for r in runs),
            "runs": [{"skill": r.get("skill"), "scope": r.get("scope")} for r in runs][:4],
            "agents": len(ag.get("active") or []), "round": {k: round_.get(k) for k in ("skill", "scope")} if round_ else None,
            "sessions": {k: sum(1 for s in sess if s["state"] == k) for k in ("working", "waiting", "idle")},
            "next": (st.get("next") or {}).get("command"), "language": st.get("language"),
            "last_activity": last, "board": board, "kit": st.get("kit")}


class Views:
    """Project views, rebuilt only when the project's files change or every CACHE_S seconds."""

    def __init__(self):
        self.cache: dict[str, tuple[tuple, float, dict]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _sig(path: str) -> tuple:
        root = Path(path)
        d = root / ".dev" / "run" / "sessions"
        extra = []
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            try:
                st = f.stat()
                extra.append((f.name, st.st_mtime_ns, st.st_size))
            except OSError:
                pass
        for f in (root / ".dev" / "run" / "board.json", root / ".dev" / "run" / "round.json"):
            try:
                st = f.stat()
                extra.append((f.name, st.st_mtime_ns))
            except OSError:
                extra.append((f.name, 0))
        return (root.is_dir(), db.signature(root) if root.is_dir() else (), tuple(extra))

    def get(self, path: str, entry: dict) -> dict:
        sig = self._sig(path)
        with self.lock:
            hit = self.cache.get(path)
        if hit and hit[0] == sig and time.monotonic() - hit[1] < CACHE_S:
            return hit[2]
        try:
            v = project_view(path, entry)
        except Exception as e:  # noqa: BLE001 - one broken project never hides the others
            v = {"path": path, "name": entry.get("name") or Path(path).name, "status": "unreadable", "error": type(e).__name__}
        with self.lock:
            self.cache[path] = (sig, time.monotonic(), v)
        return v

    def all(self) -> list[dict]:
        reg = read_registry()
        with self.lock:
            for k in [k for k in self.cache if k not in reg]:
                self.cache.pop(k)
        return sort_views([self.get(p, e) for p, e in reg.items()])


STATUS_ORDER = {"waiting": 0, "running": 1, "idle": 2, "unreadable": 3, "not_project": 4, "missing": 5}


def sort_views(views: list[dict]) -> list[dict]:
    """Waiting first (the most items first), then running, then idle by last activity, then the ones that are gone."""
    return sorted(views, key=lambda v: (STATUS_ORDER.get(v.get("status"), 9), -(v.get("needs_total") or 0),
                                        -_ts(v.get("last_activity") or v.get("since")), str(v.get("name")).lower()))


def overview(views: Views) -> dict:
    projects = views.all()
    return {"ok": True, "projects": projects, "kit": db.KIT_VERSION, "generated_at": now_iso(),
            "counts": {k: sum(1 for p in projects if p.get("status") == k) for k in STATUS_ORDER},
            "needs_total": sum(p.get("needs_total") or 0 for p in projects), "home": str(home())}


# --------------------------------------------------------------------------- server

def run_dir() -> Path:
    return home() / "run"


def record_path() -> Path:
    return run_dir() / "spog.json"


def read_record() -> dict | None:
    try:
        rec = json.loads(record_path().read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) and isinstance(rec.get("pid"), int) else None
    except (OSError, ValueError):
        return None


def write_record(rec: dict) -> None:
    run_dir().mkdir(parents=True, exist_ok=True)
    tmp = record_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)  # holds the shutdown token
    os.replace(tmp, record_path())


def remove_record(pid: int | None = None) -> None:
    rec = read_record()
    if pid is not None and rec and rec.get("pid") != pid:
        return
    record_path().unlink(missing_ok=True)


def is_spog_process(pid: int) -> bool:
    if not ds._alive(pid):
        return False
    try:
        args = [c.decode("utf-8", "replace") for c in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if c]
    except OSError:
        return True  # no /proc (macOS): trust the ping check
    return any(a.endswith("dev_spog.py") for a in args) and "serve" in args


def live_record() -> dict | None:
    rec = read_record()
    if not rec:
        return None
    p = db.ping(int(rec.get("port", 0)))
    if is_spog_process(rec["pid"]) and p and p.get("app") == APP and p.get("fingerprint") == db.fingerprint(str(rec.get("token", ""))):
        return rec
    remove_record()
    return None


def page_assets() -> dict[str, Path]:
    return {k: db.ASSETS / v for k, v in STATIC.items()}


class Spog(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, token: str, idle_s: int):
        super().__init__(addr, Handler)
        self.token, self.idle_s = token, idle_s
        self.views = Views()
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


class Handler(db.Handler):
    server: Spog  # type: ignore[assignment]
    server_version = APP

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        if db.allowed_host(host):
            return True
        print(f"refused Host header {host[:80]!r} (only localhost or an IP address)", file=sys.stderr, flush=True)
        return False

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() == f"http://{self.headers.get('Host', '')}".lower()

    def do_GET(self):
        self.server.touch()
        if not self._host_ok():
            return self._json(403, {"ok": False, "error": "forbidden host"})
        path = self.path.split("?", 1)[0]
        if path == "/api/ping":
            return self._json(200, {"ok": True, "app": APP, "pid": os.getpid(), "fingerprint": db.fingerprint(self.server.token)})
        if path == "/api/projects":
            return self._json(200, overview(self.server.views))
        if path == "/api/events":
            return self._events()
        f = page_assets().get(path)
        if not f:
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            body = f.read_bytes()
        except OSError:
            return self._json(500, {"ok": False, "error": f"missing asset {f.name}"})
        if f.name == "spog.html":
            body = body.replace(b"__BOARD_TOKEN__", self.server.token.encode()).replace(b"__BOARD_I18N__", db.i18n_payload())
        ctype = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}.get(f.suffix, "application/octet-stream")
        self._send(200, body, ctype + "; charset=utf-8")

    do_HEAD = do_GET

    def _events(self):
        """Server-sent "change" whenever any registered project's files change, or the list itself does."""
        srv = self.server
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with srv.lock:
            srv.clients += 1

        def sig() -> tuple:
            reg = read_registry()
            return tuple(sorted((p, Views._sig(p)) for p in reg))
        try:
            last, beat, tick = sig(), time.monotonic(), time.monotonic()
            self.wfile.write(b"retry: 2000\nevent: hello\ndata: {}\n\n")
            self.wfile.flush()
            while not srv.stopping.wait(2.0):
                cur = sig()
                # a run or a session can go stale with no file changing: ask for a fresh view now and then
                if cur != last or time.monotonic() - tick > CACHE_S:
                    last, tick = cur, time.monotonic()
                    self.wfile.write(b"event: change\ndata: {}\n\n")
                    self.wfile.flush()
                elif time.monotonic() - beat > 15:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    beat = time.monotonic()
                srv.touch()
            self.wfile.write(b"event: bye\ndata: {}\n\n")
            self.wfile.flush()
        except OSError:
            pass
        finally:
            with srv.lock:
                srv.clients -= 1


def cmd_serve(a: argparse.Namespace) -> int:
    token = os.environ.pop("DEV_SPOG_TOKEN", "") or secrets.token_urlsafe(24)
    try:
        srv = Spog(("127.0.0.1", a.port), token, a.idle_min * 60)
    except OSError:
        srv = Spog(("127.0.0.1", 0), token, a.idle_min * 60)
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    write_record({"pid": os.getpid(), "port": port, "token": token, "url": url, "code": CODE_ID, "started_at": now_iso()})

    def on_signal(signum, frame):
        srv.stop()
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, on_signal)

    def watchdog():
        while not srv.stopping.wait(30):
            if srv.idle_s > 0 and srv.clients == 0 and time.monotonic() - srv.last_activity > srv.idle_s:
                print(f"idle for {srv.idle_s // 60} min: stopping", flush=True)
                srv.stop()
            elif (read_record() or {}).get("pid") != os.getpid():
                srv.stop()
            elif db.code_id() != CODE_ID:
                print("the kit was updated on disk: stopping; /dev-kit:spog starts the new version", flush=True)
                srv.stop()
    threading.Thread(target=watchdog, daemon=True).start()
    print(f"serving {url} (pid {os.getpid()})", flush=True)
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        srv.server_close()
        remove_record(os.getpid())
        print("stopped", flush=True)
    return 0


def _lock() -> _FileLock:
    return _FileLock(run_dir() / "spog.lock")


def cmd_start(a: argparse.Namespace) -> int:
    if a.register:
        root = ds.find_root(a.register)
        print(f"registered {root}" if register(root) else f"not a dev-kit project (no .dev/state.json): {root}")
    with _lock():
        rec = live_record()
        restarted = False
        if rec and rec.get("code") != CODE_ID:
            code, msg = stop_locked()
            print(f"the kit was updated since the running page started; {msg}")
            if code:
                return code
            rec, restarted = None, True
        if rec:
            opened = db.open_browser(rec["url"]) if a.open else False
            print(f"already running: {rec['url']} (pid {rec['pid']})" +
                  (" · opened a new tab" if opened else " · no new tab opened (use --open to force one)"))
            return 0
        run_dir().mkdir(parents=True, exist_ok=True)
        log = open(run_dir() / "spog.log", "a", encoding="utf-8")
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "serve", "--port", str(a.port), "--idle-min", str(a.idle_min)]
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(home()),
                                start_new_session=True, close_fds=True)
        log.close()
        deadline, rec = time.monotonic() + 8, None
        while time.monotonic() < deadline and proc.poll() is None:
            r = read_record()
            if r and r.get("pid") == proc.pid and db.ping(int(r["port"]), 0.5):
                rec = r
                break
            time.sleep(0.1)
        if not rec:
            if proc.poll() is None:
                proc.terminate()
            print(f"the page did not start; see {run_dir() / 'spog.log'}", file=sys.stderr)
            return 1
    opened = False if a.no_open else db.open_browser(rec["url"])
    n = len(read_registry())
    print(f"{'restarted' if restarted else 'started'}: {rec['url']} (pid {rec['pid']})" +
          (" · opened in the default browser" if opened else " · open the URL in your browser") + f" · {n} project(s)")
    return 0


def stop_locked() -> tuple[int, str]:
    rec = read_record()
    if not rec:
        return 0, "not running"
    pid = rec["pid"]
    if not is_spog_process(pid):
        remove_record()
        return 0, f"not running (removed a stale record for pid {pid})"
    try:
        c = http.client.HTTPConnection("127.0.0.1", int(rec["port"]), timeout=2)
        c.request("POST", "/api/shutdown", body=b"", headers={"Host": f"127.0.0.1:{rec['port']}", "X-Board-Token": str(rec.get("token", ""))})
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
        while time.monotonic() < end and ds._alive(pid) and not db._zombie(pid):
            time.sleep(0.1)
        if not ds._alive(pid) or db._zombie(pid):
            break
    remove_record()
    if ds._alive(pid) and not db._zombie(pid):
        return 1, f"could not stop pid {pid}"
    return 0, f"stopped (pid {pid})"


def cmd_stop(a: argparse.Namespace) -> int:
    if not run_dir().is_dir():
        print("not running")
        return 0
    with _lock():
        code, msg = stop_locked()
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


def cmd_status(a: argparse.Namespace) -> int:
    rec = None
    if run_dir().is_dir():
        with _lock():
            rec = live_record()
    out = {"running": bool(rec), "projects": len(read_registry()),
           **({k: rec.get(k) for k in ("url", "pid", "port", "started_at")} if rec else {})}
    if a.json:
        print(json.dumps(out))
    else:
        print(f"running: {rec['url']} (pid {rec['pid']}, since {rec['started_at']}) · {out['projects']} project(s)" if rec
              else f"not running · {out['projects']} project(s)")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    ov = overview(Views())
    if a.json:
        print(json.dumps(ov, ensure_ascii=False))
        return 0
    if not ov["projects"]:
        print(f"no projects yet: a project joins when /dev-kit:board or /dev-kit:spog runs in it ({registry_path()})")
    for p in ov["projects"]:
        extra = f" · {p['needs_total']} need you" if p.get("needs_total") else ""
        print(f"{p['status']:<12} {p['name']}{extra} · since {p.get('since') or '-'} · {p['path']}")
    return 0


def cmd_register(a: argparse.Namespace) -> int:
    root = ds.find_root(a.root)
    if register(root):
        print(f"registered {root}")
        return 0
    print(f"not a dev-kit project (no .dev/state.json): {root}", file=sys.stderr)
    return 1


def cmd_forget(a: argparse.Namespace) -> int:
    if not a.paths and not a.missing:
        print("name the project paths to forget, or --missing", file=sys.stderr)
        return 1
    gone = forget(a.paths, a.missing)
    for p in gone:
        print(f"forgot {p}")
    if not gone:
        print("nothing to forget")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev_spog.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("start", "serve"):
        s = sub.add_parser(name)
        s.add_argument("--port", type=int, default=DEFAULT_PORT)
        s.add_argument("--idle-min", type=int, default=240, help="stop after N minutes with no open tab (0 = never)")
        if name == "start":
            s.add_argument("--register", metavar="DIR", help="add this project to the list first (when it is a dev-kit project)")
            g = s.add_mutually_exclusive_group()
            g.add_argument("--no-open", action="store_true", help="do not open a browser tab")
            g.add_argument("--open", action="store_true", help="open a tab even if it was already running")
    sub.add_parser("stop")
    for name in ("status", "list"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    sub.add_parser("register").add_argument("--root", help="project root (default: walk up from cwd)")
    s = sub.add_parser("forget")
    s.add_argument("paths", nargs="*", metavar="PATH")
    s.add_argument("--missing", action="store_true", help="every project whose folder or .dev/state.json is gone")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return {"start": cmd_start, "serve": cmd_serve, "stop": cmd_stop, "status": cmd_status, "list": cmd_list,
            "register": cmd_register, "forget": cmd_forget}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
