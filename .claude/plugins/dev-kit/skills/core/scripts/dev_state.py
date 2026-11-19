#!/usr/bin/env python3
"""dev_state.py - single source of truth for dev-kit project state (.dev/state.json).

Standard library only. Run with: python3 -I dev_state.py <subcommand> [...]

Subcommands
  init          create .dev/ and state.json (idempotent; updates given fields)
  sync-plan     read .dev/plan.md and add/update milestones and tasks (never touches status)
  next          print the next task to work on (fix tasks first, deps satisfied, gate respected)
  start T       mark task in_progress
  done T        mark task done (optionally --commit SHA)
  block T       mark task blocked (--reason)
  unblock T     blocked -> todo
  add-task      create a task in state and plan.md
  add-question  append a non-blocking question to open-questions.md
  gate M        set milestone gate: passed | pending | skipped (passed needs --score >= cut-off)
  review NAME   record a review (prd|design|plan|docs...): pass | fail | pending (pass needs --score >= cut-off)
  event TYPE    append an allowlisted event to .dev/telemetry.jsonl (--set k=v, --json)
  feedback      brief feedback about the dev-kit (--worked/--failed/--improve area:note)
  telemetry     summary | report | export [--all | --since D] [--json] [--out FILE] [--events]: session log, per-stage grades, export
  cleanup       kill agents' leftover processes recorded in .dev/run/*.pids (only inside this project)
  add-issue     register a bug / improvement / change in the queue (--type --class --title ...), conventions §15
  issue I       show or update an issue (--status --class --link T --duplicate-of I --note)
  pull-issues M fill the milestone's issue buffer from the queue (never creates milestones)
  cooldown M    after M's gate: small issues into the next milestone (lane cooldown), if enabled
  backlog       everything pending: issues, tasks, questions, deferred findings, deploys (--json)
  tip CTX       one contextual tip (tips each show at most twice); tips [--reset] lists them all
  deploy [ENV]  record a deploy (--sha --status ok|failed|rolled_back [--milestone M] [--migration REV])
  preview M     record the local deploy of a milestone (--url --sha [--pid]) or --stopped
  set KEY VAL   set language | phase | project | autonomy.<field> (incl. autonomy.pause_policy.<point>)
  status        human (--short) or --json view; --quiet-if-missing for hooks

Exit codes: 0 ok · 1 usage/invalid transition · 2 state not found · 3 nothing to do (next)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir; dev_telemetry lives next to us
import dev_telemetry as tel  # noqa: E402

STATE_VERSION = 1
PHASES = [
    "init", "interview", "prd", "architecture", "ux", "ui", "plan",
    "implement", "qa", "usability", "docs", "done",
]
TASK_TYPES = {"feature", "fix", "chore", "test", "docs"}
TASK_STATUSES = {"todo", "in_progress", "done", "blocked"}
GATES = {"passed", "pending", "skipped"}

DEFAULT_AUTONOMY = {
    "level": "high",
    "decide_alone": [
        "library_choice", "file_structure", "naming", "test_strategy", "ui_details",
        "minor_scope_tradeoffs", "dev_tooling", "data_model_details",
    ],
    "always_ask": [
        "paid_services", "delete_data", "public_exposure", "scope_change_major",
        "security_model_change", "credentials", "model_escalation",
    ],
    "max_fix_rounds_per_gate": 3,
    # Model/effort ladder for agents (conventions.md §9). mode: ask (confirm before each escalation) |
    # preapproved (escalate within the approved ladder without asking) | off (never escalate).
    # tiers: optional per-agent tier overrides, e.g. {"copy-reviewer": "balanced"}.
    "model_policy": {"mode": "ask", "tiers": {}},
    # What to do at each pause point (conventions.md §10). Default: ask, i.e. the supervised behaviour.
    "pause_policy": {},
    "on_park": "stop_when_idle",
    "notify_on_park": False,
    # Local deploy at the end of each approved milestone (conventions.md §11).
    "local_deploy": {"mode": "off", "port": None, "notify": False},
    # Issues (conventions.md §15): share of each milestone reserved for queued issues, optional cool-down.
    "issue_buffer_pct": 20,
    "cooldown": {"enabled": False, "max_tasks": 5},
    # Contextual tips (shared/tips.json): on (each tip at most twice) | off | always.
    "tips": "on",
    # Production deploy (conventions.md §12). when: per_milestone | on_release | manual | none.
    "production": {"when": "none", "method": None, "host": None, "targets": [], "smoke": [], "prerequisites": []},
    "task_time_budget_min": 30,
    "commit_per_task": True,
    "may_install_deps": True,
    "may_run_servers": True,
    "may_push": False,
    "quality": {
        "min_overall": 85,
        "min_dimension": 70,
        "dimension_min": {"security": 90, "tests": 80, "spec": 85, "a11y": 80},
        "review_min_overall": 80,
        "low_cap": 10,
        "weights": {
            "code": 15, "security": 15, "tests": 15, "spec": 15, "ux": 8, "a11y": 8,
            "visual": 6, "copy": 3, "performance": 6, "data": 4, "operations": 3,
            "dependencies": 2, "docs": 5, "design": 10, "requirements": 10,
        },
    },
}

MODEL_POLICY_MODES = ("ask", "preapproved", "off")
MODEL_TIERS = ("speed", "balanced", "quality")


def check_model_policy(mp: object) -> None:
    if not isinstance(mp, dict):
        fail("autonomy.model_policy must be an object like {\"mode\": \"ask\", \"tiers\": {}}")
    if mp.get("mode", "ask") not in MODEL_POLICY_MODES:
        fail(f"autonomy.model_policy.mode must be one of {', '.join(MODEL_POLICY_MODES)}")
    tiers = mp.get("tiers", {})
    if not isinstance(tiers, dict) or any(v not in MODEL_TIERS for v in tiers.values()):
        fail(f"autonomy.model_policy.tiers must map agent names to one of {', '.join(MODEL_TIERS)}")


# Pause points and the actions each one accepts. The floors live here, not only in the interview:
# scope changes and missing credentials can never be decided alone, production data is never deleted.
PAUSE_ACTIONS = {
    "paid_services": ("ask", "preauthorize", "park"),
    "delete_data": ("ask", "preauthorize", "park"),
    "public_exposure": ("ask", "preauthorize", "park"),
    "scope_change_major": ("ask", "park"),
    "security_model_change": ("ask", "auto_recommend", "park"),
    "credentials": ("ask", "park"),
    "rounds_exhausted": ("ask", "auto_recommend", "park"),
    "dirty_tree": ("ask", "auto_recommend"),
    "blocked_env": ("ask", "park"),
    "production_deploy": ("ask", "preauthorize", "park"),
}
LIMIT_KEYS = {"paid_services": "max_monthly", "delete_data": "environments", "public_exposure": "targets",
              "production_deploy": "targets"}
PROD_NAMES = {"prod", "production", "prd", "live"}
ON_PARK = ("stop_when_idle", "stop_first")
UNATTENDED_PAUSE_POLICY = {
    "paid_services": {"action": "park"},
    "delete_data": {"action": "preauthorize", "limit": {"environments": ["dev", "test"]}},
    "public_exposure": {"action": "park"},
    "scope_change_major": {"action": "park"},
    "security_model_change": {"action": "auto_recommend"},
    "credentials": {"action": "park"},
    "rounds_exhausted": {"action": "auto_recommend"},
    "dirty_tree": {"action": "auto_recommend"},
    "blocked_env": {"action": "park"},
    "production_deploy": {"action": "park"},
}


LOCAL_DEPLOY_MODES = ("off", "keep_running", "smoke")
PRODUCTION_WHEN = ("none", "per_milestone", "on_release", "manual")


def check_production(pr: object) -> None:
    if not isinstance(pr, dict) or pr.get("when", "none") not in PRODUCTION_WHEN:
        fail(f"autonomy.production.when must be one of {', '.join(PRODUCTION_WHEN)}")
    for k in ("targets", "smoke", "prerequisites"):
        if not isinstance(pr.get(k, []), list):
            fail(f"autonomy.production.{k} must be a list")
    if pr.get("when", "none") != "none" and not pr.get("method"):
        fail("autonomy.production needs a method (install script, systemd, compose, paas...) when deploys are enabled")


def check_local_deploy(ld: object) -> None:
    if not isinstance(ld, dict) or ld.get("mode", "off") not in LOCAL_DEPLOY_MODES:
        fail(f"autonomy.local_deploy.mode must be one of {', '.join(LOCAL_DEPLOY_MODES)}")
    port = ld.get("port")
    if port is not None and (not isinstance(port, int) or not 1024 <= port <= 65535):
        fail("autonomy.local_deploy.port must be an integer between 1024 and 65535 (or null)")


def check_pause_policy(pp: object) -> None:
    if not isinstance(pp, dict):
        fail("autonomy.pause_policy must be an object {\"<point>\": {\"action\": ...}}")
    for point, rule in pp.items():
        if point not in PAUSE_ACTIONS:
            fail(f"unknown pause point {point}; one of {', '.join(PAUSE_ACTIONS)}")
        if not isinstance(rule, dict) or rule.get("action") not in PAUSE_ACTIONS[point]:
            fail(f"pause_policy.{point}.action must be one of {', '.join(PAUSE_ACTIONS[point])}")
        if rule["action"] == "preauthorize":
            key = LIMIT_KEYS[point]
            limit = rule.get("limit") or {}
            if not isinstance(limit, dict) or not limit.get(key):
                fail(f"pause_policy.{point} preauthorize needs limit.{key}")
            if point == "delete_data" and any(str(e).lower() in PROD_NAMES for e in limit[key]):
                fail("pause_policy.delete_data can never be preauthorized for production")


def pause_action(state: dict, point: str) -> str:
    return state.get("autonomy", {}).get("pause_policy", {}).get(point, {}).get("action", "ask")


def check_policy_force(store: "Store", kind: str, name: str, scores: str | None) -> None:
    """A pass forced by policy (note 'policy:...') must respect the floors: rounds_exhausted is
    auto_recommend, no blocking finding is open and the security dimension met its minimum."""
    if pause_action(store.state, "rounds_exhausted") != "auto_recommend":
        fail("pause_policy.rounds_exhausted is not auto_recommend; a policy --force needs the user's decision")
    if scores:
        path = Path(scores)
    elif kind == "gate":
        path = store.dev / "qa" / name / "scores.json"
    else:
        path = store.dev / ("qa/ux" if name == "ux" else f"reviews/{name}") / "scores.json"
    if not path.is_absolute():
        path = store.root / path
    if not path.exists():
        fail(f"policy --force needs the dev_score.py result at {path} (or --scores)")
    res = json.loads(path.read_text(encoding="utf-8"))
    if res.get("blockers"):
        fail(f"policy --force refused: {len(res['blockers'])} critical/high finding(s) open")
    sec = res.get("dimensions", {}).get("security")
    if sec is not None and not sec.get("ok", False):
        fail("policy --force refused: the security dimension is below its minimum (never forced by policy)")


ISSUE_TYPES = ("bug", "improvement", "change")
ISSUE_CLASSES = ("expedite", "current", "standard", "intangible", "change")
ISSUE_STATUSES = ("open", "scheduled", "in_progress", "done", "wontfix", "duplicate")
ISSUE_SEVERITIES = ("critical", "high", "medium", "low")
ISSUE_ORIGINS = ("user", "qa", "usability", "deploy", "feedback", "review")
LANES = ("hotfix", "cooldown")
CLASS_RANK = {"standard": 0, "intangible": 1}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TIPS_MODES = ("on", "off", "always")


MILESTONE_RE = re.compile(r"^##\s+(M\d+)\s*(?:[—–-]+\s*)?(.*?)\s*$")
TASK_RE = re.compile(r"^###\s+(T-\d{3,})\s+(.*?)\s*$")
FIELD_RE = re.compile(r"^-\s+([a-z_]+):\s*(.*?)\s*$")
SUBITEM_RE = re.compile(r"^\s{2,}-\s+(.*?)\s*$")


# --------------------------------------------------------------------------- helpers

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fail(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(f"dev_state: {msg}", file=sys.stderr)
    sys.exit(code)


def find_root(explicit: str | None) -> Path:
    """Project root: --root if given, else walk up from cwd looking for .dev/state.json, else cwd."""
    if explicit:
        return Path(explicit).resolve()
    cur = Path.cwd().resolve()
    for p in [cur, *cur.parents]:
        if (p / ".dev" / "state.json").exists():
            return p
    return cur


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.dev = root / ".dev"
        self.path = self.dev / "state.json"
        self.state: dict = {}

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict:
        if not self.exists():
            fail(f"no state at {self.path}. Run `dev_state.py init` (or interview) first.", 2)
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fail(f"state.json is corrupt: {e}", 1)
        return self.state

    def save(self) -> None:
        self.state["updated_at"] = now()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def event(self, event: str, **fields) -> None:
        tel.safe_emit(self.dev, event, fields)

    def log(self, line: str) -> None:
        self.dev.mkdir(parents=True, exist_ok=True)
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write(f"- {now()} {line}\n")

    # ---- derived
    def tasks(self) -> dict:
        return self.state.setdefault("tasks", {})

    def milestones(self) -> dict:
        return self.state.setdefault("milestones", {})

    def milestone_order(self) -> list[str]:
        return sorted(self.milestones().keys(), key=lambda m: int(m[1:]))

    def task(self, tid: str) -> dict:
        t = self.tasks().get(tid)
        if t is None:
            fail(f"unknown task {tid}")
        return t

    def new_task_id(self) -> str:
        n = int(self.state.get("next_task_id", 1))
        existing = {int(t[2:]) for t in self.tasks()}
        while n in existing:
            n += 1
        self.state["next_task_id"] = n + 1
        return f"T-{n:03d}"

    def new_question_id(self) -> str:
        n = int(self.state.get("next_question_id", 1))
        self.state["next_question_id"] = n + 1
        return f"Q-{n:03d}"

    def in_progress(self) -> list[str]:
        return [t for t, v in self.tasks().items() if v["status"] == "in_progress"]

    def milestone_done(self, m: str) -> bool:
        ts = [v for v in self.tasks().values() if v["milestone"] == m]
        return bool(ts) and all(v["status"] == "done" for v in ts)

    def gate_open_for(self, m: str) -> tuple[bool, str]:
        """A milestone is workable if every previous milestone has gate passed/skipped (or has no tasks)."""
        for prev in self.milestone_order():
            if prev == m:
                return True, ""
            gate = self.milestones()[prev].get("gate", "pending")
            has_tasks = any(v["milestone"] == prev for v in self.tasks().values())
            if has_tasks and gate == "pending":
                return False, f"gate of {prev} is pending (run qa {prev} or `gate {prev} skipped`)"
        return True, ""

    def progress(self) -> dict:
        ts = self.tasks()
        by_status = {s: 0 for s in TASK_STATUSES}
        for v in ts.values():
            by_status[v["status"]] += 1
        return {"total": len(ts), **by_status}


# --------------------------------------------------------------------------- plan.md parsing

def parse_plan(text: str) -> tuple[dict, dict]:
    """Return (milestones, tasks) parsed from plan.md following shared/conventions.md section 4."""
    milestones: dict = {}
    tasks: dict = {}
    cur_m: str | None = None
    cur_t: str | None = None
    cur_field: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = MILESTONE_RE.match(line)
        if m:
            cur_m, cur_t, cur_field = m.group(1), None, None
            milestones[cur_m] = {"title": m.group(2) or cur_m}
            continue
        t = TASK_RE.match(line)
        if t:
            if cur_m is None:
                raise ValueError(f"task {t.group(1)} appears before any '## Mn' milestone heading")
            cur_t, cur_field = t.group(1), None
            tasks[cur_t] = {
                "title": t.group(2), "milestone": cur_m, "type": "feature", "deps": [],
                "acceptance": [], "test_notes": "", "files": [], "plan_status": "todo",
            }
            continue
        if line.startswith("## ") or line.startswith("# "):
            cur_m, cur_t, cur_field = None, None, None  # non-milestone heading ends context
            continue
        if cur_t is None:
            continue
        f = FIELD_RE.match(line)
        if f:
            key, val = f.group(1), f.group(2)
            cur_field = key
            task = tasks[cur_t]
            if key == "deps":
                task["deps"] = [d.strip() for d in re.split(r"[,\s]+", val) if d.strip()]
            elif key == "files":
                task["files"] = [d.strip() for d in val.split(",") if d.strip()]
            elif key == "acceptance":
                task["acceptance"] = [a.strip() for a in val.split(",") if a.strip()] if val else []
            elif key == "type":
                task["type"] = val.strip() or "feature"
            elif key == "status":
                task["plan_status"] = val.strip() or "todo"
            elif key == "test_notes":
                task["test_notes"] = val
            else:
                task.setdefault("extra", {})[key] = val
            continue
        s = SUBITEM_RE.match(raw)
        if s and cur_field == "acceptance":
            tasks[cur_t]["acceptance"].append(s.group(1))
            continue
        if s and cur_field == "files":
            tasks[cur_t]["files"].append(s.group(1))
    return milestones, tasks


def task_block(tid: str, t: dict) -> str:
    lines = [f"### {tid} {t['title']}", f"- status: {t.get('status', 'todo')}",
             "- deps: " + ", ".join(t.get("deps", [])), f"- type: {t.get('type', 'feature')}"]
    acc = t.get("acceptance", [])
    if acc:
        lines.append("- acceptance:")
        lines += [f"  - {a}" for a in acc]
    else:
        lines.append("- acceptance:")
    lines.append(f"- test_notes: {t.get('test_notes', '')}")
    lines.append("- files: " + ", ".join(t.get("files", [])))
    if t.get("source"):
        lines.append(f"- source: {t['source']}")
    if t.get("lane"):
        lines.append(f"- lane: {t['lane']}")
    return "\n".join(lines) + "\n"


def append_task_to_plan(plan_path: Path, milestone: str, m_title: str, tid: str, t: dict) -> None:
    text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else "# Implementation plan\n"
    lines = text.splitlines()
    # locate milestone section
    start = None
    for i, line in enumerate(lines):
        mm = MILESTONE_RE.match(line)
        if mm and mm.group(1) == milestone:
            start = i
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"## {milestone} — {m_title}", "", task_block(tid, t).rstrip("\n")]
    else:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("## "):
                end = j
                break
        # strip trailing blanks inside the section, then insert
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        insert = ["", *task_block(tid, t).rstrip("\n").splitlines(), ""]
        lines[end:end] = insert
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- commands

def cmd_init(store: Store, a: argparse.Namespace) -> None:
    store.dev.mkdir(parents=True, exist_ok=True)
    if store.exists() and not a.force:
        store.load()
        created = False
    else:
        store.state = {
            "version": STATE_VERSION, "project": None, "language": None, "phase": "init",
            "autonomy": json.loads(json.dumps(DEFAULT_AUTONOMY)), "stack": {}, "reviews": {}, "milestones": {}, "tasks": {},
            "next_task_id": 1, "next_question_id": 1, "created_at": now(), "updated_at": now(),
        }
        created = True
    if a.project:
        store.state["project"] = a.project
    if a.language:
        store.state["language"] = a.language
    if a.phase:
        if a.phase not in PHASES:
            fail(f"invalid phase {a.phase}; one of {', '.join(PHASES)}")
        store.state["phase"] = a.phase
    if a.stack_json:
        try:
            store.state["stack"] = json.loads(a.stack_json)
        except json.JSONDecodeError as e:
            fail(f"--stack-json is not valid JSON: {e}")
    if a.brownfield_json:
        try:
            bf = json.loads(a.brownfield_json)
        except json.JSONDecodeError as e:
            fail(f"--brownfield-json is not valid JSON: {e}")
        if not isinstance(bf, dict):
            fail("--brownfield-json must be a JSON object, e.g. {\"baseline_ref\": \"dev-kit-baseline\"}")
        store.state["brownfield"] = {**store.state.get("brownfield", {}), **bf}
    if a.autonomy_json:
        try:
            patch = json.loads(a.autonomy_json)
        except json.JSONDecodeError as e:
            fail(f"--autonomy-json is not valid JSON: {e}")
        auto = store.state.setdefault("autonomy", json.loads(json.dumps(DEFAULT_AUTONOMY)))
        q_patch = patch.pop("quality", None)
        if "model_policy" in patch:
            check_model_policy(patch["model_policy"])
        if patch.get("level") == "unattended":
            auto["pause_policy"] = json.loads(json.dumps(UNATTENDED_PAUSE_POLICY))
            auto["model_policy"] = {**auto.get("model_policy", {"tiers": {}}), "mode": "preapproved"}
        if "pause_policy" in patch:
            check_pause_policy(patch["pause_policy"])
            patch["pause_policy"] = {**auto.get("pause_policy", {}), **patch["pause_policy"]}
        if "production" in patch:
            check_production({**DEFAULT_AUTONOMY["production"], **auto.get("production", {}), **patch["production"]})
            patch["production"] = {**DEFAULT_AUTONOMY["production"], **auto.get("production", {}), **patch["production"]}
        if "local_deploy" in patch:
            check_local_deploy(patch["local_deploy"])
            patch["local_deploy"] = {**DEFAULT_AUTONOMY["local_deploy"], **auto.get("local_deploy", {}), **patch["local_deploy"]}
        if "on_park" in patch and patch["on_park"] not in ON_PARK:
            fail(f"autonomy.on_park must be one of {', '.join(ON_PARK)}")
        auto.update(patch)
        if q_patch is not None:
            q = auto.setdefault("quality", json.loads(json.dumps(DEFAULT_AUTONOMY["quality"])))
            for k, v in q_patch.items():
                if isinstance(v, dict) and isinstance(q.get(k), dict):
                    q[k].update(v)
                else:
                    q[k] = v
    store.save()
    oq = store.dev / "open-questions.md"
    if not oq.exists():
        oq.write_text(
            "# Open questions\n\n> Non-blocking doubts raised while working autonomously. "
            "Resolve with `/dev-kit:interview --gaps`.\n\n## Open\n"
            "| id | date | raised by | question | assumption used | impact if wrong |\n"
            "|---|---|---|---|---|---|\n\n## Resolved\n| id | resolved on | answer | ADR / task |\n|---|---|---|---|\n",
            encoding="utf-8",
        )
    store.log("init " + ("created" if created else "updated") + f" (phase={store.state['phase']}, language={store.state.get('language')})")
    print(f"state {'created' if created else 'updated'} at {store.path}")


def record_baseline(store: Store, tasks: dict) -> int:
    """Initial-plan snapshot for the board's graph: first write wins, a task already recorded is never changed."""
    path = store.dev / "plan-baseline.json"
    try:
        base = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(base, dict):
            base = {}
    except (OSError, json.JSONDecodeError):
        base = {}
    added = 0
    for tid, t in tasks.items():
        live = store.tasks().get(tid) or {}
        if live.get("type") == "fix" or live.get("source"):
            continue  # added during execution (QA fix, issue): not part of the initial plan
        if tid not in base:
            base[tid] = {"milestone": t["milestone"], "title": t["title"], "deps": list(t["deps"]),
                         "type": t["type"], "recorded_at": now()}
            added += 1
    if added:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(base, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    return added


def cmd_sync_plan(store: Store, a: argparse.Namespace) -> None:
    store.load()
    plan_path = Path(a.plan) if a.plan else store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    try:
        milestones, tasks = parse_plan(plan_path.read_text(encoding="utf-8"))
    except ValueError as e:
        fail(str(e))
    added_m = added_t = updated_t = 0
    for m, info in milestones.items():
        if m not in store.milestones():
            store.milestones()[m] = {"title": info["title"], "gate": "pending", "qa_runs": 0}
            added_m += 1
        else:
            store.milestones()[m]["title"] = info["title"]
    max_id = int(store.state.get("next_task_id", 1)) - 1
    for tid, t in tasks.items():
        max_id = max(max_id, int(tid[2:]))
        if tid in store.tasks():
            cur = store.tasks()[tid]
            for k in ("title", "milestone", "type", "deps", "acceptance", "test_notes", "files"):
                cur[k] = t[k]
            updated_t += 1
        else:
            store.tasks()[tid] = {
                "title": t["title"], "milestone": t["milestone"], "type": t["type"],
                "status": "todo", "deps": t["deps"], "acceptance": t["acceptance"],
                "test_notes": t["test_notes"], "files": t["files"], "commit": None,
                "blocked_reason": None, "source": None, "started_at": None, "done_at": None,
            }
            added_t += 1
    store.state["next_task_id"] = max_id + 1
    # validate deps and types
    problems = []
    for tid, t in store.tasks().items():
        if t["type"] not in TASK_TYPES:
            problems.append(f"{tid}: unknown type '{t['type']}'")
        for d in t["deps"]:
            if d not in store.tasks():
                problems.append(f"{tid}: dependency {d} does not exist")
        if t["milestone"] not in store.milestones():
            problems.append(f"{tid}: milestone {t['milestone']} not declared")
    if store.state["phase"] in ("init", "interview", "prd", "architecture", "ux", "ui", "plan") and store.tasks():
        store.state["phase"] = "implement" if store.state["phase"] == "plan" else store.state["phase"]
    store.save()
    record_baseline(store, tasks)
    store.log(f"sync-plan +{added_m} milestones, +{added_t} tasks, ~{updated_t} updated")
    print(f"synced: {added_m} new milestones, {added_t} new tasks, {updated_t} updated")
    if problems:
        print("warnings:\n  " + "\n  ".join(problems))


def pick_next(store: Store, milestone: str | None) -> tuple[str | None, str]:
    ts = store.tasks()
    if not ts:
        return None, "no tasks; run plan then sync-plan"
    if all(v["status"] == "done" for v in ts.values()):
        return None, "all tasks done"
    order = store.milestone_order()
    if milestone:
        if milestone not in store.milestones():
            return None, f"unknown milestone {milestone}"
        order = [milestone]
    # hotfix lane: expedite work runs first and ignores pending gates (conventions.md §15)
    hot = [t for t, v in ts.items() if v.get("lane") == "hotfix" and v["status"] == "todo"
           and v["milestone"] in order and all(ts.get(d, {}).get("status") == "done" for d in v["deps"])]
    if hot:
        return sorted(hot, key=lambda t: int(t[2:]))[0], ""
    for m in order:
        pending = {t: v for t, v in ts.items() if v["milestone"] == m and v["status"] != "done"}
        if not pending:
            continue
        ok, why = store.gate_open_for(m)
        if not ok:
            return None, why
        ready = [
            t for t, v in pending.items()
            if v["status"] == "todo" and all(ts.get(d, {}).get("status") == "done" for d in v["deps"])
        ]
        if not ready:
            blocked = [t for t, v in pending.items() if v["status"] == "blocked"]
            inprog = [t for t, v in pending.items() if v["status"] == "in_progress"]
            if inprog:
                return None, f"task {inprog[0]} is in_progress in {m}; finish it (done/block) first"
            if blocked:
                return None, f"only blocked tasks remain in {m}: {', '.join(blocked)}"
            return None, f"no ready task in {m} (unsatisfied dependencies)"
        ready.sort(key=lambda t: (0 if ts[t].get("lane") == "cooldown" else 1, 0 if ts[t]["type"] == "fix" else 1, int(t[2:])))
        return ready[0], ""
    return None, "nothing to do"


def cmd_next(store: Store, a: argparse.Namespace) -> None:
    store.load()
    tid, why = pick_next(store, a.milestone)
    if tid is None:
        if a.json:
            print(json.dumps({"task": None, "reason": why}))
        else:
            print(f"no task available: {why}")
        sys.exit(3)
    t = store.tasks()[tid]
    if a.json:
        print(json.dumps({"task": tid, **t}, ensure_ascii=False))
    else:
        print(f"{tid} [{t['milestone']}] ({t['type']}) {t['title']}")
        if t["acceptance"]:
            print("  acceptance: " + " | ".join(t["acceptance"]))
        if t["test_notes"]:
            print("  test_notes: " + t["test_notes"])
        if t["files"]:
            print("  files: " + ", ".join(t["files"]))


def cmd_start(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] == "done":
        fail(f"{a.task} is already done")
    if t["status"] == "in_progress":
        print(f"{a.task} already in_progress")
        return
    others = [x for x in store.in_progress() if x != a.task]
    if others and not a.force:
        fail(f"{others[0]} is already in_progress; finish it or use --force for parallel work")
    unmet = [d for d in t["deps"] if store.tasks().get(d, {}).get("status") != "done"]
    if unmet and not a.force:
        fail(f"{a.task} has unmet dependencies: {', '.join(unmet)}")
    ok, why = store.gate_open_for(t["milestone"])
    if not ok and not a.force and t.get("lane") != "hotfix":
        fail(f"cannot start {a.task}: {why}")
    t["status"] = "in_progress"
    issue_sync(store, t)
    t["started_at"] = now()
    t["blocked_reason"] = None
    if store.state["phase"] in ("plan", "qa"):
        store.state["phase"] = "implement"
    store.save()
    store.log(f"start {a.task} {t['title']}")
    store.event("task", task=a.task, transition="start", type=t.get("type"), milestone=t.get("milestone"), parallel=bool(a.force and others))
    print(f"{a.task} in_progress: {t['title']}")


def cmd_done(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] == "done":
        print(f"{a.task} already done")
        return
    if t["status"] != "in_progress" and not a.force:
        fail(f"{a.task} is {t['status']}, not in_progress (use --force to override)")
    t["status"] = "done"
    t["done_at"] = now()
    if a.commit:
        t["commit"] = a.commit
    issue_sync(store, t)
    store.save()
    store.log(f"done {a.task} commit={a.commit or '-'}")
    store.event("task", task=a.task, transition="done", type=t.get("type"), milestone=t.get("milestone"))
    m = t["milestone"]
    msg = f"{a.task} done"
    if t.get("lane") == "hotfix":
        msg += f" · hotfix: run qa --scope {a.task}, then deploy and release --hotfix"
    elif store.milestone_done(m):
        msg += f" · milestone {m} complete -> run qa {m}"
    print(msg)


def cmd_block(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] == "done":
        fail(f"{a.task} is done; cannot block")
    t["status"] = "blocked"
    t["blocked_reason"] = a.reason
    store.save()
    store.log(f"block {a.task}: {a.reason}")
    store.event("task", task=a.task, transition="block", type=t.get("type"), milestone=t.get("milestone"))
    print(f"{a.task} blocked: {a.reason}")


def cmd_unblock(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] != "blocked":
        fail(f"{a.task} is {t['status']}, not blocked")
    t["status"] = "todo"
    t["blocked_reason"] = None
    store.save()
    store.log(f"unblock {a.task}")
    store.event("task", task=a.task, transition="unblock", type=t.get("type"), milestone=t.get("milestone"))
    print(f"{a.task} todo")


def cmd_add_task(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.type not in TASK_TYPES:
        fail(f"invalid type {a.type}; one of {', '.join(sorted(TASK_TYPES))}")
    deps = [d.strip() for d in (a.deps or "").split(",") if d.strip()]
    for d in deps:
        if d not in store.tasks():
            fail(f"dependency {d} does not exist")
    if a.milestone not in store.milestones():
        if not a.milestone_title:
            fail(f"milestone {a.milestone} does not exist; pass --milestone-title to create it")
        store.milestones()[a.milestone] = {"title": a.milestone_title, "gate": "pending", "qa_runs": 0}
    issue = None
    if getattr(a, "issue", None):
        issue = store.state.get("issues", {}).get(a.issue)
        if issue is None:
            fail(f"unknown issue {a.issue}")
    if getattr(a, "lane", None):
        if a.lane not in LANES:
            fail(f"--lane must be one of {', '.join(LANES)}")
        if a.lane == "hotfix" and not a.force:
            open_hot = [x for x, v in store.tasks().items() if v.get("lane") == "hotfix" and v["status"] != "done"]
            if open_hot:
                fail(f"hotfix {open_hot[0]} is still open (WIP 1); finish it first or use --force")
    tid = store.new_task_id()
    t = {
        "title": a.title, "milestone": a.milestone, "type": a.type, "status": "todo", "deps": deps,
        "acceptance": a.acceptance or [], "test_notes": a.test_notes or "",
        "files": [f.strip() for f in (a.files or "").split(",") if f.strip()],
        "commit": None, "blocked_reason": None, "source": (f"issue:{a.issue}" if issue is not None else a.source),
        "started_at": None, "done_at": None,
    }
    if getattr(a, "lane", None):
        t["lane"] = a.lane
    store.tasks()[tid] = t
    if issue is not None:
        link_task(store, a.issue, tid, a.milestone)
    append_task_to_plan(store.dev / "plan.md", a.milestone, store.milestones()[a.milestone]["title"], tid, t)
    store.save()
    store.event("task", task=tid, transition="add", type=a.type, milestone=a.milestone)
    store.log(f"add-task {tid} [{a.milestone}] ({a.type}) {a.title} source={a.source or '-'}")
    print(tid)


def cmd_add_question(store: Store, a: argparse.Namespace) -> None:
    store.load()
    qid = store.new_question_id()
    path = store.dev / "open-questions.md"
    if not path.exists():
        path.write_text("# Open questions\n\n## Open\n| id | date | raised by | question | assumption used | impact if wrong |\n|---|---|---|---|---|---|\n\n## Resolved\n| id | resolved on | answer | ADR / task |\n|---|---|---|---|\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    row = f"| {qid} | {today()} | {a.skill or '-'} | {a.text.replace('|', '/')} | {(a.assumption or '-').replace('|', '/')} | {(a.impact or '-').replace('|', '/')} |"
    lines = text.splitlines()
    # insert after the last row of the Open table
    try:
        open_idx = next(i for i, l in enumerate(lines) if l.strip().lower() == "## open")
    except StopIteration:
        lines += ["", "## Open", "| id | date | raised by | question | assumption used | impact if wrong |", "|---|---|---|---|---|---|"]
        open_idx = len(lines) - 3
    j = open_idx + 1
    while j < len(lines) and (lines[j].startswith("|") or not lines[j].strip() and j + 1 < len(lines) and lines[j + 1].startswith("|")):
        j += 1
    lines.insert(j, row)
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    store.save()
    store.log(f"add-question {qid} ({a.skill or '-'}): {a.text}")
    print(qid)


def quality_cfg(store: Store) -> dict:
    q = json.loads(json.dumps(DEFAULT_AUTONOMY["quality"]))
    cur = store.state.get("autonomy", {}).get("quality", {})
    for k, v in cur.items():
        if isinstance(v, dict) and isinstance(q.get(k), dict):
            q[k].update(v)
        else:
            q[k] = v
    return q


def cmd_gate(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    if a.value not in GATES:
        fail(f"gate must be one of {', '.join(sorted(GATES))}")
    m = store.milestones()[a.milestone]
    if a.value == "passed":
        minimum = quality_cfg(store)["min_overall"]
        if a.score is None and not a.force:
            fail(f"gate {a.milestone} cannot pass without --score from dev_score.py (cut-off {minimum}); use --force only with a recorded decision")
        if a.score is not None and a.score < minimum and not a.force:
            fail(f"score {a.score} is below the cut-off {minimum}; fix findings and re-run qa (or --force with a recorded decision)")
        if a.force and (a.note or "").startswith("policy:"):
            check_policy_force(store, "gate", a.milestone, a.scores)
        m["passed_at"] = now()
    m["gate"] = a.value
    if a.score is not None:
        m["score"] = a.score
    if a.note:
        m["gate_note"] = a.note
    if a.force and a.value == "passed":
        m["forced"] = True
    if a.count_run:
        m["qa_runs"] = int(m.get("qa_runs", 0)) + 1
    store.save()
    store.event("gate", scope=a.milestone, value=a.value, score=a.score, qa_runs=m.get("qa_runs", 0),
                forced=bool(a.force and a.value == "passed"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "passed" else None)
    store.log(f"gate {a.milestone} {a.value}" + (f" score={a.score}" if a.score is not None else "") + (f" ({a.note})" if a.note else ""))
    print(f"{a.milestone} gate: {a.value}" + (f" (score {a.score})" if a.score is not None else ""))
    if a.value == "passed":
        print_tip(store, "gate_passed", a)


def cmd_preview(store: Store, a: argparse.Namespace) -> None:
    """Record the local deploy of a milestone (URL or install path, commit, pid) or mark it stopped."""
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    m = store.milestones()[a.milestone]
    if a.stopped:
        if "preview" not in m:
            fail(f"{a.milestone} has no recorded preview")
        m["preview"].pop("pid", None)
        m["preview"]["stopped_at"] = now()
        store.save()
        store.log(f"preview {a.milestone} stopped")
        store.event("preview", scope=a.milestone, status="stopped")
        print(f"{a.milestone} preview stopped")
        return
    if not a.url or not a.sha:
        fail("preview needs --url (URL, install path or command) and --sha")
    for other, info in store.milestones().items():  # only one preview runs at a time
        if other != a.milestone and info.get("preview", {}).get("pid") is not None:
            info["preview"].pop("pid", None)
            info["preview"]["stopped_at"] = now()
    m["preview"] = {"url": a.url, "sha": a.sha, "at": now(), **({"pid": a.pid} if a.pid is not None else {})}
    store.save()
    store.log(f"preview {a.milestone} {a.url} ({a.sha[:7]})")
    store.event("preview", scope=a.milestone, mode=store.state.get("autonomy", {}).get("local_deploy", {}).get("mode"), status="running" if a.pid else "ok")
    print(f"{a.milestone} preview: {a.url} ({a.sha[:7]})")


def _parse_set(pairs: list[str] | None) -> dict:
    out: dict = {}
    for kv in pairs or []:
        if "=" not in kv:
            fail(f"--set expects key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def cmd_event(store: Store, a: argparse.Namespace) -> None:
    """Append a structured event to .dev/telemetry.jsonl (allowlisted keys and values only)."""
    store.load()
    fields = _parse_set(a.set)
    if a.json:
        try:
            extra = json.loads(a.json)
        except json.JSONDecodeError as e:
            fail(f"--json is not valid JSON: {e}")
        if not isinstance(extra, dict):
            fail("--json must be an object")
        fields.update(extra)
    try:
        rec = tel.emit(store.dev, a.type, fields, rotate_session=(a.type == "session_start"))
    except ValueError as e:
        fail(f"event rejected: {e}")
    print(f"event {rec['event']} recorded (session {rec['session']})")


def cmd_feedback(store: Store, a: argparse.Namespace) -> None:
    """Record brief feedback about the dev-kit itself: what worked, what failed, what to improve."""
    store.load()
    fb: dict[str, list] = {}
    for kind in tel.FEEDBACK_LISTS:
        for item in getattr(a, kind) or []:
            if ":" not in item:
                fail(f"--{kind} expects area:note, got {item!r}")
            area, note = item.split(":", 1)
            fb.setdefault(kind, []).append({"area": area.strip(), "note": note.strip()})
    if a.json:
        try:
            fb = json.loads(a.json)
        except json.JSONDecodeError as e:
            fail(f"--json is not valid JSON: {e}")
    if not fb:
        fail("give at least one --worked/--failed/--improve area:note (or --json)")
    try:
        tel.emit(store.dev, "session_feedback", {"trigger": a.trigger, "feedback": fb})
    except ValueError as e:
        fail(f"feedback rejected: {e}")
    print("feedback recorded")


def stamped_path(folder: Path, prefix: str, ext: str, stamp: str | None = None) -> Path:
    """<folder>/<prefix>-<YYYYMMDD-HHMMSS>[-n].<ext>, never overwriting an existing file."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    path, n = folder / f"{prefix}-{stamp}.{ext}", 2
    while path.exists():
        path, n = folder / f"{prefix}-{stamp}-{n}.{ext}", n + 1
    return path


def cmd_telemetry(store: Store, a: argparse.Namespace) -> None:
    store.load()
    events, dropped = tel.read_events(store.dev)
    mode = "all" if a.all else ("since" if a.since else "session")
    events = tel.filter_period(events, mode, a.since)
    period = {"mode": mode, "since": a.since, "from": events[0]["ts"] if events else None, "to": events[-1]["ts"] if events else None}
    summary = tel.summarize(events, dropped, store.state.get("stack") or {})
    if a.action == "summary":
        print(tel.render_summary(summary))
        return
    if a.action == "report":
        rep = tel.stage_report(events, store.state)
        if a.json:
            print(json.dumps({"period": period, "summary": summary, "report": rep}, indent=2, ensure_ascii=False))
        else:
            print(tel.render_report(rep))
        return
    if a.out:
        out = Path(a.out)
        if not out.is_absolute():
            out = store.root / out
    else:
        out = stamped_path(store.dev / "feedback", "telemetry-export", "json", a.stamp)
    bundle = {"format": "dev-kit-telemetry-export", "v": tel.VERSION, "period": period, "summary": summary,
              "report": tel.stage_report(events, store.state), "events": events if a.events else []}
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(tel.render_summary(summary))
    print(f"\nexport written to {out} ({len(events)} events{' included' if a.events else ' summarised'}); "
          "review it before sending it to the dev-kit author")


def _proc_in_project(pid: int, root: Path) -> bool:
    try:
        cwd = Path(os.readlink(f"/proc/{pid}/cwd")).resolve()
        if cwd == root or root in cwd.parents:
            return True
    except OSError:
        pass
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        return str(root) in cmd
    except OSError:
        return False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def leftover_pids(store: Store) -> list[tuple[Path, int]]:
    run = store.dev / "run"
    out = []
    for pf in sorted(run.glob("*.pids")) if run.exists() else []:
        for tok in pf.read_text(encoding="utf-8").split():
            if tok.isdigit() and _alive(int(tok)):
                out.append((pf, int(tok)))
    return out


def board_line(store: Store) -> str | None:
    """The running /dev-kit:board server of this project (dev_board.py records it in .dev/run/board.json)."""
    try:
        rec = json.loads((store.dev / "run" / "board.json").read_text(encoding="utf-8"))
        pid = int(rec["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not _alive(pid) or not _proc_in_project(pid, store.root.resolve()):
        return None
    return f"Board: {rec.get('url')} (pid {pid}) · stop with /dev-kit:board stop"


def cmd_cleanup(store: Store, a: argparse.Namespace) -> None:
    """Kill the background processes agents recorded in .dev/run/*.pids, but only those inside this project."""
    store.load()
    root = store.root.resolve()
    run = store.dev / "run"
    files = sorted(run.glob("*.pids")) if run.exists() else []
    killed = skipped = 0
    for pf in files:
        for tok in pf.read_text(encoding="utf-8").split():
            if not tok.isdigit():
                continue
            pid = int(tok)
            if pid in (os.getpid(), os.getppid()) or not _alive(pid):
                continue
            if not _proc_in_project(pid, root):
                skipped += 1
                print(f"skip {pid} (not in this project)")
                continue
            if a.dry_run:
                print(f"would kill {pid} ({pf.name})")
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
                print(f"killed {pid} ({pf.name})")
            except OSError as e:
                print(f"cannot kill {pid}: {e}")
        if not a.dry_run:
            pf.unlink(missing_ok=True)
    if not a.dry_run:
        store.event("cleanup", killed=killed, stale_files=len(files), skipped=skipped)
        store.log(f"cleanup killed={killed} files={len(files)} skipped={skipped}")
    print(f"cleanup: {killed} killed · {skipped} skipped · {len(files)} pid files")


DEPLOY_STATUS = ("ok", "failed", "rolled_back")


def _git(store: Store, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(store.root), *args], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _int_tail(rev: str | None) -> int | None:
    m = re.search(r"(\d+)\D*$", str(rev or ""))
    return int(m.group(1)) if m else None


def cmd_deploy(store: Store, a: argparse.Namespace) -> None:
    """Record a deploy to an environment (production by default): commit, migration head, status."""
    store.load()
    if a.status not in DEPLOY_STATUS:
        fail(f"--status must be one of {', '.join(DEPLOY_STATUS)}")
    if a.milestone and a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    d = store.state.setdefault("deploys", {}).setdefault(a.env, {"history": []})
    rec = {"sha": a.sha, "milestone": a.milestone, "migration": a.migration, "status": a.status, "at": now()}
    d["history"] = (d.get("history") or [])[-19:] + [rec]
    if a.status == "ok":
        d["current"] = rec
    store.save()
    store.log(f"deploy {a.env} {a.status} {a.sha[:7]}" + (f" migr={a.migration}" if a.migration else ""))
    store.event("deploy", scope=a.milestone or "other", env=tel.scope_token(a.env), status=a.status)
    print(f"deploy {a.env}: {a.status} ({a.sha[:7]})")


def deploy_drift(store: Store, env: str, head_migration: str | None = None) -> str | None:
    cur = (store.state.get("deploys", {}).get(env) or {}).get("current")
    if not cur:
        return None
    parts = [f"{env.capitalize()}: {cur['sha'][:7]}" + (f" ({cur['milestone']}" if cur.get("milestone") else "") +
             (f", migr {cur['migration']}" if cur.get("migration") else "") + (")" if cur.get("milestone") else "")]
    head = _git(store, "rev-parse", "--short", "HEAD")
    if head:
        parts.append(f"HEAD {head}")
        behind = _git(store, "rev-list", "--count", f"{cur['sha']}..HEAD")
        if behind is not None and behind.isdigit():
            parts.append(f"{behind} commits behind")
    order = store.milestone_order()
    if cur.get("milestone") in order:
        passed_after = [m for m in order[order.index(cur["milestone"]) + 1:] if store.milestones()[m].get("gate") == "passed"]
        if passed_after:
            parts.append(f"{len(passed_after)} approved milestone(s) not deployed")
    hm, cm = _int_tail(head_migration), _int_tail(cur.get("migration"))
    if hm is not None and cm is not None and hm > cm:
        parts.append(f"{hm - cm} migrations behind")
    return " · ".join(parts)


# ---------------------------------------------------------------- issues (conventions.md §15)

def issues(store: Store) -> dict:
    return store.state.setdefault("issues", {})


def new_issue_id(store: Store) -> str:
    n = int(store.state.get("next_issue_id", 1))
    existing = {int(i[2:]) for i in issues(store)}
    while n in existing:
        n += 1
    store.state["next_issue_id"] = n + 1
    return f"I-{n:03d}"


def current_milestone(store: Store) -> str | None:
    """First milestone with work or a pending gate; else the last one (all passed)."""
    order = store.milestone_order()
    for m in order:
        ts = [v for v in store.tasks().values() if v["milestone"] == m]
        if store.milestones()[m].get("gate", "pending") == "pending" and ts:
            return m
    return order[-1] if order else None


def issue_event(store: Store, iid: str, transition: str) -> None:
    i = issues(store)[iid]
    store.event("issue", issue=iid, type=i.get("type"), **{"class": i.get("class")}, transition=transition,
                severity=i.get("severity"), origin=i.get("origin"))


def link_task(store: Store, iid: str, tid: str, milestone: str) -> None:
    i = issues(store)[iid]
    if tid not in i.setdefault("tasks", []):
        i["tasks"].append(tid)
    if i["status"] == "open":
        i["status"] = "scheduled"
        i["scheduled_in"] = milestone
        issue_event(store, iid, "scheduled")
    write_issues_md(store)


def issue_sync(store: Store, task: dict) -> None:
    """Move the linked issue forward when its tasks start or are all done."""
    src = str(task.get("source") or "")
    if not src.startswith("issue:"):
        return
    iid = src.split(":", 1)[1]
    i = issues(store).get(iid)
    if i is None or i["status"] in ("done", "wontfix", "duplicate"):
        return
    states = [store.tasks()[x]["status"] for x in i.get("tasks", []) if x in store.tasks()]
    if states and all(s == "done" for s in states):
        i["status"], i["closed_at"] = "done", now()
        issue_event(store, iid, "done")
    elif task["status"] == "in_progress" and i["status"] != "in_progress":
        i["status"] = "in_progress"
        issue_event(store, iid, "in_progress")
    write_issues_md(store)


def write_issues_md(store: Store) -> None:
    rows = issues(store)
    open_ = {k: v for k, v in rows.items() if v["status"] not in ("done", "wontfix", "duplicate")}
    closed = {k: v for k, v in rows.items() if k not in open_}
    out = ["# Issues", "", "Generated by dev_state.py; edit through `/dev-kit:issue`. Classes: conventions.md §15.", "",
           "## Open", "| id | class | type | severity | effort | status | scheduled in | tasks | title |", "|---|---|---|---|---|---|---|---|---|"]
    order = {c: n for n, c in enumerate(ISSUE_CLASSES)}
    for k, v in sorted(open_.items(), key=lambda kv: (order.get(kv[1].get("class"), 9), SEV_RANK.get(kv[1].get("severity"), 4), kv[0])):
        out.append(f"| {k} | {v.get('class')} | {v.get('type')} | {v.get('severity') or '-'} | {v.get('effort') or '-'} | {v['status']} | "
                   f"{v.get('scheduled_in') or '-'} | {', '.join(v.get('tasks', [])) or '-'} | {v['title'].replace('|', '/')} |")
    out += ["", "## Closed", "| id | status | closed | tasks | title |", "|---|---|---|---|---|"]
    for k, v in sorted(closed.items()):
        out.append(f"| {k} | {v['status']} | {str(v.get('closed_at') or '-')[:10]} | {', '.join(v.get('tasks', [])) or '-'} | {v['title'].replace('|', '/')} |")
    store.dev.mkdir(parents=True, exist_ok=True)
    (store.dev / "issues.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def check_issue_fields(itype: str | None, iclass: str | None, severity: str | None, effort: str | None, force: bool) -> None:
    if itype is not None and itype not in ISSUE_TYPES:
        fail(f"--type must be one of {', '.join(ISSUE_TYPES)}")
    if iclass is not None and iclass not in ISSUE_CLASSES:
        fail(f"--class must be one of {', '.join(ISSUE_CLASSES)}")
    if severity is not None and severity not in ISSUE_SEVERITIES:
        fail(f"--severity must be one of {', '.join(ISSUE_SEVERITIES)}")
    if effort is not None and effort not in ("S", "M", "L"):
        fail("--effort must be S, M or L")
    if (itype == "change") != (iclass == "change") and itype is not None and iclass is not None:
        fail("type change and class change go together (scope changes go through prd → review → plan)")
    if iclass == "expedite" and not force and not (itype == "bug" and severity in ("critical", "high")):
        fail("expedite (hotfix) is only for critical/high bugs in delivered work; use standard, or --force with a reason")


def cmd_add_issue(store: Store, a: argparse.Namespace) -> None:
    store.load()
    check_issue_fields(a.type, a.cls, a.severity, a.effort, a.force)
    if a.origin not in ISSUE_ORIGINS:
        fail(f"--origin must be one of {', '.join(ISSUE_ORIGINS)}")
    iid = new_issue_id(store)
    issues(store)[iid] = {
        "title": a.title, "type": a.type, "class": a.cls, "severity": a.severity, "effort": a.effort,
        "status": "open", "affects": [x.strip() for x in (a.affects or "").split(",") if x.strip()],
        "acceptance": a.acceptance or [], "origin": a.origin, "tasks": [], "scheduled_in": None,
        "duplicate_of": None, "created_at": now(), "closed_at": None, "note": a.note,
    }
    write_issues_md(store)
    store.save()
    store.log(f"add-issue {iid} ({a.type}/{a.cls}) {a.title}")
    issue_event(store, iid, "created")
    print(iid)
    print_tip(store, f"issue_created:{a.cls}", a)


def cmd_issue(store: Store, a: argparse.Namespace) -> None:
    store.load()
    i = issues(store).get(a.id)
    if i is None:
        fail(f"unknown issue {a.id}")
    check_issue_fields(None, a.cls, a.severity, a.effort, True)
    changed = []
    for key, val in (("class", a.cls), ("severity", a.severity), ("effort", a.effort), ("note", a.note)):
        if val is not None:
            i[key] = val
            changed.append(key)
    if a.duplicate_of:
        if a.duplicate_of not in issues(store) or a.duplicate_of == a.id:
            fail(f"unknown issue {a.duplicate_of}")
        i["duplicate_of"], i["status"], i["closed_at"] = a.duplicate_of, "duplicate", now()
        changed.append("duplicate")
    if a.status:
        if a.status not in ISSUE_STATUSES:
            fail(f"--status must be one of {', '.join(ISSUE_STATUSES)}")
        i["status"] = a.status
        if a.status in ("done", "wontfix", "duplicate"):
            i["closed_at"] = now()
        changed.append("status")
    if a.link:
        if a.link not in store.tasks():
            fail(f"unknown task {a.link}")
        store.tasks()[a.link]["source"] = f"issue:{a.id}"
        link_task(store, a.id, a.link, store.tasks()[a.link]["milestone"])
        changed.append("link")
    write_issues_md(store)
    store.save()
    if changed:
        store.log(f"issue {a.id} " + ", ".join(changed))
        issue_event(store, a.id, i["status"] if "status" in changed or "duplicate" in changed else "updated")
    print(f"{a.id} [{i['class']}/{i['type']}] {i['status']}: {i['title']}" + (f" · tasks {', '.join(i['tasks'])}" if i["tasks"] else ""))


def planned_count(store: Store, m: str) -> int:
    return sum(1 for v in store.tasks().values() if v["milestone"] == m and not str(v.get("source") or "").startswith("issue:"))


def queue(store: Store, classes: tuple[str, ...]) -> list[str]:
    q = [k for k, v in issues(store).items() if v["status"] == "open" and v.get("class") in classes]
    return sorted(q, key=lambda k: (CLASS_RANK.get(issues(store)[k]["class"], 5), SEV_RANK.get(issues(store)[k].get("severity"), 4),
                                    issues(store)[k]["created_at"], k))


def task_for_issue(store: Store, iid: str, milestone: str, lane: str | None) -> str:
    i = issues(store)[iid]
    ttype = "fix" if i["type"] == "bug" else ("chore" if i.get("class") == "intangible" else "feature")
    acc = i.get("acceptance") or [f"{iid} resolved: {i['title']}"]
    notes = f"start with a failing regression test that reproduces {iid}" if i["type"] == "bug" else f"cover the change with tests; see {iid}"
    tid = store.new_task_id()
    t = {"title": i["title"], "milestone": milestone, "type": ttype, "status": "todo", "deps": [], "acceptance": acc,
         "test_notes": notes, "files": [], "commit": None, "blocked_reason": None, "source": f"issue:{iid}",
         "started_at": None, "done_at": None}
    if lane:
        t["lane"] = lane
    store.tasks()[tid] = t
    append_task_to_plan(store.dev / "plan.md", milestone, store.milestones()[milestone]["title"], tid, t)
    link_task(store, iid, tid, milestone)
    return tid


def buffer_info(store: Store, m: str) -> dict:
    pct = int(store.state.get("autonomy", {}).get("issue_buffer_pct", DEFAULT_AUTONOMY["issue_buffer_pct"]))
    cap = -(-planned_count(store, m) * pct // 100)  # ceil
    used = sum(1 for v in store.tasks().values() if v["milestone"] == m and str(v.get("source") or "").startswith("issue:")
               and v.get("lane") not in ("hotfix", "cooldown"))
    return {"milestone": m, "pct": pct, "capacity": cap, "used": used, "free": max(0, cap - used)}


def cmd_pull_issues(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone} (issues never create milestones)")
    info = buffer_info(store, a.milestone)
    picked = queue(store, ("standard", "intangible"))[: info["free"]]
    created = []
    if not a.dry_run:
        for iid in picked:
            created.append((iid, task_for_issue(store, iid, a.milestone, None)))
        store.save()
        store.log(f"pull-issues {a.milestone}: " + (", ".join(f"{i}->{t}" for i, t in created) or "none"))
        store.event("issue", transition="pulled", issue=None)
    print(f"{a.milestone} buffer {info['pct']}%: capacity {info['capacity']} · used {info['used']} · "
          + ("would pull" if a.dry_run else "pulled") + f" {len(picked)}" + (": " + ", ".join(picked) if picked else ""))
    for iid, tid in created:
        print(f"  {iid} -> {tid} {issues(store)[iid]['title']}")
    left = len(queue(store, ("standard", "intangible")))
    if left:
        print(f"  {left} issue(s) stay in the queue for the next milestones")
    print_tip(store, "milestone_start", a)


def cmd_cooldown(store: Store, a: argparse.Namespace) -> None:
    store.load()
    cd = {**DEFAULT_AUTONOMY["cooldown"], **store.state.get("autonomy", {}).get("cooldown", {})}
    if not cd.get("enabled"):
        print("cool-down is off (autonomy.cooldown.enabled = false)")
        print_tip(store, "gate_passed", a)
        return
    order = store.milestone_order()
    if a.milestone not in order:
        fail(f"unknown milestone {a.milestone}")
    if store.milestones()[a.milestone].get("gate") not in ("passed", "skipped"):
        fail(f"cool-down runs after the gate of {a.milestone} passes")
    nxt = order[order.index(a.milestone) + 1] if order.index(a.milestone) + 1 < len(order) else None
    if nxt is None:
        print("no next milestone: the queue waits for the next cycle (plan it with /dev-kit:plan)")
        return
    already = sum(1 for v in store.tasks().values() if v["milestone"] == nxt and v.get("lane") == "cooldown")
    room = max(0, int(cd.get("max_tasks", 5)) - already)
    small = [k for k in queue(store, ("standard", "intangible"))
             if issues(store)[k].get("effort") == "S" and issues(store)[k].get("severity") in (None, "low", "medium")][:room]
    created = []
    if not a.dry_run:
        for iid in small:
            created.append((iid, task_for_issue(store, iid, nxt, "cooldown")))
        store.save()
        store.log(f"cooldown {a.milestone}->{nxt}: " + (", ".join(f"{i}->{t}" for i, t in created) or "none"))
    print(f"cool-down after {a.milestone}: " + ("would take" if a.dry_run else "took") + f" {len(small)} small issue(s) into {nxt} (lane cooldown, audited in its qa)")
    for iid, tid in created:
        print(f"  {iid} -> {tid} {issues(store)[iid]['title']}")


def deferred_findings(store: Store) -> list[dict]:
    out = []
    for base in ("qa", "reviews"):
        root = store.dev / base
        if not root.exists():
            continue
        for scope_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            rounds = sorted(scope_dir.glob("findings-round-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
            if not rounds:
                continue
            try:
                data = json.loads(rounds[-1].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items = (data.get("deferred") or []) if isinstance(data, dict) else []
            items += [f for f in ((data.get("findings") or []) if isinstance(data, dict) else data)
                      if isinstance(f, dict) and str(f.get("severity")) in ("medium", "low")]
            for f in items:
                if isinstance(f, dict):
                    out.append({"scope": scope_dir.name, "id": f.get("id"), "severity": f.get("severity"), "title": f.get("title")})
    return out


def backlog_data(store: Store) -> dict:
    ts = store.tasks()
    iss = issues(store)
    cur = current_milestone(store)
    hot_open = [k for k, v in ts.items() if v.get("lane") == "hotfix" and v["status"] != "done"]
    hot_in_cur = sum(1 for v in ts.values() if v.get("lane") == "hotfix" and v["milestone"] == cur)
    q = {c: [k for k, v in iss.items() if v["status"] == "open" and v.get("class") == c] for c in ISSUE_CLASSES}
    pending = {}
    for m in store.milestone_order():
        rows = [{"task": k, "status": v["status"], "type": v["type"], "lane": v.get("lane"), "title": v["title"],
                 "issue": str(v.get("source") or "")[6:] if str(v.get("source") or "").startswith("issue:") else None,
                 "blocked_reason": v.get("blocked_reason")}
                for k, v in sorted(ts.items(), key=lambda kv: int(kv[0][2:])) if v["milestone"] == m and v["status"] != "done"]
        if rows:
            pending[m] = rows
    nxt = next((m for m in store.milestone_order() if store.milestones()[m].get("gate", "pending") == "pending"), None)
    warnings = []
    if hot_in_cur > 2:
        warnings.append(f"{hot_in_cur} hotfixes in {cur}: expedite is being overused")
    deploy = [d for env in sorted(store.state.get("deploys") or {}) if (d := deploy_drift(store, env))]
    return {
        "current_milestone": cur, "hotfix_open": hot_open,
        "issues": {k: {**{f: v.get(f) for f in ("title", "type", "class", "severity", "effort", "status", "scheduled_in", "tasks", "created_at")}}
                   for k, v in iss.items() if v["status"] not in ("done", "wontfix", "duplicate")},
        "queue": q, "buffer": buffer_info(store, nxt) if nxt else None,
        "tasks": pending, "open_questions": count_open_questions(store),
        "deferred_findings": deferred_findings(store), "deploy": deploy,
        "leftover_processes": len(leftover_pids(store)), "warnings": warnings,
    }


def cmd_backlog(store: Store, a: argparse.Namespace) -> None:
    store.load()
    d = backlog_data(store)
    if a.json:
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return
    sec = a.section
    if sec in (None, "issues"):
        print(f"Hotfix open: {', '.join(d['hotfix_open']) or 'none'}")
        for c in ISSUE_CLASSES:
            ids = d["queue"][c]
            if ids:
                print(f"Queue {c}: " + ", ".join(f"{i} ({d['issues'][i].get('severity') or '-'}) {d['issues'][i]['title']}" for i in ids))
        sched = [k for k, v in d["issues"].items() if v["status"] in ("scheduled", "in_progress")]
        if sched:
            print("Scheduled: " + ", ".join(f"{k}→{d['issues'][k]['scheduled_in']}" for k in sched))
        if d["buffer"]:
            b = d["buffer"]
            print(f"Buffer {b['milestone']}: {b['used']}/{b['capacity']} used ({b['pct']}%)")
    if sec in (None, "tasks"):
        for m, rows in d["tasks"].items():
            print(f"{m}: " + ", ".join(f"{r['task']}{'[' + r['lane'] + ']' if r['lane'] else ''} {r['status']}" for r in rows))
    if sec in (None, "questions") and d["open_questions"]:
        print(f"Open questions / parked: {d['open_questions']} (resolve with /dev-kit:interview --gaps)")
    if sec in (None, "findings") and d["deferred_findings"]:
        print(f"Deferred findings: {len(d['deferred_findings'])} (promote with /dev-kit:issue --from <F-id> <scope>)")
    if sec in (None, "deploy") and d["deploy"]:
        for line in d["deploy"]:
            print(line)
    for w in d["warnings"]:
        print(f"! {w}")
    print_tip(store, "expedite_overuse" if d["warnings"] else "backlog", a)


# ---------------------------------------------------------------- tips (shared/tips.json)

TIPS_PATH = Path(__file__).resolve().parents[1] / "shared" / "tips.json"


def load_tips() -> list[dict]:
    try:
        return json.loads(TIPS_PATH.read_text(encoding="utf-8")).get("tips", [])
    except (OSError, json.JSONDecodeError):
        return []


def pick_tip(store: Store, context: str) -> dict | None:
    """English text only (kit files are English); the skill showing it translates to the user's language."""
    mode = store.state.get("autonomy", {}).get("tips", "on")
    if mode == "off":
        return None
    seen_path = store.dev / "tips-seen.json"
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {}
    cands = [t for t in load_tips() if t.get("context") == context or (":" in context and t.get("context") == context.split(":")[0])]
    if mode != "always":
        cands = [t for t in cands if seen.get(t["id"], 0) < 2]
    if not cands:
        return None
    tip = min(cands, key=lambda t: (seen.get(t["id"], 0), t["id"]))
    seen[tip["id"]] = seen.get(tip["id"], 0) + 1
    seen_path.write_text(json.dumps(seen, indent=1) + "\n", encoding="utf-8")
    store.event("tip", tip=tip["id"], context=context)
    return {"id": tip["id"], "text": tip.get("en"), "command": tip.get("command")}


def print_tip(store: Store, context: str, a: argparse.Namespace | None = None) -> None:
    if a is not None and getattr(a, "json", False):
        return
    tip = pick_tip(store, context)
    if tip:
        print(f"💡 {tip['text']}")


def cmd_tip(store: Store, a: argparse.Namespace) -> None:
    store.load()
    tip = pick_tip(store, a.context)
    if a.json:
        print(json.dumps(tip, ensure_ascii=False))
    elif tip:
        print(f"💡 {tip['text']}")


def cmd_tips(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.reset:
        (store.dev / "tips-seen.json").unlink(missing_ok=True)
        print("tips reset: every tip can show again")
        return
    for tp in load_tips():
        print(f"[{tp['context']}] {tp.get('en')}")


REVIEW_VALUES = {"pass", "fail", "pending"}


def cmd_review(store: Store, a: argparse.Namespace) -> None:
    """Record the outcome of a pre-implementation or documentation review (prd, design, plan, docs, ...)."""
    store.load()
    if a.value not in REVIEW_VALUES:
        fail(f"review value must be one of {', '.join(sorted(REVIEW_VALUES))}")
    reviews = store.state.setdefault("reviews", {})
    r = reviews.setdefault(a.name, {"rounds": 0})
    if a.value == "pass":
        minimum = quality_cfg(store)["review_min_overall"]
        if a.score is None and not a.force:
            fail(f"review {a.name} cannot pass without --score (cut-off {minimum})")
        if a.score is not None and a.score < minimum and not a.force:
            fail(f"score {a.score} is below the review cut-off {minimum}; revise the artifact and re-run review")
        if a.force and (a.note or "").startswith("policy:"):
            check_policy_force(store, "review", a.name, a.scores)
    r["verdict"] = a.value
    if a.score is not None:
        r["score"] = a.score
    if a.note:
        r["note"] = a.note
    if a.force and a.value == "pass":
        r["forced"] = True
    if a.count_run:
        r["rounds"] = int(r.get("rounds", 0)) + 1
    r["at"] = now()
    store.save()
    store.event("review", scope=tel.scope_token(a.name), value=a.value, score=a.score, round=r.get("rounds", 0),
                forced=bool(a.force and a.value == "pass"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "pass" else None)
    store.log(f"review {a.name} {a.value}" + (f" score={a.score}" if a.score is not None else ""))
    print(f"review {a.name}: {a.value}" + (f" (score {a.score})" if a.score is not None else "") + f" · rounds {r['rounds']}")


def cmd_set(store: Store, a: argparse.Namespace) -> None:
    store.load()
    key, val = a.key, a.value
    if key == "phase":
        if val not in PHASES:
            fail(f"invalid phase {val}; one of {', '.join(PHASES)}")
        store.state["phase"] = val
    elif key in ("language", "project"):
        store.state[key] = val
    elif key.startswith("autonomy."):
        field = key.split(".", 1)[1]
        auto = store.state.setdefault("autonomy", dict(DEFAULT_AUTONOMY))
        if field == "level":
            if val not in ("high", "balanced", "cautious", "unattended"):
                fail("autonomy.level must be high | balanced | cautious | unattended")
            auto["level"] = val
            if val == "unattended":
                auto["pause_policy"] = json.loads(json.dumps(UNATTENDED_PAUSE_POLICY))
                auto["model_policy"] = {**auto.get("model_policy", {"tiers": {}}), "mode": "preapproved"}
        elif field == "pause_policy" or field.startswith("pause_policy."):
            try:
                rule = json.loads(val)
            except json.JSONDecodeError:
                rule = {"action": val}
            patch = rule if field == "pause_policy" else {field.split(".", 1)[1]: rule}
            check_pause_policy(patch)
            auto["pause_policy"] = {**auto.get("pause_policy", {}), **patch}
        elif field == "production":
            try:
                pr = json.loads(val)
            except json.JSONDecodeError:
                fail("autonomy.production must be a JSON object")
            merged = {**DEFAULT_AUTONOMY["production"], **auto.get("production", {}), **pr}
            check_production(merged)
            auto["production"] = merged
        elif field == "local_deploy":
            try:
                ld = json.loads(val)
            except json.JSONDecodeError:
                ld = {"mode": val}
            check_local_deploy(ld)
            auto["local_deploy"] = {**DEFAULT_AUTONOMY["local_deploy"], **auto.get("local_deploy", {}), **ld}
        elif field == "issue_buffer_pct":
            if not val.isdigit() or not 0 <= int(val) <= 50:
                fail("autonomy.issue_buffer_pct must be an integer between 0 and 50")
            auto["issue_buffer_pct"] = int(val)
        elif field == "cooldown":
            try:
                cd = json.loads(val)
            except json.JSONDecodeError:
                cd = {"enabled": val in ("on", "true", "yes")} if val in ("on", "off", "true", "false", "yes", "no") else None
            if not isinstance(cd, dict) or not isinstance(cd.get("enabled", False), bool) or not isinstance(cd.get("max_tasks", 5), int):
                fail('autonomy.cooldown must be on | off or {"enabled": true, "max_tasks": 5}')
            auto["cooldown"] = {**DEFAULT_AUTONOMY["cooldown"], **auto.get("cooldown", {}), **cd}
        elif field == "tips":
            if val not in TIPS_MODES:
                fail(f"autonomy.tips must be one of {', '.join(TIPS_MODES)}")
            auto["tips"] = val
        elif field == "on_park":
            if val not in ON_PARK:
                fail(f"autonomy.on_park must be one of {', '.join(ON_PARK)}")
            auto["on_park"] = val
        elif field == "model_policy":
            try:
                mp = json.loads(val)
            except json.JSONDecodeError:
                mp = {"mode": val}
            check_model_policy(mp)
            auto["model_policy"] = {"mode": mp.get("mode", "ask"), "tiers": mp.get("tiers", {})}
        else:
            try:
                auto[field] = json.loads(val)
            except json.JSONDecodeError:
                auto[field] = val
    elif key.startswith("stack."):
        store.state.setdefault("stack", {})[key.split(".", 1)[1]] = val
    else:
        fail("key must be phase | language | project | autonomy.<field> | stack.<field>")
    store.save()
    store.log(f"set {key}={val}")
    if key.startswith("autonomy."):
        short = val if tel.TOKEN_RE.match(val or "") else None
        store.event("config", key=key.replace("autonomy.", "")[:40].lower(), value=short)
    print(f"{key} = {val}")


def render_short(store: Store) -> str:
    s = store.state
    p = store.progress()
    order = store.milestone_order()
    gates = ", ".join(
        f"{m}:{store.milestones()[m].get('gate', 'pending')}" + (f"({store.milestones()[m]['score']})" if store.milestones()[m].get("score") is not None else "")
        for m in order) or "no milestones"
    inprog = store.in_progress()
    open_q = count_open_questions(store)
    name = s.get("project") or store.root.name
    l1 = f"[dev-kit] {name} · phase: {s.get('phase')} · language: {s.get('language') or '?'} · tasks done {p['done']}/{p['total']} · gates: {gates}"
    if inprog:
        t = store.tasks()[inprog[0]]
        l2 = f"[dev-kit] in progress: {inprog[0]} {t['title']} (since {t.get('started_at')})"
    else:
        tid, why = pick_next(store, None)
        l2 = f"[dev-kit] next: {tid} {store.tasks()[tid]['title']}" if tid else f"[dev-kit] next: {why}"
    revs = s.get("reviews") or {}
    rv = ", ".join(f"{k}:{v.get('verdict')}" + (f"({v['score']})" if v.get("score") is not None else "") for k, v in revs.items()) or "none"
    l3 = f"[dev-kit] reviews: {rv} · blocked: {p['blocked']} · open questions: {open_q} · resume with /dev-kit:start"
    return "\n".join([l1, l2, l3])


def count_open_questions(store: Store) -> int:
    path = store.dev / "open-questions.md"
    if not path.exists():
        return 0
    n = 0
    in_open = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("## "):
            in_open = line.strip().lower() == "## open"
            continue
        if in_open and re.match(r"^\|\s*Q-\d+", line):
            n += 1
    return n


def cmd_status(store: Store, a: argparse.Namespace) -> None:
    if not store.exists():
        if a.quiet_if_missing:
            return
        fail(f"no state at {store.path}", 2)
    store.load()
    if a.json:
        out = dict(store.state)
        out["progress"] = store.progress()
        tid, why = pick_next(store, None)
        out["next"] = {"task": tid, "reason": why}
        out["open_questions"] = count_open_questions(store)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if a.short:
        print(render_short(store))
        return
    s = store.state
    p = store.progress()
    print(f"Project: {s.get('project') or store.root.name}")
    print(f"Phase: {s.get('phase')} · Language: {s.get('language') or '?'} · Autonomy: {s.get('autonomy', {}).get('level')}")
    stack = s.get("stack") or {}
    if stack:
        print("Stack: " + ", ".join(f"{k}={v}" for k, v in stack.items() if k != "detected_from" and v))
    revs = s.get("reviews") or {}
    if revs:
        print("Reviews: " + ", ".join(f"{k}:{v.get('verdict')}" + (f"({v['score']})" if v.get("score") is not None else "") for k, v in revs.items()))
    q = quality_cfg(store)
    print(f"Quality cut-off: overall {q['min_overall']} · per dimension {q['min_dimension']} · reviews {q['review_min_overall']}")
    pp = s.get("autonomy", {}).get("pause_policy", {})
    if pp:
        print("Pause policy: " + " · ".join(f"{k} {v.get('action')}" for k, v in sorted(pp.items())) + f" · on park: {s.get('autonomy', {}).get('on_park', 'stop_when_idle')}")
    for m in store.milestone_order():
        pv = store.milestones()[m].get("preview")
        if pv and not pv.get("stopped_at"):
            print(f"Preview: {m} {pv['url']} ({pv['sha'][:7]})")
    for env in sorted(s.get("deploys") or {}):
        drift = deploy_drift(store, env, getattr(a, "head_migration", None))
        if drift:
            print(drift)
    iss = [v for v in (s.get("issues") or {}).values() if v["status"] not in ("done", "wontfix", "duplicate")]
    if iss:
        hot = sum(1 for v in store.tasks().values() if v.get("lane") == "hotfix" and v["status"] != "done")
        queued = [v for v in iss if v["status"] == "open"]
        by = {}
        for v in queued:
            by[v.get("class")] = by.get(v.get("class"), 0) + 1
        print(f"Issues: {hot} hotfix · {len(queued)} queued (" + ", ".join(f"{n} {c}" for c, n in sorted(by.items())) +
              f") · {len(iss) - len(queued)} scheduled · run /dev-kit:backlog")
    cs = store.dev / "costs" / "summary.json"
    if cs.exists():
        try:
            tot = json.loads(cs.read_text(encoding="utf-8")).get("total", {})
            tk = tot.get("tokens", 0)
            tks = f"{tk / 1e6:.1f}M" if tk >= 1e6 else f"{tk / 1e3:.0f}k"
            print(f"Cost (est., API-equivalent): US$ {tot.get('usd', 0):.2f}{'' if tot.get('usd_complete', True) else '+'} · {tks} tokens"
                  " · run /dev-kit:costs for the breakdown")
        except (OSError, json.JSONDecodeError):
            pass
    tl = store.dev / "telemetry.jsonl"
    if tl.exists():
        lines = tl.read_text(encoding="utf-8").splitlines()
        sid = (store.dev / "telemetry-session").read_text(encoding="utf-8").strip() if (store.dev / "telemetry-session").exists() else "?"
        print(f"Session log: {len(lines)} events · last session {sid} · run /dev-kit:feedback for the session evaluation")
    left = leftover_pids(store)
    if left:
        print(f"Leftover agent processes: {len(left)} (run `dev_state.py cleanup`)")
    bl = board_line(store)
    if bl:
        print(bl)
    print(f"Tasks: {p['done']}/{p['total']} done · {p['in_progress']} in progress · {p['blocked']} blocked · {p['todo']} todo")
    for m in store.milestone_order():
        info = store.milestones()[m]
        ts = {t: v for t, v in store.tasks().items() if v["milestone"] == m}
        done = sum(1 for v in ts.values() if v["status"] == "done")
        sc = f" score {info['score']}" if info.get("score") is not None else ""
        print(f"\n{m} — {info.get('title')} [{done}/{len(ts)}] gate: {info.get('gate', 'pending')}{sc} (qa runs: {info.get('qa_runs', 0)})")
        for tid in sorted(ts, key=lambda x: int(x[2:])):
            v = ts[tid]
            mark = {"done": "x", "in_progress": ">", "blocked": "!", "todo": " "}[v["status"]]
            extra = f" — blocked: {v['blocked_reason']}" if v["status"] == "blocked" else ""
            extra += f" ({v['commit'][:7]})" if v.get("commit") else ""
            print(f"  [{mark}] {tid} ({v['type']}) {v['title']}{extra}")
    tid, why = pick_next(store, None)
    print(f"\nNext: {tid + ' ' + store.tasks()[tid]['title'] if tid else why}")
    oq = count_open_questions(store)
    if oq:
        print(f"Open questions: {oq} (see .dev/open-questions.md, resolve with interview --gaps)")
    print("Help: /dev-kit:help (what to do next, how each skill works)")
    print_tip(store, "status", a)


# --------------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev_state.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: walk up from cwd to find .dev/state.json, else cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.set_defaults(fn=cmd_init)
    s.add_argument("--project"); s.add_argument("--language"); s.add_argument("--phase")
    s.add_argument("--stack-json"); s.add_argument("--autonomy-json"); s.add_argument("--force", action="store_true")
    s.add_argument("--brownfield-json", help='existing-project marker, e.g. {"baseline_ref":"dev-kit-baseline","baseline_sha":"<sha>"}')

    s = sub.add_parser("sync-plan"); s.set_defaults(fn=cmd_sync_plan); s.add_argument("--plan")

    s = sub.add_parser("next"); s.set_defaults(fn=cmd_next)
    s.add_argument("--milestone"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("start"); s.set_defaults(fn=cmd_start); s.add_argument("task"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("done"); s.set_defaults(fn=cmd_done); s.add_argument("task"); s.add_argument("--commit"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("block"); s.set_defaults(fn=cmd_block); s.add_argument("task"); s.add_argument("--reason", required=True)
    s = sub.add_parser("unblock"); s.set_defaults(fn=cmd_unblock); s.add_argument("task")

    s = sub.add_parser("add-task"); s.set_defaults(fn=cmd_add_task)
    s.add_argument("--milestone", required=True); s.add_argument("--milestone-title")
    s.add_argument("--title", required=True); s.add_argument("--type", default="feature")
    s.add_argument("--deps"); s.add_argument("--acceptance", action="append"); s.add_argument("--test-notes")
    s.add_argument("--files"); s.add_argument("--source"); s.add_argument("--issue"); s.add_argument("--lane")
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("add-question"); s.set_defaults(fn=cmd_add_question)
    s.add_argument("text"); s.add_argument("--skill"); s.add_argument("--assumption"); s.add_argument("--impact")

    s = sub.add_parser("gate"); s.set_defaults(fn=cmd_gate)
    s.add_argument("milestone"); s.add_argument("value"); s.add_argument("--note"); s.add_argument("--count-run", action="store_true")
    s.add_argument("--score", type=int); s.add_argument("--force", action="store_true"); s.add_argument("--scores")

    s = sub.add_parser("review"); s.set_defaults(fn=cmd_review)
    s.add_argument("name"); s.add_argument("value"); s.add_argument("--score", type=int); s.add_argument("--note")
    s.add_argument("--count-run", action="store_true"); s.add_argument("--force", action="store_true"); s.add_argument("--scores")

    s = sub.add_parser("set"); s.set_defaults(fn=cmd_set); s.add_argument("key"); s.add_argument("value")

    s = sub.add_parser("event"); s.set_defaults(fn=cmd_event)
    s.add_argument("type"); s.add_argument("--set", action="append", metavar="KEY=VALUE"); s.add_argument("--json")
    s = sub.add_parser("feedback"); s.set_defaults(fn=cmd_feedback)
    s.add_argument("--worked", action="append", metavar="AREA:NOTE"); s.add_argument("--failed", action="append", metavar="AREA:NOTE")
    s.add_argument("--improve", action="append", metavar="AREA:NOTE"); s.add_argument("--json"); s.add_argument("--trigger", default="manual")
    s = sub.add_parser("telemetry"); s.set_defaults(fn=cmd_telemetry)
    s.add_argument("action", choices=["summary", "report", "export"]); s.add_argument("--out"); s.add_argument("--events", action="store_true")
    g = s.add_mutually_exclusive_group(); g.add_argument("--all", action="store_true"); g.add_argument("--since", metavar="YYYY-MM-DD")
    s.add_argument("--json", action="store_true"); s.add_argument("--stamp", help="timestamp for the export name (YYYYMMDD-HHMMSS)")
    s = sub.add_parser("cleanup"); s.set_defaults(fn=cmd_cleanup); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("deploy"); s.set_defaults(fn=cmd_deploy)
    s.add_argument("env", nargs="?", default="production"); s.add_argument("--sha", required=True); s.add_argument("--status", required=True)
    s.add_argument("--milestone"); s.add_argument("--migration")
    s = sub.add_parser("preview"); s.set_defaults(fn=cmd_preview)
    s.add_argument("milestone"); s.add_argument("--url"); s.add_argument("--sha"); s.add_argument("--pid", type=int)
    s.add_argument("--stopped", action="store_true")
    s = sub.add_parser("add-issue"); s.set_defaults(fn=cmd_add_issue)
    s.add_argument("--type", required=True); s.add_argument("--title", required=True)
    s.add_argument("--class", dest="cls", required=True); s.add_argument("--severity"); s.add_argument("--effort")
    s.add_argument("--affects"); s.add_argument("--origin", default="user"); s.add_argument("--acceptance", action="append")
    s.add_argument("--note"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("issue"); s.set_defaults(fn=cmd_issue); s.add_argument("id")
    s.add_argument("--status"); s.add_argument("--class", dest="cls"); s.add_argument("--severity"); s.add_argument("--effort")
    s.add_argument("--link"); s.add_argument("--duplicate-of"); s.add_argument("--note")
    s = sub.add_parser("pull-issues"); s.set_defaults(fn=cmd_pull_issues); s.add_argument("milestone"); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("cooldown"); s.set_defaults(fn=cmd_cooldown); s.add_argument("milestone"); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("backlog"); s.set_defaults(fn=cmd_backlog)
    s.add_argument("section", nargs="?", choices=["issues", "tasks", "questions", "findings", "deploy"]); s.add_argument("--json", action="store_true")
    s = sub.add_parser("tip"); s.set_defaults(fn=cmd_tip); s.add_argument("context"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("tips"); s.set_defaults(fn=cmd_tips); s.add_argument("--reset", action="store_true")
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s.add_argument("--short", action="store_true"); s.add_argument("--json", action="store_true")
    s.add_argument("--quiet-if-missing", action="store_true")
    s.add_argument("--head-migration", help="current migration head in the checkout, to show how far production is behind")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    store = Store(find_root(args.root))
    args.fn(store, args)


if __name__ == "__main__":
    main()
