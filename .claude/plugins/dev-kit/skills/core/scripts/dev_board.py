#!/usr/bin/env python3
"""dev_board.py - local, read-only Scrum board for a dev-kit project, served on 127.0.0.1.

Standard library only. Run with: python3 -I dev_board.py [--root DIR] <subcommand>

Subcommands
  start   start the board (or reuse the one already running) and open the default browser
          --port N (preferred port, default 8765; falls back to a free one) · --no-open · --open (force a tab
          even when the board was already running) · --idle-min N (auto-stop after N idle minutes, default 120)
  stop    stop the board of this project (token-authenticated shutdown, then SIGTERM, then SIGKILL)
  status  print whether the board is running, its URL and PID (--json)
  serve   internal: the server process itself (spawned by start)

One board per project: .dev/run/board.json holds {pid, port, token, url, root, started_at}; a lock file
(.dev/run/board.lock) serialises concurrent starts. A recorded PID only counts as the board when the process
is alive, its command line is this script serving this root, and /api/ping on the port answers with the
same token fingerprint. Anything else is a stale record and is removed.

The server never writes to .dev/ except its own files in .dev/run/. It binds 127.0.0.1 only, rejects
foreign Host/Origin headers and needs the per-run token to shut down.

Exit codes: 0 ok · 1 error · 2 no dev-kit state in the project
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import json
import mimetypes
import os
import secrets
import signal
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
WATCHED = ("state.json", "log.md", "open-questions.md", "costs/summary.json", "plan.md")
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


def ping(port: int, timeout: float = 1.0) -> dict | None:
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        c.request("GET", "/api/ping", headers={"Host": f"127.0.0.1:{port}"})
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
          and (p := ping(int(rec.get("port", 0)))) is not None
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
        "board": {k: board.get(k) for k in ("pid", "port", "url", "started_at")} if board else None,
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

LOOPBACK_NAMES = {"127.0.0.1", "localhost", "[::1]"}


def loopback_host(host: str) -> bool:
    """True for 'localhost', '127.0.0.1' or '[::1]', with or without a numeric port."""
    host = host.strip().lower()
    if host.startswith("["):
        name, _, rest = host.partition("]")
        name, port = name + "]", rest[1:] if rest.startswith(":") else (None if not rest else "x")
    else:
        name, _, port = host.partition(":")
        port = port if ":" in host else None
    return name in LOOPBACK_NAMES and (port is None or (port.isdigit() and 0 < int(port) < 65536))


class Board(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, root: Path, token: str, idle_s: int):
        super().__init__(addr, Handler)
        self.root, self.token, self.idle_s = root, token, idle_s
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


class Handler(BaseHTTPRequestHandler):
    server: Board
    server_version = "dev-kit-board"
    sys_version = ""

    def log_message(self, fmt, *args):  # quiet: errors only
        pass

    def _host_ok(self) -> bool:
        """Loopback names on any port: SSH tunnels and editor port forwarding may use another local port.
        Any other name (e.g. a DNS-rebinding domain) is refused."""
        host = self.headers.get("Host", "")
        if loopback_host(host):
            return True
        print(f"refused Host header {host[:80]!r} (only localhost / 127.0.0.1 / [::1] are accepted)", file=sys.stderr, flush=True)
        return False

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
                                    "hint": "open the board as http://localhost:<port>/ or http://127.0.0.1:<port>/ "
                                            "(through an SSH tunnel on remote machines)"})
        path = self.path.split("?", 1)[0]
        if path == "/api/ping":
            return self._json(200, {"ok": True, "app": "dev-kit-board", "pid": os.getpid(),
                                    "fingerprint": fingerprint(self.server.token)})
        if path == "/api/state":
            return self._json(200, build_state(self.server.root, self.server.record))
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


def bind(port: int, root: Path, token: str, idle_s: int) -> Board:
    try:
        return Board(("127.0.0.1", port), root, token, idle_s)
    except OSError:
        return Board(("127.0.0.1", 0), root, token, idle_s)


def cmd_serve(root: Path, a: argparse.Namespace) -> int:
    token = os.environ.pop("DEV_BOARD_TOKEN", "") or secrets.token_urlsafe(24)
    srv = bind(a.port, root, token, a.idle_min * 60)
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    srv.record = {"pid": os.getpid(), "port": port, "token": token, "url": url, "root": str(root),
                  "code": CODE_ID, "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
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
    print(f"serving {url} for {root} (pid {os.getpid()})", flush=True)
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
        if rec and rec.get("code") != CODE_ID:
            code, msg = stop_locked(root)  # started by an older copy of the kit: replace it
            print(f"the running board was started by another version of the kit; {msg}")
            if code:
                return code
            rec, restarted = None, True
        if rec:
            opened = open_browser(rec["url"]) if a.open else False
            print(f"already running: {rec['url']} (pid {rec['pid']})" +
                  (" · opened a new tab" if opened else " · no new tab opened (use --open to force one)"))
            return 0
        log = open(run_dir(root) / "board.log", "a", encoding="utf-8")
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--root", str(root), "serve",
               "--port", str(a.port), "--idle-min", str(a.idle_min)]
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(root),
                                start_new_session=True, close_fds=True)
        log.close()
        deadline = time.monotonic() + 8
        rec = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            r = read_record(root)
            if r and r.get("pid") == proc.pid and ping(int(r["port"]), 0.5):
                rec = r
                break
            time.sleep(0.1)
        if not rec:
            if proc.poll() is None:
                proc.terminate()
            print(f"the board did not start; see {run_dir(root) / 'board.log'}", file=sys.stderr)
            return 1
    opened = False if a.no_open else open_browser(rec["url"])
    print(f"{'restarted' if restarted else 'started'}: {rec['url']} (pid {rec['pid']})" +
          (" · opened in the default browser" if opened else " · open the URL in your browser"))
    return 0


def cmd_stop(root: Path, a: argparse.Namespace) -> int:
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
        c = http.client.HTTPConnection("127.0.0.1", int(rec["port"]), timeout=2)
        c.request("POST", "/api/shutdown", body=b"",
                  headers={"Host": f"127.0.0.1:{rec['port']}", "X-Board-Token": str(rec.get("token", ""))})
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
    with Lock(root):
        rec = live_record(root)
    out = {"running": bool(rec), **({k: rec[k] for k in ("url", "pid", "port", "started_at")} if rec else {})}
    if a.json:
        print(json.dumps(out))
    elif rec:
        print(f"running: {rec['url']} (pid {rec['pid']}, since {rec['started_at']})")
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
