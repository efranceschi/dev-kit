#!/usr/bin/env python3
"""dev_board.py - local live board for a dev-kit project, served on 127.0.0.1.

Standard library only. Run with: python3 -I dev_board.py [--root DIR] <subcommand>

Subcommands
  start   start the board (or reuse the one already running) and open the default browser
          --port N (preferred port, default 8765; falls back to a free one) · --no-open · --open (force a tab
          even when the board was already running) · --idle-min N (auto-stop after N idle minutes, default 120)
          · --host IP (listen address, default 127.0.0.1; 0.0.0.0 or :: shares it with the network, see below;
          a running board on another address is restarted) · --trusted-host NAME (a host name the board also answers to, for a reverse proxy;
          repeatable, remembered for the project in .dev/run/board-config.json; "none" forgets them)
  stop    stop the board of this project (token-authenticated shutdown, then SIGTERM, then SIGKILL)
  status  print whether the board is running, its URL and PID (--json)
  pane    what runs now, for the terminal status pane (hooks/status-pane.tsx): the board, the Autopilot (running
          in a session, its headless round, its tasks and last action) and the agents at work and what they work on
          (--json; read-only, no server needed)
  serve   internal: the server process itself (spawned by start)

One board per project: .dev/run/board.json holds {pid, port, token, url, root, started_at}; a lock file
(.dev/run/board.lock) serialises concurrent starts. A recorded PID only counts as the board when the process
is alive, its command line is this script serving this root, and /api/ping on the port answers with the
same token fingerprint. Anything else is a stale record and is removed.

The board is read-only: it reads .dev/ and writes only its own files in .dev/run/ (board.json, board.lock,
board.log, board-config.json). It never changes the project and never starts Claude Code; every decision and every
run happens in a Claude Code session. Its only POST is /api/shutdown, which needs the per-run token
(X-Board-Token), an allowed Host and, when sent, the page's own Origin.
By default it binds 127.0.0.1 and answers Host headers that are localhost or an IP literal (tunnels, forwards),
refusing host names (DNS rebinding). With --host on a non-loopback address the board is "exposed": every
request except /api/ping needs the access key (the per-run token) from ?key= - traded for an HttpOnly,
SameSite=Strict cookie - so host names are accepted there. It is plain HTTP: for trusted networks only.
Whoever can open a shared board sees the project and can stop the board. Behind a reverse proxy
(which brings its own TLS and login), name the proxy's host with --trusted-host: that name alone is accepted in
Host and Origin, so the DNS-rebinding protection stays for every other name.

Exit codes: 0 ok · 1 error · 2 no dev-kit state in the project
"""
from __future__ import annotations

import argparse
import fcntl
import gzip
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
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # -I drops the script dir
import dev_state as ds  # noqa: E402
import dev_diagram as dg  # noqa: E402

ASSETS = SCRIPTS.parent / "shared" / "board"
STATIC = {"/": "index.html", "/index.html": "index.html", "/assets/board.css": "board.css",
          "/assets/board.js": "board.js", "/assets/favicon.svg": "favicon.svg",
          "/assets/favicon-alert.svg": "favicon-alert.svg"}
DEFAULT_PORT = 8765
# Identity of this code: a running server whose record carries another value was started by an older copy
# of the kit (e.g. before a plugin update) and is restarted by `start` instead of reused.
I18N = ASSETS / "i18n"  # the board's text catalogs: en.json is the base, one file per language (pt-BR.json, …)


def i18n_payload() -> bytes:
    """Every catalog, as JSON safe inside the page's <script type="application/json">."""
    cats = {}
    for f in sorted(I18N.glob("*.json")):
        try:
            cats[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return json.dumps(cats, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").encode("utf-8")


def code_id() -> str:
    """Hash of every script and page asset the server runs, so a kit update that touches only a sibling module
    or the front-end is noticed too."""
    h = hashlib.sha256()
    for f in sorted(SCRIPTS.glob("*.py")) + sorted(p for p in ASSETS.rglob("*") if p.is_file()):
        try:
            h.update(f.name.encode() + b"\0" + f.read_bytes())
        except OSError:
            h.update(f.name.encode() + b"\0missing")
    return h.hexdigest()[:12]


CODE_ID = code_id()
WATCHED = ("state.json", "log.md", "open-questions.md", "costs/summary.json", "costs/milestones.json", "plan.md", "run/agents.jsonl",
           "telemetry.jsonl", "run/questions")
KIT_VERSION = ds.tel.kit_version()  # read once: it is the version of the code this server is actually running
AGENT_STALE_S = 3600
LINK_WINDOW_S = 30  # a hook start and a skill spawn of the same agent type this close may be the same agent
AGENTS_DONE = 8  # a start with no stop after this long is treated as lost, not running
AGENT_RECENT = 10
LOG_TAIL = 60
RUN_STALE_S = 4 * 3600  # a skill_start with no skill_end after this long is treated as abandoned
LIVE_TAIL = 40  # telemetry events merged into the activity feed
# Agents the qa skill runs as auditors: an unlinked one of these belongs to the QA gate of the milestone under audit.
QA_AGENTS = {"code-reviewer", "security-auditor", "test-auditor", "spec-tracer", "data-reviewer", "deps-auditor",
             "ops-reviewer", "performance-auditor", "a11y-auditor", "visual-reviewer", "copy-reviewer"}
# What each agent does, in two or three words, for chips and tooltips (agents/*.md has the long description).
AGENT_ROLE = {
    "implementer": "implementing", "architect": "architecture advice", "code-reviewer": "code review",
    "security-auditor": "security audit", "test-auditor": "test audit", "spec-tracer": "spec traceability",
    "data-reviewer": "data review", "deps-auditor": "dependency audit", "ops-reviewer": "operations review",
    "performance-auditor": "performance audit", "a11y-auditor": "accessibility audit", "visual-reviewer": "visual review",
    "copy-reviewer": "copy review", "requirements-reviewer": "requirements review", "design-reviewer": "design review",
    "docs-reviewer": "docs review", "usability-auditor": "usability audit",
}
AGENTS_DIR = SCRIPTS.parents[2] / "agents"


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


ADR_HEAD = re.compile(r"^###\s+(ADR-\d{1,4})\s*[—–-]\s*(.+?)\s*$")
ADR_META = re.compile(r"status:\s*([^·\n]+?)\s*(?:·|$)")
ADR_DATE = re.compile(r"date:\s*(\d{4}-\d{2}-\d{2})")
DECISIONS_SHOWN = 40


def _safe(fn):  # a derived panel never stops the board from rendering
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def decisions_list(text: str) -> list[dict]:
    """ADRs of decisions.md (id, title, status, date), newest first; the template's placeholder entry is skipped."""
    out: list[dict] = []
    for line in text.splitlines():
        m = ADR_HEAD.match(line.strip())
        if m:
            if "{{" in m.group(2):
                continue
            out.append({"id": m.group(1), "title": m.group(2), "status": None, "date": None})
        elif out and out[-1]["status"] is None and line.strip().startswith("- ") and "status:" in line:
            st, dt = ADR_META.search(line), ADR_DATE.search(line)
            out[-1]["status"] = st.group(1).strip() if st else None
            out[-1]["date"] = dt.group(1) if dt else None
    return list(reversed(out))[:DECISIONS_SHOWN]


def production_info(store: "ds.Store") -> dict | None:
    """What production runs (last ok deploy) and how far the checkout is ahead of it; None before any deploy."""
    prod = (store.state.get("deploys") or {}).get("production") or {}
    hist = [d for d in prod.get("history") or [] if isinstance(d, dict)]
    cur = prod.get("current")
    if not cur and not hist:
        return None
    try:
        drift = ds.deploy_drift(store, "production")
    except Exception:  # noqa: BLE001 - git may be missing; the board keeps rendering
        drift = None
    keep = ("sha", "milestone", "migration", "status", "at", "flag")
    return {"current": {k: cur.get(k) for k in keep} if cur else None,
            "last": {k: hist[-1].get(k) for k in keep} if hist else None, "drift": drift}


def prod_health(store: "ds.Store") -> dict | None:
    """The production health check for the Stable phase: its config, the last result and a short history."""
    hc = ds.health_cfg(store)
    if hc is None:
        return None
    log = ds.health_log(store.root)
    checks = [c for c in log.get("checks") or [] if isinstance(c, dict)]
    return {"target": hc.get("command") or hc.get("url"), "interval_min": hc["interval_min"],
            "last": checks[-1] if checks else None, "streak": log.get("streak", 0),
            "history": [{k: c.get(k) for k in ("at", "ok", "detail", "issue")} for c in checks[-12:]]}


def milestone_goals(plan: str) -> dict:
    """First paragraph after each '## Mn — title' heading of plan.md."""
    goals, cur, buf = {}, None, []
    for line in plan.splitlines():
        h = line.strip()
        if h.startswith("## "):
            if cur and buf:
                goals[cur] = " ".join(buf)
            head = h[3:].split()
            cur = head[0] if head and re.fullmatch(r"M\d+(?:\.\d+)?", head[0]) else None
            buf = []
        elif h.startswith("#"):
            if cur and buf:
                goals[cur] = " ".join(buf)
            cur, buf = None, []
        elif cur:
            if h and ds.MS_FIELD_RE.match(h):
                continue  # exit_check / size_reason are fields of the milestone, not its goal
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
            assumed = row.get("assumption used", "")
            out.append({"id": cells[0], "question": row.get("question", ""), "assumption": "" if assumed in ("-", "—") else assumed,
                        "by": row.get("raised by", ""), "date": row.get("date", "")})
    return out


def question_options(root: Path, qs: list[dict]) -> list[dict]:
    """Open questions with the answers they offer (written by add-question --options), shown with the question."""
    for q in qs:
        try:
            side = json.loads((root / ".dev" / "run" / "questions" / f"{q['id']}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            side = {}
        side = side if isinstance(side, dict) else {}
        opts = [str(o) for o in side.get("options") or []][:6]
        q["options"], q["recommended"] = opts, side.get("recommended") if side.get("recommended") in opts else None
    return qs


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
        pass
    try:  # any other ISO form (offset, fraction); naive times are UTC
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
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
    active = [{"agent": r.get("agent") or "agent", "agent_id": aid, "started_at": r.get("ts"), "transcript": r.get("transcript")}
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


DIAGRAM_MAX = 2_000_000      # bytes of the architecture diagram SVG
DOC_MAX = 1_000_000          # bytes of one markdown file shown in the side panel
DOCS_SHOWN = 300             # .md files listed in /api/state
DOCS_SKIP = ("run", "costs")  # folders of .dev that hold no document


def docs_list(root: Path) -> list[str]:
    """The markdown files of .dev/ (paths relative to it), so the page links only documents that exist."""
    dev = (root / ".dev").resolve()
    out: list[str] = []
    for p in sorted(dev.rglob("*.md")):
        rel = p.relative_to(dev)
        if rel.parts and rel.parts[0] in DOCS_SKIP or not p.is_file():
            continue
        try:
            if not p.resolve().is_relative_to(dev):
                continue  # a symlink pointing out of .dev
        except OSError:
            continue
        out.append(rel.as_posix())
        if len(out) >= DOCS_SHOWN:
            break
    return out


def doc_detail(root: Path, rel: str) -> tuple[int, dict]:
    """One markdown file of .dev/ for the side panel: read-only, never outside .dev, only .md, at most DOC_MAX bytes."""
    if not rel or "\x00" in rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return 400, {"ok": False, "error": "bad path"}
    rel = rel.removeprefix(".dev/")
    dev = (root / ".dev").resolve()
    try:
        p = (dev / rel).resolve()
    except (OSError, RuntimeError):
        return 400, {"ok": False, "error": "bad path"}
    if not p.is_relative_to(dev) or p == dev:
        return 400, {"ok": False, "error": "outside .dev"}
    if p.suffix.lower() != ".md":
        return 400, {"ok": False, "error": "only markdown files"}
    if not p.is_file():
        return 404, {"ok": False, "error": "not found"}
    size = p.stat().st_size
    if size > DOC_MAX:
        return 413, {"ok": False, "error": f"too large ({size} bytes)"}
    text = p.read_text(encoding="utf-8", errors="replace")
    return 200, {"ok": True, "path": p.relative_to(dev).as_posix(), "text": text,
                 "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}


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
    why = ds.parse_dep_reasons(t.get("dep_reasons"))
    deps = [{"id": d, "title": tasks.get(d, {}).get("title"), "status": tasks.get(d, {}).get("status", "unknown"),
             "reason": why.get(d)} for d in t.get("deps") or []]
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


def _short(agent: object) -> str:
    return str(agent or "agent").removeprefix("dev-kit:")


def _node_of(scope: object) -> str | None:
    s = str(scope or "")
    if re.fullmatch(r"T-\d{1,5}", s):
        return s
    if re.fullmatch(r"M\d{1,3}(?:\.\d{1,2})?", s):
        return f"GATE:{s}"
    return None


SCOPE_LINE = re.compile(r"(?m)^\s*Scope:\s*(T-\d{1,5}|M\d{1,3}(?:\.\d{1,2})?)\b")
_SCOPE_CACHE: dict[str, str] = {}


def _first_prompt(path: Path) -> str:
    """Text of the first user message of a subagent transcript (its prompt), from the first 64 KB only."""
    with path.open("rb") as f:
        head = f.read(64 * 1024).decode("utf-8", "replace")
    for line in head.splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(r, dict) or r.get("type") != "user":
            continue
        c = (r.get("message") or {}).get("content") if isinstance(r.get("message"), dict) else None
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and isinstance(b.get("text"), str))
        return ""
    return ""


def scope_from_transcript(agent_id: object, transcript: object) -> str | None:
    """Board node named by the `Scope: T-xxx|Mn` line the skill writes in an agent's prompt (conventions.md §13),
    read from the subagent's own transcript: an exact link, no guessing. Found scopes are cached by agent id;
    a transcript not written yet is tried again on the next call. Nothing else from the transcript is kept."""
    aid = str(agent_id or "")
    if aid and aid in _SCOPE_CACHE:
        return _SCOPE_CACHE[aid]
    p = Path(str(transcript or ""))
    if not transcript or p.parent.name != "subagents" or not re.fullmatch(r"agent-[A-Za-z0-9_\-]{1,128}\.jsonl", p.name):
        return None
    try:
        m = SCOPE_LINE.search(_first_prompt(p))
    except OSError:
        return None
    node = _node_of(m.group(1)) if m else None
    if node and aid:
        _SCOPE_CACHE[aid] = node
    return node


def open_spawns(events: list[dict], now: float) -> list[dict]:
    """agent_spawn events logged by the skills that have no matching agent_end yet (and are not stale)."""
    open_: list[dict] = []
    for e in events:
        ev = e.get("event")
        if ev == "agent_spawn":
            open_.append({"agent": _short(e.get("agent")), "scope": e.get("scope"), "slot": e.get("slot"),
                          "session": e.get("session"), "started_at": e.get("ts")})
        elif ev == "skill_end":
            # a skill that ended took its agents with it: qa's auditors (or anything on its scope) are no longer running
            se, sc = e.get("session"), e.get("scope")
            gone = [o for o in open_ if o["session"] == se and ((sc and o["scope"] == sc)
                    or (not sc and e.get("skill") == "qa" and o["agent"] in QA_AGENTS))]
            for o in gone:
                open_.remove(o)
        elif ev == "agent_end":
            ag, sc, sl, se = _short(e.get("agent")), e.get("scope"), e.get("slot"), e.get("session")
            match = [o for o in open_ if o["session"] == se and o["agent"] == ag and o["scope"] == sc and o["slot"] == sl] \
                or [o for o in open_ if o["session"] == se and o["agent"] == ag and o["scope"] == sc] \
                or ([o for o in open_ if o["session"] == se and o["agent"] == ag] if not sc else [])
            if match:
                open_.remove(match[-1])
    return [o for o in open_ if now - _ts(o["started_at"]) < AGENT_STALE_S]


AGENT_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")  # Claude Code's subagent colors


def agent_roles() -> dict:
    """Short role, first sentence of the description and color (the one Claude Code shows) of every kit agent,
    read from agents/*.md."""
    out = {}
    for f in sorted(AGENTS_DIR.glob("*.md")):
        m = re.search(r"^description:\s*(.+)$", f.read_text(encoding="utf-8"), re.M)
        about = (m.group(1).split(". ")[0].rstrip(".") if m else "")[:160]
        c = re.search(r"^color:\s*([a-z]+)\s*$", f.read_text(encoding="utf-8"), re.M)
        out[f.stem] = {"role": AGENT_ROLE.get(f.stem) or about[:40], "about": about,
                       "color": c.group(1) if c and c.group(1) in AGENT_COLORS else None}
    return out


AGENT_ROLES = agent_roles()


def open_runs(events: list[dict], now: float) -> list[dict]:
    """Skill runs logged with skill_start and no matching skill_end yet (same session and skill), newest last."""
    open_: list[dict] = []
    for e in events:
        ev = e.get("event")
        if ev == "skill_start":
            open_.append({"skill": e.get("skill"), "scope": e.get("scope"), "session": e.get("session"), "started_at": e.get("ts"),
                          "mode": e.get("args_kind")})
        elif ev == "skill_end":
            match = [o for o in open_ if o["session"] == e.get("session") and o["skill"] == e.get("skill")]
            if match:
                open_.remove(match[-1])
    return [o for o in open_ if now - _ts(o["started_at"]) < RUN_STALE_S]


def live_agents(root: Path, qa_default: str | None = None, tasks: dict | None = None) -> dict:
    """Running agents and the board node (task, or QA gate of a milestone) each one works on.

    Skills log agent_spawn/agent_end with a scope (task or milestone) in telemetry; plugin hooks, where the
    environment runs them, log exact start/stop of every agent but without the task. With hooks, the running set
    is the hook set and each agent is linked to a node by the first rule that applies:
      0. id: the `Scope:` line of its own prompt, read from its transcript (exact; the other rules are fallbacks
         for agents spawned without it);
      1. time: exactly one skill spawn of the same type, with a scope, started within LINK_WINDOW_S of it, and vice versa;
      2. type: every open spawn of its type points to the same node;
      3. qa_run: an auditor while qa runs on a milestone belongs to that milestone's QA gate;
      4. batch: the agents of one type still unlinked are as many as the open spawns of that type still free
         (implement --parallel starts N implementers for N tasks at once): paired in start order. Agents of the same
         type started together look the same on the board, so the pairing cannot mislead;
      5. task: implementers with no open spawn carrying a scope (the skill did not log them, or logged no scope)
         are as many as the in-progress tasks with no agent: paired in start order.
    Anything else stays without a node (better none than a wrong one). `tasks` (id -> {status, started_at}) drops
    spawns of tasks already done, dropped or blocked, whose agent_end was never logged.
    Without hooks, the open skill spawns are the running set; implementer spawns logged without scope are paired
    with the in-progress tasks with no agent when the counts match."""
    now = time.time()
    events = _task_events(root)
    spawns = open_spawns(events, now)
    if tasks:
        spawns = [o for o in spawns if not (_node_of(o["scope"]) or "").startswith("T-")
                  or (tasks.get(o["scope"]) or {}).get("status") not in ("done", "dropped", "blocked")]
    runs = open_runs(events, now)
    # the milestone a running qa skill audits: its scope, or (older runs without scope) the milestone waiting for its gate
    qa_runs = [r for r in runs if r["skill"] == "qa"]
    qa_scope = next((r["scope"] for r in reversed(qa_runs) if r.get("scope")), None) or (qa_default if qa_runs else None)
    qa_node = _node_of(qa_scope) if qa_scope else None
    hooks = agents_data(root)
    if not hooks["hooks"]:
        active = []
        for o in spawns:
            node, how = _node_of(o["scope"]), "spawn"
            if not node and o["agent"] in QA_AGENTS and qa_node:
                node, how = qa_node, "qa_run"
            active.append({"agent": o["agent"], "started_at": o["started_at"], "node": node, "slot": o["slot"], "linked_by": how if node else None})
        _link_to_tasks(active, tasks)
        return {"hooks": False, "active": active, "runs": runs}
    near = lambda h, o: h["agent"] == o["agent"] and abs(_ts(h["started_at"]) - _ts(o["started_at"])) <= LINK_WINDOW_S  # noqa: E731
    hs = [{"agent": _short(h["agent"]), "started_at": h["started_at"],
           "node": scope_from_transcript(h.get("agent_id"), h.get("transcript"))} for h in hooks["active"]]
    scoped = [o for o in spawns if _node_of(o["scope"])]
    active = []
    for h in hs:
        node, slot, how = h["node"], None, None
        # 0. the agent's own prompt names its task or milestone
        if node:
            how = "id"
            slot = next((o["slot"] for o in reversed(scoped) if o["agent"] == h["agent"] and _node_of(o["scope"]) == node), None)
        # 1. the start times match one spawn with a scope, and that spawn only this agent
        cands = [o for o in scoped if near(h, o)] if not node else []
        if len(cands) == 1 and sum(1 for x in hs if not x["node"] and near(x, cands[0])) == 1:
            node, slot, how = _node_of(cands[0]["scope"]), cands[0]["slot"], "time"
        # 2. every open spawn of this agent type points to the same node (heavy auditors start later than they are logged)
        if not node:
            same = [o for o in spawns if o["agent"] == h["agent"]]
            nodes = {_node_of(o["scope"]) for o in same}
            if same and len(nodes) == 1 and None not in nodes:
                node, slot, how = nodes.pop(), same[-1]["slot"], "type"
        # 3. an auditor with no spawn while qa runs on a milestone belongs to that milestone's QA gate
        if not node and h["agent"] in QA_AGENTS and qa_node:
            node, how = qa_node, "qa_run"
        active.append({"agent": h["agent"], "started_at": h["started_at"], "node": node, "slot": slot, "linked_by": how})
    by_start = lambda x: (_ts(x["started_at"]), int(x["slot"]) if str(x.get("slot") or "").isdigit() else 0)  # noqa: E731
    for ag in sorted({a["agent"] for a in active if not a["node"]}):
        loose = sorted((a for a in active if a["agent"] == ag and not a["node"]), key=by_start)
        taken = {a["node"] for a in active if a["node"]}
        # 4. as many unlinked agents of this type as open spawns of this type whose node is still free
        free = sorted((o for o in spawns if o["agent"] == ag and _node_of(o["scope"]) and _node_of(o["scope"]) not in taken),
                      key=by_start)
        if len(free) == len(loose) and len({_node_of(o["scope"]) for o in free}) == len(free):
            for a, o in zip(loose, free):
                a.update(node=_node_of(o["scope"]), slot=o["slot"], linked_by="batch")
            continue
        # 5. implementers with no spawn carrying a scope, as many as the in-progress tasks with no agent
        if ag == "implementer" and not any(o["agent"] == ag for o in scoped):
            _link_to_tasks(active, tasks)
    return {"hooks": True, "active": active, "runs": runs}


def _link_to_tasks(active: list[dict], tasks: dict | None) -> None:
    """Rule 5: implementers with no node, as many as the in-progress tasks no agent is on, paired in start order."""
    if not tasks:
        return
    by_start = lambda x: (_ts(x["started_at"]), int(x["slot"]) if str(x.get("slot") or "").isdigit() else 0)  # noqa: E731
    loose = sorted((a for a in active if a["agent"] == "implementer" and not a["node"]), key=by_start)
    taken = {a["node"] for a in active if a["node"]}
    idle = sorted(({"node": t, "started_at": v.get("started_at"), "slot": None} for t, v in tasks.items()
                   if v.get("status") == "in_progress" and t not in taken), key=by_start)
    if loose and len(idle) == len(loose):
        for a, t in zip(loose, idle):
            a.update(node=t["node"], linked_by="task")


def lifecycle(auto: dict) -> dict:
    """Settings that decide which milestone stages apply: local preview (smoke) and production deploy per milestone."""
    d = ds.DEFAULT_AUTONOMY
    ld = auto.get("local_deploy") if isinstance(auto.get("local_deploy"), dict) else {}
    pr = auto.get("production") if isinstance(auto.get("production"), dict) else {}
    return {"local_deploy": ld.get("mode") or d["local_deploy"]["mode"],
            "deploy_when": pr.get("when") or d["production"]["when"],
            "max_fix_rounds": auto.get("max_fix_rounds_per_gate") or d["max_fix_rounds_per_gate"]}


def qa_detail(dev: Path, m: str, info: dict, events: list[dict], run: dict | None) -> dict:
    """QA rounds of one milestone: past rounds (gate events), the last score breakdown (qa/<M>/scores.json) and,
    while a qa run is open on it, which auditors already finished and which are still running."""
    rounds: dict[int, dict] = {}
    for e in events:
        if e.get("event") == "gate" and e.get("scope") == m and e.get("qa_runs"):
            n = int(e["qa_runs"])
            rounds[n] = {"n": n, "value": e.get("value"), "score": e.get("score"), "at": e.get("ts"),
                         "reason": (info.get("round_reasons") or {}).get(str(n))}
    out: dict = {"runs": int(info.get("qa_runs") or 0), "note": info.get("gate_note"), "history": [rounds[k] for k in sorted(rounds)]}
    try:
        sc = json.loads((dev / "qa" / m / "scores.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        sc = None
    if isinstance(sc, dict):
        dims = sc.get("dimensions") if isinstance(sc.get("dimensions"), dict) else {}
        out["last"] = {"overall": sc.get("overall"), "cutoff": sc.get("cutoff"), "verdict": sc.get("verdict"),
                       "blockers": len(sc.get("blockers") or []),
                       "blocking": [{k: x.get(k) for k in ("id", "dimension", "severity", "title", "file", "line")}
                                    for x in (sc.get("blockers") or [])[:30] if isinstance(x, dict)],
                       "below": [{"dimension": d, "score": v.get("score"), "min": v.get("min")}
                                 for d, v in sorted(dims.items()) if isinstance(v, dict) and v.get("ok") is False]}
    if run:
        start = _ts(run["started_at"])
        mine = [e for e in events if e.get("session") == run["session"] and _ts(e.get("ts")) >= start
                and e.get("event") in ("agent_spawn", "agent_end") and _short(e.get("agent")) in QA_AGENTS
                and (not e.get("scope") or e.get("scope") == m)]
        done = [{"agent": _short(e.get("agent")), "findings": e.get("findings"), "status": e.get("status"), "at": e.get("ts")}
                for e in mine if e["event"] == "agent_end"]
        started = [_short(e.get("agent")) for e in mine if e["event"] == "agent_spawn"]
        auditors = {}
        for e in mine:  # the auditors of the round: state, model, time
            a = _short(e.get("agent"))
            x = auditors.setdefault(a, {"agent": a, "state": "running", "model": None, "started_at": None, "duration_s": None, "findings": None})
            if e["event"] == "agent_spawn":
                x.update(started_at=e.get("ts"), model=e.get("model") or x["model"])
            else:
                x.update(state="done" if e.get("status") in (None, "ok", "done") else str(e.get("status")), findings=e.get("findings"),
                         duration_s=e.get("duration_s"), model=e.get("model") or x["model"])
        out["round"] = {"n": out["runs"] + 1, "started_at": run["started_at"], "done": done,
                        "spawned": len(started), "auditors": list(auditors.values())}
    return out


def _findings_text(c: object) -> str:
    if not isinstance(c, dict):
        return ""
    parts = [f"{c[k]} {k}" for k in ("critical", "high", "medium", "low") if c.get(k)]
    return ", ".join(parts) if parts else "no findings"


def _where(scope: object) -> str:
    node = _node_of(scope)
    return "" if not node else f" on {node}" if not node.startswith("GATE:") else f" · QA gate of {node[5:]}"


def live_feed(events: list[dict], n: int = LIVE_TAIL) -> list[dict]:
    """Skill and agent starts and ends from the session log, for the activity feed (log.md has the rest)."""
    rows = []
    for e in events:
        ev, at = e.get("event"), e.get("ts")
        if ev == "skill_start" and e.get("skill") != "board":
            rows.append({"at": at, "kind": "live", "text": f"/dev-kit:{e.get('skill')} started" + (f" ({e['scope']})" if e.get("scope") else "")})
        elif ev == "skill_end" and e.get("skill") != "board":
            rows.append({"at": at, "kind": "live", "text": f"/dev-kit:{e.get('skill')} finished" + (f" ({e['scope']})" if e.get("scope") else "")
                         + (f" · {e['status']}" if e.get("status") and e.get("status") != "ok" else "")})
        elif ev == "agent_spawn":
            a = _short(e.get("agent"))
            rows.append({"at": at, "kind": "live", "text": f"{a} started ({AGENT_ROLE.get(a, 'agent')}){_where(e.get('scope'))}"})
        elif ev == "agent_end":
            a = _short(e.get("agent"))
            f = _findings_text(e.get("findings"))
            rows.append({"at": at, "kind": "live", "text": f"{a} finished{_where(e.get('scope'))}" + (f" · {f}" if f else "")})
    return rows[-n:]


# The activity feed shows what means something to the user (§16 of the 3.0 spec): each row is a kind and its values,
# worded by the board's catalog; technical lines (cleanup, tips, cost, state notes, sync) stay in the full log.
FEED_RULES = (
    ("task_done", re.compile(r"^done (?P<task>T-\d+)(?! commit corrected)")),
    ("task_started", re.compile(r"^start (?P<task>T-\d+) (?P<title>.*?)(?: tier=\S+ arm=\S+)?$")),
    ("task_blocked", re.compile(r"^block (?P<task>T-\d+): (?P<reason>.*)$")),
    ("task_dropped", re.compile(r"^drop (?P<task>T-\d+): (?P<reason>.*)$")),
    ("gate_passed", re.compile(r"^gate (?P<milestone>M[\d.]+) passed(?: score=(?P<score>\d+))?")),
    ("qa_round_done", re.compile(r"^gate (?P<milestone>M[\d.]+) pending(?: score=(?P<score>\d+))?(?: \((?P<reason>.*)\))?$")),
    ("gate_failed", re.compile(r"^gate (?P<milestone>M[\d.]+) failed(?: score=(?P<score>\d+))?")),
    ("question_open", re.compile(r"^add-question (?P<id>Q-\d+) \([^)]*\): (?P<text>.*)$")),
    ("question_answered", re.compile(r"^answer-question (?P<id>Q-\d+): (?P<text>.*)$")),
    ("issue_new", re.compile(r"^add-issue (?P<id>I-\d+) \((?P<type>[a-z]+)/(?P<cls>[a-z-]+)\) (?P<title>.*)$")),
    ("issue_classified", re.compile(r"^issue (?P<id>I-\d+) .*class=(?P<cls>[a-z-]+)")),
    ("release_submitted", re.compile(r"^release (?P<release>R\d+) submitted for approval")),
    ("release_approved", re.compile(r"^release (?P<release>R\d+) approved")),
    ("release_rejected", re.compile(r"^release (?P<release>R\d+) rejected")),
    ("released", re.compile(r"^release (?P<version>[^\sR][^\s]*) \((?P<tag>[^)]*)\)")),
    ("deploy", re.compile(r"^deploy (?P<env>\S+) (?P<status>\S+) (?P<sha>\S+)")),
    ("review", re.compile(r"^review (?P<name>\S+) (?P<value>\S+)(?: score=(?P<score>\d+))?")),
    ("checkpoint", re.compile(r"^checkpoint (?P<target>prd|plan) (?P<decision>confirm|adjust)")),
)


def feed_item(text: str) -> dict | None:
    for kind, rx in FEED_RULES:
        m = rx.match(text)
        if m:
            return {"kind": kind, "vars": {k: v for k, v in m.groupdict().items() if v is not None}}
    return None


def user_feed(log_rows: list[dict], events: list[dict], tasks: dict) -> list[dict]:
    rows = []
    for r in log_rows:
        x = feed_item(r["text"])
        if x:
            if "task" in x["vars"] and "title" not in x["vars"]:
                x["vars"]["title"] = (tasks.get(x["vars"]["task"]) or {}).get("title", "")
            rows.append({"at": r["at"], **x})
    for e in events:
        if e.get("event") == "skill_start" and e.get("skill") == "qa" and e.get("scope"):
            rows.append({"at": e.get("ts"), "kind": "qa_round_started", "vars": {"milestone": str(e["scope"])}})
        elif e.get("event") == "skill_end" and e.get("status") in ("failed", "error") and e.get("skill") not in ("board", None):
            rows.append({"at": e.get("ts"), "kind": "failure", "vars": {"skill": str(e["skill"]), "scope": str(e.get("scope") or "")}})
    return sorted(rows, key=lambda r: _ts(r.get("at")), reverse=True)[:LOG_TAIL]


def denied_permissions(root: Path) -> list[dict]:
    """Permissions a round child was denied because nobody answered (dev_perms.py), for Needs you: information
    only, cut to the tool, the agent, how it ended, the rule that would allow it and 120 characters of the target."""
    try:
        import dev_perms
        return [{k: m.get(k) for k in ("key", "tool", "count", "how", "rule", "agent")} | {"target": str(m.get("target") or "")[:120]}
                for m in dev_perms.misses(root)[:20]]
    except Exception:  # noqa: BLE001 - a broken record never breaks the board
        return []


def denied_count(root: Path) -> int:
    """How many denied permissions are recorded, so the board can say how many it does not list."""
    import dev_perms
    return len(dev_perms.misses(root))


def build_state(root: Path, board: dict | None = None) -> dict:
    store = ds.Store(root)
    if not store.exists():
        return {"ok": False, "error": "no_state", "message": f"No dev-kit state in {root}. Run /dev-kit:start."}
    try:
        store.load()  # read-only from here on: never call store.save()
    except SystemExit:
        return {"ok": False, "error": "corrupt_state", "message": "state.json could not be read (it may be mid-write)."}
    s = store.state
    lc = ds.lifecycle(store)
    goals = milestone_goals(_read(store.dev / "plan.md"))
    tasks = {}
    for tid, t in sorted(store.tasks().items(), key=lambda kv: int(kv[0][2:])):
        if t.get("status") == "dropped":
            continue  # removed by a replan: history only, not on the board
        # empty fields are left out: a large project sends ~1,000 tasks on every change
        tasks[tid] = {k: t.get(k) for k in ("title", "milestone", "type", "status", "lane", "deps", "commit",
                                            "blocked_reason", "started_at", "done_at", "source", "seq", "dep_reasons",
                                            "question", "blocked_count") if t.get(k) not in (None, [], "")}
        tasks[tid]["acceptance"] = len(t.get("acceptance") or [])
    events = _task_events(root)
    order = store.milestone_order()
    # the milestone waiting for its gate (all tasks done): where a qa run without scope is auditing
    qa_default = next((m for m in order if store.milestones()[m].get("gate", "pending") == "pending"
                       and [t for t in tasks.values() if t["milestone"] == m]
                       and all(t["status"] == "done" for t in tasks.values() if t["milestone"] == m)), None)
    agents = live_agents(root, qa_default, tasks)
    qa_run = next((r for r in reversed(agents["runs"]) if r["skill"] == "qa"), None)
    qa_scope = (qa_run.get("scope") or qa_default) if qa_run else None
    milestones = []
    prod = [d for d in ((s.get("deploys") or {}).get("production") or {}).get("history") or [] if isinstance(d, dict)]
    for m in store.milestone_order():
        info = store.milestones()[m]
        dep = next((d for d in reversed(prod) if d.get("milestone") == m), None)
        milestones.append({"id": m, "title": info.get("title"), "goal": goals.get(m, ""), "gate": info.get("gate", "pending"),
                           "score": info.get("score"), "qa_runs": info.get("qa_runs", 0), "passed_at": info.get("passed_at"),
                           "frozen_at": info.get("frozen_at"), "max_fix_rounds": ds.fix_rounds_allowed(store, m),
                           "preview": info.get("preview"), "release": info.get("release"),
                           "deploy": {k: dep.get(k) for k in ("status", "sha", "at")} if dep else None,
                           "qa": qa_detail(store.dev, m, info, events, qa_run if qa_scope == m else None),
                           "gate_checks": _safe(lambda m=m: [{"text": t, "hard": h} for t, h in ds.gate_problems(store, m, argparse.Namespace(scores=None))]) or [],
                           "hard_floor": info.get("hard_floor"), "exit_check": info.get("exit_check"),
                           "tasks": [tid for tid, t in tasks.items() if t["milestone"] == m]})
    nxt, why = ds.pick_next(store, None)
    try:
        backlog = ds.backlog_data(store)
        backlog.pop("tasks", None)  # the board reads the tasks above; this copy doubled the payload
    except Exception as e:  # noqa: BLE001 - the board must keep rendering
        backlog = {"error": str(e)}
    costs = None
    cs = store.dev / "costs" / "summary.json"
    if cs.exists():
        try:
            costs = json.loads(cs.read_text(encoding="utf-8")).get("total")
        except (OSError, json.JSONDecodeError):
            costs = None
    try:  # cost and tokens per milestone (dev_cost.py ingest), for the velocity chart
        ms_costs = json.loads((store.dev / "costs" / "milestones.json").read_text(encoding="utf-8")).get("milestones") or {}
    except (OSError, json.JSONDecodeError, AttributeError):
        ms_costs = {}
    return {
        "ok": True,
        "project": s.get("project") or root.name,
        **{k: lc[k] for k in ("phase", "step", "reopened")}, "cycle": {k: lc[k] for k in ("phases", "release", "queue", "releases")},
        "language": s.get("language"),
        "created_at": s.get("created_at"), "updated_at": s.get("updated_at"),
        "autonomy": (s.get("autonomy") or {}).get("level"),
        "brownfield": ({k: (s.get("brownfield") or {}).get(k) for k in ("mode", "baseline_ref", "first_milestone")}
                       if s.get("brownfield") else None),
        "stack": {k: v for k, v in (s.get("stack") or {}).items() if k != "detected_from" and v},
        "progress": store.progress(),
        "current_milestone": ds.current_milestone(store),
        "next": {"task": nxt, "reason": why, "command": ds.next_command(store)},
        "milestones": milestones, "tasks": tasks,
        "reviews": s.get("reviews") or {},
        "quality": ds.quality_cfg(store),
        "lifecycle": lifecycle(s.get("autonomy") or {}),
        "backlog": backlog,
        "questions": [{**q, "task": ((s.get("question_meta") or {}).get(q["id"]) or {}).get("task")}
                      for q in question_options(root, open_questions(_read(store.dev / "open-questions.md")))],
        "denied": denied_permissions(root), "denied_total": _safe(lambda: denied_count(root)) or 0,
        "log": sorted(log_tail(_read(store.dev / "log.md")) + live_feed(events), key=lambda r: _ts(r.get("at")), reverse=True)[:LOG_TAIL],
        "feed": user_feed(log_tail(_read(store.dev / "log.md"), 400), events, tasks),
        "costs": costs,
        "decisions": decisions_list(_read(store.dev / "decisions.md")),
        "forecast": _safe(lambda: ds.forecast(store)),
        # verified facts (conventions.md §2), newest first; a stale one stays with what contradicted it
        "facts": [{"id": k, **{x: f.get(x) for x in ("text", "evidence", "sha", "date", "origin", "files", "acs", "stale")}}
                  for k, f in sorted((s.get("facts") or {}).items(), key=lambda kv: int(kv[0][2:]) if kv[0][2:].isdigit() else 0,
                                     reverse=True) if isinstance(f, dict)],
        "docs": docs_list(root),
        "diagram": _safe(lambda: dg.status(root)),
        "milestone_costs": {m: {k: v.get(k) for k in ("usd", "usd_complete", "tokens", "partial")}
                            for m, v in ms_costs.items() if isinstance(v, dict)},
        "releases": [{k: r.get(k) for k in ("version", "tag", "milestones", "at", "hotfix", "release")}
                     for r in s.get("releases") or [] if isinstance(r, dict)],
        # every submission, approval and rejection of each planned release (cycle.releases carries only the last five)
        "release_history": {rid: [{k: x.get(k) for k in ("event", "at", "review_doc", "milestone", "tasks", "ref", "version") if k in x}
                                  for x in (v.get("history") or []) if isinstance(x, dict)]
                            for rid, v in (s.get("release_state") or {}).items() if isinstance(v, dict)},
        "production": production_info(store),
        "prod_health": _safe(lambda: prod_health(store)),
        "flags": [{"name": k, **{x: v.get(x) for x in ("release", "state", "cleanup_task")}}
                  for k, v in sorted((s.get("flags") or {}).items()) if isinstance(v, dict)],
        "artifacts": {step: [str(p.relative_to(root)) for p in ds.artifact_paths(store, art)]
                      for step, art in ds.STEP_ARTIFACT.items()},
        "agents": agents, "agent_roles": AGENT_ROLES,
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
    for rel in (dg.SVG, dg.MODEL, *dg.SOURCES):  # the diagram lives in docs/, its source in .dev/architecture.md
        try:
            st = (root / rel).stat()
            out.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((rel, 0, 0))
    return tuple(out)


# --------------------------------------------------------------------------- server

HOST_NAME = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


def config_path(root: Path) -> Path:
    return run_dir(root) / "board-config.json"


def trusted_hosts(root: Path, given: list[str] | None = None) -> list[str]:
    """Host names the board answers to besides localhost and IP addresses (a reverse proxy in front of it).
    `given` (from --trusted-host) is added to the remembered list and saved; "none" forgets them all."""
    try:
        saved = [h for h in json.loads(config_path(root).read_text(encoding="utf-8")).get("trusted_hosts", []) if isinstance(h, str)]
    except (OSError, json.JSONDecodeError, AttributeError):
        saved = []
    if not given:
        return saved
    names = [g.strip().lower() for g in given]
    new = [] if "none" in names else sorted(set(saved) | {n for n in names if n})
    if new != saved:
        ensure_run_dir(root)
        config_path(root).write_text(json.dumps({"trusted_hosts": new}) + "\n", encoding="utf-8")
    return new


def parse_host_name(v: str) -> str:
    name = v.strip().lower()
    if name != "none" and not HOST_NAME.match(name):
        raise argparse.ArgumentTypeError("--trusted-host takes a host name without scheme or port, e.g. board.example.com")
    return name


def host_name(host: str) -> str:
    """The name part of a Host header or URL authority, lowercased, without the port."""
    host = host.strip().lower()
    return host.partition("]")[0] + "]" if host.startswith("[") else host.partition(":")[0]


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

    def __init__(self, addr, root: Path, token: str, idle_s: int, trusted: list[str] | None = None):
        super().__init__(addr, Handler)
        self.root, self.token, self.idle_s = root, token, idle_s
        self.exposed = is_exposed(addr[0])  # listening beyond loopback: every request needs the access key
        self.trusted = set(trusted or [])  # host names of a reverse proxy in front of the board
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
        if host_name(host) in self.server.trusted:
            return True
        print(f"refused Host header {host[:80]!r} (only localhost, an IP address or a --trusted-host name are accepted)",
              file=sys.stderr, flush=True)
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
        """POSTs must come from the page itself: Origin, when sent, is the same origin the browser used, or a
        trusted host's (a reverse proxy may serve the page over https and rewrite the Host header)."""
        origin = self.headers.get("Origin")
        if origin is None or origin.lower() == f"http://{self.headers.get('Host', '')}".lower():
            return True
        scheme, sep, rest = origin.lower().partition("://")
        return bool(sep) and scheme in ("http", "https") and "/" not in rest and host_name(rest) in self.server.trusted

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
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # the state of a large project is hundreds of KB on every change; compressed it is a tenth of that
        if len(body) > 4096 and "gzip" in self.headers.get("Accept-Encoding", "") and self.command != "HEAD":
            return self._send(code, gzip.compress(body, compresslevel=5), extra={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
        self._send(code, body)

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
        if path == "/api/task":
            q = self.path.partition("?")[2]
            tid = next((v[3:] for v in q.split("&") if v.startswith("id=")), "")
            if not TASK_ID_RE.fullmatch(tid):
                return self._json(400, {"ok": False, "error": "bad task id"})
            d = task_detail(self.server.root, tid)
            return self._json(200 if d else 404, d or {"ok": False, "error": "unknown task"})
        if path == "/api/doc":
            q = self.path.partition("?")[2]
            raw = next((v[5:] for v in q.split("&") if v.startswith("path=")), "")
            code, d = doc_detail(self.server.root, urllib.parse.unquote(raw))
            return self._json(code, d)
        if path == "/api/diagram":
            return self._diagram()
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
            body = body.replace(b"__BOARD_TOKEN__", self.server.token.encode()).replace(b"__BOARD_I18N__", i18n_payload())
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
        if path != "/api/shutdown":  # the board is read-only: stopping it is the only thing a page may ask
            return self._json(404, {"ok": False, "error": "not found"})
        if not secrets.compare_digest(self.headers.get("X-Board-Token", ""), self.server.token):
            return self._json(403, {"ok": False, "error": "bad token"})
        self._json(202, {"ok": True, "stopping": True})
        self.server.stop()

    def _diagram(self):
        """The project's architecture diagram (docs/diagrams/architecture.svg), as an image: only that file, never
        through a link out of the project, at most DIAGRAM_MAX bytes. Shown in an <img>, so scripts in it never run."""
        root = self.server.root.resolve()
        try:
            p = (root / dg.SVG).resolve()
            ok = p.is_relative_to(root) and p.is_file()
            size = p.stat().st_size if ok else 0
        except OSError:
            ok, size = False, 0
        if not ok:
            return self._json(404, {"ok": False, "error": "no diagram", "hint": "run /dev-kit:diagram"})
        if size > DIAGRAM_MAX:
            return self._json(413, {"ok": False, "error": f"too large ({size} bytes)"})
        self._send(200, p.read_bytes(), "image/svg+xml; charset=utf-8",
                   {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"})

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


def bind(host: str, port: int, root: Path, token: str, idle_s: int, trusted: list[str] | None = None) -> Board:
    cls = Board6 if ":" in host else Board
    try:
        return cls((host, port), root, token, idle_s, trusted)
    except OSError:
        return cls((host, 0), root, token, idle_s, trusted)


def cmd_serve(root: Path, a: argparse.Namespace) -> int:
    token = os.environ.pop("DEV_BOARD_TOKEN", "") or secrets.token_urlsafe(24)
    host = a.host or "127.0.0.1"
    srv = bind(host, a.port, root, token, a.idle_min * 60, sorted(set(a.trusted_host or [])))
    port = srv.server_address[1]
    conn = connect_addr(host)
    url = f"http://{hostport(conn, port)}/"
    srv.record = {"pid": os.getpid(), "port": port, "token": token, "url": url, "root": str(root),
                  "host": host, "connect": conn, "exposed": srv.exposed,
                  "trusted_hosts": sorted(srv.trusted),
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
            elif code_id() != CODE_ID:
                print("the kit was updated on disk: stopping; /dev-kit:board starts the new version", flush=True)
                srv.stop()
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
    trusted = trusted_hosts(root, a.trusted_host)
    with Lock(root):
        rec = live_record(root)
        restarted = False
        why = None
        if rec and rec.get("code") != CODE_ID:
            why = "the kit was updated since the running board started"
        elif rec and a.host and rec.get("host", "127.0.0.1") != a.host:
            why = f"the running board listens on {rec.get('host', '127.0.0.1')}, not {a.host}"
        elif rec and sorted(rec.get("trusted_hosts") or []) != trusted:
            why = "the trusted host names changed"
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
        for name in trusted:
            cmd += ["--trusted-host", name]
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
    """The trusted host names, and for a board listening beyond loopback the access links and the warning that goes
    with them."""
    if rec.get("trusted_hosts"):
        print(f"trusted host names: {', '.join(rec['trusted_hosts'])} · the proxy in front of them is the board's only "
              "protection there: keep its own login on (--trusted-host none forgets them)")
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
    out = {"running": bool(rec), **({k: rec.get(k) for k in ("url", "pid", "port", "started_at", "host", "exposed", "access_urls",
                                                              "trusted_hosts")}
                                    if rec else {})}
    if a.json:
        print(json.dumps(out))
    elif rec:
        print(f"running: {rec['url']} (pid {rec['pid']}, since {rec['started_at']})")
        print_exposure(rec)
    else:
        print("not running")
    return 0


def round_view(root: Path) -> dict | None:
    """The headless round running now (`dev_state.py round run`): skill, milestone, since when, the tasks it has in
    progress or in an open slot, and its last action (.dev/run/round-activity.json, written by the fence hook).
    `unregistered` is true when an implement round works with no task started (the state would say todo)."""
    run = root / ".dev" / "run"

    def rd(p: Path) -> dict:
        try:
            v = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}
    mk = rd(run / "round.json")
    if not mk or not (ds._alive(mk.get("child")) or ds._alive(mk.get("pid"))):
        return None
    st = rd(root / ".dev" / "state.json")
    tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
    scope = mk.get("scope")
    ids = {k for k, v in tasks.items() if isinstance(v, dict) and v.get("status") == "in_progress" and (not scope or v.get("milestone") == scope)}
    for f in sorted((run / "slots").glob("*.json")) if (run / "slots").is_dir() else []:
        rec = rd(f)
        if rec.get("task") and not rec.get("closed_at"):
            ids.add(str(rec["task"]))
    act = rd(run / "round-activity.json")
    if act.get("round") != mk.get("round"):
        act = {}
    return {"skill": mk.get("skill"), "scope": scope, "since": mk.get("started"),
            "tasks": sorted(ids, key=lambda x: int(x[2:]) if x[2:].isdigit() else 0),
            "unregistered": mk.get("skill") == "implement" and not ids,
            **({"last": {k: act.get(k) for k in ("at", "tool", "agent")}} if act else {})}


def pane_data(root: Path) -> dict:
    """What runs now, in one small read for the terminal status pane: never the server's token."""
    rec = read_record(root)
    board = {"running": bool(rec and ds._alive(rec.get("pid")))}
    if board["running"]:
        board["url"] = rec.get("url")
    tasks: dict = {}
    try:
        store = ds.Store(root)
        store.load()
        for tid, t in store.tasks().items():
            if isinstance(t, dict):
                tasks[tid] = {"status": t.get("status"), "started_at": t.get("started_at"), "milestone": t.get("milestone")}
    except (Exception, SystemExit):  # noqa: BLE001 - the pane shows what it can
        pass
    try:
        live = live_agents(root, None, tasks)
    except Exception:  # noqa: BLE001
        live = {"hooks": False, "active": [], "runs": []}
    agents = [{"agent": a.get("agent"), "node": a.get("node"), "started_at": a.get("started_at")} for a in live.get("active") or []]
    runs = [{"skill": r.get("skill"), "scope": r.get("scope"), "started_at": r.get("started_at")} for r in live.get("runs") or []
            if r.get("skill") not in ("board",)]
    # the Autopilot is /dev-kit:autopilot running in a Claude Code session (its skill_start with no skill_end)
    ap_run = next((r for r in runs if r["skill"] == "autopilot"), None)
    autopilot: dict = {"on": bool(ap_run), "state": "running" if ap_run else "off"}
    if ap_run and ap_run.get("started_at"):
        autopilot["since"] = ap_run["started_at"]
    rd = round_view(root)
    if rd:
        autopilot["round"] = rd
    return {"board": board, "autopilot": autopilot, "agents": agents, "runs": runs}


def cmd_pane(root: Path, a: argparse.Namespace) -> int:
    if not (root / ".dev" / "state.json").exists():
        return 2
    out = pane_data(root)
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        ap = out["autopilot"]
        print(f"board {'up' if out['board']['running'] else 'down'} · autopilot {ap.get('state')}"
              + (f" · round {ap['round']['skill']} {ap['round'].get('scope') or ''}".rstrip() if ap.get("round") else "")
              + f" · {len(out['agents'])} agent(s)")
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
        s.add_argument("--trusted-host", action="append", type=parse_host_name, metavar="NAME",
                       help="host name of a reverse proxy in front of the board (repeatable; remembered; 'none' forgets)")
        if name == "start":
            g = s.add_mutually_exclusive_group()
            g.add_argument("--no-open", action="store_true", help="do not open a browser tab")
            g.add_argument("--open", action="store_true", help="open a tab even if the board was already running")
    sub.add_parser("stop")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("pane")
    s.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    root = ds.find_root(a.root)
    return {"start": cmd_start, "serve": cmd_serve, "stop": cmd_stop, "status": cmd_status, "pane": cmd_pane}[a.cmd](root, a)


if __name__ == "__main__":
    sys.exit(main())
