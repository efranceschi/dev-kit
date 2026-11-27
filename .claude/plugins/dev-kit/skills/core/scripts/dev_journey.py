#!/usr/bin/env python3
"""dev_journey.py - the journey of a project: every step the kit recorded, from the first command to now.

Standard library only, read-only. Nothing new is recorded for it: the journey is rebuilt from what the kit already
keeps, always the same way for the same files (no model, no guess), when someone asks for it:

  .dev/log.md           every state change (artifacts, plan, tasks, gates, reviews, releases, flags, deploys, questions,
                        issues), one timestamped line each, never cut
  .dev/telemetry.jsonl  the session log: skill runs and agents (start and end), never cut
  .dev/state.json       milestones and releases (which release a milestone belongs to, when it passed, when it shipped)
  .dev/costs/milestones.json  the estimated cost per milestone (dev_cost.py ingest), when there is one
  .dev/run/prod-health.json   the production health checks, when there are any

  build [--json]    print the journey (the board's Journey tab reads the same thing from /api/journey)

Output: lanes (the phases of the flow plus "inbox" for questions and issues), categories (the filters), items
(`t` start and `e` end in epoch seconds, `l` lane, `c` category, `k` kind, `r` the task, milestone or release it is
about, `m` its milestone, `v` its values, `s` a status), and the bands of the milestones and releases with their
duration and cost. Times in the files are UTC; the page shows them in the viewer's time zone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # -I drops the script dir
import dev_state as ds  # noqa: E402
import dev_ids as dids  # noqa: E402

VERSION = 1
LANES = ("conception", "planning", "construction", "releases", "stable", "inbox")
CATS = ("docs", "skills", "agents", "tasks", "checks", "delivery", "inbox")
TEXT_MAX = 160          # free text (reasons, questions, titles) is cut to this
OPEN_RUN_S = 12 * 3600  # a skill or agent start with no end, older than this, did not end (it is not running)
HEALTH_KEEP = 400       # production health checks kept (the newest)
# skills that only show or set up the project: not a step of its journey
QUIET_SKILLS = {"board", "spog", "help", "status", "costs", "debug", "settings"}
SKILL_LANE = {
    "start": "conception", "interview": "conception", "prd": "conception", "architecture": "conception", "ux": "conception",
    "ui": "conception", "diagram": "conception", "plan": "planning", "issue": "planning", "backlog": "planning",
    "implement": "construction", "qa": "construction", "test": "construction", "autopilot": "construction",
    "usability": "releases", "docs": "releases", "release": "releases", "deploy": "releases", "feedback": "stable",
}
REVIEW_LANE = {"prd": "conception", "design": "conception", "plan": "planning", "docs": "releases", "ux": "releases"}
CONCEPTION_ARTIFACTS = {"brief", "interview", "prd", "architecture", "ux", "ui", "design"}

T = rf"(?P<task>{dids.TASK})"
M = rf"(?P<milestone>{dids.MILESTONE})"
# (kind, category, lane or None for "decided by the values", pattern) over the text of a log.md line
LOG_RULES = (
    ("init", "docs", "conception", re.compile(r"^init (?P<how>created|updated)\b")),
    ("artifact", "docs", None, re.compile(r"^artifact mark (?P<names>[^(]+?)(?: \((?P<note>.*)\))?$")),
    ("plan_sync", "docs", "planning", re.compile(r"^sync-plan (?P<text>.*)$")),
    ("plan_edit", "docs", "planning", re.compile(r"^(?P<op>move-task|new-milestone|reorder|plan-apply): (?P<text>.*)$")),
    ("task_start", "tasks", "construction", re.compile(rf"^start {T}(?: (?P<title>.*?))?(?: tier=(?P<tier>\S+) arm=(?P<arm>\S+))?$")),
    ("task_done", "tasks", "construction", re.compile(rf"^done {T}(?P<fix> commit corrected)?(?:.*?commit=(?P<commit>\w+))?")),
    ("task_blocked", "tasks", "construction", re.compile(rf"^block {T}: (?P<reason>.*)$")),
    ("task_unblocked", "tasks", "construction", re.compile(rf"^unblock {T}$")),
    ("task_dropped", "tasks", "construction", re.compile(rf"^drop {T}: (?P<reason>.*)$")),
    ("task_reopened", "tasks", "construction", re.compile(rf"^reopen {T}: (?P<reason>.*)$")),
    ("freeze", "checks", "construction", re.compile(rf"^freeze {M}:")),
    ("hard_floor", "checks", "construction", re.compile(rf"^hard-floor {M}: (?P<result>.*)$")),
    ("ci", "checks", "construction", re.compile(rf"^ci {M} (?P<status>\S+)")),
    ("gate", "checks", "construction", re.compile(rf"^gate {M} (?P<value>passed|pending|failed|skipped)(?: score=(?P<score>\d+))?(?: \((?P<reason>.*)\))?")),
    ("challenge", "checks", "construction", re.compile(rf"^challenge {M} (?P<finding>\S+): (?P<verdict>\S+)")),
    ("qa_decide", "checks", "construction", re.compile(rf"^qa-decide {M} (?P<decision>\S+)")),
    ("review", "checks", None, re.compile(r"^review (?P<name>\S+) (?P<value>\S+)(?: score=(?P<score>\d+))?")),
    ("checkpoint", "checks", None, re.compile(r"^checkpoint (?P<target>prd|plan) (?P<decision>confirm|adjust)")),
    ("preview", "delivery", "construction", re.compile(rf"^preview {M} (?P<status>stopped|\S+)")),
    ("release_submitted", "delivery", "releases", re.compile(r"^release (?P<release>" + dids.RELEASE + r") submitted for approval")),
    ("release_approved", "delivery", "releases", re.compile(r"^release (?P<release>" + dids.RELEASE + r") approved")),
    ("release_rejected", "delivery", "releases", re.compile(r"^release (?P<release>" + dids.RELEASE + r") rejected: (?P<reason>.*?)(?: \([^)]*\))?$")),
    ("released", "delivery", "releases", re.compile(r"^release (?P<version>[^\sR][^\s]*) \((?P<tag>[^)]*)\): (?P<what>.*)$")),
    ("flag", "delivery", "releases", re.compile(r"^flag (?P<name>\S+) (?P<event>\S+)")),
    ("deploy", "delivery", "releases", re.compile(r"^deploy (?P<env>\S+) (?P<status>\S+) (?P<sha>\S+)")),
    ("prod_failed", "delivery", "stable", re.compile(r"^prod-check failed \((?P<detail>.*?)\): (?P<issue>" + dids.ISSUE + r")")),
    ("cooldown", "inbox", "stable", re.compile(rf"^cooldown {M}->(?P<next>\S+): (?P<text>.*)$")),
    ("question_open", "inbox", "inbox", re.compile(r"^add-question (?P<id>" + dids.QUESTION + r") \((?P<skill>[^)]*)\): (?P<text>.*)$")),
    ("question_answered", "inbox", "inbox", re.compile(r"^answer-question (?P<id>" + dids.QUESTION + r"): (?P<text>.*)$")),
    ("issue_new", "inbox", "inbox", re.compile(r"^add-issue (?P<id>" + dids.ISSUE + r") \((?P<type>[a-z]+)/(?P<cls>[a-z-]+)\) (?P<text>.*)$")),
    ("issue_pulled", "inbox", "planning", re.compile(rf"^pull-issues {M}: (?P<text>.*)$")),
)
LOG_LINE = re.compile(r"^- (?P<at>\S+) (?P<text>.*)$")


def epoch(v: object) -> int | None:
    """Seconds since 1970 of an ISO time (naive is UTC), or None."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp())


def _cut(v: object) -> str:
    s = " ".join(str(v).split())
    return s if len(s) <= TEXT_MAX else s[: TEXT_MAX - 1] + "…"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _item(t: int, lane: str, cat: str, kind: str, ref: str = "", vars_: dict | None = None, **extra) -> dict:
    it = {"t": t, "l": lane, "c": cat, "k": kind}
    if ref:
        it["r"] = ref
    vs = {k: (_cut(v) if isinstance(v, str) else v) for k, v in (vars_ or {}).items() if v not in (None, "")}
    if vs:
        it["v"] = vs
    it.update({k: v for k, v in extra.items() if v not in (None, "")})
    return it


def _log_items(text: str, task_ms: dict) -> list[dict]:
    """Every log.md line the journey shows, task runs paired into bars (start to done, block, drop or the next start)."""
    out: list[dict] = []
    open_runs: dict[str, dict] = {}
    for line in text.splitlines():
        lm = LOG_LINE.match(line)
        if not lm:
            continue
        t = epoch(lm["at"])
        if t is None:
            continue
        body = lm["text"]
        for kind, cat, lane, rx in LOG_RULES:
            mm = rx.match(body)
            if not mm:
                continue
            v = {k: x for k, x in mm.groupdict().items() if x is not None}
            if kind == "artifact":
                names = [n.strip() for n in v["names"].split(",") if n.strip() and n.strip() != "-"]
                if not names:
                    break
                for n in names:
                    base = n.split("/")[0]
                    out.append(_item(t, "planning" if base == "plan" else "conception" if base in CONCEPTION_ARTIFACTS else "construction",
                                     cat, kind, n, {"name": n, "note": v.get("note")}))
                break
            if kind == "review":
                lane = REVIEW_LANE.get(v["name"], "releases")
            elif kind == "checkpoint":
                lane = "conception" if v["target"] == "prd" else "planning"
            task = v.pop("task", None)
            ms = v.get("milestone") or (task_ms.get(task) if task else None)
            if kind == "task_start":
                prev = open_runs.pop(task, None)
                if prev:
                    prev.update(e=t, s="restarted")
                run = _item(t, lane, cat, "task", task, {"title": v.get("title"), "tier": v.get("tier"), "arm": v.get("arm")}, m=ms, s="running")
                open_runs[task] = run
                out.append(run)
            elif kind in ("task_done", "task_blocked", "task_dropped") and task in open_runs and not v.get("fix"):
                run = open_runs.pop(task)
                run.update(e=t, s={"task_done": "done", "task_blocked": "blocked", "task_dropped": "dropped"}[kind])
                if v.get("commit"):
                    run.setdefault("v", {})["commit"] = v["commit"]
                if v.get("reason"):
                    run.setdefault("v", {})["reason"] = _cut(v["reason"])
                if kind != "task_done":  # a block or a drop is also a mark of its own
                    out.append(_item(t, lane, cat, kind, task, v, m=ms))
            elif kind == "task_done":
                if not v.get("fix"):
                    out.append(_item(t, lane, cat, kind, task, v, m=ms))
            else:
                ref = (task or v.get("milestone") or v.get("release") or v.get("id") or v.get("version")
                       or (v.get("name") if kind == "review" else None) or v.get("target") or "")
                if kind == "gate" and v.get("score"):
                    v["score"] = int(v["score"])
                if kind == "review" and v.get("score"):
                    v["score"] = int(v["score"])
                out.append(_item(t, lane, cat, kind, ref, v, m=ms))
            break
    return out


def _session_runs(events: list[dict], now: int) -> list[dict]:
    """Skill runs and agents from the session log, each start paired with its end."""
    out: list[dict] = []
    skills: dict[tuple, dict] = {}
    agents: dict[tuple, dict] = {}
    last_skill: dict[str, dict] = {}   # session -> its latest skill run, the owner of an agent with no task

    def close_stale(run: dict, at: int) -> None:
        run.update(e=at, s="no_end")

    # in time order (a log appended out of order still pairs each start with its end); sorted() keeps ties in file order
    for e in sorted(events, key=lambda x: epoch(x.get("ts")) or 0):
        ev, t = e.get("event"), epoch(e.get("ts"))
        if t is None:
            continue
        sess = str(e.get("session") or "")
        if ev in ("skill_start", "skill_end"):
            skill = str(e.get("skill") or "")
            if not skill or skill in QUIET_SKILLS:
                continue
            key = (sess, skill)
            if ev == "skill_start":
                if key in skills:
                    close_stale(skills.pop(key), t)
                scope = str(e.get("scope") or "")
                lane = REVIEW_LANE.get(scope, "releases") if skill == "review" else SKILL_LANE.get(skill, "construction")
                run = _item(t, lane, "skills", "skill", scope, {"skill": skill, "args": e.get("args_kind")},
                            m=scope if dids.is_id("milestone", scope) else None, s="running")
                skills[key] = run
                last_skill[sess] = run
                out.append(run)
            else:
                run = skills.pop(key, None)
                status = str(e.get("status") or "ok")
                if run is None:  # an end with no start (log cut by hand): a point
                    run = _item(t, SKILL_LANE.get(skill, "construction"), "skills", "skill", str(e.get("scope") or ""), {"skill": skill})
                    run["t"] = t - int(e.get("duration_s") or 0)
                    out.append(run)
                run.update(e=t, s="failed" if status in ("failed", "error") else status)
        elif ev in ("agent_spawn", "agent_end"):
            agent = str(e.get("agent") or "agent").split(":")[-1]
            scope = str(e.get("scope") or "")
            key = (str(e["agent_id"]),) if e.get("agent_id") else (sess, agent, scope, e.get("slot"))
            if ev == "agent_spawn":
                if key in agents:
                    close_stale(agents.pop(key), t)
                owner = last_skill.get(sess)
                lane = "construction" if re.match(rf"^({dids.TASK}|{dids.MILESTONE}|GATE:)", scope) else (owner["l"] if owner else "construction")
                ms = scope[5:] if scope.startswith("GATE:") else scope if dids.is_id("milestone", scope) else None
                run = _item(t, lane, "agents", "agent", scope, {"agent": agent, "model": e.get("model"), "effort": e.get("effort"),
                                                                 "skill": e.get("skill") or (owner["v"]["skill"] if owner else None)}, m=ms, s="running")
                agents[key] = run
                out.append(run)
            else:
                run = agents.pop(key, None)
                if run is None:
                    continue
                run.update(e=t, s=str(e.get("status") or "ok"))
                for k in ("tokens", "findings"):
                    if e.get(k) not in (None, "", {}):
                        run.setdefault("v", {})[k] = e[k]
    for run in list(skills.values()) + list(agents.values()):  # never ended: running if recent, else it just stopped
        if now - run["t"] > OPEN_RUN_S:
            run.update(e=run["t"], s="no_end")
    return out


def _health_items(dev: Path) -> list[dict]:
    checks = [c for c in (_json(dev / "run" / "prod-health.json").get("checks") or []) if isinstance(c, dict)][-HEALTH_KEEP:]
    out = []
    for c in checks:
        t = epoch(c.get("at"))
        if t is not None:
            out.append(_item(t, "stable", "delivery", "health", "", {"detail": c.get("detail"), "issue": c.get("issue")}, s="ok" if c.get("ok") else "failed"))
    return out


def _bands(state: dict, items: list[dict], dev: Path, now: int) -> tuple[list[dict], list[dict]]:
    """Milestones (first task start to the gate) and releases (first milestone to the version shipped), with cost."""
    ms_state = state.get("milestones") or {}
    costs = (_json(dev / "costs" / "milestones.json").get("milestones") or {})
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    passed: dict[str, int] = {}
    for it in items:
        m = it.get("m")
        if not m:
            continue
        first[m] = min(first.get(m, it["t"]), it["t"])
        last[m] = max(last.get(m, 0), it.get("e") or it["t"])
        if it["k"] == "gate" and (it.get("v") or {}).get("value") in ("passed", "skipped"):
            passed[m] = it["t"]
    order = [m for m in ms_state if m in first]
    order.sort(key=lambda m: (first[m], m))
    milestones = []
    for m in order:
        info = ms_state.get(m) or {}
        done = epoch(info.get("passed_at")) or passed.get(m) if info.get("gate") in ("passed", "skipped") else None
        c = costs.get(m) if isinstance(costs.get(m), dict) else {}
        tasks = [it for it in items if it["k"] == "task" and it.get("m") == m]
        milestones.append({"id": m, "title": _cut(info.get("title") or ""), "release": info.get("release"),
                           "from": first[m], "to": done or None, "status": "done" if done else "active",
                           "usd": c.get("usd"), "tokens": c.get("tokens"), "tasks": len({it.get("r") for it in tasks}),
                           "qa_runs": int(info.get("qa_runs") or 0), "score": info.get("score")})
    shipped: dict[str, dict] = {}
    for r in state.get("releases") or []:
        if isinstance(r, dict) and r.get("release") and epoch(r.get("at")):
            shipped.setdefault(str(r["release"]), r)
    rel_ids: list[str] = []
    for mb in milestones:
        if mb["release"] and mb["release"] not in rel_ids:
            rel_ids.append(mb["release"])
    releases = []
    for rid in rel_ids:
        mine = [mb for mb in milestones if mb["release"] == rid]
        sh = shipped.get(rid)
        usd = [mb["usd"] for mb in mine if isinstance(mb.get("usd"), (int, float))]
        releases.append({"id": rid, "from": min(mb["from"] for mb in mine), "to": epoch(sh.get("at")) if sh else None,
                         "status": "released" if sh else "active", "version": sh.get("version") if sh else None,
                         "milestones": [mb["id"] for mb in mine], "usd": round(sum(usd), 2) if usd else None})
    return milestones, releases


def build(root: Path) -> dict:
    """The journey of the project at root, or {"ok": False, ...} when it has no dev-kit state."""
    store = ds.Store(root)
    if not store.exists():
        return {"ok": False, "error": "no_state"}
    dev = store.dev
    state = _json(dev / "state.json")
    if not state:
        return {"ok": False, "error": "corrupt_state"}
    now = epoch(ds.now()) or 0
    task_ms = {tid: t.get("milestone") for tid, t in (state.get("tasks") or {}).items() if isinstance(t, dict)}
    events, _ = ds.tel.read_events(dev)
    items = _log_items(_read(dev / "log.md"), task_ms) + _session_runs(events, now) + _health_items(dev)
    for it in items:   # a task run's milestone also labels its agents (scope T-xxx)
        if it["k"] == "agent" and not it.get("m") and it.get("r") in task_ms:
            it["m"] = task_ms[it["r"]]
    items.sort(key=lambda it: (it["t"], LANES.index(it["l"]), CATS.index(it["c"]), it["k"], it.get("r", "")))
    milestones, releases = _bands(state, items, dev, now)
    counts = {c: sum(1 for it in items if it["c"] == c) for c in CATS}
    created = epoch(state.get("created_at"))
    start = min([it["t"] for it in items] + ([created] if created else [])) if items or created else now
    return {"ok": True, "version": VERSION, "project": state.get("project") or root.name, "generated_at": now,
            "start": start, "end": max([now] + [it.get("e") or it["t"] for it in items]),
            "lanes": list(LANES), "cats": list(CATS), "counts": counts, "items": items,
            "milestones": milestones, "releases": releases}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dev_journey.py", description="The journey of a dev-kit project, rebuilt from .dev/.")
    ap.add_argument("--root", default=".", help="the project folder (default: the current one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="print the journey")
    b.add_argument("--json", action="store_true", help="the whole journey as JSON (default: a summary)")
    a = ap.parse_args(argv)
    j = build(Path(a.root).resolve())
    if not j.get("ok"):
        print(f"no dev-kit project at {a.root} ({j.get('error')})", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(j, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    days = max(1, round((j["end"] - j["start"]) / 86400))
    print(f"{j['project']}: {len(j['items'])} steps over {days} days, {len(j['milestones'])} milestones, {len(j['releases'])} releases")
    for c in CATS:
        print(f"  {c:9} {j['counts'][c]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
