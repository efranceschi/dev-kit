#!/usr/bin/env python3
"""dev_state.py - single source of truth for dev-kit project state (.dev/state.json).

Standard library only. Run with: python3 -I dev_state.py <subcommand> [...]

Subcommands
  init          create .dev/ and state.json (idempotent; updates given fields)
  sync-plan     read .dev/plan.md and add/update milestones and tasks (never touches status)
  strings       user-facing strings added since a commit (--since SHA [--worktree]), for the copy review
  contrast      WCAG contrast of the colour token pairs in ui-spec.md (--pairs fg/bg,… or automatic)
  lock          acquire | release | status NAME: one holder at a time for an exclusive resource (--holder --ttl --wait)
  brief T       base prompt of an implementer for task T (languages, commands, verification rule, history)
  next          print the next task to work on (fix tasks first, deps satisfied, gate respected); --batch N: tasks
                that can run in parallel (no common files, one serialising file at most)
  start T       mark task in_progress
  done T        mark task done (optionally --commit SHA)
  block T       mark task blocked (--reason)
  unblock T     blocked -> todo
  drop T        drop a task removed by a replan (--reason); it no longer counts for milestones or release
  add-task      create a task in state and plan.md
  fix-tasks     one fix task per blocking finding of a findings file (--from --milestone; idempotent)
  add-question  append a non-blocking question to open-questions.md (--options a|b --recommended a: the board
                offers them as answers)
  answer-question Q  move an open question to Resolved with its answer (--answer --ref)
  move-task T M move a task not started to another open milestone (--before T2), in plan.md and state
  new-milestone M TITLE  add the next milestone (M<last+1>) to plan.md and state; milestones are never inserted
  reorder M T…  new order of tasks not started inside a milestone (the order `next` follows)
  plan-apply    apply a plan draft from the board (--draft R-nnn, or --ops JSON): all its changes or none
                (--dry-run shows them)
  gate M        set milestone gate: passed | pending | skipped (passed needs --score >= cut-off)
  artifact mark NAME  record that an artifact (brief|prd|architecture|ux|ui|plan|all) is up to date with its upstream
  stale         artifacts whose upstream changed since they were marked, and passed reviews now out of date
  ledger        work ledger (conventions §18): plan | record (files of an audit dimension), sections |
                record-sections (document review), put | check | get KEY, drop --prefix; reuse only unchanged ok work
  tests         record | lookup: test results per commit (.dev/run/test-runs.jsonl) so a green suite is not re-run
                on unchanged code (--kind unit|integration|e2e|all, --paths); lookup exits 3 when nothing is reusable
  xref          cross-document checks: ACs without tasks, unknown ACs, unspecified screens, unknown ADRs and deps
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
  release-record  record a cut release (--version [--tag] [--milestones M1,M2 | --hotfix T]): the milestones
                leave the release train; the phase (conception, planning, construction, stable) is always derived
  set KEY VAL   set language | project | stack.<field> | autonomy.<field>[.<sub>] (nested keys merge;
                autonomy.level applies its preset; incl. autonomy.pause_policy.<point>)
  status        human (--short) or --json view; --next prints only the next command; --quiet-if-missing for hooks
  notify TEXT   queue a desktop notification shown at the end of the turn (only with autonomy.ui.notify on)

Exit codes: 0 ok · 1 usage/invalid transition · 2 state not found · 3 nothing to do (next)
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir; dev_telemetry lives next to us
import dev_telemetry as tel  # noqa: E402
import dev_ledger as led  # noqa: E402

STATE_VERSION = 1
# Project lifecycle (conventions.md §19): derived from the artifacts, reviews, milestones, issues and releases,
# never set by hand. Conception and planning run once at the start and again for every scope change; construction
# runs the milestone cycle and the release train; stable = nothing open, everything built is released.
PHASES = ["conception", "planning", "construction", "stable"]
CONCEPTION_STEPS = ["interview", "prd", "architecture", "ux", "ui"]
PLANNING_STEPS = ["plan"]
STEP_ARTIFACT = {"interview": "brief", "prd": "prd", "architecture": "architecture", "ux": "ux", "ui": "ui", "plan": "plan"}
STEP_REVIEW = {"prd": "prd", "ui": "design", "plan": "plan"}  # the design review covers ux and ui
# phase names of kit versions before 1.30 (a straight line); state.json files still holding one are migrated on load
LEGACY_PHASES = ["init", "interview", "prd", "architecture", "ux", "ui", "plan",
                 "implement", "qa", "usability", "docs", "done"]
TASK_TYPES = {"feature", "fix", "chore", "test", "docs"}
TASK_STATUSES = {"todo", "in_progress", "done", "blocked", "dropped"}
FINISHED = ("done", "dropped")  # a dropped task (replan) no longer holds a milestone or the release
GATES = {"passed", "pending", "skipped"}
BROWNFIELD_MODES = ("feature", "maintenance", "import")
DEFAULT_COMMIT_STYLE = "[{task}] {type}: {summary}"  # used when autonomy.commit_style is absent (conventions §5)

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
    # Rounds of a document review (prd, design, plan, docs) before rounds_exhausted applies (conventions.md §9).
    "max_review_rounds": 3,
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
    # Claude Code interface (conventions.md §15): offered = start already asked once; spinner_tips and statusline are
    # written to the project's .claude/settings.local.json by dev_ui.py; title = session title and one-line banner at
    # session start (hook); notify = desktop notification at the end of the turn for gates, blocks and autopilot.
    "ui": {"offered": False, "spinner_tips": False, "statusline": False, "title": True, "notify": False},
    # Cheap checks at the end of each task (conventions.md §7): ui = copy and static a11y agents on tasks that touch
    # UI files (haiku) | all = also on other tasks with user-facing strings | off = implementer self-check only.
    "task_checks": "ui",
    # Incremental work (conventions.md §18): reuse verified units whose inputs did not change. spot_check_pct of the
    # reused units is re-verified each round; full_on_last_gate turns the cache off for the last milestone gate.
    "incremental": {"enabled": True, "spot_check_pct": 10, "full_on_last_gate": False},
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

# Level presets (shared/interview/autonomy-policy.md). `set autonomy.level` applies them; the interview may
# then override single fields. Quality numbers only ever go up through a preset.
LEVEL_PRESETS = {
    "high": {"decide_alone": DEFAULT_AUTONOMY["decide_alone"], "always_ask": DEFAULT_AUTONOMY["always_ask"], "quality": {}},
    "balanced": {
        "decide_alone": ["library_choice", "file_structure", "naming", "test_strategy", "dev_tooling"],
        "always_ask": DEFAULT_AUTONOMY["always_ask"] + ["ui_details", "data_model_details", "minor_scope_tradeoffs"],
        "quality": {},
    },
    "cautious": {
        "decide_alone": ["naming", "file_structure"],
        "always_ask": DEFAULT_AUTONOMY["always_ask"] + ["library_choice", "test_strategy", "ui_details",
                                                       "data_model_details", "minor_scope_tradeoffs", "dev_tooling"],
        "quality": {"min_overall": 90, "review_min_overall": 85, "min_dimension": 75,
                    "dimension_min": {"security": 95, "tests": 85, "spec": 90, "a11y": 85}},
    },
    "unattended": {"decide_alone": DEFAULT_AUTONOMY["decide_alone"], "always_ask": DEFAULT_AUTONOMY["always_ask"], "quality": {}},
}
LEVELS = tuple(LEVEL_PRESETS)
BOOL_FIELDS = ("commit_per_task", "may_install_deps", "may_run_servers", "may_push", "notify_on_park")
INT_FIELDS = {"max_fix_rounds_per_gate": (1, 10), "max_review_rounds": (1, 10), "task_time_budget_min": (5, 480)}

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
TASK_CHECKS = ("ui", "all", "off")
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


def check_commit_style(cs: object) -> None:
    if not isinstance(cs, str) or "{summary}" not in cs:
        fail('autonomy.commit_style must be a template containing {summary}, e.g. "{type}: {summary}" or "[{task}] {type}: {summary}"')
    try:
        cs.format(task="T-001", type="feat", summary="x")
    except (KeyError, IndexError, ValueError):
        fail("autonomy.commit_style may only use the placeholders {task}, {type} and {summary}")


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
            if point == "paid_services":
                v = limit[key]
                if not (v == "unlimited" or (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0)):
                    fail('pause_policy.paid_services limit.max_monthly must be a positive amount or "unlimited" '
                         '(an explicit choice: no monthly cap, still recorded as an ADR per service)')
            if point == "delete_data" and any(str(e).lower() in PROD_NAMES for e in limit[key]):
                fail("pause_policy.delete_data can never be preauthorized for production")


def pause_action(state: dict, point: str) -> str:
    return state.get("autonomy", {}).get("pause_policy", {}).get(point, {}).get("action", "ask")


def _copy(x):
    return json.loads(json.dumps(x))


def merge_quality(q: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(q.get(k), dict):
            q[k].update(v)
        else:
            q[k] = v
    return q


def apply_level(state: dict, level: str) -> None:
    """Apply a level preset. Leaving unattended restores the supervised pause and model policies.
    Existing projects keep dirty_tree at ask (the tree may hold the user's own work, conventions §16)."""
    if level not in LEVEL_PRESETS:
        fail(f"autonomy.level must be {' | '.join(LEVELS)}")
    auto = state.setdefault("autonomy", _copy(DEFAULT_AUTONOMY))
    previous = auto.get("level")
    preset = LEVEL_PRESETS[level]
    auto["level"] = level
    auto["decide_alone"] = list(preset["decide_alone"])
    auto["always_ask"] = list(preset["always_ask"])
    if state.get("brownfield") and "dev_tooling" in auto["decide_alone"]:
        auto["decide_alone"].remove("dev_tooling")  # new runners, linters, formatters: always ask (§16)
        auto["always_ask"].append("dev_tooling")
    if preset["quality"]:
        q = auto.setdefault("quality", _copy(DEFAULT_AUTONOMY["quality"]))
        for k, v in preset["quality"].items():  # a preset never lowers a bar the user raised
            if isinstance(v, dict):
                cur = q.setdefault(k, {})
                for dk, dv in v.items():
                    cur[dk] = max(dv, cur.get(dk, 0))
            else:
                q[k] = max(v, q.get(k, 0))
    if level == "unattended":
        auto["pause_policy"] = _copy(UNATTENDED_PAUSE_POLICY)
        auto["model_policy"] = {**auto.get("model_policy", {"tiers": {}}), "mode": "preapproved"}
    elif previous == "unattended":
        auto["pause_policy"] = {}
        auto["model_policy"] = {**auto.get("model_policy", {"tiers": {}}), "mode": "ask"}
    if state.get("brownfield"):
        auto.setdefault("pause_policy", {})["dirty_tree"] = {"action": "ask"}


def check_autonomy_field(field: str, val: object) -> object:
    """Validate one top-level autonomy field (shared by init --autonomy-json and set). Returns the value to store."""
    if field in BOOL_FIELDS:
        if isinstance(val, str) and val.lower() in ("true", "yes", "on", "false", "no", "off"):
            val = val.lower() in ("true", "yes", "on")
        if not isinstance(val, bool):
            fail(f"autonomy.{field} must be true or false")
    elif field in INT_FIELDS:
        lo, hi = INT_FIELDS[field]
        if isinstance(val, str) and val.isdigit():
            val = int(val)
        if not isinstance(val, int) or isinstance(val, bool) or not lo <= val <= hi:
            fail(f"autonomy.{field} must be an integer between {lo} and {hi}")
    elif field == "issue_buffer_pct":
        if isinstance(val, str) and val.isdigit():
            val = int(val)
        if not isinstance(val, int) or isinstance(val, bool) or not 0 <= val <= 50:
            fail("autonomy.issue_buffer_pct must be an integer between 0 and 50")
    elif field == "tips":
        if val not in TIPS_MODES:
            fail(f"autonomy.tips must be one of {', '.join(TIPS_MODES)}")
    elif field == "on_park":
        if val not in ON_PARK:
            fail(f"autonomy.on_park must be one of {', '.join(ON_PARK)}")
    elif field == "incremental":
        if not isinstance(val, dict) or set(val) - {"enabled", "spot_check_pct", "full_on_last_gate"}:
            fail("autonomy.incremental must be an object with enabled, spot_check_pct, full_on_last_gate")
        if "spot_check_pct" in val and (not isinstance(val["spot_check_pct"], (int, float)) or isinstance(val["spot_check_pct"], bool)
                                        or not 0 <= val["spot_check_pct"] <= 100):
            fail("autonomy.incremental.spot_check_pct must be a number between 0 and 100")
        for k in ("enabled", "full_on_last_gate"):
            if k in val and not isinstance(val[k], bool):
                fail(f"autonomy.incremental.{k} must be true or false")
    elif field == "task_checks":
        if val not in TASK_CHECKS:
            fail(f"autonomy.task_checks must be one of {', '.join(TASK_CHECKS)}")
    elif field == "commit_style":
        check_commit_style(val)
    elif field == "model_policy":
        check_model_policy(val)
    elif field == "local_deploy":
        check_local_deploy(val)
    elif field == "cooldown":
        if not isinstance(val, dict) or not isinstance(val.get("enabled", False), bool) or not isinstance(val.get("max_tasks", 5), int):
            fail('autonomy.cooldown must be on | off or {"enabled": true, "max_tasks": 5}')
    elif field in ("decide_alone", "always_ask"):
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            fail(f"autonomy.{field} must be a list of decision categories")
    elif field == "quality":
        if not isinstance(val, dict):
            fail("autonomy.quality must be an object")
    elif field == "ui":
        if not isinstance(val, dict) or set(val) - set(UI_KEYS) or not all(isinstance(v, bool) for v in val.values()):
            fail(f"autonomy.ui must be an object with true/false values for {', '.join(UI_KEYS)}")
        val = {**DEFAULT_AUTONOMY["ui"], **val}
    return val


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
ISSUE_ORIGINS = ("user", "qa", "usability", "deploy", "feedback", "review", "baseline")
LANES = ("hotfix", "cooldown")
CLASS_RANK = {"standard": 0, "intangible": 1}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TIPS_MODES = ("on", "off", "always")
UI_KEYS = ("offered", "spinner_tips", "statusline", "title", "notify")


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
        migrate_legacy_phase(self)
        return self.state

    def save(self) -> None:
        self.state["updated_at"] = now()
        try:  # cached for the status line, the session banner and the board, which read state.json directly
            lc = lifecycle(self)
            self.state["phase"], self.state["step"], self.state["reopened"] = lc["phase"], lc["step"], lc["reopened"]
        except Exception:  # noqa: BLE001 - a derived label must never stop the state from being saved
            pass
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
        ts = [v for v in self.tasks().values() if v["milestone"] == m and v["status"] != "dropped"]
        return bool(ts) and all(v["status"] == "done" for v in ts)

    def gate_open_for(self, m: str) -> tuple[bool, str]:
        """A milestone is workable if every previous milestone has gate passed/skipped (or has no tasks)."""
        for prev in self.milestone_order():
            if prev == m:
                return True, ""
            gate = self.milestones()[prev].get("gate", "pending")
            has_tasks = any(v["milestone"] == prev and v["status"] != "dropped" for v in self.tasks().values())
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
            elif key == "contract":
                task["contract"] = val  # what this task provides to others (columns, routes, field names), §4
            elif key == "consumes":
                task["consumes"] = [d.strip() for d in re.split(r"[,\s]+", val) if d.strip()]
            elif key == "shared":
                task["shared"] = val.strip().lower() not in ("", "no", "false", "0")
            else:
                task.setdefault("extra", {})[key] = val
            continue
        s = SUBITEM_RE.match(raw)
        if s and cur_field == "contract":
            tasks[cur_t]["contract"] = "; ".join(x for x in (tasks[cur_t].get("contract") or "", s.group(1)) if x)
            continue
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
            "version": STATE_VERSION, "project": None, "language": None, "phase": "conception", "step": "interview",
            "autonomy": json.loads(json.dumps(DEFAULT_AUTONOMY)), "stack": {}, "reviews": {}, "milestones": {}, "tasks": {},
            "next_task_id": 1, "next_question_id": 1, "created_at": now(), "updated_at": now(),
        }
        created = True
    if a.project:
        store.state["project"] = a.project
    if a.language:
        store.state["language"] = a.language
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
        if "mode" in bf and bf["mode"] not in BROWNFIELD_MODES:
            fail(f"brownfield.mode must be one of {', '.join(BROWNFIELD_MODES)}")
        if "first_milestone" in bf and (not isinstance(bf["first_milestone"], int) or isinstance(bf["first_milestone"], bool)
                                        or bf["first_milestone"] < 1):
            fail("brownfield.first_milestone must be an integer >= 1 (the number of the first milestone, e.g. 1 for M1)")
        old = store.state.get("brownfield", {})
        store.state["brownfield"] = {**old, **bf}
        if old.get("mode") == "maintenance" and bf.get("mode") in ("feature", "import"):
            # leaving maintenance: the as-built n/a reviews no longer apply to the new PRD, design and plan
            for name, r in (store.state.get("reviews") or {}).items():
                if r.get("verdict") == "n/a":
                    r.update({"verdict": "pending", "note": f"reopened: mode {old['mode']} -> {bf['mode']}", "at": now()})
                    print(f"review {name}: n/a -> pending (mode changed to {bf['mode']})")
        auto = store.state.setdefault("autonomy", _copy(DEFAULT_AUTONOMY))
        auto.setdefault("pause_policy", {})["dirty_tree"] = {"action": "ask"}
    if a.autonomy_json:
        try:
            patch = json.loads(a.autonomy_json)
        except json.JSONDecodeError as e:
            fail(f"--autonomy-json is not valid JSON: {e}")
        if not isinstance(patch, dict):
            fail("--autonomy-json must be a JSON object")
        auto = store.state.setdefault("autonomy", _copy(DEFAULT_AUTONOMY))
        q_patch = patch.pop("quality", None)
        if q_patch is not None:
            check_autonomy_field("quality", q_patch)
        level = patch.pop("level", None)
        if level is not None:
            apply_level(store.state, level)  # preset first; explicit fields below override it
        for f in list(patch):
            if f == "ui":
                check_autonomy_field(f, patch[f])
                patch[f] = {**DEFAULT_AUTONOMY["ui"], **auto.get("ui", {}), **patch[f]}
            elif f not in ("pause_policy", "production", "local_deploy"):
                patch[f] = check_autonomy_field(f, patch[f])
        if "pause_policy" in patch:
            check_pause_policy(patch["pause_policy"])
            patch["pause_policy"] = {**auto.get("pause_policy", {}), **patch["pause_policy"]}
        if "production" in patch:
            check_production({**DEFAULT_AUTONOMY["production"], **auto.get("production", {}), **patch["production"]})
            patch["production"] = {**DEFAULT_AUTONOMY["production"], **auto.get("production", {}), **patch["production"]}
        if "local_deploy" in patch:
            check_local_deploy(patch["local_deploy"])
            patch["local_deploy"] = {**DEFAULT_AUTONOMY["local_deploy"], **auto.get("local_deploy", {}), **patch["local_deploy"]}
        if "cooldown" in patch:
            patch["cooldown"] = {**DEFAULT_AUTONOMY["cooldown"], **auto.get("cooldown", {}), **patch["cooldown"]}
        auto.update(patch)
        if q_patch is not None:
            merge_quality(auto.setdefault("quality", _copy(DEFAULT_AUTONOMY["quality"])), q_patch)
        if store.state.get("brownfield"):
            auto.setdefault("pause_policy", {})["dirty_tree"] = {"action": "ask"}
    store.save()
    gi = store.dev / ".gitignore"
    if not gi.exists():  # machine-local files never belong in git; the rest of .dev/ is versioned with the code
        gi.write_text("# written by dev_state.py init\nrun/\npreview/\ntmp/\ntelemetry-session\n", encoding="utf-8")
    oq = store.dev / "open-questions.md"
    if not oq.exists():
        oq.write_text(
            "# Open questions\n\n> Non-blocking doubts raised while working autonomously. "
            "Resolve with `/dev-kit:interview --gaps`.\n\n## Open\n"
            "| id | date | raised by | question | assumption used | impact if wrong |\n"
            "|---|---|---|---|---|---|\n\n## Resolved\n| id | resolved on | answer | ADR / task |\n|---|---|---|---|\n",
            encoding="utf-8",
        )
    store.log("init " + ("created" if created else "updated") + f" (phase={store.state.get('phase')}, language={store.state.get('language')})")
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


def sync_plan_text(store: Store, text: str) -> tuple[dict, tuple[int, int, int], list[str]]:
    """Bring state in line with plan.md text, in memory: milestones and tasks added or updated (never status), each
    task's position in the plan as `seq` (the order `next` follows within a milestone). Returns the parsed tasks,
    the counts (milestones added, tasks added, tasks updated) and the problems found. Raises ValueError."""
    milestones, tasks = parse_plan(text)
    added_m = added_t = updated_t = 0
    for m, info in milestones.items():
        if m not in store.milestones():
            store.milestones()[m] = {"title": info["title"], "gate": "pending", "qa_runs": 0}
            added_m += 1
        else:
            store.milestones()[m]["title"] = info["title"]
    max_id = int(store.state.get("next_task_id", 1)) - 1
    for seq, (tid, t) in enumerate(tasks.items(), 1):
        t["seq"] = seq
        max_id = max(max_id, int(tid[2:]))
        if tid in store.tasks():
            cur = store.tasks()[tid]
            for k in ("title", "milestone", "type", "deps", "acceptance", "test_notes", "files", "seq"):
                cur[k] = t[k]
            for k in ("contract", "consumes", "shared"):
                if k in t:
                    cur[k] = t[k]
                else:
                    cur.pop(k, None)
            updated_t += 1
        else:
            store.tasks()[tid] = {
                "title": t["title"], "milestone": t["milestone"], "type": t["type"],
                "status": "todo", "deps": t["deps"], "acceptance": t["acceptance"],
                "test_notes": t["test_notes"], "files": t["files"], "commit": None,
                "blocked_reason": None, "source": None, "started_at": None, "done_at": None, "seq": t["seq"],
                **{k: t[k] for k in ("contract", "consumes", "shared") if k in t},
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
        for d in t.get("consumes") or []:
            if d not in store.tasks():
                problems.append(f"{tid}: consumes {d}, which does not exist")
            elif d not in t["deps"]:
                problems.append(f"{tid}: consumes {d} but does not depend on it (add it to deps)")
        if t["milestone"] not in store.milestones():
            problems.append(f"{tid}: milestone {t['milestone']} not declared")
    return tasks, (added_m, added_t, updated_t), problems


def cmd_sync_plan(store: Store, a: argparse.Namespace) -> None:
    store.load()
    plan_path = Path(a.plan) if a.plan else store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    try:
        tasks, (added_m, added_t, updated_t), problems = sync_plan_text(store, plan_path.read_text(encoding="utf-8"))
    except ValueError as e:
        fail(str(e))
    store.save()
    record_baseline(store, tasks)
    store.log(f"sync-plan +{added_m} milestones, +{added_t} tasks, ~{updated_t} updated")
    print(f"synced: {added_m} new milestones, {added_t} new tasks, {updated_t} updated")
    if problems:
        print("warnings:\n  " + "\n  ".join(problems))


def plan_order(ts: dict, tid: str) -> tuple[int, int]:
    """Position of a task in plan.md (seq, set by sync-plan), then its id: a task added after the last sync sits
    at the end of its milestone section, and so comes after the synced ones."""
    seq = ts[tid].get("seq")
    return (seq if isinstance(seq, int) else 10 ** 6, int(tid[2:]))


def pick_next(store: Store, milestone: str | None) -> tuple[str | None, str]:
    ts = store.tasks()
    if not ts:
        return None, "no tasks; run plan then sync-plan"
    if all(v["status"] in FINISHED for v in ts.values()):
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
        pending = {t: v for t, v in ts.items() if v["milestone"] == m and v["status"] not in FINISHED}
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
        ready.sort(key=lambda t: (0 if ts[t].get("lane") == "cooldown" else 1, 0 if ts[t]["type"] == "fix" else 1, plan_order(ts, t)))
        return ready[0], ""
    return None, "nothing to do"


# Files that make tasks run one at a time (implement --parallel): registries, barrels, migration heads, manifests.
SERIAL_FILES = re.compile(r"(^|/)(package(-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|"
                          r"poetry\.lock|uv\.lock|Cargo\.(toml|lock)|go\.(mod|sum)|Gemfile(\.lock)?|__init__\.py|"
                          r"index\.(t|j)sx?|routes?\.(t|j)sx?|urls\.py|CHANGELOG\.md|README\.md)$|(^|/)(migrations?|alembic)/")


def pick_batch(store: Store, milestone: str | None, n: int) -> tuple[list[str], str]:
    """Up to n ready tasks that can run in parallel: no shared files between them, at most one that touches a
    serialising file (SERIAL_FILES, or `shared` in the plan) or lists no files, hotfixes alone."""
    first, why = pick_next(store, milestone)
    if first is None:
        return [], why
    ts = store.tasks()
    t0 = ts[first]
    if t0.get("lane") == "hotfix" or n <= 1:
        return [first], ""
    m = t0["milestone"]
    ready = [t for t, v in ts.items() if v["milestone"] == m and v["status"] == "todo" and v.get("lane") != "hotfix"
             and all(ts.get(d, {}).get("status") == "done" for d in v["deps"])]
    ready.sort(key=lambda t: (t != first, 0 if ts[t].get("lane") == "cooldown" else 1, 0 if ts[t]["type"] == "fix" else 1, plan_order(ts, t)))
    chosen, files, serial_used = [], set(), False
    for t in ready:
        fs = set(ts[t].get("files") or [])
        serial = (not fs) or bool(ts[t].get("shared")) or any(SERIAL_FILES.search(f) for f in fs)
        if fs & files or (serial and serial_used):
            continue
        chosen.append(t)
        files |= fs
        serial_used = serial_used or serial
        if len(chosen) >= n:
            break
    return chosen, ""


def cmd_next(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if getattr(a, "batch", None):
        batch, why = pick_batch(store, a.milestone, a.batch)
        if not batch:
            print(json.dumps({"tasks": [], "reason": why}) if a.json else f"no task available: {why}")
            sys.exit(3)
        if a.json:
            print(json.dumps({"tasks": [{"task": t, **store.tasks()[t]} for t in batch]}, ensure_ascii=False))
        else:
            for t in batch:
                v = store.tasks()[t]
                print(f"{t} [{v['milestone']}] ({v['type']}) {v['title']}" + (f" · files: {', '.join(v['files'])}" if v["files"] else ""))
        return
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
    if t["status"] in FINISHED:
        fail(f"{a.task} is already {t['status']}")
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
    store.save()
    store.log(f"start {a.task} {t['title']}")
    store.event("task", task=a.task, transition="start", type=t.get("type"), milestone=t.get("milestone"), parallel=bool(a.force and others))
    print(f"{a.task} in_progress: {t['title']}")


def cmd_done(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] == "done":
        if a.commit and a.force and a.commit != t.get("commit"):
            old = t.get("commit")
            t["commit"] = a.commit
            store.save()
            store.log(f"done {a.task} commit corrected {old or '-'} -> {a.commit}")
            print(f"{a.task} already done · commit corrected to {a.commit[:12]}")
        else:
            print(f"{a.task} already done" + (" (pass --force with --commit to correct the recorded SHA)" if a.commit else ""))
        return
    if t["status"] == "dropped":
        fail(f"{a.task} was dropped; add a new task instead")
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
        msg += f" · hotfix: run qa --scope {a.task}, then release --hotfix (it deploys)"
    elif store.milestone_done(m):
        msg += f" · milestone {m} complete -> run qa {m}"
    print(msg)


def cmd_block(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] in FINISHED:
        fail(f"{a.task} is {t['status']}; cannot block")
    t["status"] = "blocked"
    t["blocked_reason"] = a.reason
    store.save()
    store.log(f"block {a.task}: {a.reason}")
    store.event("task", task=a.task, transition="block", type=t.get("type"), milestone=t.get("milestone"))
    print(f"{a.task} blocked: {a.reason}")
    queue_notice(store, f"dev-kit · {a.task} blocked · {next_command(store)}")


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


def cmd_drop(store: Store, a: argparse.Namespace) -> None:
    """A task removed by a replan: kept for history, no longer counted by milestones, next or release."""
    store.load()
    t = store.task(a.task)
    if t["status"] == "done":
        fail(f"{a.task} is done; a delivered task is reverted by a new task, not dropped")
    if t["status"] == "dropped":
        print(f"{a.task} already dropped")
        return
    t["status"] = "dropped"
    t["blocked_reason"] = None
    t["dropped_reason"] = a.reason
    t["dropped_at"] = now()
    issue_sync(store, t)
    store.save()
    store.log(f"drop {a.task}: {a.reason}")
    store.event("task", task=a.task, transition="drop", type=t.get("type"), milestone=t.get("milestone"))
    print(f"{a.task} dropped: {a.reason}")


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
    elif store.milestones()[a.milestone].get("gate") == "passed" and a.lane != "hotfix" and not a.force:
        nxt = f"M{max(int(m[1:]) for m in store.milestones()) + 1}"
        later = [m for m in store.milestone_order() if int(m[1:]) > int(a.milestone[1:])
                 and store.milestones()[m].get("gate", "pending") == "pending"]
        fail(f"gate of {a.milestone} already passed; add the task to {later[0] if later else nxt}"
             + ("" if later else f" (--milestone {nxt} --milestone-title \"...\")") + ", use --lane hotfix, or --force")
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


def cmd_fix_tasks(store: Store, a: argparse.Namespace) -> None:
    """Create one fix task per blocking finding of a consolidated findings file (qa §4), deterministically and
    idempotently: a finding that already has a task with the same source anchor is skipped.

    A finding still open from an earlier round (`previous`) whose fix task is done means the fix did not hold: the
    task is reopened the first time and blocked the second (`rounds_exhausted`: the same finding came back twice),
    so the card leaves Done and waits for a decision instead of disappearing. A new finding that reuses the id of an
    earlier, closed one gets a round-qualified anchor, so it is not mistaken for the old one."""
    store.load()
    path = Path(a.src_file)
    if not path.is_absolute():
        path = store.root / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read {path}: {e}")
    items = data.get("findings", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        fail("findings file must be a list or {\"findings\": [...]}")
    if a.milestone not in store.milestones():
        fail(f"milestone {a.milestone} does not exist")
    block_on = set(quality_cfg(store).get("block_on", ["critical", "high"]))
    extra = {x.strip() for x in (a.include or "").split(",") if x.strip()}
    source = a.source or f"qa/{a.milestone}/report.md"
    existing = {str(t.get("source") or "") for t in store.tasks().values() if t.get("status") != "dropped"}
    by_anchor = {str(t.get("source") or ""): tid for tid, t in store.tasks().items() if t.get("status") != "dropped"}
    round_n = data.get("round") if isinstance(data, dict) and isinstance(data.get("round"), int) else \
        int(store.milestones()[a.milestone].get("qa_runs", 0)) + 1
    created, skipped, reopened, blocked = [], [], [], []
    for f in items:
        if not isinstance(f, dict) or f.get("legacy") or f.get("out_of_scope") or not f.get("id"):
            continue
        sev = str(f.get("severity", "")).lower()
        if sev not in block_on and f["id"] not in extra:
            continue
        anchor = f"{source}#{f['id']}"
        twins = {f"{source}#{x}" for x in f.get("same_as") or []}
        tid = by_anchor.get(anchor)
        if f.get("previous") and tid and store.tasks()[tid]["status"] == "done":
            # still open after its fix was done: the fix did not hold
            t = store.tasks()[tid]
            returns = int(t.get("returns", 0)) + 1
            if a.dry_run:
                (blocked if returns >= 2 else reopened).append(f"{tid}={f['id']}")
                continue
            t["returns"] = returns
            t.pop("done_at", None)
            if returns >= 2:
                t["status"] = "blocked"
                t["blocked_reason"] = (f"{f['id']} is still open after {returns} fixes (rounds_exhausted): keep fixing, "
                                       f"accept with an ADR, or change the spec")
                blocked.append(f"{tid}={f['id']}")
                store.log(f"block {tid}: {t['blocked_reason']}")
                store.event("task", task=tid, transition="block", type=t.get("type"), milestone=t.get("milestone"))
            else:
                t["status"], t["blocked_reason"] = "todo", None
                reopened.append(f"{tid}={f['id']}")
                store.log(f"reopen {tid}: {f['id']} still open after the fix (round {round_n})")
                store.event("task", task=tid, transition="reopen", type=t.get("type"), milestone=t.get("milestone"))
            store.save()  # add_task below reloads the state from disk
            continue
        old_t = store.tasks()[tid] if tid else None
        if (old_t and not f.get("previous") and not twins & existing and old_t["status"] == "done"
                and old_t.get("qa_round", round_n - 1) != round_n):
            # a new finding that reuses the id of an earlier, closed one: its own task, under a round-qualified anchor
            anchor = f"{source}#{f['id']}-r{round_n}"
        if anchor in existing or twins & existing:
            skipped.append(f["id"])  # already has a task, or the same problem reported by another dimension has one
            continue
        cond = str(f.get("recommendation") or f.get("failure_scenario") or "the finding no longer reproduces").strip()
        acc = [f"{f['id']} resolved: {cond[:200]}"]
        if f.get("acceptance_ref"):
            acc.insert(0, f"{f['acceptance_ref']} met")
        files = f.get("file") or ""
        if isinstance(f.get("files"), list):
            files = ",".join(str(x) for x in f["files"])
        if a.dry_run:
            created.append(f["id"])
            continue
        ns = argparse.Namespace(type="fix", milestone=a.milestone, milestone_title=None, title=str(f.get("title") or f["id"])[:80],
                                deps=None, acceptance=acc, test_notes=f"regression test for {f['id']}", files=files,
                                source=anchor, issue=None, lane=None, force=False)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            cmd_add_task(store, ns)
        new_id = buf.getvalue().strip()
        if new_id in store.tasks():
            store.tasks()[new_id]["qa_round"] = round_n
            store.save()
        created.append(f"{new_id}={f['id']}")
        existing.add(anchor)
    if a.json:
        print(json.dumps({"created": created, "skipped": skipped, "reopened": reopened, "blocked": blocked, "dry_run": bool(a.dry_run)}))
    else:
        verb = "would create" if a.dry_run else "created"
        print(f"fix-tasks {a.milestone}: {verb} {len(created)}" + (f" ({', '.join(created)})" if created else "")
              + (f"; reopened (fix did not hold): {', '.join(reopened)}" if reopened else "")
              + (f"; blocked (came back twice, rounds_exhausted): {', '.join(blocked)}" if blocked else "")
              + (f"; already had a task: {', '.join(skipped)}" if skipped else ""))


def cmd_add_question(store: Store, a: argparse.Namespace) -> None:
    store.load()
    options = [o.strip().replace("|", "/") for o in (a.options or "").split("|") if o.strip()]
    if a.options is not None and not 2 <= len(options) <= 6:
        fail("--options takes 2 to 6 answers separated by |")
    if a.recommended is not None and a.recommended.strip() not in options:
        fail("--recommended must be one of --options")
    if a.request is not None and not re.fullmatch(r"R-\d{3,6}", a.request):
        fail("--request takes a board request id such as R-004")
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
    if options:  # the board shows them as answers to pick (conventions §10, board mode)
        _write_json(question_sidecar(store, qid), {"id": qid, "options": options, "recommended": a.recommended,
                                                   "request": a.request, "answered": False, "at": now()})
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
    # past the agreed number of fix rounds the next round is the user's (or the policy's) decision, not automatic:
    # the open fix tasks of this milestone go to Blocked with the reason, so `next` stops picking them
    max_rounds = int((store.state.get("autonomy") or {}).get("max_fix_rounds_per_gate") or DEFAULT_AUTONOMY["max_fix_rounds_per_gate"])
    exhausted = []
    if a.count_run and a.value == "pending" and m["qa_runs"] > max_rounds:
        for tid, t in store.tasks().items():
            if t.get("milestone") == a.milestone and t.get("type") == "fix" and t.get("status") in ("todo", "in_progress"):
                t["status"] = "blocked"
                t["blocked_reason"] = (f"QA round limit reached ({m['qa_runs'] - 1} fix rounds of {max_rounds}; rounds_exhausted): "
                                       f"keep fixing, accept with an ADR, or replan")
                exhausted.append(tid)
    store.save()
    for tid in exhausted:
        store.log(f"block {tid}: {store.tasks()[tid]['blocked_reason']}")
        store.event("task", task=tid, transition="block", type="fix", milestone=a.milestone)
    store.event("gate", scope=a.milestone, value=a.value, score=a.score, qa_runs=m.get("qa_runs", 0),
                forced=bool(a.force and a.value == "passed"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "passed" else None)
    store.log(f"gate {a.milestone} {a.value}" + (f" score={a.score}" if a.score is not None else "") + (f" ({a.note})" if a.note else ""))
    print(f"{a.milestone} gate: {a.value}" + (f" (score {a.score})" if a.score is not None else ""))
    if exhausted:
        print(f"{a.milestone}: {m['qa_runs'] - 1} fix rounds used of {max_rounds} (rounds_exhausted); blocked {', '.join(exhausted)}")
    if a.value == "passed" or a.count_run:
        queue_notice(store, f"dev-kit · {a.milestone} gate {a.value}" + (f" ({a.score})" if a.score is not None else "")
                     + f" · {next_command(store)}")
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
    if not store.exists():  # logging never blocks work: before `init` there is no session to log into
        print("event skipped: no state yet (run init first; the session starts after it)", file=sys.stderr)
        return
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
    if a.type in ("agent_spawn", "agent_end") and not fields.get("scope"):
        agent = str(fields.get("agent") or "").removeprefix("dev-kit:")
        doing = [t for t, v in store.tasks().items() if v.get("status") == "in_progress"]
        if agent == "implementer" and len(doing) == 1:
            fields["scope"] = doing[0]
            print(f"warning: {a.type} without scope: using {doing[0]}, the only task in progress "
                  "(always pass --set scope=T-xxx)", file=sys.stderr)
        else:
            print(f"warning: {a.type} without scope: the board cannot place this agent on a task or QA gate "
                  "(pass --set scope=T-xxx or Mn)", file=sys.stderr)
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
    shared = f" · shared on the network ({rec.get('host')})" if rec.get("exposed") else ""
    return f"Board: {rec.get('url')} (pid {pid}){shared} · stop with /dev-kit:board stop"


LOCK_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,59}$")


def _lock_path(store: Store, name: str) -> Path:
    if not LOCK_NAME.match(name):
        fail("lock names are short lowercase tokens (e.g. remote-session, shared-db, emulator)")
    return store.dev / "run" / "locks" / f"{name}.json"


def _lock_read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _lock_expired(rec: dict | None) -> bool:
    if not rec:
        return True
    try:
        at = datetime.fromisoformat(str(rec.get("at")).replace("Z", "+00:00"))
    except ValueError:
        return True
    ttl = rec.get("ttl_min")
    return (datetime.now(timezone.utc) - at).total_seconds() >= float(30 if ttl is None else ttl) * 60


def cmd_lock(store: Store, a: argparse.Namespace) -> None:
    """Exclusive resources (architecture.md "Exclusive resources"): one holder at a time, with expiry, so parallel
    agents never share a remote session, a shared database or an emulator."""
    store.load()
    if a.action == "status":
        d = store.dev / "run" / "locks"
        recs = {p.stem: _lock_read(p) for p in sorted(d.glob("*.json"))} if d.exists() else {}
        if a.json:
            print(json.dumps({k: {**(v or {}), "expired": _lock_expired(v)} for k, v in recs.items()}, indent=2))
        else:
            print("\n".join(f"{k}: {v.get('holder')} since {v.get('at')}" + (" (expired)" if _lock_expired(v) else "")
                            for k, v in recs.items() if v) or "no locks held")
        return
    if not a.name:
        fail(f"lock {a.action} needs a resource name")
    path = _lock_path(store, a.name)
    if a.action == "release":
        rec = _lock_read(path)
        if rec and rec.get("holder") != a.holder and not a.force:
            fail(f"{a.name} is held by {rec.get('holder')}, not {a.holder}; use --force only for a dead holder")
        path.unlink(missing_ok=True)
        print(f"released {a.name}")
        return
    if not a.holder:
        fail("lock acquire needs --holder <agent-slot> (e.g. implementer-2)")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0, a.wait or 0)
    while True:
        body = json.dumps({"holder": a.holder, "at": now(), "ttl_min": a.ttl, "note": (a.note or "")[:120]})
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            print(f"acquired {a.name} for {a.holder} (expires in {a.ttl} min unless renewed)")
            return
        except FileExistsError:
            rec = _lock_read(path)
            if rec and rec.get("holder") == a.holder or _lock_expired(rec):
                path.write_text(body, encoding="utf-8")  # renew own lock, or take over an expired one
                print(f"acquired {a.name} for {a.holder}" + ("" if rec and rec.get("holder") == a.holder else " (previous lock expired)"))
                return
            if time.monotonic() >= deadline:
                print(f"{a.name} is held by {rec.get('holder')} since {rec.get('at')}; retry later or pass --wait <seconds>")
                sys.exit(3)
            time.sleep(min(5.0, max(0.2, deadline - time.monotonic())))


def cmd_cleanup(store: Store, a: argparse.Namespace) -> None:
    """Kill the background processes agents recorded in .dev/run/*.pids, but only those inside this project."""
    store.load()
    for lp in sorted((store.dev / "run" / "locks").glob("*.json")) if (store.dev / "run" / "locks").exists() else []:
        if _lock_expired(_lock_read(lp)) and not getattr(a, "dry_run", False):
            lp.unlink(missing_ok=True)  # expired exclusive-resource locks
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


TEST_KINDS = ("unit", "integration", "e2e", "all")


def _tree_dirty(store: Store) -> bool | None:
    out = _git(store, "status", "--porcelain", "--", ".", ":(exclude).dev")
    return None if out is None else bool(out)


def test_runs_path(store: Store) -> Path:
    return store.dev / "run" / "test-runs.jsonl"


def cmd_tests(store: Store, a: argparse.Namespace) -> None:
    """Test results per commit (machine-local), so the same suite is not run again on the same code by the
    implementer, the test auditor and the gate (qa §2)."""
    store.load()
    if a.kind not in TEST_KINDS:
        fail(f"--kind must be one of {', '.join(TEST_KINDS)}")
    path = test_runs_path(store)
    if a.action == "record":
        sha = _git(store, "rev-parse", a.sha or "HEAD")
        if not sha:
            fail(f"unknown commit {a.sha or 'HEAD'}")
        if a.passed is None or a.failed is None:
            fail("tests record needs --passed and --failed")
        rec = {"sha": sha, "kind": a.kind, "command": (a.command or "")[:200], "passed": a.passed, "failed": a.failed,
               "coverage": a.coverage, "duration_s": a.duration, "dirty": bool(_tree_dirty(store)) if not a.sha else False,
               "at": now()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"tests {a.kind}: {a.passed} passed, {a.failed} failed at {sha[:7]}" + (" (dirty tree: not reusable)" if rec["dirty"] else ""))
        return
    # lookup
    head = _git(store, "rev-parse", a.sha or "HEAD")
    if not head:
        fail(f"unknown commit {a.sha or 'HEAD'}")
    if not a.sha and _tree_dirty(store):
        print("no reusable run: the working tree has uncommitted changes outside .dev/; run the suite")
        sys.exit(3)
    recs = []
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                recs.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    scope = [x.strip() for x in (a.paths or "").split(",") if x.strip()] or [".", ":(exclude).dev", ":(exclude)*.md", ":(exclude)docs"]
    for r in reversed(recs):
        # a run of the full suite ("all") covers any kind; a partial run covers only its own kind
        if r.get("failed") != 0 or r.get("dirty") or r.get("kind") not in (a.kind, "all"):
            continue
        if r.get("sha") == head:
            hit = {**r, "reused": True, "same_commit": True}
        elif _git(store, "merge-base", "--is-ancestor", r["sha"], head) is not None:
            changed = _git(store, "diff", "--name-only", r["sha"], head, "--", *scope)
            if changed is None or changed:
                continue
            hit = {**r, "reused": True, "same_commit": False}
        else:
            continue
        if a.json:
            print(json.dumps(hit))
        else:
            print(f"reuse: {r['kind']} run at {r['sha'][:7]} ({r['passed']} passed, 0 failed"
                  + (f", coverage {r['coverage']}%" if r.get("coverage") is not None else "") + ")"
                  + ("" if hit["same_commit"] else f"; nothing it covers changed up to {head[:7]}"))
        return
    print(f"no reusable {a.kind} run for {head[:7]}; run the suite and record it")
    sys.exit(3)


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _files_arg(store: Store, a: argparse.Namespace) -> list[str]:
    files = _csv(getattr(a, "files", None))
    src = getattr(a, "files_from", None)
    if src:
        path = Path(src) if Path(src).is_absolute() else store.root / src
        try:
            files += [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError as e:
            fail(f"cannot read {src}: {e}")
    return list(dict.fromkeys(files))


def _finding_refs(store: Store, paths: list[str]) -> list[dict]:
    out = []
    for src in paths:
        path = Path(src) if Path(src).is_absolute() else store.root / src
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            fail(f"cannot read findings from {src}: {e}")
        items = data.get("findings", []) if isinstance(data, dict) else data
        for f in items if isinstance(items, list) else []:
            if not isinstance(f, dict) or f.get("legacy") or f.get("out_of_scope"):
                continue
            files = f.get("files") if isinstance(f.get("files"), list) else [f.get("file")]
            for x in files:
                if x:
                    out.append({"file": str(x).split(":")[0], "line": f.get("line")})
    return out


def _norm_rel(store: Store, rel: str) -> str:
    if (store.root / rel).exists() or not (store.dev / rel).exists():
        return rel
    return f".dev/{rel}"


def cmd_ledger(store: Store, a: argparse.Namespace) -> None:
    """Work ledger (conventions.md §18): reuse verified work whose inputs did not change."""
    store.load()
    inc = {"enabled": True, "spot_check_pct": 10, **(store.state.get("autonomy", {}).get("incremental") or {})}
    salt = _csv(getattr(a, "salt", None)) + [f"kit:{tel.kit_version()}"]
    context = _csv(getattr(a, "context", None))
    no_cache = bool(getattr(a, "no_cache", False)) or not inc.get("enabled", True)
    spot = inc.get("spot_check_pct", 10) if getattr(a, "spot_pct", None) is None else a.spot_pct
    seed = getattr(a, "seed", None) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    act = a.action

    def out(obj: dict, human: str) -> None:
        print(json.dumps(obj, indent=2, ensure_ascii=False) if getattr(a, "json", False) else human)

    if act in ("plan", "record"):
        if not a.prefix:
            fail(f"ledger {act} needs --prefix (e.g. audit:code)")
        files = _files_arg(store, a)
        if not files:
            fail(f"ledger {act} needs --files or --files-from")
        # an entry is a file (its own unit) or `unit=file1+file2` (e.g. a screen and the files of its route)
        units = {}
        for f in files:
            name, _, ins = f.partition("=")
            units[name] = [x for x in ins.split("+") if x] if ins else [name]
        if act == "plan":
            res = led.plan(store.dev, store.root, a.prefix, units, context, salt, _csv(a.shared), spot, seed, no_cache)
            res.pop("fingerprints", None)
            store.event("ledger", scope=tel.scope_token(a.prefix), review=len(res["review"]), reuse=len(res["reuse"]),
                        spot=len(res["spot"]), no_cache=no_cache)
            out(res, f"{a.prefix}: review {len(res['review'])} · reuse {len(res['reuse'])} · spot {len(res['spot'])}"
                + f" · never reviewed {len(res['never'])}" + (" · shared changed" if res["shared_changed"] else "")
                + "".join(f"\n  review {x['unit']} ({x['why']})" for x in res["review"]))
            return
        hits = {_norm_rel(store, r["file"]) for r in _finding_refs(store, _csv(a.findings_from))}
        # a unit has findings when a finding names the unit itself (a screen id) or one of its files
        with_findings = {u for u, ins in units.items() if u in hits or hits & set(ins)}
        res = led.record(store.dev, store.root, a.prefix, units, context, salt, with_findings, a.ref, _csv(a.shared))
        out(res, f"{a.prefix}: recorded {res['ok']} ok, {res['findings']} with findings")
        return
    if act in ("sections", "record-sections"):
        if not a.target:
            fail(f"ledger {act} needs --target (prd, design, plan, docs)")
        files = _files_arg(store, a) or [f".dev/{x}" for n in led_review_artifacts(a.target) for x in ARTIFACT_FILES[n] if "*" not in x]
        if act == "sections":
            res = led.section_plan(store.dev, store.root, a.target, files, context, salt, spot, seed, no_cache)
            store.event("ledger", scope=tel.scope_token(f"review:{a.target}"), review=len(res["review"]),
                        reuse=len(res["reuse"]), spot=len(res["spot"]), no_cache=no_cache)
            out(res, f"review {a.target}: {len(res['review'])} of {res['sections']} section(s) to review, {len(res['reuse'])} reused"
                + "".join(f"\n  {x['file']} § {x['section']} (lines {x['lines'][0]}-{x['lines'][1]}): {x['why']}" for x in res["review"]))
            return
        lines: dict[str, list[int]] = {}
        for r in _finding_refs(store, _csv(a.findings_from)):
            if isinstance(r.get("line"), int):
                lines.setdefault(_norm_rel(store, r["file"]), []).append(r["line"])
        res = led.section_record(store.dev, store.root, a.target, files, context, salt, lines)
        out(res, f"review {a.target}: recorded {res['ok']} section(s) ok, {res['findings']} with findings")
        return
    if act == "drop":
        if not a.prefix:
            fail("ledger drop needs --prefix")
        n = led.drop(store.dev, a.prefix)
        print(f"dropped {n} unit(s) under {a.prefix}")
        return
    if not a.key:
        fail(f"ledger {act} needs a KEY")
    recs = led.load(store.dev)
    if act == "get":
        rec = recs.get(a.key)
        if not rec:
            print(f"no record for {a.key}")
            sys.exit(3)
        print(json.dumps(rec, ensure_ascii=False))
        return
    fp = led.fingerprint(store.root, _files_arg(store, a), context, salt)
    if act == "check":
        ok = not no_cache and led.reusable(recs.get(a.key), fp)
        out({"key": a.key, "reusable": ok, "record": recs.get(a.key)}, f"{a.key}: {'reuse' if ok else 'redo'}")
        if not ok:
            sys.exit(3)
        return
    if act == "put":
        try:
            rec = led.put(store.dev, a.key, fp, a.result or "ok", a.ref, a.note)
        except ValueError as e:
            fail(str(e))
        out(rec, f"{a.key}: {rec['result']}")
        return
    fail(f"unknown ledger action {act}")


def led_review_artifacts(target: str) -> list[str]:
    return REVIEW_ARTIFACTS.get(target, [])


def _section_rows(text: str, heading_re: str) -> list[tuple[str, str]]:
    m = re.search(heading_re, text, flags=re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, flags=re.M)
    body = body[:nxt.start()] if nxt else body
    rows = []
    for ln in body.splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.strip().startswith("|") else []
        if len(cells) >= 2 and cells[1] and not set(cells[1]) <= set("-: ") and cells[0].lower() not in ("purpose",):
            rows.append((cells[0], cells[1]))
    return rows


def cmd_brief(store: Store, a: argparse.Namespace) -> None:
    """The base prompt of an implementer for one task, generated from state and architecture (implement)."""
    store.load()
    t = store.tasks().get(a.task)
    if t is None:
        fail(f"unknown task {a.task}")
    arch = (store.dev / "architecture.md").read_text(encoding="utf-8", errors="replace") if (store.dev / "architecture.md").exists() else ""
    brief = (store.dev / "brief.md").read_text(encoding="utf-8", errors="replace") if (store.dev / "brief.md").exists() else ""
    m = re.search(r"(?im)^\W*(?:application|app|ui|interface|product)\s+language[^:\n]*:\s*(.+)$", brief)
    app_lang = m.group(1).strip()[:80] if m else "see .dev/brief.md block 2"
    cmds = _section_rows(arch, r"^## 8\b.*$")
    deps = [f"{d} ({(store.tasks()[d].get('commit') or '')[:7] or 'no commit'}) {store.tasks()[d]['title']}" for d in t.get("deps") or [] if d in store.tasks()]
    hist = led.load(store.dev).get(f"task:{a.task}")
    kit = Path(__file__).resolve().parents[1]
    out = [f"Task: {a.task} — {t['title']} (milestone {t['milestone']}, type {t['type']})",
           f"Scope: {a.task}", f"Kit root: {kit}", f"Project root: {store.root}",
           f"Language for prose (report): {store.state.get('language') or 'en'} · application language (UI copy): {app_lang}",
           f"Base commit: {_git(store, 'rev-parse', '--short', 'HEAD') or '-'}", "", "Acceptance:"]
    out += [f"  - {x}" for x in t.get("acceptance") or ["(none listed: ask the orchestrator)"]]
    out += [f"Test notes: {t.get('test_notes') or '-'}", f"Files: {', '.join(t.get('files') or []) or '-'}"]
    if deps:
        out += ["Depends on (done): " + "; ".join(deps)]
    if t.get("contract"):
        out += [f"Contract this task must provide: {t['contract']}"]
    for c in t.get("consumes") or []:
        ct = store.tasks().get(c, {})
        if ct.get("contract"):
            out += [f"Contract you consume from {c}: {ct['contract']}"]
    if cmds:
        out += ["", "Commands (architecture.md §8):"] + [f"  - {k}: {v}" for k, v in cmds]
    out += ["", "Verification you run (conventions.md §18): unit tests, lint and type-check, plus only the integration tests "
            "of this task's ACs and of the modules you changed (e.g. -k AC-n or their paths). The orchestrator runs the full "
            "suite once after merging, so do not run it more than once yourself.",
            "Worktree rules (resource-isolation.md): one simple command per Bash call; no heredocs and no `cd … &&` chains; "
            "write scripts and files with Write/Edit; link node_modules/.venv from the Project root instead of installing; "
            "never commit or touch git state; take a lock (dev_state.py lock acquire <resource> --holder <you>) before "
            "using an exclusive resource listed in architecture.md, and release it when done."]
    if hist:
        out += ["", f"Previous attempt ({hist.get('result')}, {hist.get('at')}): {hist.get('note') or '-'}"
                + (f" · its work is on {hist['ref']}: start from it, do not redo what it finished" if hist.get("ref") else "")]
    print("\n".join(out))


UI_FILE = re.compile(r"\.(tsx|jsx|vue|svelte|astro|html?|hbs|ejs|erb|jinja2?|j2|liquid|twig|php|po|pot|json|ya?ml|arb|strings|xliff)$")
CATALOG = re.compile(r"(^|/)(locales?|i18n|lang|messages|translations)/|\.(po|pot|arb|strings|xliff)$")
STR_PATTERNS = [
    re.compile(r">\s*([^<>{}]*[^\W\d_][^<>{}]*?)\s*<"),
    re.compile(r"\b(?:placeholder|aria-label|title|alt|label|helperText|errorMessage)\s*=\s*[\"']([^\"']+)[\"']"),
    re.compile(r"\b(?:toast|alert|confirm|notify|message\.\w+|setError|showError|flash|t|i18n\.t|_)\(\s*[\"'`]([^\"'`]+)[\"'`]"),
]
CATALOG_PATTERNS = [re.compile(r"^\s*[\"']?[\w.-]+[\"']?\s*[:=]\s*[\"'](.+?)[\"'],?\s*$"), re.compile(r'^msgstr\s+"(.+)"\s*$')]


def _user_string(t: str) -> bool:
    t = t.strip()
    if len(t) < 2 or not re.search(r"[^\W\d_]", t):
        return False
    if " " not in t and re.search(r"[-_./:#]|^[a-z]+[A-Z]", t):
        return False  # identifiers, classes, paths, keys
    return not re.fullmatch(r"\{\{?.*\}\}?|\$\{.*\}", t)


def cmd_strings(store: Store, a: argparse.Namespace) -> None:
    """User-facing strings added since a commit (copy-reviewer gets only these): literals in templates and
    components, UI attributes, message calls and i18n catalogs. A heuristic: it lists candidates, not a verdict."""
    store.load()
    args = ["diff", "-U0", "--no-color", a.since] + (["HEAD"] if not a.worktree else []) + ["--", ".", ":(exclude).dev"]
    diff = _git(store, *args)
    if diff is None:
        fail(f"git diff from {a.since} failed")
    out, cur, ln = [], None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", line)
        if m:
            ln = int(m.group(1))
            continue
        if cur is None or not line.startswith("+") or line.startswith("+++"):
            continue
        text = line[1:]
        if UI_FILE.search(cur) and (not cur.endswith((".json", ".yaml", ".yml")) or CATALOG.search(cur)):
            pats = CATALOG_PATTERNS if CATALOG.search(cur) else STR_PATTERNS
            for pat in pats:
                for hit in pat.findall(text):
                    if _user_string(hit):
                        out.append({"file": cur, "line": ln, "text": hit.strip()[:200]})
        ln += 1
    seen, uniq = set(), []
    for x in out:
        k = (x["file"], x["text"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    if a.json:
        print(json.dumps({"since": a.since, "strings": uniq}, indent=2, ensure_ascii=False))
    else:
        print(f"{len(uniq)} new user-facing string(s) since {a.since}")
        for x in uniq:
            print(f"  {x['file']}:{x['line']}  {x['text']}")


def _rgb(v: str) -> tuple[float, float, float] | None:
    v = v.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})(?:[0-9a-f]{2})?", v)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,?\s*(\d+)\s*,?\s*(\d+).*\)", v)
    if m:
        return tuple(int(x) / 255 for x in m.groups())  # type: ignore[return-value]
    return None


def contrast_ratio(fg: str, bg: str) -> float | None:
    a_, b_ = _rgb(fg), _rgb(bg)
    if a_ is None or b_ is None:
        return None
    def lum(c):
        lin = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    l1, l2 = sorted((lum(a_), lum(b_)), reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 2)


TOKEN_LINE = [re.compile(r"^\s*\|\s*`?([\w.-]+)`?\s*\|\s*`?(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))`?\s*\|"),
              re.compile(r"^\s*(--[\w-]+|[\w.-]+)\s*:\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\s*;?")]
FG_NAME = re.compile(r"text|fg|foreground|on-|on_|link|icon|primary|danger|error|success|warning|accent|border|focus", re.I)
BG_NAME = re.compile(r"bg|background|surface|canvas|base|paper|page", re.I)


def cmd_contrast(store: Store, a: argparse.Namespace) -> None:
    """WCAG contrast of colour token pairs read from the UI spec (design-reviewer interprets, never computes)."""
    store.load()
    spec = Path(a.spec) if a.spec and Path(a.spec).is_absolute() else store.root / (a.spec or ".dev/design/ui-spec.md")
    if not spec.exists():
        fail(f"{spec} not found")
    tokens: dict[str, str] = {}
    for ln in spec.read_text(encoding="utf-8", errors="replace").splitlines():
        for pat in TOKEN_LINE:
            m = pat.match(ln)
            if m and _rgb(m.group(2)):
                tokens.setdefault(m.group(1).lstrip("-"), m.group(2))
                break
    if a.pairs:
        pairs = [tuple(x.split("/", 1)) for x in _csv(a.pairs) if "/" in x]
    else:
        fgs = [t for t in tokens if FG_NAME.search(t) and not BG_NAME.search(t)]
        bgs = [t for t in tokens if BG_NAME.search(t)]
        pairs = [(f, b) for f in fgs for b in bgs]
    rows = []
    for f, b in pairs:
        if f not in tokens or b not in tokens:
            rows.append({"fg": f, "bg": b, "ratio": None, "note": "token not found"})
            continue
        r = contrast_ratio(tokens[f], tokens[b])
        ui = bool(re.search(r"border|focus|icon", f, re.I))
        need = 3.0 if ui else 4.5
        rows.append({"fg": f, "bg": b, "fg_value": tokens[f], "bg_value": tokens[b], "ratio": r,
                     "required": need, "large_text_ok": r is not None and r >= 3.0, "ok": r is not None and r >= need})
    if a.json:
        print(json.dumps({"spec": str(spec), "tokens": len(tokens), "pairs": rows}, indent=2))
    else:
        print(f"{len(tokens)} colour token(s), {len(rows)} pair(s) (WCAG 2.2: 4.5 text, 3.0 large text and UI parts)")
        for r in rows:
            mark = "?" if r["ratio"] is None else ("ok " if r["ok"] else "LOW")
            print(f"  {mark} {r['fg']} on {r['bg']}: " + (f"{r['ratio']}:1 (needs {r['required']})" if r["ratio"] else r.get("note", "")))
    if a.strict and any(r["ratio"] is not None and not r["ok"] for r in rows):
        sys.exit(1)


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
    if a.milestone and a.env == "production" and a.status == "ok":
        gate = store.milestones()[a.milestone].get("gate", "pending")
        if gate not in ("passed", "skipped") and not any(t.get("lane") == "hotfix" for t in store.tasks().values()
                                                          if t.get("milestone") == a.milestone):
            print(f"warning: gate of {a.milestone} is {gate}; production gets one deploy per approved gate, "
                  "after the whole fix round (conventions §12)", file=sys.stderr)
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
    if states and all(s in FINISHED for s in states) and "done" in states:
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
           "## Open", "| id | class | type | severity | effort | status | scheduled in | tasks | origin | title |", "|---|---|---|---|---|---|---|---|---|---|"]
    order = {c: n for n, c in enumerate(ISSUE_CLASSES)}
    for k, v in sorted(open_.items(), key=lambda kv: (order.get(kv[1].get("class"), 9), SEV_RANK.get(kv[1].get("severity"), 4), kv[0])):
        out.append(f"| {k} | {v.get('class')} | {v.get('type')} | {v.get('severity') or '-'} | {v.get('effort') or '-'} | {v['status']} | "
                   f"{v.get('scheduled_in') or '-'} | {', '.join(v.get('tasks', [])) or '-'} | {v.get('origin') or '-'} | {v['title'].replace('|', '/')} |")
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
                if isinstance(f, dict) and not f.get("legacy") and f.get("status") != "closed":
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
                for k, v in sorted(ts.items(), key=lambda kv: int(kv[0][2:])) if v["milestone"] == m and v["status"] not in FINISHED]
        if rows:
            pending[m] = rows
    nxt = next((m for m in store.milestone_order() if store.milestones()[m].get("gate", "pending") == "pending"), None)
    warnings = []
    if hot_in_cur > 2:
        warnings.append(f"{hot_in_cur} hotfixes in {cur}: expedite is being overused")
    deploy = [d for env in sorted(store.state.get("deploys") or {}) if (d := deploy_drift(store, env))]
    return {
        "current_milestone": cur, "hotfix_open": hot_open, "brownfield": store.state.get("brownfield"),
        "issues": {k: {**{f: v.get(f) for f in ("title", "type", "class", "severity", "effort", "status", "scheduled_in", "tasks", "created_at", "origin", "note")}}
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


REVIEW_VALUES = {"pass", "fail", "pending", "n/a"}


# ------------------------------------------------------------------ artifact dependencies (conventions.md §7)
# Each planning artifact is derived from the ones listed; when an upstream changes after an artifact was produced
# (`artifact mark`), the artifact is stale and must be refreshed before any review that reads it runs.
ARTIFACT_FILES = {
    "brief": ["brief.md"],
    "prd": ["prd.md", "prd/*.md"],
    "architecture": ["architecture.md"],
    "ux": ["design/ux-flows.md"],
    "ui": ["design/ui-spec.md"],
    "plan": ["plan.md"],
}
ARTIFACT_DEPS = {
    "brief": [],
    "prd": ["brief"],
    "architecture": ["prd"],
    "ux": ["prd", "architecture"],
    "ui": ["ux"],
    "plan": ["prd", "architecture", "ux", "ui"],
}
REVIEW_ARTIFACTS = {"prd": ["prd"], "design": ["ux", "ui"], "plan": ["plan"]}
ARTIFACT_PRODUCER = {"brief": "interview", "prd": "prd", "architecture": "architecture", "ux": "ux", "ui": "ui", "plan": "plan replan"}
# Header lines that change without changing the content (conventions.md §8 header: date, status).
_VOLATILE = re.compile(r"^\W*(date|status|updated|last updated|revision|rev)\W*\s*[:=]", re.I)


def artifact_paths(store: Store, name: str) -> list[Path]:
    out: list[Path] = []
    for pat in ARTIFACT_FILES[name]:
        out += sorted(store.dev.glob(pat)) if "*" in pat else ([store.dev / pat] if (store.dev / pat).exists() else [])
    return out


def artifact_hash(store: Store, name: str) -> str | None:
    paths = artifact_paths(store, name)
    if not paths:
        return None
    h = hashlib.sha256()
    for path in paths:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        body = [ln.rstrip() for i, ln in enumerate(lines) if not (i < 12 and _VOLATILE.match(ln))]
        h.update(path.relative_to(store.dev).as_posix().encode() + b"\0" + "\n".join(body).strip().encode() + b"\0")
    return h.hexdigest()[:16]


def stale_report(store: Store) -> dict:
    """Which artifacts are stale (an upstream changed after they were marked, directly or through a stale
    upstream), which passed reviews no longer match their artifact, and which artifacts are not tracked yet."""
    recs = store.state.get("artifacts") or {}
    cur = {n: artifact_hash(store, n) for n in ARTIFACT_FILES}
    direct: dict[str, list[str]] = {}
    untracked = []
    for n in ARTIFACT_FILES:
        if cur[n] is None:
            continue
        r = recs.get(n)
        if not r:
            untracked.append(n)
            continue
        ups = r.get("upstream") or {}
        why = [d for d in ARTIFACT_DEPS[n] if cur.get(d) is not None and ups.get(d) != cur[d]]
        if why:
            direct[n] = why
    stale: dict[str, list[str]] = {}
    for n in ARTIFACT_FILES:  # declaration order is topological
        if cur[n] is None or n in untracked:
            continue
        why = [f"{d} changed" for d in direct.get(n, [])]
        why += [f"{d} is stale" for d in ARTIFACT_DEPS[n] if d in stale and f"{d} changed" not in why]
        if why:
            stale[n] = why
    reviews = []
    # Once a task is done, dev_state.py itself appends fix and issue tasks to plan.md: a passed plan review is no
    # longer re-checked against the file (a stale upstream still makes plan.md stale, above). PRD and design reviews
    # are always checked, so a scope change during construction reopens them (conventions.md §19).
    built = any(v.get("status") == "done" for v in store.tasks().values())
    for rname, arts in REVIEW_ARTIFACTS.items():
        if built and rname == "plan":
            continue
        r = (store.state.get("reviews") or {}).get(rname) or {}
        if r.get("verdict") != "pass" or not r.get("hashes"):
            continue
        changed = [x for x in arts if cur.get(x) is not None and r["hashes"].get(x) != cur[x]]
        upstream = sorted({x for x in arts if x in stale})
        if changed or upstream:
            reviews.append({"review": rname, "changed": changed, "stale_artifacts": upstream})
    order = [n for n in ARTIFACT_FILES if n in stale]
    return {"stale": [{"artifact": n, "because": stale[n], "refresh_with": ARTIFACT_PRODUCER[n]} for n in order],
            "reviews": reviews, "untracked": untracked}


def cmd_artifact(store: Store, a: argparse.Namespace) -> None:
    store.load()
    names = list(ARTIFACT_FILES) if a.name == "all" else [a.name]
    if a.name != "all" and a.name not in ARTIFACT_FILES:
        fail(f"unknown artifact {a.name}; one of {', '.join(ARTIFACT_FILES)}, all")
    recs = store.state.setdefault("artifacts", {})
    marked = []
    for n in names:
        h = artifact_hash(store, n)
        if h is None:
            if a.name != "all":
                fail(f"artifact {n} does not exist yet (.dev/{ARTIFACT_FILES[n][0]})")
            continue
        recs[n] = {"hash": h, "at": now(),
                   "upstream": {d: artifact_hash(store, d) for d in ARTIFACT_DEPS[n] if artifact_hash(store, d)}}
        if a.note:
            recs[n]["note"] = a.note[:200]
        marked.append(n)
    store.save()
    store.log(f"artifact mark {', '.join(marked) or '-'}" + (f" ({a.note})" if a.note else ""))
    print(f"marked: {', '.join(marked) or 'nothing'}")


def cmd_stale(store: Store, a: argparse.Namespace) -> None:
    store.load()
    rep = stale_report(store)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        if not rep["stale"] and not rep["reviews"]:
            print("stale: nothing" + (f" (not tracked yet: {', '.join(rep['untracked'])}; run `artifact mark all` once)" if rep["untracked"] else ""))
        for it in rep["stale"]:
            print(f"stale: {it['artifact']} ({'; '.join(it['because'])}) -> refresh with {it['refresh_with']}, or `artifact mark {it['artifact']} --note \"no impact: ...\"`")
        for it in rep["reviews"]:
            print(f"review {it['review']}: passed on an older version ({', '.join(it['changed'] + it['stale_artifacts'])}) -> re-run review {it['review']}")
    if a.strict and (rep["stale"] or rep["reviews"]):
        sys.exit(1)


def xref_report(store: Store) -> dict:
    """Deterministic cross-document checks the producing skills run before a review (shared/prompts/self-check.md)."""
    def read(paths: list[Path]) -> str:
        return "\n".join(x.read_text(encoding="utf-8", errors="replace") for x in paths)
    problems: list[dict] = []
    prd = read(artifact_paths(store, "prd"))
    defined, inactive = set(), set()
    for ln in prd.splitlines():
        m = re.match(r"^\s*(?:[-*]|\d+\.)\s*\**(AC-\d+)\b", ln)
        if not m:
            continue
        defined.add(m.group(1))
        low = ln.lower()
        if "superseded" in low or "~~" in ln or re.search(r"\[\s*existing\s*\]|\(existing\)|`existing`", low):
            inactive.add(m.group(1))
    tasks = {k: v for k, v in store.tasks().items() if v.get("status") != "dropped"}
    planned: dict[str, list[str]] = {}
    for tid, t in tasks.items():
        for item in t.get("acceptance") or []:
            for ac in re.findall(r"\bAC-\d+\b", str(item)):
                planned.setdefault(ac, []).append(tid)
        for d in t.get("deps") or []:
            if d not in store.tasks():
                problems.append({"check": "dep_unknown", "id": tid, "detail": f"depends on {d}, which does not exist"})
    for tid, t in tasks.items():
        for c in t.get("consumes") or []:
            if c in store.tasks() and not store.tasks()[c].get("contract"):
                problems.append({"check": "contract_missing", "id": tid, "detail": f"consumes {c}, which declares no contract"})
    acn = lambda x: int(x.split("-")[1])  # noqa: E731
    if defined and tasks:
        for ac in sorted(defined - inactive - set(planned), key=acn):
            problems.append({"check": "ac_unplanned", "id": ac, "detail": "AC in the PRD with no task"})
    if prd:
        for ac in sorted(set(planned) - defined, key=acn):
            problems.append({"check": "ac_unknown", "id": ac, "detail": f"cited by {', '.join(planned[ac])} but not defined in the PRD"})
    ux = read(artifact_paths(store, "ux"))
    ui = read(artifact_paths(store, "ui"))
    if ux and ui:
        screens = {}
        for ln in ux.splitlines():
            m = re.match(r"^\s*\|\s*(S-\d+)\s*\|", ln)
            if m:
                screens[m.group(1)] = "existing" in ln.lower().split("|")[-2] if ln.count("|") > 2 else False
        specced = set(re.findall(r"^#{2,4}\s*(S-\d+)\b", ui, flags=re.M))
        for sid in sorted(screens):
            if not screens[sid] and sid not in specced:
                problems.append({"check": "screen_unspecified", "id": sid, "detail": "screen in ux-flows.md with no section in ui-spec.md"})
        for sid in sorted(specced - set(screens)):
            problems.append({"check": "screen_unknown", "id": sid, "detail": "section in ui-spec.md for a screen not in the ux-flows.md inventory"})
    dec = store.dev / "decisions.md"
    adrs = set(re.findall(r"^#{2,4}\s*(ADR-\d+)\b", dec.read_text(encoding="utf-8", errors="replace"), flags=re.M)) if dec.exists() else set()
    cited: dict[str, set[str]] = {}
    for n in ("prd", "architecture", "ux", "ui", "plan"):
        for adr in re.findall(r"\bADR-\d+\b", read(artifact_paths(store, n))):
            cited.setdefault(adr, set()).add(n)
    for adr in sorted(set(cited) - adrs, key=acn):
        problems.append({"check": "adr_unknown", "id": adr, "detail": f"cited in {', '.join(sorted(cited[adr]))} but not in decisions.md"})
    counts: dict[str, int] = {}
    for x in problems:
        counts[x["check"]] = counts.get(x["check"], 0) + 1
    return {"problems": problems, "counts": counts,
            "acs": {"defined": len(defined), "inactive": len(inactive), "planned": len(set(planned) & defined)}}


def cmd_xref(store: Store, a: argparse.Namespace) -> None:
    store.load()
    rep = xref_report(store)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        acs = rep["acs"]
        print(f"xref: {len(rep['problems'])} problem(s) · ACs {acs['planned']}/{acs['defined'] - acs['inactive']} planned")
        for x in rep["problems"]:
            print(f"  {x['check']}: {x['id']} - {x['detail']}")
    if a.strict and rep["problems"]:
        sys.exit(1)


def cmd_review(store: Store, a: argparse.Namespace) -> None:
    """Record the outcome of a pre-implementation or documentation review (prd, design, plan, docs, ...)."""
    store.load()
    if a.value not in REVIEW_VALUES:
        fail(f"review value must be one of {', '.join(sorted(REVIEW_VALUES))}")
    if a.value == "n/a" and not a.note:
        fail(f"review {a.name} n/a needs --note with the reason (e.g. 'no new UI in this project')")
    reviews = store.state.setdefault("reviews", {})
    r = reviews.setdefault(a.name, {"rounds": 0})
    if a.value == "n/a":
        r.pop("score", None)
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
    if a.value == "pass" and a.name in REVIEW_ARTIFACTS:
        r["hashes"] = {x: artifact_hash(store, x) for x in REVIEW_ARTIFACTS[a.name] if artifact_hash(store, x)}
    if a.count_run:
        r["rounds"] = int(r.get("rounds", 0)) + 1
    r["at"] = now()
    store.save()
    store.event("review", scope=tel.scope_token(a.name), value="na" if a.value == "n/a" else a.value, score=a.score, round=r.get("rounds", 0),
                forced=bool(a.force and a.value == "pass"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "pass" else None)
    store.log(f"review {a.name} {a.value}" + (f" score={a.score}" if a.score is not None else ""))
    print(f"review {a.name}: {a.value}" + (f" (score {a.score})" if a.score is not None else "") + f" · rounds {r['rounds']}")


def cmd_set(store: Store, a: argparse.Namespace) -> None:
    store.load()
    key, val = a.key, a.value
    if key == "phase":
        fail("the phase is derived from the artifacts, reviews, milestones and releases (conventions.md §19); "
             "run the skill of the step instead (`status` shows it)")
    if key in ("language", "project"):
        store.state[key] = val
    elif key.startswith("autonomy."):
        field = key.split(".", 1)[1]
        auto = store.state.setdefault("autonomy", _copy(DEFAULT_AUTONOMY))
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            parsed = val
        top, _, sub = field.partition(".")
        if field == "level":
            apply_level(store.state, val)
        elif top == "pause_policy":
            rule = parsed if isinstance(parsed, dict) else {"action": val}
            patch = rule if not sub else {sub: rule}
            check_pause_policy(patch)
            auto["pause_policy"] = {**auto.get("pause_policy", {}), **patch}
            if store.state.get("brownfield") and pause_action(store.state, "dirty_tree") != "ask":
                print("note: existing project; dirty_tree is no longer ask, so the user's own uncommitted work may be stashed", file=sys.stderr)
        elif sub:
            # nested key, e.g. autonomy.quality.min_overall or autonomy.production.when: merge into the object
            cur = auto.get(top)
            if cur is None and isinstance(DEFAULT_AUTONOMY.get(top), dict):  # object added in a later kit version
                cur = _copy(DEFAULT_AUTONOMY[top])
            if not isinstance(cur, dict):
                fail(f"autonomy.{top} is not an object; set it as a whole")
            node = merged = _copy(cur)
            parts = sub.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
                if not isinstance(node, dict):
                    fail(f"autonomy.{field}: {part} is not an object")
            node[parts[-1]] = parsed
            store_autonomy_object(auto, top, merged)
        elif top in ("production", "local_deploy", "cooldown", "quality", "model_policy", "ui"):
            if top == "local_deploy" and not isinstance(parsed, dict):
                parsed = {"mode": val}
            elif top == "model_policy" and not isinstance(parsed, dict):
                parsed = {"mode": val}
            elif top == "cooldown" and not isinstance(parsed, dict):
                if val not in ("on", "off", "true", "false", "yes", "no"):
                    fail('autonomy.cooldown must be on | off or {"enabled": true, "max_tasks": 5}')
                parsed = {"enabled": val in ("on", "true", "yes")}
            if not isinstance(parsed, dict):
                fail(f"autonomy.{top} must be a JSON object")
            base = _copy(auto.get(top) or DEFAULT_AUTONOMY.get(top) or {})
            store_autonomy_object(auto, top, merge_quality(base, parsed) if top == "quality" else {**base, **parsed})
        else:
            auto[field] = check_autonomy_field(field, val if field in ("commit_style", "tips", "on_park", "task_checks") else parsed)
    elif key.startswith("stack."):
        store.state.setdefault("stack", {})[key.split(".", 1)[1]] = val
    else:
        fail("key must be language | project | autonomy.<field> | stack.<field>")
    store.save()
    store.log(f"set {key}={val}")
    if key.startswith("autonomy."):
        short = val if tel.TOKEN_RE.match(val or "") else None
        store.event("config", key=key.replace("autonomy.", "")[:40].lower(), value=short)
    print(f"{key} = {val}")


def store_autonomy_object(auto: dict, top: str, obj: dict) -> None:
    """Validate and store a whole autonomy sub-object after a merge."""
    if top == "production":
        check_production({**DEFAULT_AUTONOMY["production"], **obj})
        obj = {**DEFAULT_AUTONOMY["production"], **obj}
    elif top == "model_policy":
        check_model_policy(obj)
        obj = {"mode": obj.get("mode", "ask"), "tiers": obj.get("tiers", {})}
    elif top == "local_deploy":
        check_local_deploy(obj)
        obj = {**DEFAULT_AUTONOMY["local_deploy"], **obj}
    elif top in ("cooldown", "quality"):
        check_autonomy_field(top, obj)
    elif top == "ui":
        obj = check_autonomy_field(top, obj)
    auto[top] = obj


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
    bf = s.get("brownfield")
    l1 = (f"[dev-kit] {name} · phase: {phase_label(store, lifecycle(store))} · language: {s.get('language') or '?'}"
          + (f" · existing project: {bf.get('mode', 'feature')} (baseline {bf.get('baseline_ref', '?')})" if bf else "")
          + f" · tasks done {p['done']}/{p['total'] - p['dropped']} · gates: {gates}")
    if inprog:
        t = store.tasks()[inprog[0]]
        l2 = f"[dev-kit] in progress: {inprog[0]} {t['title']} (since {t.get('started_at')})"
    else:
        tid, why = pick_next(store, None)
        l2 = f"[dev-kit] next: {tid} {store.tasks()[tid]['title']}" if tid else f"[dev-kit] next: {why}"
    revs = s.get("reviews") or {}
    rv = ", ".join(f"{k}:{v.get('verdict')}" + (f"({v['score']})" if v.get("score") is not None else "") for k, v in revs.items()) or "none"
    l3 = f"[dev-kit] reviews: {rv} · blocked: {p['blocked']} · open questions: {open_q} · resume with /dev-kit:start"
    st = stale_report(store) if s.get("artifacts") else {"stale": [], "reviews": []}
    if st["stale"] or st["reviews"]:
        items = [x["artifact"] for x in st["stale"]] + [f"review {x['review']}" for x in st["reviews"]]
        return "\n".join([l1, l2, l3, f"[dev-kit] stale: {', '.join(items)} (dev_state.py stale)"])
    return "\n".join([l1, l2, l3])


# --------------------------------------------------------------------------- project lifecycle (conventions.md §19)

DONE_STEP = ("done", "skipped")


def has_ui(store: Store) -> bool:
    """False when the design review was recorded n/a (product without a UI, or no new UI in an existing project)."""
    return ((store.state.get("reviews") or {}).get("design") or {}).get("verdict") != "n/a"


def migrate_legacy_phase(store: Store) -> None:
    """state.json written before 1.30 holds a phase of the old straight line; keep what it implied and let the
    lifecycle be derived from then on (the brief was finished, ux/ui were skipped, the product was released)."""
    s = store.state
    old = s.get("phase")
    if old in PHASES or old not in LEGACY_PHASES:
        return
    idx = LEGACY_PHASES.index(old)
    if idx >= LEGACY_PHASES.index("prd") and (store.dev / "brief.md").exists() and "brief" not in (s.get("artifacts") or {}):
        s.setdefault("artifacts", {})["brief"] = {"hash": artifact_hash(store, "brief"), "at": now(), "upstream": {},
                                                  "note": "interview finished before 1.30"}
    revs = s.setdefault("reviews", {})
    if idx >= LEGACY_PHASES.index("plan") and not (store.dev / "design" / "ux-flows.md").exists() and "design" not in revs:
        revs["design"] = {"rounds": 0, "verdict": "n/a", "note": "no UI (skipped before 1.30)", "at": now()}
    if old == "done" and not s.get("releases"):
        closed = [m for m, v in sorted((s.get("milestones") or {}).items(), key=lambda kv: int(kv[0][1:]))
                  if v.get("gate") in ("passed", "skipped")]
        s["releases"] = [{"version": None, "tag": None, "milestones": closed, "at": s.get("updated_at") or now(),
                          "note": "released before 1.30"}]
    s["phase"], s["step"], s["reopened"] = None, None, False


def lifecycle_steps(store: Store, rep: dict) -> dict:
    """State of each conception and planning step: todo | doing | stale | review | done | skipped."""
    revs = store.state.get("reviews") or {}
    arts = store.state.get("artifacts") or {}
    stale = {x["artifact"]: x for x in rep["stale"]}
    outdated = {x["review"] for x in rep["reviews"]}
    out = {}
    for step in CONCEPTION_STEPS + PLANNING_STEPS:
        art = STEP_ARTIFACT[step]
        exists = bool(artifact_paths(store, art))
        rname = STEP_REVIEW.get(step)
        r = (revs.get(rname) or {}) if rname else {}
        note = None
        if step in ("ux", "ui") and not has_ui(store):
            st, note = "skipped", revs["design"].get("note") or "no UI"
        elif step == "interview":
            # the brief is written block by block; `artifact mark brief` closes the interview (a PRD implies it too)
            st = "done" if "brief" in arts or artifact_paths(store, "prd") else ("doing" if exists else "todo")
        elif not exists:
            st = "todo"
        elif art in stale:
            st, note = "stale", "; ".join(stale[art]["because"])
        elif rname and (r.get("verdict") not in ("pass", "n/a") or rname in outdated):
            st = "review"
            note = f"review {rname} " + ("outdated" if rname in outdated else (r.get("verdict") or "not run"))
        else:
            st = "done"
        out[step] = {"key": step, "state": st, "note": note}
    return out


def release_train(store: Store, mlist: list[dict]) -> dict:
    """Milestones closed since the last release and what the next release still needs (usability, docs)."""
    revs = store.state.get("reviews") or {}
    releases = store.state.get("releases") or []
    ms = store.milestones()
    pending = [x["id"] for x in mlist if x["state"] == "closed"]
    building = [x["id"] for x in mlist if x["state"] == "open" and x["started"]]
    since = max((ms[m].get("passed_at") or "" for m in pending), default="")

    def fresh(name: str) -> str:
        r = revs.get(name) or {}
        if r.get("verdict") == "n/a" or (r.get("verdict") == "pass" and (r.get("at") or "") >= since):
            return "done"
        return "review" if r.get("verdict") in ("pending", "fail") and (r.get("at") or "") >= since else "todo"

    ui = has_ui(store) and (store.dev / "design" / "ui-spec.md").exists()
    return {"milestones": pending, "ready": bool(pending) and not building and not store.in_progress(),
            "waiting_for": building, "usability": (fresh("ux") if ui else "n/a") if pending else None,
            "docs": fresh("docs") if pending else None, "last": releases[-1] if releases else None,
            "count": len(releases)}


def lifecycle(store: Store) -> dict:
    """Where the project is in its lifecycle: conception -> planning -> construction -> stable, as a cycle. The
    phase is the most upstream one with work left; the others report their own state, so a scope change in
    conception and a milestone in construction show side by side (conventions.md §19)."""
    rep = stale_report(store)
    steps = lifecycle_steps(store, rep)
    ts = store.tasks()
    ms = store.milestones()
    released = {m for r in store.state.get("releases") or [] for m in r.get("milestones") or []}
    mlist = []
    for m in store.milestone_order():
        live = [v for v in ts.values() if v["milestone"] == m and v["status"] != "dropped"]
        gate = ms[m].get("gate", "pending")
        st = "empty" if not live else ("released" if m in released else "closed") if gate in ("passed", "skipped") else "open"
        mlist.append({"id": m, "title": ms[m].get("title"), "state": st, "gate": gate,
                      "done": sum(1 for v in live if v["status"] == "done"), "total": len(live),
                      "started": any(v["status"] in ("done", "in_progress") for v in live)})
    train = release_train(store, mlist)
    queue = sorted(k for k, v in issues(store).items() if v.get("status") == "open")
    planned = any(x["total"] for x in mlist)
    maintenance = (store.state.get("brownfield") or {}).get("mode") == "maintenance"
    open_ms = [x["id"] for x in mlist if x["state"] == "open"]
    pending = {
        "conception": [k for k in CONCEPTION_STEPS if steps[k]["state"] not in DONE_STEP],
        "planning": [k for k in PLANNING_STEPS if steps[k]["state"] not in DONE_STEP],
        "construction": bool(open_ms or any(v["status"] not in FINISHED for v in ts.values()) or queue
                             or train["milestones"] or (not planned and not maintenance)),
    }
    ever_built = any(v["status"] == "done" for v in ts.values()) or bool(released) or any(x["state"] == "closed" for x in mlist)
    cur = current_milestone(store)
    if pending["conception"]:
        phase, step = "conception", pending["conception"][0]
    elif pending["planning"]:
        phase, step = "planning", pending["planning"][0]
    elif pending["construction"]:
        phase = "construction"
        step = open_ms[0] if open_ms else ("release" if train["milestones"] else "issues" if queue else None)
    else:
        phase, step = "stable", None

    def pstate(p: str) -> str:
        if p == phase:
            return "current"
        if p == "stable":
            return "upcoming"
        if pending[p]:
            return "active" if p == "construction" and ever_built else "upcoming"
        return "upcoming" if p == "construction" and not ever_built else "done"

    closed = sum(1 for x in mlist if x["state"] in ("closed", "released"))
    phases = [
        {"key": "conception", "state": pstate("conception"), "reopened": bool(pending["conception"]) and ever_built,
         "steps": [steps[k] for k in CONCEPTION_STEPS]},
        {"key": "planning", "state": pstate("planning"), "reopened": bool(pending["planning"]) and ever_built,
         "steps": [steps[k] for k in PLANNING_STEPS]},
        {"key": "construction", "state": pstate("construction"), "reopened": False, "current_milestone": cur,
         "milestones": mlist, "closed": closed, "queue": queue, "release": train},
        {"key": "stable", "state": pstate("stable"), "reopened": False},
    ]
    return {"phase": phase, "step": step, "reopened": phase in ("conception", "planning") and ever_built,
            "steps": steps, "phases": phases, "release": train, "queue": queue}


def phase_label(store: Store, lc: dict | None = None) -> str:
    """`conception · prd`, `construction · M3`, `stable`: one label for the status line, banner and reports."""
    if lc is None:
        s = store.state
        if s.get("phase") in PHASES:
            return " · ".join(x for x in (s["phase"], s.get("step")) if x) + (" (reopened)" if s.get("reopened") else "")
        lc = lifecycle(store)
    return " · ".join(x for x in (lc["phase"], lc["step"]) if x) + (" (reopened)" if lc.get("reopened") else "")


def next_command(store: Store) -> str:
    """The one command the user most likely runs next. Shown by the status line and the session banner, and the
    last line of a skill's report (conventions.md §15), so Claude Code's prompt suggestion (Tab / Right arrow) offers it."""
    ts = store.tasks()
    hot = sorted((t for t, v in ts.items() if v.get("lane") == "hotfix" and v["status"] in ("todo", "in_progress")),
                 key=lambda t: int(t[2:]))
    if hot:
        return f"/dev-kit:implement {hot[0]}"
    lc = lifecycle(store)
    if lc["phase"] in ("conception", "planning"):
        step = lc["step"]
        if lc["steps"][step]["state"] == "review":
            return f"/dev-kit:review {STEP_REVIEW[step]}"
        return f"/dev-kit:{step}"
    if lc["phase"] == "stable":
        return "/dev-kit:backlog"
    if store.in_progress():
        return "/dev-kit:implement"
    for m in store.milestone_order():
        live = [v for v in ts.values() if v["milestone"] == m and v["status"] != "dropped"]
        if live and store.milestones()[m].get("gate", "pending") == "pending":
            if all(v["status"] == "done" for v in live):
                return f"/dev-kit:qa {m}"
            break
    tid, _ = pick_next(store, None)
    if tid:
        return "/dev-kit:implement"
    if any(v["status"] == "blocked" for v in ts.values()) or count_open_questions(store):
        return "/dev-kit:interview --gaps"
    rel = lc["release"]
    if rel["milestones"] and rel["ready"]:
        if rel["usability"] == "todo":
            return "/dev-kit:usability"
        if rel["docs"] == "review":
            return "/dev-kit:review docs"
        if rel["docs"] == "todo":
            return "/dev-kit:docs"
        return "/dev-kit:release"
    return "/dev-kit:plan" if not ts else "/dev-kit:backlog"


def cmd_release_record(store: Store, a: argparse.Namespace) -> None:
    """Record a cut release: the milestones it ships leave the release train (conventions.md §19)."""
    store.load()
    ms = store.milestones()
    if a.hotfix:
        store.task(a.hotfix)
        names: list[str] = []
    elif a.milestones:
        names = _csv(a.milestones)
        bad = [m for m in names if m not in ms or ms[m].get("gate") not in ("passed", "skipped")]
        if bad:
            fail(f"not closed (gate passed or skipped): {', '.join(bad)}")
    else:
        names = lifecycle(store)["release"]["milestones"]
        if not names:
            fail("no closed milestone waiting for a release (use --hotfix T-nnn for a patch release)")
    rel = {"version": a.version, "tag": a.tag or f"v{a.version}", "milestones": names, "at": now()}
    if a.hotfix:
        rel["hotfix"] = a.hotfix
    store.state.setdefault("releases", []).append(rel)
    store.save()
    store.log(f"release {rel['version']} ({rel['tag']}): {', '.join(names) or 'hotfix ' + str(a.hotfix)}")
    print(f"release {rel['version']} recorded ({rel['tag']}): {', '.join(names) or 'hotfix ' + a.hotfix} · phase {phase_label(store)}")


def queue_notice(store: Store, text: str) -> None:
    """Queue a desktop notification; the Stop hook (dev_agent_hook.py) shows it at the end of the turn. Only when
    autonomy.ui.notify is on. Text only, never project data beyond ids and scores."""
    if not (store.state.get("autonomy", {}).get("ui") or {}).get("notify"):
        return
    run = store.dev / "run"
    run.mkdir(parents=True, exist_ok=True)
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()[:200]
    with (run / "notify.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "text": clean}, ensure_ascii=False) + "\n")


def cmd_notify(store: Store, a: argparse.Namespace) -> None:
    store.load()
    queue_notice(store, a.text)


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
    if a.next:
        print(next_command(store))
        return
    if a.json:
        out = dict(store.state)
        out["progress"] = store.progress()
        tid, why = pick_next(store, None)
        out["next"] = {"task": tid, "reason": why}
        out["next_command"] = next_command(store)
        out["open_questions"] = count_open_questions(store)
        out["stale"] = stale_report(store)
        lc = lifecycle(store)
        out["phase"], out["step"], out["reopened"] = lc["phase"], lc["step"], lc["reopened"]
        out["lifecycle"] = {k: lc[k] for k in ("phases", "release", "queue")}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if a.short:
        print(render_short(store))
        return
    s = store.state
    p = store.progress()
    print(f"Project: {s.get('project') or store.root.name}")
    lc = lifecycle(store)
    rel = lc["release"]
    print(f"Phase: {phase_label(store, lc)} · Language: {s.get('language') or '?'} · Autonomy: {s.get('autonomy', {}).get('level')}")
    stack = s.get("stack") or {}
    if stack:
        print("Stack: " + ", ".join(f"{k}={v}" for k, v in stack.items() if k != "detected_from" and v))
    bf = s.get("brownfield")
    if bf:
        print(f"Brownfield: mode {bf.get('mode', 'feature')} · baseline {bf.get('baseline_ref', '?')} ({str(bf.get('baseline_sha') or '?')[:7]})"
              + (f" · first milestone M{bf['first_milestone']}" if bf.get("first_milestone") else "")
              + f" · commit style {s.get('autonomy', {}).get('commit_style') or DEFAULT_COMMIT_STYLE}"
              + (" · test baseline: .dev/qa/baseline.md" if (store.dev / "qa" / "baseline.md").exists() else ""))
    revs = s.get("reviews") or {}
    if revs:
        print("Reviews: " + ", ".join(f"{k}:{v.get('verdict')}" + (f"({v['score']})" if v.get("score") is not None else "") for k, v in revs.items()))
    todo = [f"{x['key']} ({x['state']})" for x in lc["steps"].values() if x["state"] not in DONE_STEP]
    if todo and lc["phase"] in ("conception", "planning"):
        print("Steps left: " + ", ".join(todo))
    if rel["milestones"] or rel["last"]:
        last = rel["last"]
        print("Release train: " + (f"{', '.join(rel['milestones'])} closed since the last release" if rel["milestones"] else "nothing to release")
              + (f" · usability {rel['usability']} · docs {rel['docs']}" if rel["milestones"] else "")
              + (f" · waiting for {', '.join(rel['waiting_for'])}" if rel["waiting_for"] else "")
              + (f" · last: {last.get('tag') or last.get('version') or 'before 1.30'} ({str(last.get('at'))[:10]})" if last else ""))
    q = quality_cfg(store)
    print(f"Quality cut-off: overall {q['min_overall']} · per dimension {q['min_dimension']} · reviews {q['review_min_overall']}")
    if s.get("artifacts"):
        st = stale_report(store)
        items = [x["artifact"] for x in st["stale"]] + [f"review {x['review']}" for x in st["reviews"]]
        if items:
            print(f"Stale: {', '.join(items)} (the next review brings them up to date)")
    ld = store.dev / "run" / "locks"
    held = [(lp.stem, _lock_read(lp)) for lp in sorted(ld.glob("*.json"))] if ld.exists() else []
    if held:
        print("Locks: " + ", ".join(f"{n} by {(r or {}).get('holder', '?')}" + (" (expired)" if _lock_expired(r) else "") for n, r in held))
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
    print(f"Tasks: {p['done']}/{p['total'] - p['dropped']} done · {p['in_progress']} in progress · {p['blocked']} blocked · {p['todo']} todo"
          + (f" · {p['dropped']} dropped" if p["dropped"] else ""))
    for m in store.milestone_order():
        info = store.milestones()[m]
        ts = {t: v for t, v in store.tasks().items() if v["milestone"] == m}
        done = sum(1 for v in ts.values() if v["status"] == "done")
        live = sum(1 for v in ts.values() if v["status"] != "dropped")
        sc = f" score {info['score']}" if info.get("score") is not None else ""
        print(f"\n{m} — {info.get('title')} [{done}/{live}] gate: {info.get('gate', 'pending')}{sc} (qa runs: {info.get('qa_runs', 0)})")
        for tid in sorted(ts, key=lambda x: int(x[2:])):
            v = ts[tid]
            mark = {"done": "x", "in_progress": ">", "blocked": "!", "todo": " ", "dropped": "-"}[v["status"]]
            extra = f" — blocked: {v['blocked_reason']}" if v["status"] == "blocked" else ""
            extra += f" — dropped: {v.get('dropped_reason')}" if v["status"] == "dropped" else ""
            extra += f" ({v['commit'][:7]})" if v.get("commit") else ""
            print(f"  [{mark}] {tid} ({v['type']}) {v['title']}{extra}")
    tid, why = pick_next(store, None)
    print(f"\nNext: {tid + ' ' + store.tasks()[tid]['title'] if tid else why}")
    oq = count_open_questions(store)
    if oq:
        print(f"Open questions: {oq} (see .dev/open-questions.md, resolve with interview --gaps)")
    print("Help: /dev-kit:help (what to do next, how each skill works)")
    print_tip(store, "status", a)


# --------------------------------------------------------------------------- questions with options (board)

def question_sidecar(store: Store, qid: str) -> Path:
    return store.dev / "run" / "questions" / f"{qid}.json"


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def cmd_answer_question(store: Store, a: argparse.Namespace) -> None:
    """Move a question from Open to Resolved in open-questions.md with its answer (the board's answers and
    interview --gaps both use it)."""
    store.load()
    if not re.fullmatch(r"Q-\d{1,5}", a.id):
        fail("question ids look like Q-3")
    answer = re.sub(r"\s+", " ", a.answer).strip().replace("|", "/")
    if not answer:
        fail("--answer is empty")
    path = store.dev / "open-questions.md"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    section, row_i = None, None
    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            section = line.strip().lower()
        elif section == "## open" and re.match(rf"^\|\s*{re.escape(a.id)}\s*\|", line):
            row_i = i
    if row_i is None:
        fail(f"{a.id} is not an open question in .dev/open-questions.md")
    del lines[row_i]
    res = next((i for i, line in enumerate(lines) if line.strip().lower() == "## resolved"), None)
    if res is None:
        lines += ["", "## Resolved", "| id | resolved on | answer | ADR / task |", "|---|---|---|---|"]
        res = len(lines) - 3
    j = res + 1
    while j < len(lines) and (lines[j].startswith("|") or not lines[j].strip() and j + 1 < len(lines) and lines[j + 1].startswith("|")):
        j += 1
    lines.insert(j, f"| {a.id} | {today()} | {answer} | {(a.ref or '-').replace('|', '/')} |")
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    side = question_sidecar(store, a.id)
    try:
        q = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        q = {"id": a.id}
    _write_json(side, {**q, "answered": True, "answer": answer, "answered_at": now()})
    store.log(f"answer-question {a.id}: {answer}")
    print(f"{a.id} resolved: {answer}")


# --------------------------------------------------------------------------- plan edits (board drafts)

HEADING_RE = re.compile(r"^#{1,3}\s")
TOP_HEADING_RE = re.compile(r"^#{1,2}\s")


class PlanDoc:
    """plan.md as segments: task sections (`### T-nnn` up to the next heading of level 3 or less) and text
    segments (everything else, a new one at every `#`/`##` heading), so tasks and milestones can be moved
    without touching the text around them."""

    def __init__(self, text: str):
        self.segs: list[dict] = []
        cur: dict | None = None
        for line in text.splitlines():
            tm = TASK_RE.match(line)
            if tm or TOP_HEADING_RE.match(line) or (cur and cur["kind"] == "task" and HEADING_RE.match(line)):
                cur = {"kind": "task", "id": tm.group(1), "lines": [line]} if tm else {"kind": "text", "lines": [line]}
                self.segs.append(cur)
            elif cur is None:
                cur = {"kind": "text", "lines": [line]}
                self.segs.append(cur)
            else:
                cur["lines"].append(line)
        for s in self.segs:
            if s["kind"] == "task":
                while len(s["lines"]) > 1 and not s["lines"][-1].strip():
                    s["lines"].pop()

    def milestone_of(self) -> list[str | None]:
        out, m = [], None
        for s in self.segs:
            first = s["lines"][0] if s["lines"] else ""
            mm = MILESTONE_RE.match(first)
            if s["kind"] == "text" and mm:
                m = mm.group(1)
            elif s["kind"] == "text" and TOP_HEADING_RE.match(first):
                m = None
            out.append(m)
        return out

    def find(self, tid: str) -> int | None:
        return next((i for i, s in enumerate(self.segs) if s["kind"] == "task" and s["id"] == tid), None)

    def has_milestone(self, m: str) -> bool:
        return m in self.milestone_of()

    def _end_of(self, m: str) -> int:
        owners = self.milestone_of()
        idx = [i for i, o in enumerate(owners) if o == m]
        return idx[-1] + 1

    def put(self, seg: dict, m: str, before: str | None = None) -> None:
        if before:
            self.segs.insert(self.find(before), seg)  # type: ignore[arg-type]
        else:
            self.segs.insert(self._end_of(m), seg)

    def move(self, tid: str, m: str, before: str | None = None) -> None:
        seg = self.segs.pop(self.find(tid))  # type: ignore[arg-type]
        self.put(seg, m, before)

    def reorder(self, order: list[str]) -> None:
        slots = sorted(self.find(x) for x in order)  # type: ignore[type-var]
        segs = {x: self.segs[self.find(x)] for x in order}  # type: ignore[index]
        for slot, x in zip(slots, order):
            self.segs[slot] = segs[x]

    def add_milestone(self, m: str, title: str) -> None:
        owners = self.milestone_of()
        nums = [(int(o[1:]), i) for i, o in enumerate(owners) if o]
        at = (max(i for n, i in nums if n == max(n for n, _ in nums)) + 1) if nums else len(self.segs)
        self.segs.insert(at, {"kind": "text", "lines": [f"## {m} — {title}", ""]})

    def text(self) -> str:
        out: list[str] = []
        for s in self.segs:
            lines = list(s["lines"])
            if out and out[-1].strip() and lines and (s["kind"] == "task" or TOP_HEADING_RE.match(lines[0])):
                out.append("")
            out += lines
            if s["kind"] == "task":
                out.append("")
        return "\n".join(out).rstrip("\n") + "\n"


def plan_edit(store: Store, ops: list[dict], text: str) -> tuple[str, list[str], list[str], dict]:
    """Apply a board draft to state (in memory) and to plan.md text. Every operation is checked against the state
    as the earlier ones left it; nothing is written here. Returns (new plan text, changes, errors, effects)."""
    doc = PlanDoc(text)
    ts, ms = store.tasks(), store.milestones()
    errors: list[str] = []
    changes: list[str] = []
    moved: set[str] = set()
    effects: dict = {"new_milestones": [], "scheduled": [], "moved": []}

    def gate(m: str) -> str:
        return ms[m].get("gate", "pending") if m in ms else "missing"

    def open_m(m: str, where: str) -> bool:
        if m not in ms or not doc.has_milestone(m):
            errors.append(f"{where}: milestone {m} does not exist")
            return False
        if gate(m) != "pending":
            errors.append(f"{where}: the gate of {m} is {gate(m)}; a closed milestone takes no change")
            return False
        return True

    def before_ok(before: str | None, m: str, where: str, tid: str | None = None) -> bool:
        if not before:
            return True
        if before == tid or before not in ts or ts[before]["milestone"] != m or doc.find(before) is None:
            errors.append(f"{where}: {before} is not a task of {m} in the plan")
            return False
        return True

    for n, op in enumerate(ops, 1):
        where, kind = f"change {n}", op.get("op")
        if kind == "new_milestone":
            m, title = op.get("milestone", ""), str(op.get("title") or "").strip()
            nxt = f"M{max([int(x[1:]) for x in ms] or [0]) + 1}"
            if effects["new_milestones"]:
                errors.append(f"{where}: one new milestone per draft")
            elif m != nxt:
                errors.append(f"{where}: the new milestone must be {nxt} (milestones are never inserted or renumbered)")
            elif not title:
                errors.append(f"{where}: the new milestone needs a title")
            else:
                ms[m] = {"title": title, "gate": "pending", "qa_runs": 0}
                doc.add_milestone(m, title)
                effects["new_milestones"].append(m)
                changes.append(f"new milestone {m} — {title}")
        elif kind == "move_task":
            tid, m, before = op.get("task", ""), op.get("milestone", ""), op.get("before")
            t = ts.get(tid)
            if t is None or t["status"] == "dropped" or doc.find(tid) is None:
                errors.append(f"{where}: {tid} is not a task of the plan")
            elif t["status"] != "todo":
                errors.append(f"{where}: {tid} is {t['status']}; only tasks not started can move")
            elif t.get("lane") == "hotfix":
                errors.append(f"{where}: {tid} is a hotfix; it stays in its milestone")
            elif gate(t["milestone"]) != "pending":
                errors.append(f"{where}: {tid} is in {t['milestone']}, whose gate is {gate(t['milestone'])}")
            elif open_m(m, where) and before_ok(before, m, where, tid):
                old = t["milestone"]
                doc.move(tid, m, before)
                t["milestone"] = m
                moved.add(tid)
                effects["moved"].append((tid, old, m))
                changes.append(f"{tid} {old} → {m}" + (f" (before {before})" if before else "") if old != m
                               else f"{tid} placed before {before}" if before else f"{tid} to the end of {m}")
        elif kind == "reorder":
            m, order = op.get("milestone", ""), list(op.get("tasks") or [])
            if not open_m(m, where):
                continue
            if len(set(order)) != len(order):
                errors.append(f"{where}: a task appears twice in the new order")
                continue
            bad = [x for x in order if x not in ts or ts[x]["milestone"] != m or doc.find(x) is None]
            if bad:
                errors.append(f"{where}: {bad[0]} is not a task of {m} in the plan")
                continue
            fixed = [x for x in order if ts[x]["status"] not in ("todo", "blocked")]
            if fixed:
                errors.append(f"{where}: {fixed[0]} is {ts[fixed[0]]['status']}; only tasks not started are reordered")
                continue
            doc.reorder(order)
            changes.append(f"{m}: order {', '.join(order)}")
        elif kind == "schedule_issue":
            iid, m, before = op.get("issue", ""), op.get("milestone", ""), op.get("before")
            i = issues(store).get(iid)
            if i is None:
                errors.append(f"{where}: unknown issue {iid}")
            elif i["status"] != "open":
                errors.append(f"{where}: {iid} is {i['status']}, not open")
            elif i.get("class") == "expedite":
                errors.append(f"{where}: {iid} is expedite; it goes through the hotfix lane (/dev-kit:issue {iid})")
            elif i.get("class") == "change" or i.get("type") == "change":
                errors.append(f"{where}: {iid} changes the scope; it goes through the PRD first (/dev-kit:issue {iid})")
            elif open_m(m, where) and before_ok(before, m, where):
                info = buffer_info(store, m)
                if m not in effects["new_milestones"] and info["free"] <= 0 and not op.get("force"):
                    errors.append(f"{where}: the issue buffer of {m} is full ({info['used']} of {info['capacity']}); "
                                  "confirm to go over it")
                    continue
                ttype = "fix" if i["type"] == "bug" else ("chore" if i.get("class") == "intangible" else "feature")
                tid = store.new_task_id()
                t = {"title": i["title"], "milestone": m, "type": ttype, "status": "todo", "deps": [],
                     "acceptance": i.get("acceptance") or [f"{iid} resolved: {i['title']}"],
                     "test_notes": f"start with a failing regression test that reproduces {iid}" if i["type"] == "bug"
                     else f"cover the change with tests; see {iid}",
                     "files": [], "commit": None, "blocked_reason": None, "source": f"issue:{iid}",
                     "started_at": None, "done_at": None}
                ts[tid] = t
                doc.put({"kind": "task", "id": tid, "lines": task_block(tid, t).rstrip("\n").splitlines()}, m, before)
                i.setdefault("tasks", []).append(tid)
                i["status"], i["scheduled_in"] = "scheduled", m
                effects["scheduled"].append((iid, tid, m))
                changes.append(f"{iid} → {tid} in {m}" + (" (over the issue buffer)" if info["free"] <= 0 and m not in effects["new_milestones"] else ""))
        else:
            errors.append(f"{where}: unknown operation {kind}")

    # a task never sits in an earlier milestone than a task it depends on (done dependencies do not count)
    rank = {m: int(m[1:]) for m in ms}
    for tid in sorted(moved):
        t = ts[tid]
        for d in sorted(set(t.get("deps", [])) | set(t.get("consumes") or [])):
            dt = ts.get(d)
            if dt and dt["status"] != "done" and rank.get(dt["milestone"], 0) > rank[t["milestone"]]:
                errors.append(f"{tid} depends on {d}, which is in a later milestone ({dt['milestone']})")
        for x, xt in sorted(ts.items()):
            if tid in (xt.get("deps") or []) and xt["status"] not in FINISHED and rank.get(xt["milestone"], 0) < rank[t["milestone"]]:
                errors.append(f"{x} depends on {tid}, which would come after it ({t['milestone']} after {xt['milestone']})")
    return doc.text(), changes, sorted(set(errors), key=errors.index), effects


def _load_draft(store: Store, a: argparse.Namespace) -> tuple[list[dict], str | None]:
    import dev_worker as dw
    if a.draft:
        x = dw.item(store.root, a.draft)
        if x is None or x.get("action") != "plan_draft":
            fail(f"{a.draft} is not a plan draft from the board")
        return x["args"].get("ops") or [], x["args"].get("base")
    try:
        raw = json.loads(Path(a.ops_file).read_text(encoding="utf-8") if a.ops_file else a.ops)
    except (OSError, TypeError, json.JSONDecodeError) as e:
        fail(f"the operations are not valid JSON: {e}")
    try:
        ops = dw.validate("plan_draft", {"ops": raw if isinstance(raw, list) else raw.get("ops")})["ops"]
    except dw.Invalid as e:
        fail("; ".join(e.errors))
    return ops, None


def apply_plan_ops(store: Store, ops: list[dict], *, dry_run: bool, as_json: bool, base: str | None = None,
                   label: str = "plan-apply") -> None:
    plan_path = store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    stale = bool(base) and base != store.state.get("updated_at")
    text, changes, errors, eff = plan_edit(store, ops, plan_path.read_text(encoding="utf-8"))
    out = {"ok": not errors, "changes": changes, "errors": errors, "state_changed_since_draft": stale, "applied": False}
    if not errors and not dry_run:
        try:
            _, _, problems = sync_plan_text(store, text)
        except ValueError as e:
            fail(f"the edited plan does not parse: {e}")
        tmp = plan_path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, plan_path)
        store.save()
        write_issues_md(store)
        for tid, old, new in eff["moved"]:
            store.event("task", task=tid, transition="move", milestone=new)
        for iid, tid, m in eff["scheduled"]:
            issue_event(store, iid, "scheduled")
        store.log(f"{label}: " + "; ".join(changes))
        out.update(applied=True, warnings=problems + [f"{x['check']}: {x['id']} - {x['detail']}" for x in xref_report(store)["problems"]])
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if stale:
            print("the state changed since this draft was made; every change was checked again against the current state")
        if errors:
            print("nothing changed:\n  " + "\n  ".join(errors))
        else:
            print(("would apply" if dry_run else "applied") + ":\n  " + "\n  ".join(changes))
            for w in out.get("warnings") or []:
                print(f"  warning: {w}")
    if errors:
        sys.exit(1)


def cmd_plan_apply(store: Store, a: argparse.Namespace) -> None:
    """Apply a plan draft made on the board (or given as JSON): every change is checked first, then all are
    written together (plan.md and state), or none."""
    store.load()
    if sum(bool(x) for x in (a.draft, a.ops, a.ops_file)) != 1:
        fail("give exactly one of --draft R-nnn, --ops JSON or --ops-file FILE")
    ops, base = _load_draft(store, a)
    apply_plan_ops(store, ops, dry_run=a.dry_run, as_json=a.json, base=base)


def cmd_move_task(store: Store, a: argparse.Namespace) -> None:
    store.load()
    op = {"op": "move_task", "task": a.task, "milestone": a.milestone, **({"before": a.before} if a.before else {})}
    apply_plan_ops(store, [op], dry_run=a.dry_run, as_json=a.json, label="move-task")


def cmd_new_milestone(store: Store, a: argparse.Namespace) -> None:
    store.load()
    apply_plan_ops(store, [{"op": "new_milestone", "milestone": a.milestone, "title": a.title}], dry_run=a.dry_run,
                   as_json=a.json, label="new-milestone")


def cmd_reorder(store: Store, a: argparse.Namespace) -> None:
    store.load()
    apply_plan_ops(store, [{"op": "reorder", "milestone": a.milestone, "tasks": a.tasks}], dry_run=a.dry_run,
                   as_json=a.json, label="reorder")


# --------------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev_state.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: walk up from cwd to find .dev/state.json, else cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.set_defaults(fn=cmd_init)
    s.add_argument("--project"); s.add_argument("--language")
    s.add_argument("--stack-json"); s.add_argument("--autonomy-json"); s.add_argument("--force", action="store_true")
    s.add_argument("--brownfield-json", help='existing-project marker, e.g. {"baseline_ref":"dev-kit-baseline","baseline_sha":"<sha>","mode":"feature","first_milestone":1}')

    s = sub.add_parser("sync-plan"); s.set_defaults(fn=cmd_sync_plan); s.add_argument("--plan")

    s = sub.add_parser("brief"); s.set_defaults(fn=cmd_brief); s.add_argument("task")
    s = sub.add_parser("strings"); s.set_defaults(fn=cmd_strings)
    s.add_argument("--since", required=True); s.add_argument("--worktree", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("contrast"); s.set_defaults(fn=cmd_contrast)
    s.add_argument("--spec"); s.add_argument("--pairs"); s.add_argument("--json", action="store_true"); s.add_argument("--strict", action="store_true")
    s = sub.add_parser("lock"); s.set_defaults(fn=cmd_lock)
    s.add_argument("action", choices=["acquire", "release", "status"]); s.add_argument("name", nargs="?")
    s.add_argument("--holder"); s.add_argument("--ttl", type=float, default=30); s.add_argument("--wait", type=float, default=0)
    s.add_argument("--note"); s.add_argument("--force", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("next"); s.set_defaults(fn=cmd_next)
    s.add_argument("--milestone"); s.add_argument("--json", action="store_true")
    s.add_argument("--batch", type=int, help="up to N ready tasks that can run in parallel")

    s = sub.add_parser("start"); s.set_defaults(fn=cmd_start); s.add_argument("task"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("done"); s.set_defaults(fn=cmd_done); s.add_argument("task"); s.add_argument("--commit"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("block"); s.set_defaults(fn=cmd_block); s.add_argument("task"); s.add_argument("--reason", required=True)
    s = sub.add_parser("unblock"); s.set_defaults(fn=cmd_unblock); s.add_argument("task")
    s = sub.add_parser("drop"); s.set_defaults(fn=cmd_drop); s.add_argument("task"); s.add_argument("--reason", required=True)

    s = sub.add_parser("add-task"); s.set_defaults(fn=cmd_add_task)
    s.add_argument("--milestone", required=True); s.add_argument("--milestone-title")
    s.add_argument("--title", required=True); s.add_argument("--type", default="feature")
    s.add_argument("--deps"); s.add_argument("--acceptance", action="append"); s.add_argument("--test-notes")
    s.add_argument("--files"); s.add_argument("--source"); s.add_argument("--issue"); s.add_argument("--lane")
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("fix-tasks"); s.set_defaults(fn=cmd_fix_tasks)
    s.add_argument("--from", dest="src_file", required=True); s.add_argument("--milestone", required=True)
    s.add_argument("--source"); s.add_argument("--include", help="comma-separated non-blocking finding ids to include")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("add-question"); s.set_defaults(fn=cmd_add_question)
    s.add_argument("text"); s.add_argument("--skill"); s.add_argument("--assumption"); s.add_argument("--impact")
    s.add_argument("--options", help="answers the board offers, separated by | (2 to 6)")
    s.add_argument("--recommended", help="the option recommended, first in the board"); s.add_argument("--request")
    s = sub.add_parser("answer-question"); s.set_defaults(fn=cmd_answer_question)
    s.add_argument("id"); s.add_argument("--answer", required=True); s.add_argument("--ref")
    s = sub.add_parser("plan-apply"); s.set_defaults(fn=cmd_plan_apply)
    s.add_argument("--draft", help="board request id of a plan draft (R-nnn)"); s.add_argument("--ops"); s.add_argument("--ops-file")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("move-task"); s.set_defaults(fn=cmd_move_task)
    s.add_argument("task"); s.add_argument("milestone"); s.add_argument("--before")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("new-milestone"); s.set_defaults(fn=cmd_new_milestone)
    s.add_argument("milestone"); s.add_argument("title")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("reorder"); s.set_defaults(fn=cmd_reorder)
    s.add_argument("milestone"); s.add_argument("tasks", nargs="+")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("gate"); s.set_defaults(fn=cmd_gate)
    s.add_argument("milestone"); s.add_argument("value"); s.add_argument("--note"); s.add_argument("--count-run", action="store_true")
    s.add_argument("--score", type=int); s.add_argument("--force", action="store_true"); s.add_argument("--scores")

    s = sub.add_parser("review"); s.set_defaults(fn=cmd_review)
    s.add_argument("name"); s.add_argument("value"); s.add_argument("--score", type=int); s.add_argument("--note")
    s.add_argument("--count-run", action="store_true"); s.add_argument("--force", action="store_true"); s.add_argument("--scores")

    s = sub.add_parser("artifact"); s.set_defaults(fn=cmd_artifact)
    s.add_argument("action", choices=["mark"]); s.add_argument("name"); s.add_argument("--note")
    s = sub.add_parser("ledger"); s.set_defaults(fn=cmd_ledger)
    s.add_argument("action", choices=["plan", "record", "sections", "record-sections", "put", "check", "get", "drop"])
    s.add_argument("key", nargs="?"); s.add_argument("--prefix"); s.add_argument("--target")
    s.add_argument("--files"); s.add_argument("--files-from"); s.add_argument("--context"); s.add_argument("--salt")
    s.add_argument("--shared"); s.add_argument("--findings-from"); s.add_argument("--result"); s.add_argument("--ref")
    s.add_argument("--note"); s.add_argument("--spot-pct", type=float); s.add_argument("--seed")
    s.add_argument("--no-cache", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("tests"); s.set_defaults(fn=cmd_tests)
    s.add_argument("action", choices=["record", "lookup"]); s.add_argument("--kind", default="all")
    s.add_argument("--sha"); s.add_argument("--command"); s.add_argument("--passed", type=int); s.add_argument("--failed", type=int)
    s.add_argument("--coverage", type=float); s.add_argument("--duration", type=float); s.add_argument("--paths")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("xref"); s.set_defaults(fn=cmd_xref)
    s.add_argument("--json", action="store_true"); s.add_argument("--strict", action="store_true")
    s = sub.add_parser("stale"); s.set_defaults(fn=cmd_stale)
    s.add_argument("--json", action="store_true"); s.add_argument("--strict", action="store_true")
    s = sub.add_parser("release-record"); s.set_defaults(fn=cmd_release_record)
    s.add_argument("--version", required=True); s.add_argument("--tag")
    s.add_argument("--milestones", help="comma-separated; default: every closed milestone not released yet")
    s.add_argument("--hotfix", help="patch release of a hotfix task; ships no milestone")
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
    s.add_argument("--next", action="store_true", help="print only the next command (status line, session banner)")
    s.add_argument("--quiet-if-missing", action="store_true")
    s.add_argument("--head-migration", help="current migration head in the checkout, to show how far production is behind")
    s = sub.add_parser("notify"); s.set_defaults(fn=cmd_notify); s.add_argument("text")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    store = Store(find_root(args.root))
    args.fn(store, args)


if __name__ == "__main__":
    main()
