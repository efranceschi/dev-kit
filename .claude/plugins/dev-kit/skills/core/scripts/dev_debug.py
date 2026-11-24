#!/usr/bin/env python3
"""dev_debug.py - a diagnostic dump of a dev-kit project, for /dev-kit:debug and for patches to the kit.

Standard library only. Read-only for the project: it reads .dev/ and git, runs consistency checks between them, and
writes one Markdown file under .dev/run/debug/ (machine-local, never committed). Nothing is sent anywhere.

  dump [--out PATH] [--tail N] [--json]   write the dump; --json prints {path, checks} instead of the path
  check [--json]                          only the consistency checks (exit 1 when one is an error)

The dump holds: the kit and tool versions, the checks, git (status, worktrees, branches, recent commits), the tasks
that are not done, the run files (.dev/run/*.json: autopilot, round, slots, activity), the end of .dev/log.md, of the
autopilot log and of the round logs, the ledger's task records and the last telemetry events. It never copies the
project's source files or the environment. The home folder is written as `~`. Read it before you share it.
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


def dump(root: Path, n: int) -> tuple[str, list[dict]]:
    dev = root / ".dev"
    st = read_json(dev / "state.json")
    tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
    found = checks(root)
    run = dev / "run"
    parts = [f"# dev-kit debug dump\n\nWritten {now()} by dev_debug.py. Read it before sharing: it holds task titles, paths and "
             "log lines of this project, never source files or the environment.\n",
             section("Versions", "\n".join([f"dev-kit {kit_version()} (state written by {st.get('kit_version') or '?'})",
                                            f"python {platform.python_version()} · {platform.system()} {platform.release()}",
                                            (git(root, "--version") or "git ?").strip(),
                                            f"work branch: {((st.get('autonomy') or {}).get('git') or {}).get('base_branch') or git(root, 'rev-parse', '--abbrev-ref', 'HEAD').strip()}"]))]
    lines = [f"[{c['level']}] {c['code']}: {c['text']}" + (f"\n    {c['evidence']}" if c["evidence"] else "") for c in found]
    parts.append(section("Checks (state vs git and processes)", "\n".join(lines) or "no inconsistency found"))
    parts.append(section("git", "\n".join([
        "$ git status --short", git(root, "status", "--short").rstrip(),
        "$ git worktree list", git(root, "worktree", "list").rstrip(),
        "$ git branch --list 'dev-kit/*'", git(root, "branch", "--list", "dev-kit/*").rstrip(),
        "$ git log --oneline -15", git(root, "log", "--oneline", "-15").rstrip()])))
    open_tasks = {k: v for k, v in tasks.items() if isinstance(v, dict) and v.get("status") not in FINISHED}
    keep = ("title", "milestone", "type", "status", "deps", "files", "started_at", "blocked_reason", "blocked_count", "question",
            "branch", "tier", "resumed_from")
    parts.append(section(f"Tasks not done ({len(open_tasks)} of {len(tasks)})",
                         json.dumps({k: {f: v.get(f) for f in keep if v.get(f) not in (None, [], "")} for k, v in open_tasks.items()},
                                    indent=1, ensure_ascii=False), "json"))
    ms = st.get("milestones") if isinstance(st.get("milestones"), dict) else {}
    parts.append(section("Milestones", "\n".join(f"{k}: gate {v.get('gate')} score {v.get('score')} qa_runs {v.get('qa_runs')}"
                                                 for k, v in ms.items() if isinstance(v, dict))))
    runs = []
    for f in sorted(run.glob("*.json")) if run.is_dir() else []:
        runs.append(f"--- .dev/run/{f.name}\n{f.read_text(encoding='utf-8', errors='replace')[:3000].rstrip()}")
    for f in sorted((run / "slots").glob("*.json")) if (run / "slots").is_dir() else []:
        runs.append(f"--- .dev/run/slots/{f.name}\n{f.read_text(encoding='utf-8', errors='replace')[:2000].rstrip()}")
    for f in (run / "autopilot.stop",):
        if f.exists():
            runs.append(f"--- .dev/run/{f.name} (present)")
    parts.append(section("Run files", "\n".join(runs)))
    parts.append(section(f".dev/log.md (last {n})", tail(dev / "log.md", n)))
    parts.append(section("Open questions", tail(dev / "open-questions.md", 60)))
    parts.append(section(f"Autopilot log (last {n // 2} lines)", tail(run / "autopilot.log", n // 2)))
    rlogs = sorted((run / "rounds").glob("*.log"), key=lambda p: p.stat().st_mtime) if (run / "rounds").is_dir() else []
    for p in rlogs[-3:]:
        size = p.stat().st_size
        parts.append(section(f"Round log {p.name} ({size} bytes)", tail(p, 40) if size else "(empty: `claude -p` writes only at the end)"))
    try:
        import dev_ledger as led
        tasks_led = {k: v for k, v in led.load(dev).items() if k.startswith("task:")}
        parts.append(section("Ledger (task records)", json.dumps(tasks_led, indent=1, ensure_ascii=False)[:6000], "json"))
    except Exception:  # noqa: BLE001 - a dump never fails on one part
        pass
    parts.append(section(f"Telemetry (last {n // 2} events)", tail(dev / "telemetry.jsonl", n // 2)))
    parts.append(section("Hook trace (last 20)", tail(run / "hook-trace.jsonl", 20)))
    text = "".join(parts)
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    return text, found


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out")
    d.add_argument("--tail", type=int, default=80)
    d.add_argument("--json", action="store_true")
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
    text, found = dump(root, max(10, a.tail))
    out = Path(a.out) if a.out else root / ".dev" / "run" / "debug" / f"dump-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if a.json:
        print(json.dumps({"path": str(out), "checks": found}, indent=1, ensure_ascii=False))
    else:
        print(out)
        errs = sum(1 for x in found if x["level"] == "error")
        print(f"{len(found)} finding(s), {errs} error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
