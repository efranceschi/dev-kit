#!/usr/bin/env python3
"""dev_debug.py - a diagnostic dump of a dev-kit project, for /dev-kit:debug and for patches to the kit.

Standard library only. Read-only for the project: it reads .dev/ and git, runs consistency checks between them, and
writes one Markdown file under .dev/run/debug/ (machine-local, never committed). Nothing is sent anywhere.

  dump [--share] [--out PATH] [--tail N] [--json]   write the dump; --json prints {path, checks, share} instead
  check [--json]                                    only the consistency checks (exit 1 when one is an error)

The dump holds: the kit and tool versions, the checks, git (status, worktrees, branches, recent commits), the tasks
that are not done, the run files (.dev/run/*.json: autopilot, round, slots, activity), the end of .dev/log.md, of the
autopilot log and of the round logs, the ledger's task records and the last telemetry events. It never copies the
project's source files or the environment.

Every dump keeps codes only: task, question, milestone, issue and ADR ids, statuses, times, counts and check codes.
Names and free text never go in: titles of tasks, milestones, releases and issues, the text of questions, commit
subjects, block reasons, log details, the answers of the claude runs and the round's last action. Secrets are removed
too: values of keys named like token, secret, password, api key, credential, cookie (the board's own token included),
and anything shaped like a credential (private keys, AWS, GitHub, Slack, Google, Databricks and `sk-` keys, JWTs,
Bearer tokens, `password=…`, credentials in URLs, e-mail addresses). The local dump keeps paths and branches.

`--share` writes a dump meant for someone else (the kit's author, a colleague): on top of that, the project folder,
the home folder and the user name are replaced, every file path of the project becomes a stable pseudonym
(`p:3fa2c1.js`, the same in every section) and branches other than the kit's and main/master become `<branch-n>`.

Before writing, every dump checks its own text: when a secret pattern or one of the project's names (and, with
--share, the project or home folder, the user name or a project path) is still there, it writes nothing and exits 3
with what it found. Read it anyway before you send it.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir

FINISHED = ("done", "dropped")
SECRET_KEY = re.compile(r"(?i)token|secret|passw|pwd|api[_-]?key|access[_-]?key|private[_-]?key|credential|cookie|session[_-]?key|^auth")
SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bdapi[0-9a-f]{32}\b"),
    re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[\w.~+/=-]{12,}"),
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
]
SECRET_ASSIGN = re.compile(r"(?i)(\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|auth)\b[\"']?\s*[:=]\s*[\"']?)"
                           r"([^\s\"',;&]{4,})")
URL_CREDS = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")
IDS = re.compile(r"\b(?:T-\d{1,5}|Q-\d{1,5}|I-\d{1,5}|F-\d{1,5}|ADR-\d{1,5}|P-\d{1,5}|A-\d{1,5}|M\d{1,3}|R\d{1,3})\b")
KIT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+@-]{0,63}$")
KEEP_BRANCHES = ("main", "master", "HEAD")


def redact(text: str) -> str:
    """Credentials out of any text (both modes)."""
    for rx in SECRETS:
        text = rx.sub("[REDACTED]", text)
    text = SECRET_ASSIGN.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return URL_CREDS.sub(r"\1[REDACTED]@", text)


def scrub_json(v: object, share: "Sharer | None" = None, key: str = "") -> object:
    """Values of secret-looking keys out; with a Sharer, free text and paths anonymised too."""
    if isinstance(v, dict):
        return {k: ("[REDACTED]" if SECRET_KEY.search(str(k)) and not isinstance(x, (dict, list, bool)) else scrub_json(x, share, str(k)))
                for k, x in v.items()}
    if isinstance(v, list):
        return [scrub_json(x, share, key) for x in v]
    if isinstance(v, str):
        return share.value(v) if share else redact(v)
    return v


def names_of(root: Path, st: dict) -> list[str]:
    """The project's own names, which no dump carries: titles of tasks, milestones, releases and issues, and the
    text of the questions (only their codes are kept)."""
    out = set()
    for key in ("tasks", "milestones", "issues", "releases"):
        coll = st.get(key)
        for v in (coll.values() if isinstance(coll, dict) else coll if isinstance(coll, list) else []):
            if isinstance(v, dict):
                for f in ("title", "name", "goal"):
                    if isinstance(v.get(f), str):
                        out.add(v[f].strip())
    try:
        for ln in (root / ".dev" / "open-questions.md").read_text(encoding="utf-8", errors="replace").splitlines():
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and re.fullmatch(r"Q-\d+", cells[0]):
                out.update(c for c in cells[3:5] if c)
    except OSError:
        pass
    return sorted((x for x in out if len(x) >= 6), key=len, reverse=True)


class Sharer:
    """What a dump keeps of the project. Always: codes only (T-, Q-, M-, I-, ADR-), never titles, questions, commit
    subjects or free text, and no secrets. With `anon` (--share) also one pseudonym per path and per branch, the same
    in every section, and the folders and user name replaced."""

    def __init__(self, root: Path, st: dict, anon: bool = True):
        tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
        self.anon = anon
        self.root = str(root)
        self.home = str(Path.home())
        try:
            import getpass
            self.user = getpass.getuser()
        except Exception:  # noqa: BLE001
            self.user = ""
        if self.user.lower() in ("root", "admin", "user", "runner", "ubuntu", "ec2-user", "debian", "node", "app"):
            self.user = ""  # a generic account name says nothing about a person, and replacing it would break words
        self.paths: dict[str, str] = {}
        self.branches: dict[str, str] = {}
        self.titles = names_of(root, st)
        for t in tasks.values():
            for f in (t.get("files") or []) if isinstance(t, dict) else []:
                self.path(f)

    def path(self, p: str) -> str:
        p = p.strip()
        if not self.anon:
            return p
        if not p or p.startswith((".dev/", ".dev", ".claude/", "dev-kit/", "<project>", "~")):
            return p
        if p not in self.paths:
            import hashlib
            ext = Path(p.rstrip("/")).suffix[:8]
            self.paths[p] = f"p:{hashlib.sha256(p.encode()).hexdigest()[:6]}{ext}" + ("/" if p.endswith("/") else "")
        return self.paths[p]

    def branch(self, b: str) -> str:
        b = b.strip()
        if not self.anon:
            return b
        if not b or b in KEEP_BRANCHES or b.startswith("dev-kit/") or b.startswith("("):
            return b
        if b not in self.branches:
            self.branches[b] = f"<branch-{len(self.branches) + 1}>"
        return self.branches[b]

    def text(self, t: str) -> str:
        """Folders, user, known paths and branches replaced in a text that is kept (structure lines, evidence);
        without `anon` only the home folder. The project's names go in both modes."""
        for name in self.titles:
            t = t.replace(name, "(name removed)")
        if not self.anon:
            home = self.home if self.home and self.home != "/" else None
            return redact(t.replace(home, "~") if home else t)
        for src, dst in ((self.root, "<project>"), (self.home, "~")):
            if src and src != "/":
                t = t.replace(src, dst)
        for p in sorted(self.paths, key=len, reverse=True):
            t = t.replace(p, self.paths[p])
        for b in sorted(self.branches, key=len, reverse=True):
            t = re.sub(r"(?<![\w/-])" + re.escape(b) + r"(?![\w/-])", self.branches[b], t)
        if self.user and len(self.user) >= 3:
            t = re.sub(r"\b" + re.escape(self.user) + r"\b", "<user>", t)
        return redact(t)

    def free(self, t: object) -> str:
        """Free text dropped; the ids it mentions kept."""
        ids = sorted(set(IDS.findall(str(t or ""))))
        return "(text removed" + (f"; mentions {', '.join(ids)}" if ids else "") + ")"

    def value(self, v: str) -> str:
        """A string value of a JSON file: kept when it is a token, an id, a time or a number; a path becomes its
        pseudonym; anything else is free text and is dropped."""
        if v.startswith((self.root, self.home)) and self.root:
            return self.text(v)
        if not self.anon and " " not in v:
            return self.text(v)
        if v.startswith("/dev-kit:") or re.fullmatch(r"[a-z]+/[a-z+]+", v):
            return self.text(v)
        if "/" in v and " " not in v:
            if v in self.paths or not v.startswith((".dev", ".claude", "dev-kit/", "refs/")):
                return self.path(v) if not v.startswith(("http:", "https:")) else "(url removed)"
            return v
        if KIT_TOKEN.match(v):
            return v
        return self.free(v)

    def leaks(self, text: str) -> list[str]:
        out = [rx.pattern[:30] for rx in SECRETS if rx.search(text)]
        if SECRET_ASSIGN.search(text.replace("[REDACTED]", "")):
            out.append("key=value secret")
        out += [f"project name {t[:30]!r}" for t in self.titles if t in text]
        if not self.anon:
            return out
        for what, s in (("project folder", self.root), ("home folder", self.home)):
            if s and s != "/" and s in text:
                out.append(what)
        if self.user and len(self.user) >= 3 and re.search(r"\b" + re.escape(self.user) + r"\b", text):
            out.append("user name")
        out += [f"path {p}" for p in self.paths if len(p) >= 4 and p in text]
        return out
TASK_REF = r"(?:\[{tid}\]|^Refs:.*\b{tid}\b)"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(root: Path, *args: str, timeout: int = 30) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def read_json(p: Path) -> dict:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def tail(p: Path, n: int) -> str:
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)  # type: ignore[arg-type]
        return True
    except (OSError, ValueError, TypeError):
        return False


def kit_version() -> str:
    try:
        return json.loads((Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, json.JSONDecodeError, KeyError):
        return "?"


def worktrees(root: Path) -> list[dict]:
    out, cur = [], {}
    for line in git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[9:]}
            out.append(cur)
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
        elif line.startswith("HEAD "):
            cur["head"] = line[5:12]
        elif line.strip() in ("locked", "prunable", "detached"):
            cur[line.strip()] = True
    return out


def checks(root: Path) -> list[dict]:
    """Where the state and git disagree: each finding has a code, a level (error | warn | info), a text and evidence."""
    dev = root / ".dev"
    st = read_json(dev / "state.json")
    tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
    run = dev / "run"
    out: list[dict] = []

    def add(code: str, level: str, text: str, evidence: str = "") -> None:
        out.append({"code": code, "level": level, "text": text, "evidence": evidence})

    slots = {}
    for f in sorted((run / "slots").glob("*.json")) if (run / "slots").is_dir() else []:
        rec = read_json(f)
        if rec and not rec.get("closed_at"):
            slots[f.stem] = rec
    rnd = read_json(run / "round.json")
    round_alive = bool(rnd) and (alive(rnd.get("child")) or alive(rnd.get("pid")))
    if rnd and not round_alive:
        add("round_marker_dead", "error", "a round marker is left but its processes are gone: the round died and was not reconciled",
            f".dev/run/round.json {rnd.get('round')} (run `dev_state.py reconcile --since {rnd.get('started')}`)")
    ap = read_json(run / "autopilot-run.json")
    if ap.get("state") == "running" and not alive(ap.get("pid")):
        add("autopilot_dead", "warn", "the Autopilot run file says running but its process is gone", f"pid {ap.get('pid')}")
    in_prog = {k for k, v in tasks.items() if isinstance(v, dict) and v.get("status") == "in_progress"}
    if round_alive and rnd.get("skill") == "implement" and not in_prog and not slots:
        add("round_without_task", "error", "an implement round is running with no task in progress and no open slot: the state "
            "cannot say what it works on", f"{rnd.get('round')} since {rnd.get('started')}")
    for n, rec in slots.items():
        t = tasks.get(rec.get("task") or "") or {}
        if rec.get("task") and t.get("status") != "in_progress":
            add("slot_task_not_started", "error", f"slot {n} is open for {rec['task']}, which is {t.get('status') or 'unknown'}",
                f".dev/run/slots/{n}.json opened {rec.get('opened_at')}")
        if rec.get("worktree") and not Path(rec["worktree"]).exists():
            add("slot_worktree_missing", "warn", f"slot {n} points to a worktree that does not exist", rec["worktree"])
    if in_prog and not round_alive and not slots:
        add("in_progress_idle", "info", "tasks in progress with no round and no open slot: an inline session may hold them, or "
            "a session stopped (reconcile blocks them)", ", ".join(sorted(in_prog)))
    wts = worktrees(root)
    kit_wt = str((dev / "run" / "worktrees").resolve())
    for w in wts[1:]:
        br = w.get("branch") or ""
        m = re.fullmatch(r"dev-kit/(T-\d+)", br)
        if m:
            t = tasks.get(m.group(1)) or {}
            if not os.path.realpath(w["path"]).startswith(kit_wt):
                add("foreign_task_worktree", "warn", f"{m.group(1)} has a worktree outside the kit's folder (made by Claude Code's own "
                    "isolation before 3.5.0?): `start --resume` or `slot open --worktree` reuses it", f"{w['path']} on {br}")
            if t.get("status") in FINISHED:
                add("worktree_of_finished_task", "info", f"{m.group(1)} is {t['status']} but its worktree is still there",
                    f"{w['path']} (git worktree remove + git branch -D {br})")
        elif "/worktrees/" in w["path"] and not br.startswith("dev-kit/"):
            add("other_worktree", "info", "a worktree the kit does not manage", f"{w['path']} {br or '(detached)'}"
                + (" locked" if w.get("locked") else ""))
    started = (rnd.get("started") if rnd else None) or ""
    log = git(root, "log", "-200", "--format=%H%x00%cI%x00%B%x01", "HEAD")
    commits = [c.strip("\n").split("\x00") for c in log.split("\x01") if c.strip()]
    for tid, t in sorted(tasks.items(), key=lambda kv: int(kv[0][2:]) if kv[0][2:].isdigit() else 0):
        if not isinstance(t, dict) or t.get("status") in FINISHED:
            continue
        rx = re.compile(TASK_REF.format(tid=re.escape(tid)), re.M)
        hit = next((c for c in commits if len(c) == 3 and rx.search(c[2])), None)
        if hit:
            add("committed_not_done", "error", f"{tid} is {t.get('status')} but a commit carries it", f"{hit[0][:9]} {hit[1]}"
                f" (`dev_state.py done {tid} --commit {hit[0][:12]} --force` if that commit finished it)")
        if t.get("status") == "todo" and t.get("started_at"):
            add("todo_with_start", "info", f"{tid} is todo but was started before (blocked and unblocked, or reset)",
                f"started_at {t['started_at']}" + (f", blocked {t.get('blocked_count')} time(s)" if t.get("blocked_count") else ""))
    files: dict[str, list[str]] = {}
    for tid, t in tasks.items():
        if isinstance(t, dict) and t.get("status") not in FINISHED:
            for f in t.get("files") or []:
                files.setdefault(f.rstrip("/"), []).append(tid)
    status = git(root, "status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude).dev")
    by_task: dict[str, list[str]] = {}
    for ln in status.splitlines():
        f = ln[3:]
        for k, owners in files.items():
            if f == k or f.startswith(k + "/"):
                for o in owners:
                    by_task.setdefault(o, []).append(f)
    for tid, fs in sorted(by_task.items()):
        s = (tasks.get(tid) or {}).get("status")
        if s != "in_progress":
            add("dirty_files_of_unstarted_task", "error" if round_alive else "warn",
                f"the main checkout has uncommitted changes in files of {tid}, which is {s}", ", ".join(sorted(set(fs))[:12]))
    if started:
        add("round_running", "info", f"round {rnd.get('round')} started {started}", f"pids {rnd.get('pid')}/{rnd.get('child')}")
    return out


def section(title: str, body: str, lang: str = "") -> str:
    body = body.strip("\n") or "(empty)"
    return f"\n## {title}\n\n```{lang}\n{body}\n```\n"


CLAUDE_RUN_KEYS = ("type", "subtype", "is_error", "stop_reason", "terminal_reason", "duration_ms", "duration_api_ms", "num_turns",
                   "total_cost_usd", "session_id", "api_error_status")


def claude_log(text: str, share: Sharer) -> str:
    """A log of `claude -p --output-format json` runs: the header lines and, per run, its numbers and the tools it
    was denied; the run's answer (`result`) is free text and is never kept."""
    out = []
    for line in text.splitlines():
        ln = line.strip()
        if ln.startswith("{"):
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                out.append(share.free(ln) if share else redact(ln[:2000]))
                continue
            keep = {k: d.get(k) for k in CLAUDE_RUN_KEYS if k in d}
            keep["permission_denials"] = [x.get("tool_name") for x in d.get("permission_denials") or [] if isinstance(x, dict)]
            out.append(json.dumps(keep, ensure_ascii=False))
        else:
            out.append(share.text(line) if share else redact(line))
    return "\n".join(out)


LOG_KV = re.compile(r"\b(?:tier|arm|score|commit|killed|files|skipped|kind|mode|result)=[\w./+:-]+")


def log_line(line: str, share: Sharer) -> str:
    """One line of .dev/log.md: its time, its verb, the ids and the kit's key=value tokens only."""
    m = re.match(r"^(-\s*\S+\s+)(\S+)", line)
    if not m:
        return share.free(line)
    rest = line[m.end():]
    keep = sorted(set(IDS.findall(rest)), key=rest.find) + LOG_KV.findall(rest)
    return f"{m.group(1)}{m.group(2)} {' '.join(keep)}".rstrip() + (" …" if rest.strip() else "")


def dump(root: Path, n: int, share: bool = False) -> tuple[str, list[dict]]:
    dev = root / ".dev"
    st = read_json(dev / "state.json")
    tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
    found = checks(root)
    sh = Sharer(root, st, anon=share)
    run = dev / "run"
    status = git(root, "status", "--porcelain")
    if sh:
        for ln in status.splitlines():
            if len(ln) > 3 and not ln[3:].startswith(".dev"):
                sh.path(ln[3:])
        for w in worktrees(root):
            sh.branch(w.get("branch") or "")
        for b in git(root, "branch", "--format=%(refname:short)").splitlines():
            sh.branch(b)
    work_branch = ((st.get("autonomy") or {}).get("git") or {}).get("base_branch") or git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = ("# dev-kit debug dump (shareable)\n\nWritten {t} by dev_debug.py --share. Paths are pseudonyms (`p:…`, the same in "
            "every section), other branches are `<branch-n>`, free text is removed and secrets are redacted; the text was checked "
            "for leaks before it was written. Read it anyway before you send it.\n" if share else
            "# dev-kit debug dump\n\nWritten {t} by dev_debug.py. For this machine: it keeps the project's paths and branches; "
            "names are codes only (no titles, questions or commit subjects) and secrets are redacted. To send it to someone, write "
            "one with `dev_debug.py dump --share`.\n").format(t=now())
    parts = [head, section("Versions", "\n".join([f"dev-kit {kit_version()} (state written by {st.get('kit_version') or '?'})",
                                                  f"python {platform.python_version()} · {platform.system()} {platform.release()}",
                                                  (git(root, "--version") or "git ?").strip(),
                                                  f"work branch: {sh.branch(work_branch) if sh else work_branch}"]))]
    lines = [f"[{c['level']}] {c['code']}: {c['text']}" + (f"\n    {c['evidence']}" if c["evidence"] else "") for c in found]
    parts.append(section("Checks (state vs git and processes)", "\n".join(lines) or "no inconsistency found"))
    if sh:
        commits = []
        for c in git(root, "log", "-15", "--format=%h%x00%B%x01").split("\x01"):
            sha, _, body = c.strip("\n").partition("\x00")
            if sha:
                ids = sorted(set(re.findall(r"\bT-\d+\b", body)))
                commits.append(f"{sha} " + (" ".join(ids) if ids else "") + " (subject removed)")
        status_txt = "\n".join(f"{ln[:2]} {sh.path(ln[3:]) if not ln[3:].startswith('.dev') else ln[3:]}" for ln in status.splitlines() if len(ln) > 3)
        branches = "\n".join(sh.branch(b) for b in git(root, "branch", "--list", "dev-kit/*", "--format=%(refname:short)").splitlines())
        wt_txt = "\n".join(f"{w['path']} {w.get('head', '')} [{sh.branch(w.get('branch') or '(detached)')}]" + (" locked" if w.get("locked") else "")
                           for w in worktrees(root))
    else:
        commits = [git(root, "log", "--oneline", "-15").rstrip()]
        status_txt, branches, wt_txt = git(root, "status", "--short").rstrip(), git(root, "branch", "--list", "dev-kit/*").rstrip(), git(root, "worktree", "list").rstrip()
    parts.append(section("git", "\n".join(["$ git status --short", status_txt, "$ git worktree list", wt_txt,
                                           "$ git branch --list 'dev-kit/*'", branches, "$ git log -15", "\n".join(commits)])))
    open_tasks = {k: v for k, v in tasks.items() if isinstance(v, dict) and v.get("status") not in FINISHED}
    keep = ("title", "milestone", "type", "status", "deps", "files", "started_at", "blocked_reason", "blocked_count", "question",
            "branch", "tier", "resumed_from")
    rows = {}
    for k, v in open_tasks.items():
        r = {f: v.get(f) for f in keep if v.get(f) not in (None, [], "")}
        if sh:
            r.pop("title", None)
            if "files" in r:
                r["files"] = [sh.path(f) for f in r["files"]]
            if "blocked_reason" in r:
                r["blocked_reason"] = sh.free(r["blocked_reason"])
            if "branch" in r:
                r["branch"] = sh.branch(str(r["branch"]))
            r = scrub_json(r, sh)
        else:
            r = scrub_json(r)
        rows[k] = r
    parts.append(section(f"Tasks not done ({len(open_tasks)} of {len(tasks)})", json.dumps(rows, indent=1, ensure_ascii=False), "json"))
    ms = st.get("milestones") if isinstance(st.get("milestones"), dict) else {}
    parts.append(section("Milestones", "\n".join(f"{k}: gate {v.get('gate')} score {v.get('score')} qa_runs {v.get('qa_runs')}"
                                                 for k, v in ms.items() if isinstance(v, dict))))
    runs = []
    files = sorted(run.glob("*.json")) if run.is_dir() else []
    files += sorted((run / "slots").glob("*.json")) if (run / "slots").is_dir() else []
    for f in files:
        rel = f.relative_to(dev).as_posix()
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            body = json.dumps(scrub_json(data, sh), indent=1, ensure_ascii=False)[:3000]
        except (OSError, json.JSONDecodeError):
            body = "(not JSON: left out)"
        runs.append(f"--- .dev/{rel}\n{body}")
    if (run / "autopilot.stop").exists():
        runs.append("--- .dev/run/autopilot.stop (present)")
    parts.append(section("Run files", "\n".join(runs)))
    parts.append(section(f".dev/log.md (last {n})", "\n".join(log_line(x, sh) for x in tail(dev / "log.md", n).splitlines())))
    oq = tail(dev / "open-questions.md", 60)
    if sh:
        oq = "\n".join(sorted({f"{q} " + ("open" if re.search(r"(?i)\bopen\b", ln) else "") for ln in oq.splitlines() for q in re.findall(r"\bQ-\d+\b", ln)}))
    parts.append(section("Open questions", oq if sh else redact(oq)))
    parts.append(section(f"Autopilot log (last {n // 2} lines)", claude_log(tail(run / "autopilot.log", n // 2), sh)))
    rlogs = sorted((run / "rounds").glob("*.log"), key=lambda p: p.stat().st_mtime) if (run / "rounds").is_dir() else []
    for p in rlogs[-3:]:
        size = p.stat().st_size
        parts.append(section(f"Round log {p.name} ({size} bytes)", claude_log(tail(p, 40), sh) if size else "(empty: `claude -p` writes only at the end)"))
    try:
        import dev_ledger as led
        tasks_led = {k: v for k, v in led.load(dev).items() if k.startswith("task:")}
        if sh:
            tasks_led = {k: {f: (sh.free(x) if f == "note" else sh.branch(str(x)) if f == "ref" and x else x)
                             for f, x in v.items() if f in ("result", "at", "ref", "note")} for k, v in tasks_led.items()}
        parts.append(section("Ledger (task records)", json.dumps(scrub_json(tasks_led, sh), indent=1, ensure_ascii=False)[:6000], "json"))
    except Exception:  # noqa: BLE001 - a dump never fails on one part
        pass
    parts.append(section(f"Telemetry (last {n // 2} events; allowlisted ids, tokens and numbers)", redact(tail(dev / "telemetry.jsonl", n // 2))))
    trace = []
    for ln in tail(run / "hook-trace.jsonl", 20).splitlines():
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue
        trace.append(json.dumps({k: d.get(k) for k in ("ts", "event", "tool", "permission_mode", "answered", "elapsed_s")
                                 if k in d} | ({"decision": ((d.get("decision") or {}).get("behavior"))} if d.get("decision") else {})))
    parts.append(section("Hook trace (last 20)", "\n".join(trace)))
    text = "".join(parts)
    text = sh.text(text)
    leaks = sh.leaks(text)
    if leaks:
        raise LeakError(leaks)
    return text, found


class LeakError(Exception):
    def __init__(self, leaks: list[str]):
        super().__init__(", ".join(leaks))
        self.leaks = leaks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out")
    d.add_argument("--tail", type=int, default=80)
    d.add_argument("--json", action="store_true")
    d.add_argument("--share", action="store_true", help="anonymised, for someone else: see the module help")
    c = sub.add_parser("check")
    c.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    if not (root / ".dev" / "state.json").is_file():
        print(f"no dev-kit project at {root} (.dev/state.json missing)", file=sys.stderr)
        return 2
    if a.cmd == "check":
        found = checks(root)
        if a.json:
            print(json.dumps(found, indent=1, ensure_ascii=False))
        else:
            for x in found:
                print(f"[{x['level']}] {x['code']}: {x['text']}" + (f" ({x['evidence']})" if x["evidence"] else ""))
            if not found:
                print("no inconsistency found")
        return 1 if any(x["level"] == "error" for x in found) else 0
    try:
        text, found = dump(root, max(10, a.tail), a.share)
    except LeakError as e:
        print("dump refused: the text still holds " + "; ".join(e.leaks[:10])
              + ". Nothing was written; report this as a dev-kit bug (the names above are what leaked).", file=sys.stderr)
        return 3
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    out = Path(a.out) if a.out else root / ".dev" / "run" / "debug" / (f"dump-share-{stamp}.md" if a.share else f"dump-{stamp}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if a.json:
        print(json.dumps({"path": str(out), "checks": found, "share": a.share}, indent=1, ensure_ascii=False))
    else:
        print(out)
        errs = sum(1 for x in found if x["level"] == "error")
        print(f"{len(found)} finding(s), {errs} error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
