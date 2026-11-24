#!/usr/bin/env python3
"""dev_state.py - single source of truth for dev-kit project state (.dev/state.json).

Standard library only. Run with: python3 -I dev_state.py <subcommand> [...]

Subcommands
  init          create .dev/ and state.json (idempotent; updates given fields)
  sync-plan     read .dev/plan.md and add/update milestones and tasks (never touches status)
  strings       user-facing strings added since a commit (--since SHA [--worktree]), for the copy review
  contrast      WCAG contrast of the colour token pairs in ui-spec.md (--pairs fg/bg,… or automatic)
  lock          acquire | release | status NAME: one holder at a time for an exclusive resource (--holder --ttl --wait)
  brief T       base prompt of an implementer for task T (languages, commands, verification rule, history, tier, route)
  tier T        risk tier of a task (rule from objective signals and the plan's risk fields) and its model/effort
                route (dev_router.py); --json
  set-risk T    set the risk fields of a task in plan.md and state (--risk --complexity --uncertainty --opportunity
                --risk-reasons --tier --tier-reason); plan --annotate-risk uses it on tasks already planned
  risk-profile M  risk profile of a milestone for the QA gate: max tier, high-risk tasks, seams, auditor models (--json)
  risk-report M   predicted tier against what happened (findings, rounds, time, tokens) per task and per tier;
                writes .dev/qa/M/risk-report.md (--all: every milestone; --json)
  next          print the next task to work on (fix tasks first, deps satisfied, gate respected); --batch N: tasks
                that can run in parallel (no common files, one serialising file at most)
  start T       mark task in_progress (--resume: take over an earlier attempt's worktree or dev-kit/T-nnn, §17)
  done T        mark task done (optionally --commit SHA)
  block T       mark task blocked (--reason; --blocked-by I-nnn pauses it until the replan of that scope change)
  forecast [--json]   probable (P50) and late (P85) finish and cost to finish per open milestone and release,
                from the last 3 measured milestones (after 2), conventions §13
  pipeline ACTION   status [--json] | worktree BRANCH | integrate BRANCH: work ahead of a release waiting for
                approval or a milestone in QA, on dev-kit/R<n> or dev-kit/M<n> (autonomy.pipeline), conventions §19
  round run SKILL M   one QA round or a milestone's implementation in a headless child session (claude -p),
                prints a JSON summary [--permission-mode MODE --timeout MIN], conventions §17
  fact ACTION   add --text --evidence --origin [--files --acs --sha] | stale K-nnn --by --evidence | list [--files
                --acs --all --json]: verified facts in .dev/facts.md (secrets and personal data refused), conventions §2
  lesson ACTION add AGENT "<text>" | rm AGENT N | show AGENT | list | suggest | dismiss AGENT SIGNAL: lessons of
                method per role in .dev/lessons/ (at most 8 each), conventions §13
  challenger M F   who challenges a critical/high finding: another role, or another model family (--json)
  challenge record M --from FILE  a challenger's verdict (agree | dispute | refine, with evidence), conventions §7
  slot ACTION N open --task T-nnn [--allow PATH] [--worktree] | close [--remove] | show | check [--since SHA] |
                apply: the file fence of an agent slot (dev_fence.py enforces it as a hook; check fails an integration
                that touched a file outside); --worktree creates the task's worktree from the work branch, apply brings
                its changes into the main checkout, conventions §17
  reconcile [--milestone M] [--since ISO] [--adopt T-nnn] [--json]   after a round or a session that stopped: close
                the slots left open, block the tasks left in_progress (Previous attempt in the ledger), remove clean
                worktrees; with --since, a todo task committed since then is done and one left changed is moved to its
                worktree and blocked; --adopt moves a task's changes from the main checkout into its worktree, §17
  affected      pending tasks whose acceptance cites changed ACs (--acs AC-4,AC-7 [--json]), conventions §15
  unblock T     blocked -> todo
  drop T        drop a task removed by a replan (--reason); it no longer counts for milestones or release
  task-decide T unblock|skip|drop|run [--note]: Needs-you decision on a blocked task or a hotfix
  flag list|set release_R<n> on|off [--rollback]: release flags (autonomy.release_flags, §21)
  prod-check    run the production health check once (--due: only when its interval passed); a failure opens an
                expedite issue (one per check) and a Needs-you item
  qa-decide M continue|accept|replan [--rounds N] [--note]: QA rounds used up
  add-task      create a task in state and plan.md
  fix-tasks     one fix task per blocking finding of a findings file (--from --milestone; idempotent)
  add-question  append a non-blocking question to open-questions.md (--options a|b --recommended a: the board
                shows them with the question)
  answer-question Q  move an open question to Resolved with its answer (--answer --ref)
  move-task T M move a task not started to another open milestone (--before T2), in plan.md and state
  new-milestone M TITLE  add the next milestone (M<last+1>) to plan.md and state; milestones are never inserted
  reorder M T…  new order of tasks not started inside a milestone (the order `next` follows)
  plan-apply    apply plan edits given as JSON (--ops or --ops-file): all its changes or none
                (--dry-run shows them)
  gate M        set milestone gate: passed | pending | skipped (passed needs --score >= cut-off, the hard floor,
                a green CI when required and, with an exit_check, `exit: pass` in scores.json; conventions §7)
  hard-floor M  record the round's deterministic checks (--from JSON): each failure becomes a hard_floor:<check> fix
  ci ACTION M   check | record (--sha --status success|failure|pending|none [--url]) | status: CI as the gate's verdict
  debt ACTION   status [--json] | decide promote|accept|cooldown: deferred debt above the cap
  artifact mark NAME  record that an artifact (brief|prd|architecture|ux|ui|plan|all) is up to date with its upstream
  stale         artifacts whose upstream changed since they were marked, and passed reviews now out of date
  ledger        work ledger (conventions §18): plan | record (files of an audit dimension), sections |
                record-sections (document review), put | check | get KEY, drop --prefix; reuse only unchanged ok work
  tests         record | lookup: test results per commit (.dev/run/test-runs.jsonl) so a green suite is not re-run
                on unchanged code (--kind unit|integration|e2e|all, --paths); lookup exits 3 when nothing is reusable
  xref          cross-document checks: ACs without tasks, unknown ACs, unspecified screens, unknown ADRs and deps
  review NAME   record a review (prd|design|plan|docs...): pass | fail | pending (pass needs --score >= cut-off);
                a passed prd or plan review opens its checkpoint
  checkpoint ACTION TARGET  status | confirm | adjust --feedback | summary --text, for prd or plan, conventions §19
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
  release-submit R  freeze a planned release for the user's approval (--review PATH): awaiting approval
  release-decide R  the user's decision: --approve, or --reject --feedback ITEM… (a fixes milestone in the release)
  release-record  record a release (--version [--tag] --release R after its approval, or --hotfix T): its
                milestones are no longer waiting for a release (writes .dev/releases/R/flow.json); the phase (conception, planning, construction, stable) is always derived
  set KEY VAL   set language | project | stack.<field> | autonomy.<field>[.<sub>] (nested keys merge;
                autonomy.level applies its preset; incl. autonomy.pause_policy.<point>)
  status        human (--short) or --json view; --next prints only the next command; --quiet-if-missing for hooks
  notify TEXT   queue a desktop notification shown at the end of the turn (only with autonomy.ui.notify on)

Exit codes: 0 ok · 1 usage/invalid transition · 2 state not found · 3 nothing to do (next)
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir; dev_telemetry lives next to us
import dev_telemetry as tel  # noqa: E402
import dev_ledger as led  # noqa: E402
import dev_risk as risk  # noqa: E402
import dev_router as router  # noqa: E402

STATE_VERSION = 2  # 2 = 3.0: planned releases always, a managed .dev/.gitignore (migrate_state)
# Project lifecycle (conventions.md §19): derived from the artifacts, reviews, milestones, issues and releases,
# never set by hand. Conception and planning run once at the start and again for every scope change; construction
# runs the milestone cycle and the next release; stable = nothing open, everything built is released.
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
    # risk_tiers: per-task tier from the risk rule (dev_risk.py): apply | suggest (shown, agent base used) | off.
    # risk_weights: per-project weight overrides of the rule's signals, e.g. {"schema": 3}.
    # router: model/effort router that learns from the project's runs (dev_router.py): mode apply | suggest | off,
    # balance balanced | speed | cost | quality (or {"cost": 1, "time": 1, "quality": 2}), optional budget per milestone.
    "model_policy": {"mode": "ask", "tiers": {}, "risk_tiers": "apply", "risk_weights": {},
                     "router": {"mode": "apply", "balance": "balanced", "budget_usd_per_milestone": None}},
    # What to do at each pause point (conventions.md §10). Default: ask, i.e. the supervised behaviour.
    "pause_policy": {},
    "on_park": "stop_when_idle",
    "notify_on_park": False,
    # Local deploy at the end of each approved milestone (conventions.md §11).
    "local_deploy": {"mode": "off", "port": None, "notify": False},
    # Issues (conventions.md §15): share of each milestone reserved for queued issues, optional cool-down.
    "issue_buffer_pct": 20,
    "cooldown": {"enabled": False, "max_tasks": 5},
    # Issue queue throughput (conventions.md §15): above `limit` open issues, or above `limit_pct_remaining`% of the
    # plan's remaining tasks, Needs you offers a milestone of the queue; an issue left unscheduled for
    # `aging_milestones` closed milestones asks for a decision; every milestone keeps at least `buffer_floor` slots.
    "queue": {"limit": 15, "limit_pct_remaining": 50, "aging_milestones": 3, "buffer_floor": 1},
    # Milestone size (conventions.md §4): planned tasks + buffer slots + cool-down; outside the range sync-plan warns
    # unless the milestone states a `size_reason:`.
    "milestone_size": {"min": 5, "max": 12},
    # work does not stop while a person decides (§19): one release ahead of the one waiting for approval, and the
    # independent tasks of the next milestone while the current one is in QA, each on its own branch
    "pipeline": {"releases_ahead": 1, "milestone_overlap": True},
    # the branch the project builds on (conventions.md §17): implementers' worktrees start from it and the pipeline
    # integrates into it; null = the branch checked out in the main checkout (not necessarily main)
    "git": {"base_branch": None},
    # feature flags per planned release (conventions.md §21): off by default; when on, every release R<n> has the
    # flag release_R<n>, its feature tasks wrap the new behaviour in it, approved milestones go to production with the
    # flag off (production.when per_milestone_flagged), and approving the release turns it on. provider = how the
    # project switches a flag (env var, config file, a flag service), recorded by architecture
    "release_flags": {"enabled": False, "provider": None},
    # CI as the source of truth for the gate's deterministic signals (conventions.md §7): provider auto (GitHub when
    # .github/workflows exists, GitLab when .gitlab-ci.yml exists) | github | gitlab | none; required = the gate needs
    # a green run on the round's commit; timeout_min = wait before the ci_timeout pause.
    "ci": {"provider": "auto", "required": True, "timeout_min": 30},
    # Contextual tips (shared/tips.json): on (each tip at most twice) | off | always.
    "tips": "on",
    # Claude Code interface (conventions.md §15): offered = start already asked once; spinner_tips and statusline are
    # written to the project's .claude/settings.local.json by dev_ui.py; title = session title and one-line banner at
    # session start (hook); notify = desktop notification at the end of the turn for gates, blocks and autopilot.
    "ui": {"offered": False, "spinner_tips": False, "statusline": False, "title": True, "notify": False},
    # Cheap checks at the end of each task (conventions.md §7): ui = copy and static a11y agents on tasks that touch
    # UI files (copy on sonnet, a11y on haiku) | all = also on other tasks with user-facing strings | off = implementer self-check only.
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
        # Deterministic floor of every gate (conventions.md §7): tests, lint, typecheck, deps, secrets, a11y.
        "hard_floor": {"enabled": True},
        # Deferred findings still open across milestones, past which a gate close asks the user (Needs you).
        "deferred_cap": {"total": 20, "medium": 10},
        # How long one auditor may work before the fence makes it write its result, and how long a QA round may go
        # without any tool call before it counts as stalled (qa-watch, round run; conventions.md §17).
        "watchdog": {"auditor_budget_min": 30, "stall_min": 20},
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


ROUTE_MODES = ("apply", "suggest", "off")
BALANCES = ("balanced", "speed", "cost", "quality")


def check_model_policy(mp: object) -> None:
    if not isinstance(mp, dict):
        fail("autonomy.model_policy must be an object like {\"mode\": \"ask\", \"tiers\": {}}")
    extra = set(mp) - {"mode", "tiers", "risk_tiers", "risk_weights", "router"}
    if extra:
        fail(f"autonomy.model_policy has unknown keys: {', '.join(sorted(extra))}")
    if mp.get("mode", "ask") not in MODEL_POLICY_MODES:
        fail(f"autonomy.model_policy.mode must be one of {', '.join(MODEL_POLICY_MODES)}")
    tiers = mp.get("tiers", {})
    if not isinstance(tiers, dict) or any(v not in MODEL_TIERS for v in tiers.values()):
        fail(f"autonomy.model_policy.tiers must map agent names to one of {', '.join(MODEL_TIERS)}")
    if mp.get("risk_tiers", "apply") not in ROUTE_MODES:
        fail(f"autonomy.model_policy.risk_tiers must be one of {', '.join(ROUTE_MODES)}")
    rw = mp.get("risk_weights", {})
    if not isinstance(rw, dict) or any(k not in risk.RISK_WEIGHTS for k in rw) or \
            any(not isinstance(v, int) or isinstance(v, bool) or not -5 <= v <= 6 for v in rw.values()):
        fail(f"autonomy.model_policy.risk_weights must map signals ({', '.join(risk.RISK_WEIGHTS)}) to integers from -5 to 6")
    for k in risk.FLOOR_SIGNALS:
        if k in rw and rw[k] < 1:
            fail(f"autonomy.model_policy.risk_weights.{k} is a floor signal and must stay at 1 or more")
    r = mp.get("router", {})
    if not isinstance(r, dict) or set(r) - {"mode", "balance", "budget_usd_per_milestone"}:
        fail("autonomy.model_policy.router must be an object with mode, balance, budget_usd_per_milestone")
    if r.get("mode", "apply") not in ROUTE_MODES:
        fail(f"autonomy.model_policy.router.mode must be one of {', '.join(ROUTE_MODES)}")
    b = r.get("balance", "balanced")
    if not (b in BALANCES or (isinstance(b, dict) and set(b) <= {"cost", "time", "quality"} and
                              all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 10 for v in b.values()))):
        fail(f"autonomy.model_policy.router.balance must be one of {', '.join(BALANCES)} or {{cost, time, quality}} numbers 0-10")
    bud = r.get("budget_usd_per_milestone")
    if bud is not None and (not isinstance(bud, (int, float)) or isinstance(bud, bool) or bud <= 0):
        fail("autonomy.model_policy.router.budget_usd_per_milestone must be a positive number or null")


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
    "ci_timeout": ("ask", "park"),
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
    "ci_timeout": {"action": "park"},
}


LOCAL_DEPLOY_MODES = ("off", "keep_running", "smoke")
PRODUCTION_WHEN = ("none", "per_milestone", "per_milestone_flagged", "on_release", "manual")
HEALTH_DEFAULTS = {"command": None, "url": None, "interval_min": 15}


def check_production(pr: object) -> None:
    if not isinstance(pr, dict) or pr.get("when", "none") not in PRODUCTION_WHEN:
        fail(f"autonomy.production.when must be one of {', '.join(PRODUCTION_WHEN)}")
    for k in ("targets", "smoke", "prerequisites"):
        if not isinstance(pr.get(k, []), list):
            fail(f"autonomy.production.{k} must be a list")
    if pr.get("when", "none") != "none" and not pr.get("method"):
        fail("autonomy.production needs a method (install script, systemd, compose, paas...) when deploys are enabled")
    hc = pr.get("health")
    if hc is not None:
        if (not isinstance(hc, dict) or set(hc) - set(HEALTH_DEFAULTS)
                or not all(isinstance(hc.get(k), (str, type(None))) for k in ("command", "url"))
                or (hc.get("url") and not re.match(r"^https?://", hc["url"]))
                or not isinstance(hc.get("interval_min", 15), int) or isinstance(hc.get("interval_min", 15), bool)
                or not 1 <= hc.get("interval_min", 15) <= 1440):
            fail('autonomy.production.health must be {"command": "<shell command>" | null, "url": "https://..." | null, '
                 '"interval_min": 1-1440}')


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
    elif field == "queue":
        check_queue(val)
    elif field == "milestone_size":
        if (not isinstance(val, dict) or set(val) - {"min", "max"}
                or not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 200 for v in val.values())
                or val.get("min", 5) > val.get("max", 12)):
            fail("autonomy.milestone_size must be {\"min\": 5, \"max\": 12} (integers, min <= max)")
    elif field == "pipeline":
        if (not isinstance(val, dict) or set(val) - {"releases_ahead", "milestone_overlap"}
                or not isinstance(val.get("releases_ahead", 1), int) or isinstance(val.get("releases_ahead", 1), bool)
                or not 0 <= val.get("releases_ahead", 1) <= 3 or not isinstance(val.get("milestone_overlap", True), bool)):
            fail('autonomy.pipeline must be {"releases_ahead": 0-3, "milestone_overlap": true | false}')
    elif field == "git":
        br = val.get("base_branch") if isinstance(val, dict) else None
        if (not isinstance(val, dict) or set(val) - {"base_branch"} or not isinstance(br, (str, type(None)))
                or (br is not None and not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", br))):
            fail('autonomy.git must be {"base_branch": "<branch>" | null} (null = the branch of the main checkout)')
    elif field == "release_flags":
        if (not isinstance(val, dict) or set(val) - {"enabled", "provider"} or not isinstance(val.get("enabled", False), bool)
                or not isinstance(val.get("provider"), (str, type(None)))):
            fail('autonomy.release_flags must be {"enabled": true | false, "provider": "<how a flag is switched>"}')
        if val.get("enabled") and not (val.get("provider") or "").strip():
            fail("autonomy.release_flags needs a provider when enabled (env var, config file, flag service...): "
                 "/dev-kit:architecture records it")
    elif field == "ci":
        if (not isinstance(val, dict) or set(val) - {"provider", "required", "timeout_min"}
                or val.get("provider", "auto") not in CI_PROVIDERS or not isinstance(val.get("required", True), bool)
                or not isinstance(val.get("timeout_min", 30), int) or not 1 <= val.get("timeout_min", 30) <= 600):
            fail(f"autonomy.ci must be {{\"provider\": {' | '.join(CI_PROVIDERS)}, \"required\": true, \"timeout_min\": 30}}")
    elif field == "cooldown":
        if not isinstance(val, dict) or not isinstance(val.get("enabled", False), bool) or not isinstance(val.get("max_tasks", 5), int):
            fail('autonomy.cooldown must be on | off or {"enabled": true, "max_tasks": 5}')
    elif field in ("decide_alone", "always_ask"):
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            fail(f"autonomy.{field} must be a list of decision categories")
    elif field == "quality":
        if not isinstance(val, dict):
            fail("autonomy.quality must be an object")
        hf = val.get("hard_floor", {})
        if not isinstance(hf, dict) or set(hf) - {"enabled"} or not isinstance(hf.get("enabled", True), bool):
            fail('autonomy.quality.hard_floor must be {"enabled": true}')
        dc = val.get("deferred_cap", {})
        if (not isinstance(dc, dict) or set(dc) - {"total", "medium"}
                or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000 for v in dc.values())):
            fail('autonomy.quality.deferred_cap must be {"total": 20, "medium": 10} (0 turns a cap off)')
        wd = val.get("watchdog", {})
        if (not isinstance(wd, dict) or set(wd) - {"auditor_budget_min", "stall_min"}
                or not all(isinstance(v, int) and not isinstance(v, bool) and 5 <= v <= 240 for v in wd.values())):
            fail('autonomy.quality.watchdog must be {"auditor_budget_min": 30, "stall_min": 20} (minutes, 5 to 240)')
    elif field == "ui":
        if not isinstance(val, dict) or set(val) - set(UI_KEYS) or not all(isinstance(v, bool) for v in val.values()):
            fail(f"autonomy.ui must be an object with true/false values for {', '.join(UI_KEYS)}")
        val = {**DEFAULT_AUTONOMY["ui"], **val}
    return val


CI_PROVIDERS = ("auto", "github", "gitlab", "none")
QUEUE_LIMITS = {"limit": (1, 500), "limit_pct_remaining": (1, 1000), "aging_milestones": (1, 50), "buffer_floor": (0, 20)}


def check_queue(val: object) -> None:
    if not isinstance(val, dict) or set(val) - set(QUEUE_LIMITS):
        fail(f"autonomy.queue must be an object with {', '.join(QUEUE_LIMITS)}")
    for k, (lo, hi) in QUEUE_LIMITS.items():
        if k in val and (not isinstance(val[k], int) or isinstance(val[k], bool) or not lo <= val[k] <= hi):
            fail(f"autonomy.queue.{k} must be an integer between {lo} and {hi}")


def queue_cfg(state: dict) -> dict:
    return {**DEFAULT_AUTONOMY["queue"], **((state.get("autonomy") or {}).get("queue") or {})}


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
ISSUE_STATUSES = ("open", "scheduled", "in_progress", "done", "wontfix", "duplicate", "parked")  # parked: never pulled (§15)
ISSUE_SEVERITIES = ("critical", "high", "medium", "low")
ISSUE_ORIGINS = ("user", "qa", "usability", "deploy", "feedback", "review", "baseline")
LANES = ("hotfix", "cooldown")
CLASS_RANK = {"standard": 0, "intangible": 1}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TIPS_MODES = ("on", "off", "always")
UI_KEYS = ("offered", "spinner_tips", "statusline", "title", "notify")


MID = r"M\d+(?:\.\d+)?"  # M5, or M5.1 for the fixes milestone of a rejected release (§3)
MILESTONE_RE = re.compile(r"^##\s+(" + MID + r")\s*(?:[—–-]+\s*)?(.*?)\s*$")
RELEASE_RE = re.compile(r"^##\s+(R\d+)\s*(?:[—–-]+\s*)?(.*?)\s*$")  # a planned release groups the milestones below it (§4)
RELEASE_STATUSES = ("in_progress", "ready_for_review", "awaiting_approval", "deploying_prod", "released")
RELEASE_SIZE = (2, 5)  # milestones per release the planner aims for (§4 grouping rules)
TASK_RE = re.compile(r"^###\s+(T-\d{3,})\s+(.*?)\s*$")
FIELD_RE = re.compile(r"^-\s+([a-z_]+):\s*(.*?)\s*$")
SUBITEM_RE = re.compile(r"^\s{2,}-\s+(.*?)\s*$")
# milestone fields, between the `## Mn` heading and its first task (conventions.md §4)
MS_FIELD_RE = re.compile(r"^\s*(?:[-*]\s+)?\**(exit_check|size_reason)\**\s*:\s*(.*?)\s*$")
EXIT_KINDS = ("e2e", "cmd", "acs")
# milestones that need no exit_check of their own: release fixes (M<k>.<i>) and maintenance/issue milestones
EXIT_EXEMPT_TITLE = re.compile(r"\b(maintenance|fixes|issues|cool-?down)\b", re.I)


def parse_exit_check(val: str) -> dict:
    """`e2e: checkout.spec; cmd: npm run smoke; acs: AC-1, AC-2` -> {"e2e": [...], "cmd": [...], "acs": [...]}.
    `acs: tasks` means the milestone inherits its tasks' ACs. Raises ValueError on an unknown kind or no check."""
    out: dict = {}
    for part in re.split(r";\s*(?=(?:e2e|cmd|acs)\s*:)", val.strip()):
        if not part.strip():
            continue
        k, sep, v = part.partition(":")
        k = k.strip().lower()
        if not sep or k not in EXIT_KINDS or not v.strip():
            raise ValueError(f"exit_check part {part.strip()!r} must be one of e2e: <test>, cmd: <command>, acs: AC-n, AC-m")
        if k == "acs":
            out.setdefault("acs", []).extend(x.strip() for x in v.split(",") if x.strip())
        else:
            out.setdefault(k, []).append(v.strip())
    if not out:
        raise ValueError("exit_check is empty")
    return out


def exit_exempt(m: str, title: str) -> bool:
    return "." in m or bool(EXIT_EXEMPT_TITLE.search(title or ""))


def explicit_exit(ms: dict) -> bool:
    """The milestone declares a check of its own (not only `acs: tasks`): the gate then needs `exit: pass`."""
    ec = ms.get("exit_check") or {}
    return bool(ec.get("e2e") or ec.get("cmd") or [a for a in ec.get("acs") or [] if a.lower() != "tasks"])


# --------------------------------------------------------------------------- helpers

def mkey(m: str) -> tuple[int, int]:
    """Order of a milestone id: M5 < M5.1 < M5.2 < M6 (a release's fixes milestone follows its last milestone)."""
    mm = re.fullmatch(r"M(\d+)(?:\.(\d+))?", str(m))
    return (int(mm.group(1)), int(mm.group(2) or 0)) if mm else (10 ** 6, 0)


def mmajor(m: str) -> int:
    return mkey(m)[0]


def _clock() -> datetime:
    """The current time; DEV_KIT_NOW (ISO 8601) pins it so tests and replays produce byte-identical artifacts."""
    pinned = os.environ.get("DEV_KIT_NOW")
    if pinned:
        try:
            d = datetime.fromisoformat(pinned.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def now() -> str:
    return _clock().replace(microsecond=0).isoformat()


def today() -> str:
    return _clock().strftime("%Y-%m-%d")


def atomic_write(path: Path, text: str) -> None:
    """Replace `path` with `text` so a reader (or a crash) sees the old or the new content, never a mix: a unique
    temp file in the same directory, flushed and fsynced, renamed over the target, then the directory fsynced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _write_tmp(path, text)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _write_tmp(path: Path, text: str) -> Path:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    return tmp


def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


LOCK_TIMEOUT = 30.0


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
    """Project state. Every change goes through `transaction()`: an exclusive lock, a fresh load, the command's
    edits to state and to the files it stages, then one commit (all files or none, state.json last), then the log
    and telemetry lines. A command that fails (`fail()`) commits nothing."""

    def __init__(self, root: Path):
        self.root = root
        self.dev = root / ".dev"
        self.path = self.dev / "state.json"
        self.state: dict = {}
        self._depth = 0
        self._lock_f = None
        self._staged: dict[Path, str] = {}
        self._pending: list[tuple[str, object]] = []
        self._state_dirty = False

    def exists(self) -> bool:
        return self.path.exists()

    # ---- transactions
    @property
    def in_txn(self) -> bool:
        return self._depth > 0

    @property
    def lock_path(self) -> Path:
        return self.dev / "run" / "state.lock"

    @property
    def journal_path(self) -> Path:
        return self.dev / "run" / "txn.json"

    @contextlib.contextmanager
    def lock(self, timeout: float = LOCK_TIMEOUT):
        """Exclusive project lock, reentrant inside one process; timeout 0 = try once and raise TimeoutError."""
        if self._depth > 0:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        run = self.dev / "run"
        run.mkdir(parents=True, exist_ok=True)
        gi = run / ".gitignore"
        if not gi.exists():
            try:
                gi.write_text("*\n", encoding="utf-8")
            except OSError:
                pass
        f = open(self.lock_path, "a+")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    f.close()
                    raise TimeoutError(f"another dev-kit command holds {self.lock_path} (waited {timeout:g}s)")
                time.sleep(0.05)
        self._lock_f = f
        self._depth = 1
        try:
            yield
        finally:
            self._depth = 0
            self._lock_f = None
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            finally:
                f.close()

    @contextlib.contextmanager
    def transaction(self, timeout: float = LOCK_TIMEOUT):
        """Lock, load the latest state, let the caller edit it, then commit; nested use joins the outer one."""
        if self._depth > 0:
            with self.lock():
                yield self
            return
        try:
            cm = self.lock(timeout)
            cm.__enter__()
        except TimeoutError as e:
            fail(str(e), 4)
        outer_exc: tuple = (None, None, None)
        try:
            self._staged, self._pending, self._state_dirty = {}, [], False
            self._recover()
            self.state = {}
            if self.exists():
                self._read_state()
            try:
                yield self
            except BaseException as e:  # noqa: BLE001 - decide below whether the command succeeded
                ok = isinstance(e, SystemExit) and not e.code
                if not ok:
                    outer_exc = (type(e), e, e.__traceback__)
                    self._staged, self._pending, self._state_dirty = {}, [], False
                    raise
            self._commit()
        finally:
            cm.__exit__(*outer_exc)

    def stage(self, path: Path, text: str) -> None:
        """Write `text` to `path` as part of the transaction (immediately when there is none)."""
        if self._depth > 0:
            self._staged[path] = text
        else:
            atomic_write(path, text)

    def read_text(self, path: Path) -> str:
        """A file's content as the transaction will leave it (staged text wins over the disk)."""
        if path in self._staged:
            return self._staged[path]
        return path.read_text(encoding="utf-8")

    def file_exists(self, path: Path) -> bool:
        return path in self._staged or path.exists()

    def _commit(self) -> None:
        if self._state_dirty:
            self._stamp_state()
            self._staged[self.path] = json.dumps(self.state, indent=2, ensure_ascii=False) + "\n"
        staged, pending = self._staged, self._pending
        self._staged, self._pending, self._state_dirty = {}, [], False
        if staged:
            order = [p for p in staged if p != self.path] + ([self.path] if self.path in staged else [])
            for p in order:
                p.parent.mkdir(parents=True, exist_ok=True)
            tmps = [(_write_tmp(p, staged[p]), p) for p in order]  # every file complete on disk before the first rename
            if self.path in staged and self.path.exists():
                try:
                    atomic_write(self.path.with_name("state.json.bak"), self.path.read_text(encoding="utf-8"))
                except OSError:
                    pass
            journal = {"files": [[str(t), str(p)] for t, p in tmps]}
            atomic_write(self.journal_path, json.dumps(journal))
            self._roll_forward(journal)
        for kind, payload in pending:  # side effects only once the change is committed
            if kind == "log":
                self._append_log(payload)  # type: ignore[arg-type]
            else:
                tel.safe_emit(self.dev, payload[0], payload[1])  # type: ignore[index]

    def _roll_forward(self, journal: dict) -> None:
        for t, p in journal.get("files", []):
            if os.path.exists(t):
                os.replace(t, p)
        for d in {os.path.dirname(p) for _, p in journal.get("files", [])}:
            _fsync_dir(Path(d))
        self.journal_path.unlink(missing_ok=True)

    def _recover(self) -> None:
        """A journal left by a killed command: finish its renames, so the files are all new or (never started) all old."""
        if self.journal_path.exists():
            try:
                self._roll_forward(json.loads(self.journal_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                self.journal_path.unlink(missing_ok=True)

    def _read_state(self) -> None:
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            bak = self.path.with_name("state.json.bak")
            fail(f"state.json is corrupt: {e}" + (f" (the previous good copy is {bak})" if bak.exists() else ""), 1)
        migrate_legacy_phase(self)
        migrate_state(self)

    def load(self) -> dict:
        if self._depth > 0 and self.state:
            return self.state  # inside a transaction the in-memory state is the latest, staged edits included
        if not self.exists():
            fail(f"no state at {self.path}. Run `dev_state.py init` (or interview) first.", 2)
        if self._depth == 0 and self.journal_path.exists():
            try:
                with self.lock():
                    self._recover()
            except TimeoutError:
                pass  # the writer that owns the journal is still finishing: read what is there
        self._read_state()
        return self.state

    def _stamp_state(self) -> None:
        self.state["updated_at"] = now()
        kv = kit_version()
        if kv:
            self.state["kit_version"] = kv
        try:  # cached for the status line, the session banner and the board, which read state.json directly
            lc = lifecycle(self)
            self.state["phase"], self.state["step"], self.state["reopened"] = lc["phase"], lc["step"], lc["reopened"]
        except Exception:  # noqa: BLE001 - a derived label must never stop the state from being saved
            pass

    def save(self) -> None:
        """Mark the state to be written at commit. Outside a transaction it takes one: lock, write, done."""
        if self._depth > 0:
            self._state_dirty = True
            return
        with self.lock():
            self._recover()
            self._staged, self._pending, self._state_dirty = {}, [], True
            self._commit()

    def _append_log(self, line: str) -> None:
        self.dev.mkdir(parents=True, exist_ok=True)
        with (self.dev / "log.md").open("a", encoding="utf-8") as f:
            f.write(f"- {now()} {line}\n")

    def event(self, event: str, **fields) -> None:
        if self._depth > 0:
            self._pending.append(("event", (event, fields)))
        else:
            tel.safe_emit(self.dev, event, fields)

    def log(self, line: str) -> None:
        if self._depth > 0:
            self._pending.append(("log", f"{line}"))
        else:
            self._append_log(line)

    # ---- derived
    def tasks(self) -> dict:
        return self.state.setdefault("tasks", {})

    def milestones(self) -> dict:
        return self.state.setdefault("milestones", {})

    def milestone_order(self) -> list[str]:
        """Plan order: by release when releases are planned (a release's fixes milestone stays inside it), then by number."""
        ms = self.milestones()
        rplan = self.state.get("release_plan") or []
        if not rplan:
            return sorted(ms.keys(), key=mkey)
        idx = {m: i for i, r in enumerate(rplan) for m in r.get("milestones") or []}
        return sorted(ms.keys(), key=lambda m: (idx.get(m, len(rplan)), mkey(m)))

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
        ts = gate_tasks(self, m)
        return bool(ts) and all(v["status"] == "done" for v in ts)

    def gate_open_for(self, m: str) -> tuple[bool, str]:
        """A milestone is workable if every previous milestone has gate passed/skipped (or has no tasks), and, with
        planned releases, every earlier release is released (no milestone of R2 starts while R1 waits, §19)."""
        rel = release_of(self, m)
        if rel:
            for r in self.state.get("release_plan") or []:
                if r["id"] == rel:
                    break
                st = release_status(self, r["id"])["status"]
                if st != "released":
                    return False, f"{m} is in {rel}; {r['id']} must be released first ({st.replace('_', ' ')})"
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
    cur_r: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        r = RELEASE_RE.match(line)
        if r:
            cur_r, cur_m, cur_t, cur_field = r.group(1), None, None, None
            continue
        if line.startswith("# "):
            cur_r = None
        m = MILESTONE_RE.match(line)
        if m:
            cur_m, cur_t, cur_field = m.group(1), None, None
            milestones[cur_m] = {"title": m.group(2) or cur_m, "release": cur_r}
            continue
        if cur_m is not None and cur_t is None:
            mf = MS_FIELD_RE.match(line)
            if mf:
                if mf.group(1) == "exit_check":
                    try:
                        milestones[cur_m]["exit_check"] = parse_exit_check(mf.group(2))
                    except ValueError as e:
                        raise ValueError(f"{cur_m}: {e}") from None
                elif mf.group(2):
                    milestones[cur_m]["size_reason"] = mf.group(2)
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
            elif key == "flag":
                if val.strip():
                    task["flag"] = val.strip()  # the release flag that wraps the new behaviour (§21)
            elif key == "dep_reasons":
                if val.strip():
                    task["dep_reasons"] = val.strip()  # why each dependency is needed, `T-nnn=<text>; T-mmm=<text>`, §4
            elif key in ("risk", "complexity", "uncertainty", "tier"):
                if val.strip():
                    task[key] = val.strip().lower()
            elif key in ("risk_reasons", "tier_reason"):
                if val.strip():
                    task[key] = val.strip()
            elif key == "opportunity":
                ops = [o for o in risk.parse_opportunity(val) if o != "none"]
                if ops:
                    task["opportunity"] = ops
            else:
                task.setdefault("extra", {})[key] = val
            continue
        s = SUBITEM_RE.match(raw)
        if s and cur_field == "contract":
            tasks[cur_t]["contract"] = "; ".join(x for x in (tasks[cur_t].get("contract") or "", s.group(1)) if x)
            continue
        if s and cur_field == "dep_reasons":
            tasks[cur_t]["dep_reasons"] = "; ".join(x for x in (tasks[cur_t].get("dep_reasons") or "", s.group(1)) if x)
            continue
        if s and cur_field == "risk_reasons":
            tasks[cur_t]["risk_reasons"] = "; ".join(x for x in (tasks[cur_t].get("risk_reasons") or "", s.group(1)) if x)
            continue
        if s and cur_field == "acceptance":
            tasks[cur_t]["acceptance"].append(s.group(1))
            continue
        if s and cur_field == "files":
            tasks[cur_t]["files"].append(s.group(1))
    return milestones, tasks


def parse_dep_reasons(text: str | None) -> dict[str, str]:
    """`T-001=why; T-002=why` -> {id: why}. Malformed parts are ignored."""
    out: dict[str, str] = {}
    for part in (text or "").split(";"):
        k, sep, v = part.partition("=")
        if sep and k.strip():
            out[k.strip()] = v.strip()
    return out


def _paths_overlap(a: str, b: str) -> bool:
    a, b = a.strip().lstrip("./").rstrip("/"), b.strip().lstrip("./").rstrip("/")
    return bool(a and b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))


def unjustified_deps(tasks: dict) -> list[tuple[str, str]]:
    """(task, dep) for every dependency of a pending task with no contract, no common path, no `shared` and no reason."""
    out = []
    for tid, t in tasks.items():
        if t.get("status") not in ("todo", "blocked"):
            continue
        reasons = parse_dep_reasons(t.get("dep_reasons"))
        for d in t.get("deps") or []:
            a = tasks.get(d)
            if a is None or a.get("status") == "dropped":
                continue
            if d in (t.get("consumes") or []) or a.get("shared") or d in reasons:
                continue
            if any(_paths_overlap(x, y) for x in a.get("files") or [] for y in t.get("files") or []):
                continue
            out.append((tid, d))
    return out


def critical_paths(tasks: dict) -> dict[str, dict]:
    """Per milestone: task count and the longest dependency chain inside it."""
    live = {k: v for k, v in tasks.items() if v.get("status") != "dropped"}
    memo: dict[str, list[str]] = {}

    def chain(tid: str, seen: tuple = ()) -> list[str]:
        if tid in memo:
            return memo[tid]
        best: list[str] = []
        for d in live[tid].get("deps") or []:
            if d in live and d not in seen and live[d]["milestone"] == live[tid]["milestone"]:
                c = chain(d, seen + (tid,))
                if len(c) > len(best):
                    best = c
        memo[tid] = best + [tid]
        return memo[tid]

    out: dict[str, dict] = {}
    for tid, t in live.items():
        e = out.setdefault(t["milestone"], {"tasks": 0, "critical_path": 0, "chain": []})
        e["tasks"] += 1
        c = chain(tid)
        if len(c) > e["critical_path"]:
            e["critical_path"], e["chain"] = len(c), c
    return out


def maybe_false_deps(store: "Store", milestone: str | None, batch: list[str]) -> list[dict]:
    """Pending tasks that wait only on tasks in progress through dependencies that look unjustified."""
    ts = store.tasks()
    ms = {ts[t]["milestone"] for t in batch} | {v["milestone"] for v in ts.values() if v.get("status") == "in_progress"}
    if milestone:
        ms &= {milestone}
    bad: dict[str, set[str]] = {}
    for tid, d in unjustified_deps(ts):
        bad.setdefault(tid, set()).add(d)
    out = []
    for tid, v in ts.items():
        if v.get("status") != "todo" or v["milestone"] not in ms or v.get("lane") == "hotfix":
            continue
        unmet = [d for d in v["deps"] if ts.get(d, {}).get("status") != "done"]
        if unmet and all(ts.get(d, {}).get("status") == "in_progress" and d in bad.get(tid, ()) for d in unmet):
            out.append({"task": tid, "waits_on": unmet})
    return out


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
    if t.get("dep_reasons"):
        lines.append(f"- dep_reasons: {t['dep_reasons']}")
    if t.get("flag"):
        lines.append(f"- flag: {t['flag']}")
    if t.get("source"):
        lines.append(f"- source: {t['source']}")
    if t.get("lane"):
        lines.append(f"- lane: {t['lane']}")
    lines += risk_lines(t)
    return "\n".join(lines) + "\n"


def risk_lines(t: dict) -> list[str]:
    out = []
    for k in risk.RISK_FIELDS:
        v = t.get(k)
        if v in (None, "", []):
            continue
        out.append(f"- {k}: {', '.join(v) if isinstance(v, list) else v}")
    return out


def release_for_new_milestone(store: Store, milestone: str, title: str) -> tuple[str, str] | None:
    """A milestone created at the end of plan.md (an issue opening `M<n+1> — Maintenance`, §16) falls under the last
    release heading. It needs a new one when that release was submitted for approval (or approved, or released)
    or, for maintenance, already holds the most milestones a release groups (§4). Returns (id, title) to add, or None."""
    plan = store.state.get("release_plan") or []
    if not plan:
        return None
    last = plan[-1]
    st = release_status(store, last["id"])
    maint = bool(re.search(r"\bmaintenance\b", title or "", re.I))
    full = maint and len(last.get("milestones") or []) >= RELEASE_SIZE[1]
    if st["status"] in ("in_progress", "ready_for_review") and not full and last["id"] != "R0":
        last.setdefault("milestones", []).append(milestone)
        store.milestones()[milestone]["release"] = last["id"]
        return None
    n = max(int(r["id"][1:]) for r in plan) + 1
    rid, rtitle = f"R{n}", ("Maintenance" if maint else title or f"Release {n}")
    plan.append({"id": rid, "title": rtitle, "milestones": [milestone]})
    store.milestones()[milestone]["release"] = rid
    return rid, rtitle


def append_task_to_plan(store: Store, plan_path: Path, milestone: str, m_title: str, tid: str, t: dict) -> None:
    text = store.read_text(plan_path) if store.file_exists(plan_path) else "# Implementation plan\n"
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
        rel = release_for_new_milestone(store, milestone, m_title)
        if rel:
            lines += [f"## {rel[0]} — {rel[1]}", ""]
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
    store.stage(plan_path, "\n".join(lines).rstrip("\n") + "\n")


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
    stage_gitignore(store)
    oq = store.dev / "open-questions.md"
    if not oq.exists():
        store.stage(
            oq,
            "# Open questions\n\n> Non-blocking doubts raised while working autonomously. "
            "Resolve with `/dev-kit:interview --gaps`.\n\n## Open\n"
            "| id | date | raised by | question | assumption used | impact if wrong |\n"
            "|---|---|---|---|---|---|\n\n## Resolved\n| id | resolved on | answer | ADR / task |\n|---|---|---|---|\n",
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
        store.stage(path, json.dumps(base, indent=1, ensure_ascii=False) + "\n")
    return added


def plan_releases(text: str, milestones: dict) -> tuple[list[dict], list[str]]:
    """The planned releases of plan.md in order ({id, title, milestones}) and the grouping problems found."""
    out: list[dict] = []
    problems: list[str] = []
    for line in text.splitlines():
        r = RELEASE_RE.match(line.rstrip())
        if r:
            if any(x["id"] == r.group(1) for x in out):
                problems.append(f"release {r.group(1)} is declared twice")
                continue
            out.append({"id": r.group(1), "title": r.group(2) or r.group(1), "milestones": []})
    for m, info in milestones.items():
        rel = next((x for x in out if x["id"] == info.get("release")), None)
        if rel is not None:
            rel["milestones"].append(m)
    if out:
        loose = [m for m, info in milestones.items() if not info.get("release")]
        if loose:
            problems.append(f"milestones outside any release: {', '.join(loose)} (put them under a '## R<n>' heading)")
        for x in out:
            n = len(x["milestones"])
            if not n:
                problems.append(f"release {x['id']} has no milestone")
            elif n > RELEASE_SIZE[1] and x["id"] != "R0":
                problems.append(f"release {x['id']} has {n} milestones; aim for {RELEASE_SIZE[0]} to {RELEASE_SIZE[1]} so its review stays short")
    return out, problems


def sync_plan_text(store: Store, text: str) -> tuple[dict, tuple[int, int, int], list[str]]:
    """Bring state in line with plan.md text, in memory: milestones and tasks added or updated (never status), each
    task's position in the plan as `seq` (the order `next` follows within a milestone). Returns the parsed tasks,
    the counts (milestones added, tasks added, tasks updated) and the problems found. Raises ValueError."""
    milestones, tasks = parse_plan(text)
    rplan, rel_problems = plan_releases(text, milestones)
    added_m = added_t = updated_t = 0
    # exit_check (§4): required on a new milestone of a plan that already uses it (a 3.0 plan); a milestone without
    # one in an older plan only warns, and its gate does not ask for `exit: pass` until it is annotated
    v3 = bool(store.state.get("exit_checks")) or any(i.get("exit_check") for i in milestones.values())
    exit_problems = []
    released = {x for r in store.state.get("releases") or [] for x in r.get("milestones") or []}
    turning_on = v3 and not store.state.get("exit_checks")
    lacking = []
    for m, info in milestones.items():
        if info.get("exit_check") or exit_exempt(m, info["title"]):
            continue
        if m in released or (store.milestones().get(m) or {}).get("gate") in ("passed", "skipped"):
            continue  # closed: nothing left to check
        if v3 and m not in store.milestones():
            raise ValueError(f"{m} has no exit_check: add `exit_check: e2e: <test>; cmd: <command>; acs: AC-n` "
                             "below its goal (conventions.md §4)")
        lacking.append(m)
        exit_problems.append(f"{m}: no exit_check; its gate checks only the tasks (/dev-kit:plan --annotate-exit proposes one)")
    if turning_on and lacking:
        exit_problems.insert(0, f"exit checks are now on for the whole project: every gate also needs the hard floor recorded, "
                                f"and these open milestones have no exit_check: {', '.join(lacking)} (annotate them all with "
                                "/dev-kit:plan --annotate-exit)")
    if v3:
        store.state["exit_checks"] = True
    for m, info in milestones.items():
        if m not in store.milestones():
            store.milestones()[m] = {"title": info["title"], "gate": "pending", "qa_runs": 0}
            added_m += 1
        else:
            store.milestones()[m]["title"] = info["title"]
        for k in ("exit_check", "size_reason"):
            if info.get(k):
                store.milestones()[m][k] = info[k]
            else:
                store.milestones()[m].pop(k, None)
        if info.get("release"):
            store.milestones()[m]["release"] = info["release"]
        else:
            store.milestones()[m].pop("release", None)
    if rplan:
        store.state["release_plan"] = rplan
    else:
        store.state.pop("release_plan", None)
    max_id = int(store.state.get("next_task_id", 1)) - 1
    for seq, (tid, t) in enumerate(tasks.items(), 1):
        t["seq"] = seq
        max_id = max(max_id, int(tid[2:]))
        if tid in store.tasks():
            cur = store.tasks()[tid]
            for k in ("title", "milestone", "type", "deps", "acceptance", "test_notes", "files", "seq"):
                cur[k] = t[k]
            for k in ("contract", "consumes", "shared", "dep_reasons", "flag") + risk.RISK_FIELDS:
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
                **{k: t[k] for k in ("contract", "consumes", "shared", "dep_reasons", "flag") + risk.RISK_FIELDS if k in t},
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
        for d in parse_dep_reasons(t.get("dep_reasons")):
            if d not in t["deps"]:
                problems.append(f"{tid}: dep_reasons explains {d}, which is not in deps")
        if t["milestone"] not in store.milestones():
            problems.append(f"{tid}: milestone {t['milestone']} not declared")
        problems += risk.check_risk_fields(tid, t)
    problems += flag_problems(store)
    return tasks, (added_m, added_t, updated_t), rel_problems + exit_problems + problems + size_problems(store, milestones)


def milestone_size_cfg(state: dict) -> dict:
    return {**DEFAULT_AUTONOMY["milestone_size"], **((state.get("autonomy") or {}).get("milestone_size") or {})}


def milestone_load(store: Store, m: str) -> dict:
    """Size of a milestone as §4 counts it: planned tasks + the buffer slots it reserves + the cool-down tasks."""
    planned = sum(1 for v in store.tasks().values() if v["milestone"] == m and v.get("status") != "dropped"
                  and not str(v.get("source") or "").startswith(("issue:", "qa/", "hard_floor:")))
    buf = buffer_info(store, m)["capacity"] if planned else 0
    cd = {**DEFAULT_AUTONOMY["cooldown"], **(store.state.get("autonomy", {}).get("cooldown") or {})}
    cool = int(cd.get("max_tasks") or 0) if cd.get("enabled") and m != (store.milestone_order() or [None])[0] else 0
    return {"planned": planned, "buffer": buf, "cooldown": cool, "total": planned + buf + cool}


def size_problems(store: Store, milestones: dict) -> list[str]:
    """Milestones outside autonomy.milestone_size with no `size_reason:` (a warning, never a refusal)."""
    cfg = milestone_size_cfg(store.state)
    out = []
    for m, info in milestones.items():
        if info.get("size_reason") or exit_exempt(m, info["title"]):
            continue
        ld = milestone_load(store, m)
        if ld["planned"] and not cfg["min"] <= ld["total"] <= cfg["max"]:
            parts = f"{ld['planned']} planned + {ld['buffer']} buffer" + (f" + {ld['cooldown']} cool-down" if ld["cooldown"] else "")
            out.append(f"{m}: size {ld['total']} ({parts}) is outside {cfg['min']}-{cfg['max']}; split or merge it, "
                       "or add `size_reason: <why>` below its heading")
    return out


def cmd_sync_plan(store: Store, a: argparse.Namespace) -> None:
    store.load()
    plan_path = Path(a.plan) if a.plan else store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    text = plan_path.read_text(encoding="utf-8")
    mig = migrate_releases(store, text)
    notices: list[str] = []
    legacy = bool(store.state.get("needs_release_migration") or store.state.get("releases")
                  or any(v.get("status") != "todo" for v in store.tasks().values()))
    if mig and not legacy:
        text, groups = mig
        store.stage(plan_path, text)
        notices.append("plan.md had no `## R<n>`: every milestone now belongs to a planned release (" + " · ".join(groups)
                       + "); /dev-kit:plan groups them")
    elif mig:
        text, groups = mig
        store.stage(plan_path, text)
        adr = append_adr(store, "Migration to planned releases", [
            "- context: dev-kit 3.0 has one model: every milestone belongs to a planned release, and every release waits for the "
            "user's approval before production (conventions.md §19).",
            "- decision: " + "; ".join(groups) + ".",
            "- consequences: review plan is stale until the grouping is reviewed; the next passed plan review opens the "
            "Confirm plan checkpoint, and no milestone that has not started begins until it is confirmed."])
        revs = store.state.setdefault("reviews", {})
        if (revs.get("plan") or {}).get("verdict") == "pass":
            revs["plan"]["stale_reason"] = "planned releases added by the 3.0 migration"
        store.state.pop("needs_release_migration", None)
        notices.append(f"migrated to planned releases ({adr}): " + " · ".join(groups))
        notices.append("review the grouping with /dev-kit:review plan (now stale); when it passes, Confirm plan holds every "
                       "milestone not started yet until you confirm it (the review's question)")
        store.event("migration", transition="releases")
    if store.state.pop("needs_gitignore", None) and stage_gitignore(store):
        notices.append("updated .dev/.gitignore: machine-local files are ignored (your own rules were kept)")
        tracked = _git(store, "ls-files", "--", ".dev/telemetry.jsonl", ".dev/tips-seen.json", ".dev/costs") or ""
        if tracked:
            notices.append("still tracked by git, now ignored: " + ", ".join(tracked.split()) + " (`git rm --cached` them to stop versioning)")
    try:
        tasks, (added_m, added_t, updated_t), problems = sync_plan_text(store, text)
    except ValueError as e:
        fail(str(e))
    made = ensure_flags(store)
    if made:
        notices.append("release flags created (off): " + ", ".join(made))
    for name, f in sorted((store.state.get("flags") or {}).items()):
        if f.get("cleanup_task") == "pending":
            f.pop("cleanup_task")
            tid = flag_cleanup_task(store, f["release"])
            if tid:
                notices.append(f"{tid}: Remove flag {name} (its release is out)")
    store.save()
    record_baseline(store, tasks)
    store.log(f"sync-plan +{added_m} milestones, +{added_t} tasks, ~{updated_t} updated")
    print(f"synced: {added_m} new milestones, {added_t} new tasks, {updated_t} updated")
    for x in notices:
        print(f"migration: {x}")
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
        ahead = None
        if not ok:
            ahead = ahead_branch(store, m)
            if not ahead:
                return None, why
        if checkpoint_pending(store, "plan") and not any(v["milestone"] == m and v["status"] in ("done", "in_progress") for v in ts.values()):
            return None, f"{m} waits for the plan's confirmation (Needs you › Confirm plan, §19)"
        ready = [
            t for t, v in pending.items()
            if v["status"] == "todo" and all(ts.get(d, {}).get("status") == "done" for d in v["deps"])
            and (not ahead or ahead_ok(store, t, ahead))
        ]
        if ahead and not ready:
            return None, why + f" (nothing of {m} can run ahead on {ahead['branch']})"
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
    ahead = ahead_branch(store, m) if not store.gate_open_for(m)[0] else None
    ready = [t for t, v in ts.items() if v["milestone"] == m and v["status"] == "todo" and v.get("lane") != "hotfix"
             and all(ts.get(d, {}).get("status") == "done" for d in v["deps"]) and (not ahead or ahead_ok(store, t, ahead))]
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


PARALLEL_MIN, PARALLEL_MAX, PARALLEL_DEFAULT = 1, 6, 3  # implementers at once (`next --batch auto` = the default)


def cmd_next(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if getattr(a, "batch", None) is not None:
        if a.batch == "auto":
            a.batch = PARALLEL_DEFAULT
        else:
            try:
                a.batch = int(a.batch)
            except ValueError:
                fail("--batch takes a number or auto")
            if a.batch < 1:
                fail("--batch must be 1 or more")
        batch, why = pick_batch(store, a.milestone, a.batch)
        maybe = maybe_false_deps(store, a.milestone, batch) if len(batch) < a.batch else []
        hint = [f"maybe false dependency: {m['task']} waits only on {', '.join(m['waits_on'])} (in progress); review it before waiting" for m in maybe]
        if not batch:
            if a.json:
                print(json.dumps({"tasks": [], "reason": why, **({"maybe_false_deps": maybe} if maybe else {})}))
            else:
                print(f"no task available: {why}")
                print("\n".join(hint))
            sys.exit(3)
        if a.json:
            m0 = store.tasks()[batch[0]]["milestone"]
            ah = None if store.gate_open_for(m0)[0] else ahead_branch(store, m0)
            print(json.dumps({"tasks": [{"task": t, **store.tasks()[t]} for t in batch], "batch_size": a.batch, **({"maybe_false_deps": maybe} if maybe else {}),
                              **({"branch": ah["branch"], "ahead_of": ah["waits_for"]} if ah else {})}, ensure_ascii=False))
        else:
            for t in batch:
                v = store.tasks()[t]
                print(f"{t} [{v['milestone']}] ({v['type']}) {v['title']}" + (f" · files: {', '.join(v['files'])}" if v["files"] else ""))
            if hint:
                print("\n".join(hint))
        return
    tid, why = pick_next(store, a.milestone)
    if tid is None:
        if a.json:
            print(json.dumps({"task": None, "reason": why}))
        else:
            print(f"no task available: {why}")
        sys.exit(3)
    t = store.tasks()[tid]
    ah = None if store.gate_open_for(t["milestone"])[0] else ahead_branch(store, t["milestone"])
    if a.json:
        print(json.dumps({"task": tid, **t, **({"branch": ah["branch"], "ahead_of": ah["waits_for"]} if ah else {})}, ensure_ascii=False))
    else:
        print(f"{tid} [{t['milestone']}] ({t['type']}) {t['title']}" + (f" · ahead on {ah['branch']}" if ah else ""))
        if t["acceptance"]:
            print("  acceptance: " + " | ".join(t["acceptance"]))
        if t["test_notes"]:
            print("  test_notes: " + t["test_notes"])
        if t["files"]:
            print("  files: " + ", ".join(t["files"]))


def cmd_start(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if getattr(a, "resume", False):
        resume_task(store, a.task, a.force)
        return
    start_task(store, a.task, a.force)


def start_task(store: Store, tid: str, force: bool, keep_started: bool = False, via: str | None = None) -> dict | None:
    """in_progress, with the task's tier and route recorded. `keep_started` keeps the first start of a task resumed
    from an earlier attempt (its execution time counts from there); `via` names the command that started it."""
    a = argparse.Namespace(task=tid, force=force)
    t = store.task(a.task)
    if t["status"] in FINISHED:
        fail(f"{a.task} is already {t['status']}")
    if t["status"] == "in_progress":
        print(f"{a.task} already in_progress")
        return None
    others = [x for x in store.in_progress() if x != a.task]
    if others and not a.force:
        fail(f"{others[0]} is already in_progress; finish it or use --force for parallel work")
    unmet = [d for d in t["deps"] if store.tasks().get(d, {}).get("status") != "done"]
    if unmet and not a.force:
        fail(f"{a.task} has unmet dependencies: {', '.join(unmet)}")
    ok, why = store.gate_open_for(t["milestone"])
    ahead = None if ok or t.get("lane") == "hotfix" else ahead_branch(store, t["milestone"])
    if ahead and not ahead_ok(store, a.task, ahead):
        ahead = None
    if not ok and not ahead and not a.force and t.get("lane") != "hotfix":
        fail(f"cannot start {a.task}: {why}")
    if (checkpoint_pending(store, "plan") and t.get("lane") != "hotfix" and not any(
            v["milestone"] == t["milestone"] and v["status"] in ("done", "in_progress") for v in store.tasks().values())):
        fail(f"cannot start {a.task}: {t['milestone']} waits for the plan's confirmation (Needs you › Confirm plan, §19)")
    r = safe_route(store, a.task)
    t["status"] = "in_progress"
    issue_sync(store, t)
    t["started_at"] = (t.get("started_at") if keep_started else None) or now()
    t["blocked_reason"] = None
    if ahead:
        t["branch"] = ahead["branch"]
        t["ahead_of"] = ahead["waits_for"]
    if r:
        t["tier"] = {"rule": r["tier"], "score": r["score"], "source": r["source"], "rule_arm": r["arm"],
                     "arm": r["final_arm"], "routed": r["final_arm"] != r["arm"], "context": r["route"]["context"],
                     "signals": sorted({s["signal"] for s in r["reasons"]}), "at": now()}
    store.save()
    store.log(f"start {a.task} {t['title']}" + (f" tier={r['tier']} arm={r['final_arm']}" if r else "") + (f" (by {via})" if via else ""))
    store.event("task", task=a.task, transition="start", type=t.get("type"), milestone=t.get("milestone"), parallel=bool(a.force and others),
                tier=risk.tier_token(r["tier"]) if r else None, risk_score=r["score"] if r else None)
    if r:
        store.event("route", context=tel_ctx(r["route"]["context"]), rule_tier=risk.tier_token(r["tier"]),
                    arm=r["final_arm"].replace("/", "."), reason_code=r["route"]["reason_code"], explore=bool(r["route"]["explore"]))
    print(f"{a.task} in_progress: {t['title']}" + (f" · {r['final_model']} / {r['final_effort']} ({r['tier']})" if r else "")
          + (f" · started by {via}" if via else ""))
    if ahead:
        print(f"  ahead of {ahead['waits_for']}: work on branch {ahead['branch']} in its own worktree "
              f"(`pipeline worktree {ahead['branch']}`), never on the main branch; it is integrated when {ahead['waits_for']} "
              + ("is released" if ahead["kind"] == "release" else "passes its gate") + " (§19)")
    return r


def safe_route(store: Store, tid: str) -> dict | None:
    """Rule tier + router route of a task; a failure in the router never blocks a state transition."""
    try:
        return router.route_task(store, tid)
    except Exception as e:  # noqa: BLE001
        print(f"note: router unavailable ({type(e).__name__}); the agent's base model applies", file=sys.stderr)
        return None


def safe_observe(store: Store, tid: str, outcome: str) -> None:
    """Fast feedback loop of the router (dev_router.py observe); never blocks a state transition."""
    if risk.model_policy(store.state)["router"].get("mode") == "off":
        return
    try:
        r = router.observe(store, tid, outcome)
        if r.get("bump") and outcome != "done":
            print(f"router: {r['context']} failed twice in a row; one tier up for the rest of {r['bump']['milestone']}")
    except Exception as e:  # noqa: BLE001
        print(f"note: router observe skipped ({type(e).__name__})", file=sys.stderr)


def tel_ctx(ctx: str) -> str:
    return ctx.replace("+", "-plus")[:40]


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
        fail(f"{a.task} is {t['status']}, not in_progress: run `start {a.task}` first (`start {a.task} --resume` takes over an "
             "earlier attempt). --force only corrects the record of work already committed")
    t["status"] = "done"
    t["done_at"] = now()
    if a.commit:
        t["commit"] = a.commit
    issue_sync(store, t)
    store.save()
    if t.get("scope_after_freeze") and t.get("files"):
        drop_ledger_files(store, t["files"])
    rs = t.get("resumed_from") or {}
    if rs.get("worktree"):
        why = remove_worktree(store, Path(rs["worktree"]), rs.get("branch"), rs.get("applied"), rs.get("base_sha"))
        print(f"note: the earlier attempt's worktree {rs['worktree']} was kept ({why})" if why
              else f"earlier attempt's worktree {rs['worktree']} and branch {rs.get('branch')} removed")
    store.log(f"done {a.task} commit={a.commit or '-'}")
    store.event("task", task=a.task, transition="done", type=t.get("type"), milestone=t.get("milestone"))
    safe_observe(store, a.task, "done")
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
    if a.blocked_by:
        if a.blocked_by not in (store.state.get("issues") or {}):
            fail(f"unknown issue {a.blocked_by}")
        t["blocked_by"] = a.blocked_by  # paused until the replan of that scope change (§15)
    if not a.reason:
        if not a.blocked_by:
            fail("block needs --reason")
        a.reason = f"waiting for the replan of {a.blocked_by}"
    t["status"] = "blocked"
    t["blocked_reason"] = a.reason
    t["blocked_count"] = int(t.get("blocked_count", 0) or 0) + 1
    store.save()
    store.log(f"block {a.task}: {a.reason}")
    store.event("task", task=a.task, transition="block", type=t.get("type"), milestone=t.get("milestone"))
    safe_observe(store, a.task, "blocked")
    print(f"{a.task} blocked: {a.reason}")
    queue_notice(store, f"dev-kit · {a.task} blocked · {next_command(store)}")


def gate_tasks(store: "Store", m: str) -> list[dict]:
    """Tasks that count for a milestone's completion: not dropped, and in a frozen milestone not paused by a scope
    change (blocked_by an issue) until the replan decides (§15)."""
    fz = frozen(store, m)
    return [v for v in store.tasks().values() if v["milestone"] == m and v["status"] != "dropped"
            and not (fz and v["status"] == "blocked" and v.get("blocked_by"))]


def affected_tasks(store: Store, acs: list[str]) -> list[dict]:
    """Pending tasks whose acceptance cites one of these ACs: what a scope change reaches now (§15)."""
    want = {x.strip().upper() for x in acs if x.strip()}
    out = []
    for tid, v in sorted(store.tasks().items(), key=lambda kv: int(kv[0][2:])):
        if v["status"] not in ("todo", "in_progress", "blocked"):
            continue
        cited = set(re.findall(r"\bAC-\d+\b", " ".join(map(str, v.get("acceptance") or [])) + " " + str(v.get("title") or ""), re.I))
        hit = sorted({c.upper() for c in cited} & want, key=lambda c: int(c.split("-")[1]))
        if hit:
            out.append({"task": tid, "title": v["title"], "status": v["status"], "milestone": v["milestone"], "acs": hit,
                        "frozen": frozen(store, v["milestone"])})
    return out


def cmd_affected(store: Store, a: argparse.Namespace) -> None:
    store.load()
    acs = [x for x in re.split(r"[,\s]+", a.acs or "") if x]
    if not acs or not all(re.fullmatch(r"AC-\d+", x, re.I) for x in acs):
        fail("--acs needs AC ids, e.g. AC-4,AC-7")
    rows = affected_tasks(store, acs)
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no pending task cites " + ", ".join(acs))
        return
    for r in rows:
        print(f"{r['task']} {r['status']} {r['milestone']}{' (frozen)' if r['frozen'] else ''} · {', '.join(r['acs'])} · {r['title']}")
    print(f"{len(rows)} task(s): pause them until the replan (recommended: `block T-nnn --blocked-by I-nnn`) or continue")


# ---------------------------------------------------------------- challenge of blocking findings (conventions.md §7)
# A different role that covers the finding's dimension; None = the same role on a model of another family.
CHALLENGER_FOR = {"code": "test-auditor", "security": "code-reviewer", "tests": "code-reviewer", "spec": "test-auditor",
                  "performance": "code-reviewer", "data": "code-reviewer", "operations": "code-reviewer",
                  "dependencies": "security-auditor", "a11y": "visual-reviewer", "visual": "a11y-auditor",
                  "ux": "a11y-auditor", "copy": "usability-auditor", "docs": None, "design": None, "requirements": None}
OTHER_FAMILY = {"opus": "sonnet", "sonnet": "opus", "haiku": "sonnet", "fable": "opus"}
CHALLENGE_VERDICTS = ("agree", "dispute", "refine")


def _family(model: object) -> str:
    m = str(model or "").lower()
    return next((f for f in OTHER_FAMILY if f in m), m or "inherit")


def finding_of(store: Store, m: str, fid: str) -> dict:
    path = store.dev / "qa" / m / "findings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail(f"no consolidated findings at {path} (run dev_score.py consolidate first)")
    items = (data.get("findings") or []) + (data.get("disputed") or []) if isinstance(data, dict) else data
    f = next((x for x in items if isinstance(x, dict) and x.get("id") == fid), None)
    if f is None:
        fail(f"{fid} is not in {path}")
    return f


def author_model(store: Store, m: str, auditor: str) -> str:
    """The model the auditor ran on this round: the session log's agent_spawn, else its frontmatter."""
    try:
        for e in reversed(tel.read_events(store.dev)[0]):
            if e["event"] == "agent_spawn" and e.get("agent") == auditor and e.get("scope") == m and e.get("model"):
                return str(e["model"])
    except (OSError, ValueError):
        pass
    import dev_agent_hook
    return dev_agent_hook.agent_meta(auditor).get("model") or "inherit"


def pick_challenger(store: Store, m: str, f: dict) -> dict:
    import dev_agent_hook
    auditor = str(f.get("auditor") or "")
    amodel = author_model(store, m, auditor)
    role = CHALLENGER_FOR.get(str(f.get("dimension") or ""))
    if role and role != auditor:
        meta = dev_agent_hook.agent_meta(role)
        return {"agent": role, "model": meta.get("model") or "inherit", "effort": meta.get("effort") or "high",
                "why": f"another role covering {f.get('dimension')}"}
    model = OTHER_FAMILY.get(_family(amodel), "opus" if _family(amodel) != "opus" else "sonnet")
    return {"agent": auditor, "model": model, "effort": "high", "why": f"same role on another model family ({amodel} -> {model})"}


def cmd_challenger(store: Store, a: argparse.Namespace) -> None:
    """Who challenges a critical/high finding (§7): never the author's agent+model."""
    store.load()
    f = finding_of(store, a.milestone, a.finding)
    ch = pick_challenger(store, a.milestone, f)
    out = {"finding": a.finding, "dimension": f.get("dimension"), "severity": f.get("severity"),
           "author": {"agent": f.get("auditor"), "model": author_model(store, a.milestone, str(f.get("auditor") or ""))},
           "challenger": ch, "output": f".dev/qa/{a.milestone}/challenges/{a.finding}.json"}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{a.finding} ({f.get('severity')} {f.get('dimension')}, by {f.get('auditor')}): challenge with {ch['agent']} on "
              f"{ch['model']} / {ch['effort']} ({ch['why']}) · Output file: {out['output']}")


def files_fp(store: Store, files: list[str]) -> str:
    h = hashlib.sha256()
    for f in sorted(set(files)):
        p = store.root / f
        h.update(f.encode() + b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:16]


def challenges_path(store: Store, m: str) -> Path:
    return store.dev / "qa" / m / "challenges.json"


def cmd_challenge(store: Store, a: argparse.Namespace) -> None:
    """Record a challenger's answer (§7): {"finding": "F-003", "verdict": "agree|dispute|refine", "evidence": "<command and
    output, or file:line>", "refined": {"severity": "medium"}, "challenger": "<agent>", "model": "<model>"}. Stored in
    .dev/qa/<M>/challenges.json with a fingerprint of the cited files; dev_score.py --challenges applies it while
    those files are unchanged. A disputed critical security finding keeps blocking and asks the user."""
    store.load()
    if a.milestone not in store.milestones() and a.milestone != "release":
        fail(f"unknown milestone {a.milestone}")
    try:
        raw = json.loads(Path(a.from_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read the challenge: {e}")
    if not isinstance(raw, dict):
        fail("the challenge must be a JSON object")
    fid = str(raw.get("finding") or "")
    f = finding_of(store, a.milestone, fid)
    verdict = raw.get("verdict")
    if verdict not in CHALLENGE_VERDICTS:
        fail(f"verdict must be one of {', '.join(CHALLENGE_VERDICTS)}")
    evidence = str(raw.get("evidence") or "").strip()
    if len(evidence) < 8:
        fail("evidence is required: the command and a summary of its output, or file:line")
    refined = raw.get("refined") if isinstance(raw.get("refined"), dict) else {}
    if verdict == "refine" and str(refined.get("severity") or "") not in ("critical", "high", "medium", "low"):
        fail("refine needs refined.severity (critical, high, medium or low)")
    agent, model = str(raw.get("challenger") or ""), str(raw.get("model") or "")
    amodel = author_model(store, a.milestone, str(f.get("auditor") or ""))
    if not agent:
        fail("challenger is required (the agent that answered)")
    if agent == f.get("auditor") and _family(model) == _family(amodel):
        fail(f"the challenger cannot be the author's own agent and model ({agent} on {amodel}); use `challenger {a.milestone} {fid}`")
    files = [x for x in ([f.get("file")] + list(f.get("files") or [])) if x]
    rec = {"finding": fid, "original_id": f.get("original_id") or fid, "auditor": f.get("auditor"), "dimension": f.get("dimension"),
           "severity": f.get("severity"), "title": f.get("title"), "file": f.get("file"), "line": f.get("line"),
           "verdict": verdict, "evidence": evidence[:2000], "refined": refined or None, "challenger": agent, "model": model or None,
           "author_evidence": str(f.get("evidence") or "")[:2000] or None, "files": files, "files_fp": files_fp(store, files), "at": now()}
    qid = None
    if verdict == "dispute" and f.get("dimension") == "security" and f.get("severity") == "critical":
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            cmd_add_question(store, argparse.Namespace(
                text=f"Disputed security finding {fid} ({f.get('title')}): keep the block? Challenger's evidence: {evidence[:300]}",
                skill="qa", assumption="keep blocking (recommended)", impact="a real critical security flaw would ship",
                options="keep blocking|release it", recommended="keep blocking"))
        qid = buf.getvalue().strip()
        rec["question"] = qid
    path = challenges_path(store, a.milestone)
    try:
        allc = json.loads(store.read_text(path)) if store.file_exists(path) else {}
    except (OSError, json.JSONDecodeError):
        allc = {}
    allc[fid] = rec
    store.stage(path, json.dumps(allc, indent=2, ensure_ascii=False) + "\n")
    store.save()
    store.event("challenge", scope=a.milestone, finding=fid, auditor=tel.scope_token(f.get("auditor") or "-"),
                challenger=tel.scope_token(agent), model=tel.scope_token(model) if model else None, verdict=verdict,
                dimension=f.get("dimension"), severity=f.get("severity"))
    store.log(f"challenge {a.milestone} {fid}: {verdict} by {agent}")
    effect = {"agree": "stays blocking (fix task)", "refine": f"rewritten as {refined.get('severity')}",
              "dispute": "not scored and no fix task; listed under Contested (counts toward the debt cap)"}[verdict]
    if qid:
        effect = f"still blocking: a disputed critical security finding is the user's decision ({qid} in Needs you)"
    print(f"{a.milestone} {fid}: {verdict} · {effect}")


# ---------------------------------------------------------------- delivery forecast (conventions.md §13)
FORECAST_MIN = 2  # measured milestones needed before a forecast is shown


def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def measured_flows(store: Store, last: int = 3) -> list[dict]:
    """flow.json of the last closed milestones with a measured cycle (pre-3.0 ones have none)."""
    out = []
    for m in store.milestone_order():
        f = _flow_doc(store, m)
        if f and f.get("tasks") and f.get("cycle_time_s"):
            out.append(f)
    return out[-last:]


def _flow_doc(store: Store, m: str) -> dict | None:
    try:
        f = json.loads((store.dev / "qa" / m / "flow.json").read_text(encoding="utf-8"))
        return f if isinstance(f, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def forecast(store: Store) -> dict:
    """Probable finish (P50) and a late finish (P85) per open milestone and per release not released, with the cost to
    finish: pace = cycle time per task of the last 3 measured milestones, plus the mean wait for a person (it is a
    calendar forecast). Needs FORECAST_MIN measured milestones."""
    flows = measured_flows(store)
    if len(flows) < FORECAST_MIN:
        return {"available": False, "measured": len(flows), "reason": f"forecast available after {FORECAST_MIN} measured milestones"}
    cyc = [f["cycle_time_s"] / f["tasks"] for f in flows]
    work = [float(f.get("working_time_s") or 0) / f["tasks"] for f in flows]
    wait = [float(f.get("human_wait_s") or 0) for f in flows]
    cost = [float(f["cost_per_task"]) for f in flows if f.get("cost_per_task") is not None]
    pace = {"p50": statistics_median(cyc), "p85": _pct(cyc, 0.85)}
    wait_m = sum(wait) / len(wait)
    cpt = {"p50": statistics_median(cost), "p85": _pct(cost, 0.85)} if cost else None
    start = datetime.now(timezone.utc)
    if os.environ.get("DEV_KIT_NOW"):
        start = datetime.fromisoformat(now().replace("Z", "+00:00"))
    ts = store.tasks()
    ms_rows, clock = [], {"p50": 0.0, "p85": 0.0}
    for m in store.milestone_order():
        mm = store.milestones()[m]
        live = [v for v in ts.values() if v["milestone"] == m and v["status"] != "dropped"]
        if not live or mm.get("gate") in ("passed", "skipped"):
            continue
        left = sum(1 for v in live if v["status"] not in FINISHED)
        for k in clock:  # milestones run one after the other: each one starts where the previous ends
            clock[k] += left * pace[k] + wait_m
        ms_rows.append({"milestone": m, "release": release_of(store, m), "tasks_left": left,
                        **{f"finish_{k}": (start + timedelta(seconds=clock[k])).strftime("%Y-%m-%dT%H:%M:%SZ") for k in clock},
                        **({f"cost_{k}_usd": round(left * cpt[k], 2) for k in cpt} if cpt else {})})
    rel_rows = []
    for r in release_plan_status(store):
        if r["status"] == "released":
            continue
        mine = [x for x in ms_rows if x["release"] == r["id"]]
        if not mine:
            continue
        rel_rows.append({"release": r["id"], "tasks_left": sum(x["tasks_left"] for x in mine),
                         "finish_p50": mine[-1]["finish_p50"], "finish_p85": mine[-1]["finish_p85"],
                         **({"cost_p50_usd": round(sum(x.get("cost_p50_usd", 0) for x in mine), 2),
                             "cost_p85_usd": round(sum(x.get("cost_p85_usd", 0) for x in mine), 2)} if cpt else {})})
    return {"available": True, "measured": len(flows), "basis": [f["milestone"] for f in flows],
            "pace_s_per_task": {k: round(v) for k, v in pace.items()},
            "work_s_per_task": round(statistics_median(work)), "wait_s_per_milestone": round(wait_m),
            "cost_per_task_usd": {k: round(v, 4) for k, v in cpt.items()} if cpt else None,
            "milestones": ms_rows, "releases": rel_rows}


def statistics_median(xs: list[float]) -> float:
    return _pct(xs, 0.5)


def forecast_line(fc: dict) -> str:
    if not fc.get("available"):
        return f"Forecast: {fc['reason']}"
    parts = []
    for r in fc["releases"][:2]:
        cost = f" · ~US$ {r['cost_p50_usd']:.0f}–{r['cost_p85_usd']:.0f} to finish" if "cost_p50_usd" in r else ""
        parts.append(f"{r['release']} probable {r['finish_p50'][:10]}, by {r['finish_p85'][:10]}{cost}")
    if not parts and fc["milestones"]:
        x = fc["milestones"][0]
        parts.append(f"{x['milestone']} probable {x['finish_p50'][:10]}, by {x['finish_p85'][:10]}")
    return "Forecast: " + (" · ".join(parts) if parts else "nothing open")


def cmd_forecast(store: Store, a: argparse.Namespace) -> None:
    store.load()
    fc = forecast(store)
    print(json.dumps(fc, indent=2) if a.json else forecast_line(fc))


# ---------------------------------------------------------------- pipeline: work ahead while a person decides (§19)
def _flow_field(store: Store, m: str, key: str) -> object:
    try:
        return json.loads((store.dev / "qa" / m / "flow.json").read_text(encoding="utf-8")).get(key)
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def record_wait(store: Store, kind: str, since: object, scope: object) -> None:
    """How long something waited for a person in Needs you (§19, `human_wait_s`): a question, a permission, a
    checkpoint, a release approval. Logged once, when the answer arrives; flow.json and feedback sum it."""
    try:
        secs = _secs_between(str(since), now()) if since else None
    except Exception:  # noqa: BLE001
        secs = None
    if secs is None or secs < 0:
        return
    store.event("human_wait", kind=kind, scope=tel.scope_token(scope or "-"), duration_s=round(secs))


def human_wait(events: list[dict], scopes: set) -> int | None:
    xs = [float(e.get("duration_s") or 0) for e in events if e["event"] == "human_wait" and e.get("scope") in scopes]
    return round(sum(xs)) if xs else 0


def pipeline_cfg(store: Store) -> dict:
    return {**DEFAULT_AUTONOMY["pipeline"], **((store.state.get("autonomy") or {}).get("pipeline") or {})}


def ahead_branch(store: Store, m: str) -> dict | None:
    """Whether milestone m may run ahead, and on which branch: {kind, branch, waits_for}. A release ahead: every
    earlier release not released is waiting for approval (or approved and deploying), at most `releases_ahead` of
    them, and m's own milestones before it are closed. A milestone ahead: the milestone right before m is frozen for
    QA (its tasks are done), `milestone_overlap` is on, and everything before that one is closed."""
    cfg = pipeline_cfg(store)
    rel = release_of(store, m)
    plan = store.state.get("release_plan") or []
    ms, ts = store.milestones(), store.tasks()

    def closed(x: str) -> bool:
        return ms[x].get("gate") in ("passed", "skipped") or not any(v["milestone"] == x and v["status"] != "dropped" for v in ts.values())

    order = store.milestone_order()
    before = order[:order.index(m)] if m in order else []
    if rel:
        waiting = []
        for r in plan:
            if r["id"] == rel:
                break
            st = release_status(store, r["id"])["status"]
            if st == "released":
                continue
            if st not in ("awaiting_approval", "deploying_prod"):
                waiting = None
                break
            waiting.append(r["id"])
        if waiting:
            if len(waiting) > int(cfg["releases_ahead"]):
                return None
            own = [x for x in before if release_of(store, x) == rel]
            if all(closed(x) for x in own):
                return {"kind": "release", "branch": f"dev-kit/{rel}", "waits_for": waiting[-1]}
            return None
        if waiting is None:
            return None
    if not cfg["milestone_overlap"] or not before:
        return None
    prev = before[-1]
    if not frozen(store, prev) or closed(prev) or not all(closed(x) for x in before[:-1]):
        return None
    if release_of(store, prev) != rel:
        return None  # across releases only the release rule applies
    return {"kind": "milestone", "branch": f"dev-kit/{m}", "waits_for": prev}


def ahead_ok(store: Store, tid: str, ahead: dict) -> bool:
    """A task may run ahead of a milestone in QA only if it shares nothing with it: no dependency on its tasks, no file
    it touched, not `shared`, and not sent back by one of its fixes. Ahead of a release every task of the
    milestone may run (it is on its own branch until the release ships)."""
    t = store.tasks()[tid]
    if t.get("redo_after") and (store.milestones().get(t["redo_after"]) or {}).get("gate") not in ("passed", "skipped"):
        return False
    if ahead["kind"] == "release":
        return True
    prev = ahead["waits_for"]
    theirs = {k: v for k, v in store.tasks().items() if v["milestone"] == prev and v["status"] != "dropped"}
    if t.get("shared") or any(d in theirs for d in t.get("deps") or []):
        return False
    mine = [f.strip("/") for f in t.get("files") or [] if f.strip()]
    if not mine:
        return False
    used = [f.strip("/") for v in theirs.values() for f in v.get("files") or [] if f.strip()]
    return not any(x == y or x.startswith(y + "/") or y.startswith(x + "/") for x in mine for y in used)


def ahead_tasks(store: Store, branch: str | None = None) -> dict:
    return {k: v for k, v in store.tasks().items() if v.get("branch") and (branch is None or v["branch"] == branch)}


def send_back_ahead(store: Store, m: str, files: list[str], why: str) -> list[str]:
    """A fix in milestone m that touches a file of a task run ahead of it: that task goes back to todo (its work stays on
    the branch to reuse) and is redone after m's gate (§19)."""
    fs = [f.strip("/") for f in files if f and f.strip()]
    out = []
    for tid, v in ahead_tasks(store).items():
        if v.get("ahead_of") != m or v["status"] not in ("done", "in_progress"):
            continue
        mine = [f.strip("/") for f in v.get("files") or [] if f.strip()]
        if any(x == y or x.startswith(y + "/") or y.startswith(x + "/") for x in mine for y in fs):
            v.update(status="todo", redo_after=m, blocked_reason=None, done_at=None)
            v["redo_note"] = f"{why}: redo after the gate of {m}; the earlier work is on {v['branch']}"
            out.append(tid)
            store.event("task", task=tid, transition="reopen", type=v.get("type"), milestone=v.get("milestone"))
    return out


def pause_ahead(store: Store, rid: str) -> list[str]:
    """A rejected release: the work of later releases started ahead stops until it is submitted again (§19)."""
    out = []
    for tid, v in ahead_tasks(store).items():
        if v.get("ahead_of") == rid and v["status"] == "in_progress":
            v.update(status="blocked", blocked_reason=f"pipeline: {rid} was rejected; this resumes when it is submitted again",
                     pipeline_paused=rid)
            out.append(tid)
    return out


def resume_ahead(store: Store, rid: str) -> list[str]:
    out = []
    for tid, v in store.tasks().items():
        if v.get("pipeline_paused") == rid and v["status"] == "blocked":
            v.update(status="in_progress", blocked_reason=None)
            v.pop("pipeline_paused", None)
            out.append(tid)
    return out


def main_branch(store: Store) -> str:
    for b in ("main", "master"):
        if _git(store, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}") is not None:
            return b
    return _git(store, "rev-parse", "--abbrev-ref", "HEAD") or "main"


def work_branch(store: Store) -> str:
    """The branch the project builds on (§17): autonomy.git.base_branch, else the branch checked out in the main
    checkout, else main/master. Worktrees start from it and the pipeline integrates into it, so a project that works
    on another branch than main never gets a worktree of main."""
    br = (((store.state.get("autonomy") or {}).get("git") or {}).get("base_branch") or "").strip()
    if br:
        return br
    cur = _git(store, "rev-parse", "--abbrev-ref", "HEAD")
    if cur and cur != "HEAD" and not re.fullmatch(r"dev-kit/.+", cur):
        return cur
    return main_branch(store)


def cmd_pipeline(store: Store, a: argparse.Namespace) -> None:
    """status [--json] | worktree BRANCH (create or show the worktree of a branch ahead) | integrate BRANCH (rebase it on
    the main branch once what it waited for is released or gated, then fast-forward the main branch to it)."""
    store.load()
    if a.action == "status":
        rows = []
        for m in store.milestone_order():
            if store.gate_open_for(m)[0]:
                continue
            ah = ahead_branch(store, m)
            if ah:
                rows.append({"milestone": m, **ah, "tasks": sorted(k for k, v in store.tasks().items() if v["milestone"] == m
                                                                    and v["status"] == "todo" and ahead_ok(store, k, ah))})
        branches = sorted({v["branch"] for v in ahead_tasks(store).values()})
        out = {"config": pipeline_cfg(store), "work_branch": work_branch(store), "ahead": rows, "branches": branches,
               "paused": sorted(k for k, v in store.tasks().items() if v.get("pipeline_paused")),
               "redo": sorted(k for k, v in store.tasks().items() if v.get("redo_after") and v["status"] == "todo")}
        if a.json:
            print(json.dumps(out, indent=2))
        else:
            for r in rows:
                print(f"{r['milestone']} can run ahead of {r['waits_for']} on {r['branch']}: {', '.join(r['tasks']) or 'no task yet'}")
            if not rows:
                print("nothing can run ahead now")
            for b in branches:
                print(f"branch {b}: {', '.join(sorted(k for k, v in ahead_tasks(store, b).items()))}")
        return
    br = a.branch or ""
    if not re.fullmatch(r"dev-kit/(R\d+|M\d+(?:\.\d+)?)", br):
        fail("the branch is dev-kit/R<n> or dev-kit/M<n>")
    target = br.split("/", 1)[1]
    wt = store.dev / "run" / "worktrees" / br.replace("/", "-")
    main = work_branch(store)
    if a.action == "worktree":
        if wt.exists():
            print(str(wt))
            return
        exists = _git(store, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}") is not None
        args = ["worktree", "add", str(wt), br] if exists else ["worktree", "add", "-b", br, str(wt), main]
        if _git(store, *args) is None:
            fail(f"git worktree add failed for {br}")
        print(str(wt))
        return
    # integrate
    if target.startswith("R"):
        waits = sorted({v.get("ahead_of") for v in ahead_tasks(store, br).values() if v.get("ahead_of")})
        open_ = [r for r in waits if release_status(store, r)["status"] != "released"]
        if open_:
            fail(f"{br} waits for {', '.join(open_)} to be released")
    else:
        prev = sorted({v.get("ahead_of") for v in ahead_tasks(store, br).values() if v.get("ahead_of")})
        open_ = [m for m in prev if store.milestones()[m].get("gate") not in ("passed", "skipped")]
        if open_:
            fail(f"{br} waits for the gate of {', '.join(open_)}")
    if _git(store, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}") is None:
        fail(f"no branch {br}")
    old_base = _git(store, "merge-base", main, br)
    cwd = wt if wt.exists() else store.root
    if wt.exists():
        r = subprocess.run(["git", "-C", str(wt), "rebase", main], capture_output=True, text=True)
    else:
        r = subprocess.run(["git", "-C", str(store.root), "rebase", main, br], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", str(cwd), "rebase", "--abort"], capture_output=True, text=True)
        if not wt.exists():
            subprocess.run(["git", "-C", str(store.root), "checkout", "-q", main], capture_output=True, text=True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            cmd_add_question(store, argparse.Namespace(
                text=f"Rebasing {br} on {main} conflicts: resolve it by hand, or redo its tasks on {main}?", skill="implement",
                assumption="redo its tasks on the main branch", impact="the work ahead may be lost if redone",
                options="resolve by hand|redo the tasks", recommended="resolve by hand"))
        tel.safe_emit(store.dev, "error", {"code": "merge_conflict"})
        print(f"conflict rebasing {br} on {main}: {buf.getvalue().strip()} in Needs you; nothing was changed")
        store.event("pipeline", transition="conflict")
        store.exit_code = 1
        return
    new_base = _git(store, "rev-parse", main)
    changed = (_git(store, "diff", "--name-only", f"{old_base}..{new_base}") or "").split() if old_base else []
    dropped = drop_ledger_files(store, changed) if changed else 0
    # milestones of the branch already gated: re-run QA on the delta only (§18), since their base moved
    requal = []
    if changed:
        for mm in sorted({v["milestone"] for v in ahead_tasks(store, br).values()}, key=mkey):
            if store.milestones()[mm].get("gate") == "passed":
                store.milestones()[mm].update(gate="pending", requalify=f"{br} rebased on {main}")
                requal.append(mm)
    cur = _git(store, "rev-parse", "--abbrev-ref", "HEAD")
    if cur == main:
        ff = subprocess.run(["git", "-C", str(store.root), "merge", "--ff-only", "-q", br], capture_output=True, text=True)
        merged = ff.returncode == 0
    else:
        merged = False
    for v in ahead_tasks(store, br).values():
        v["integrated"] = now()
    store.save()
    store.log(f"pipeline integrate {br} on {main}" + (f": {len(changed)} files changed below it" if changed else ""))
    store.event("pipeline", transition="integrate", requalify=len(requal))
    print(f"{br} rebased on {main}" + (f" and {main} fast-forwarded to it" if merged else f"; merge it into {main} (fast-forward)")
          + (f" · ledger: {dropped} unit(s) invalidated" if dropped else "")
          + (f" · re-run qa on the delta: {', '.join(requal)}" if requal else ""))


# ---------------------------------------------------------------- rounds in a child session (conventions.md §17)
ROUND_SKILLS = ("qa", "implement")
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk")


def round_snapshot(store: Store, scope: str) -> dict:
    ts = store.tasks()
    return {"done": {t for t, v in ts.items() if v["status"] == "done"}, "tasks": set(ts),
            "qa_runs": int((store.milestones().get(scope) or {}).get("qa_runs", 0))}


def round_summary(store: Store, skill: str, scope: str, before: dict, rc: int, dur: float, log: Path) -> dict:
    """What the parent session reads instead of the child's reports: counts, ids and paths only."""
    store.state = {}
    store.load()
    ms = store.milestones().get(scope) or {}
    ts = store.tasks()
    new = sorted(set(ts) - before["tasks"], key=lambda t: int(t[2:]))
    fixes = [t for t in new if ts[t].get("type") == "fix"]
    done = sorted({t for t, v in ts.items() if v["status"] == "done"} - before["done"], key=lambda t: int(t[2:]))
    sc_path = store.dev / "qa" / scope / "scores.json"
    sc = {}
    if skill == "qa":
        try:
            sc = json.loads(sc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sc = {}
    try:
        deferred = len(json.loads((store.dev / "qa" / scope / "findings.json").read_text(encoding="utf-8")).get("deferred") or [])
    except (OSError, json.JSONDecodeError, AttributeError):
        deferred = None
    gate = ms.get("gate")
    if rc != 0:
        verdict = "error"
    elif skill == "qa":
        verdict = "pass" if gate == "passed" else ("fail" if int(ms.get("qa_runs", 0)) > before["qa_runs"] or sc else "unknown")
    else:
        left = [t for t, v in ts.items() if v["milestone"] == scope and v["status"] not in FINISHED]
        verdict = "done" if not left else ("blocked" if any(ts[t]["status"] == "blocked" for t in left) else "partial")
    cost = None
    try:
        cost = (json.loads((store.dev / "costs" / "summary.json").read_text(encoding="utf-8")).get("total") or {}).get("usd")
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    report = store.dev / "qa" / scope / "report.md"
    return {"skill": skill, "scope": scope, "verdict": verdict, "exit_code": rc, "score": ms.get("score") if skill == "qa" else None,
            "fix_tasks": fixes, "tasks_done": done, "deferred": deferred, "gate": gate, "cost": cost,
            "duration_s": round(dur, 1), "report": str(report.relative_to(store.root)) if report.exists() else None,
            "log": str(log.relative_to(store.root)), "next": next_command(store)}


def headless_allowed_tools(store: Store, kit: Path | None = None) -> list[str]:
    """What a headless session of the kit may run without asking (§17): the kit's own scripts, the git commands of
    the orchestrator, `cd`, the project's commands of architecture.md §8 (tests, lint, type-check) and the safe set
    of audits (dev_perms.safe_rules). Everything else still goes to Needs you."""
    kit = kit or Path(__file__).resolve().parents[3]
    out = [f"Bash(python3 -I *{kit}/skills/*core/scripts/dev_*.py*)", "Bash(cd *)"]
    for verb in ("status", "diff", "log", "show", "rev-parse", "add", "commit", "check-ignore", "ls-files"):
        out += [f"Bash(git {verb}*)", f"Bash(git -C * {verb}*)"]
    try:
        arch = (store.dev / "architecture.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        arch = ""
    for _, cmd in _section_rows(arch, r"^## 8\b.*$"):
        c = cmd.strip().strip("`").strip()
        if c and c not in ("-", "n/a") and not re.search(r"[;&|<>`$()]", c) and len(c) <= 200:
            out.append(f"Bash({c}*)")
    import dev_perms  # the kit's safe set for audits: read-only inspection and timed scratch measurements
    out += dev_perms.safe_rules()
    return list(dict.fromkeys(out))


AUDITOR_AGENTS = ("a11y-auditor", "code-reviewer", "copy-reviewer", "data-reviewer", "deps-auditor", "design-reviewer",
                  "docs-reviewer", "ops-reviewer", "performance-auditor", "requirements-reviewer", "security-auditor",
                  "spec-tracer", "test-auditor", "usability-auditor", "visual-reviewer")


def _iso_age(iso: object, ref: float | None = None) -> float | None:
    try:
        t = datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None
    return max(0.0, (ref or time.time()) - t)


def watchdog(store: Store) -> dict:
    wd = quality_cfg(store).get("watchdog") or {}
    out = {"auditor_budget_min": int(wd.get("auditor_budget_min", 30)), "stall_min": int(wd.get("stall_min", 20))}
    with contextlib.suppress(ValueError):
        if os.environ.get("DEV_KIT_STALL_S"):
            out["stall_s"] = max(1.0, float(os.environ["DEV_KIT_STALL_S"]))
    out.setdefault("stall_s", out["stall_min"] * 60.0)
    return out


def qa_auditors(store: Store, scope: str, since: float | None = None) -> list[dict]:
    """The auditors of a milestone's current QA round and where each one is (conventions.md §17): `delivered` (its
    raw file was written after it started, or it ended), `working` (a tool call within stall_min), `stalled`
    (silent for longer, or past its time budget plus stall_min). From the hooks' records: agent-slots.json (start),
    agent-beats.json (last tool call), agents.jsonl (end). Only the latest start of each auditor counts."""
    run = store.dev / "run"
    slots = _read_json(run / "agent-slots.json")
    beats = _read_json(run / "agent-beats.json")
    ended = set()
    with contextlib.suppress(OSError):
        for line in (run / "agents.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                r = json.loads(line)
                if r.get("event") == "agent_stop" and r.get("agent_id"):
                    ended.add(str(r["agent_id"]).lower())
    wd = watchdog(store)
    ref = time.time()
    floor = since if since is not None else ref - 12 * 3600
    latest: dict[str, tuple[str, dict]] = {}
    for aid, b in slots.items():
        if not isinstance(b, dict) or b.get("scope") != scope or b.get("agent") not in AUDITOR_AGENTS:
            continue
        age = _iso_age(b.get("at"), ref)
        if age is None or ref - age < floor:
            continue
        cur = latest.get(b["agent"])
        if not cur or str(b.get("at")) >= str(cur[1].get("at")):
            latest[b["agent"]] = (aid, b)
    raw = store.dev / "qa" / scope / "raw"
    out = []
    for agent, (aid, b) in sorted(latest.items()):
        started = ref - (_iso_age(b.get("at"), ref) or 0.0)
        files = [f for f in raw.glob(f"{agent}*.json") if f.stat().st_mtime >= started - 1] if raw.is_dir() else []
        bt = beats.get(aid) if isinstance(beats.get(aid), dict) else {}
        idle = _iso_age(bt.get("last") or b.get("at"), ref) or 0.0
        elapsed = ref - started
        if files or aid.lower() in ended:
            status = "delivered" if files else "ended_without_result"
        elif idle > wd["stall_s"] or elapsed > wd["auditor_budget_min"] * 60 + wd["stall_s"]:
            status = "stalled"
        else:
            status = "working"
        out.append({"agent": agent, "agent_id": aid, "status": status, "elapsed_s": round(elapsed), "idle_s": round(idle),
                    "last": (bt.get("tool") or None), "output": str(files[0].relative_to(store.root)) if files else None})
    return out


def settle_auditor(store: Store, scope: str, agent: str, why: str) -> Path:
    """Write the result of an auditor that did not finish as incomplete: its dimension is not judged this round,
    the gate cannot pass, no fix task comes from it, and the next round re-runs only it (`dev_score.py select`)."""
    raw = store.dev / "qa" / scope / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    p = raw / f"{agent}.json"
    sha = ""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        sha = subprocess.run(["git", "-C", str(store.root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip()
    atomic_write(p, json.dumps({"auditor": agent, "scope": scope, "sha": sha, "incomplete": why[:160],
                                "summary": f"{agent} did not finish: {why}"[:200], "findings": [], "verdict": "fail"}, indent=2) + "\n")
    return p


def cmd_qa_watch(store: Store, a: argparse.Namespace) -> None:
    """qa-watch M [--wait S] [--settle] [--json]: where each auditor of the round is (delivered, working, stalled),
    waiting up to S seconds (at most 540) while any is still working and none stalled. --settle writes the result of
    each stalled one, and of one that ended without a file, as incomplete (conventions.md §17)."""
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    since = None
    if a.since:
        since = time.time() - (_iso_age(a.since) or 0.0)
    deadline = time.monotonic() + max(0, min(540, a.wait or 0))
    while True:
        rows = qa_auditors(store, a.milestone, since)
        working = [r for r in rows if r["status"] == "working"]
        stuck = [r for r in rows if r["status"] in ("stalled", "ended_without_result")]
        if not working or stuck or time.monotonic() >= deadline:
            break
        time.sleep(min(10.0, max(0.2, deadline - time.monotonic())))
    settled = []
    if a.settle:
        wd = watchdog(store)
        for r in stuck:
            why = ("ended without writing its result" if r["status"] == "ended_without_result"
                   else f"no tool call for {round(r['idle_s'] / 60)} min" if r["idle_s"] > wd["stall_s"]
                   else f"past its {wd['auditor_budget_min']} min budget")
            settled.append(str(settle_auditor(store, a.milestone, r["agent"], why).relative_to(store.root)))
            store.event("auditor_stalled", scope=a.milestone, agent=r["agent"], idle_s=r["idle_s"])
    out = {"milestone": a.milestone, "auditors": rows, "working": len(working), "stalled": [r["agent"] for r in stuck],
           "settled": settled}
    if a.json:
        print(json.dumps(out, indent=2))
        return
    for r in rows:
        print(f"{r['agent']}: {r['status']} · {round(r['elapsed_s'] / 60)} min · last call {round(r['idle_s'] / 60)} min ago"
              + (f" · {r['output']}" if r["output"] else ""))
    if stuck:
        print(f"stalled: {', '.join(out['stalled'])}" + (f" · settled as incomplete: {', '.join(settled)}" if settled else
                                                          " · stop them and run qa-watch again with --settle"))


def cmd_round(store: Store, a: argparse.Namespace) -> None:
    """run SKILL SCOPE: one QA round or one milestone's implementation in a headless child session of Claude Code
    (`claude -p "/dev-kit:<skill> <scope> --round-child" --plugin-dir <kit>`), with a clean context, the same project
    directory and permission mode, and the kit's own commands allowed (headless_allowed_tools); it waits and prints a
    JSON summary for the parent, which never reads the child's reports (conventions.md §17). The child logs into the
    parent's telemetry session (`parent_session`). Whatever way it ends, `reconcile` then makes the state true (slots closed, tasks left in progress
    blocked with their attempt in the ledger)."""
    store.load()
    if a.skill not in ROUND_SKILLS:
        fail(f"round run takes {' or '.join(ROUND_SKILLS)}")
    if a.scope not in store.milestones():
        fail(f"unknown milestone {a.scope}")
    if a.permission_mode and a.permission_mode not in PERMISSION_MODES:
        fail(f"--permission-mode must be one of {', '.join(PERMISSION_MODES)}")
    exe = os.environ.get("DEV_KIT_CLAUDE") or shutil.which("claude")
    if not exe:
        fail("`claude` is not on PATH: run the round in this session instead (plan B, conventions.md §17)", 3)
    mk = _read_json(round_marker(store))
    if mk and _pid_alive(mk.get("pid")):
        fail(f"a round is already running ({mk.get('skill')} {mk.get('scope')}, pid {mk.get('pid')})")
    kit = Path(__file__).resolve().parents[3]
    run = store.dev / "run" / "rounds"
    run.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rid = f"{a.skill}-{a.scope}-{stamp}"
    log = run / f"{rid}.log"
    prompt = f"/dev-kit:{a.skill} {a.scope} --round-child"
    cmd = [exe, "-p", prompt, "--plugin-dir", str(kit), "--output-format", "json"]
    mode = a.permission_mode or os.environ.get("DEV_KIT_PERMISSION_MODE")
    if mode:
        cmd += ["--permission-mode", mode]
    cmd += ["--allowedTools", *headless_allowed_tools(store, kit)]
    env = {**os.environ, "DEV_KIT_PARENT_SESSION": tel.session_id(store.dev), "DEV_KIT_ROUND_CHILD": "1",
           "DEV_KIT_ROUND_ID": rid, "CLAUDE_PROJECT_DIR": str(store.root)}
    before = round_snapshot(store, a.scope)
    started = now()
    t0 = time.monotonic()
    stalled: dict = {}
    try:
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, cwd=store.root, env=env, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
            atomic_write(round_marker(store), json.dumps({"pid": os.getpid(), "child": proc.pid, "skill": a.skill,
                                                          "scope": a.scope, "round": rid, "started": started}) + "\n")
            deadline = t0 + a.timeout * 60 if a.timeout else None
            stall_s = watchdog(store)["stall_s"]
            rc = None
            while rc is None:
                try:
                    rc = proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # heartbeat: the round's last tool call (orchestrator or agent); none for stall_min = stalled
                    act = _read_json(store.dev / "run" / "round-activity.json")
                    beat = time.time() - (_iso_age(act.get("at")) or 0.0) if act.get("round") == rid else None
                    last = max(beat or 0.0, time.time() - (time.monotonic() - t0))
                    if time.time() - last > stall_s:
                        stalled = {"idle_s": round(time.time() - last), "what": act.get("what") if beat else None,
                                   "agent": act.get("agent") if beat else None}
                    if stalled or (deadline and time.monotonic() > deadline):
                        with contextlib.suppress(OSError):
                            os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            with contextlib.suppress(OSError):
                                os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                        rc = 126 if stalled else 124
    except OSError as e:
        round_marker(store).unlink(missing_ok=True)
        fail(f"cannot start the child session: {e}", 3)
    round_marker(store).unlink(missing_ok=True)
    why = (f"round {rid} stalled: no tool call for {round(stalled['idle_s'] / 60)} min"
           + (f" (last: {stalled.get('agent') or 'orchestrator'} {str(stalled.get('what') or '')[:60]})" if stalled.get("what") else "")
           if stalled else
           f"round {rid} ended with exit code {rc}" if rc else f"round {rid} ended with the task unfinished")
    with store.transaction():
        rec = reconcile(store, a.scope, started, why)
    out = round_summary(store, a.skill, a.scope, before, rc, time.monotonic() - t0, log)
    out["reconciled"] = rec
    if a.skill == "qa":  # what the next round reuses and what it re-runs (dev_score.py select --raw-dir)
        rows = qa_auditors(store, a.scope, time.time() - (time.monotonic() - t0) - 5)
        out["auditors"] = {"delivered": [r["agent"] for r in rows if r["status"] == "delivered"],
                           "undelivered": [r["agent"] for r in rows if r["status"] != "delivered"]}
        if stalled:
            for ag in out["auditors"]["undelivered"]:
                settle_auditor(store, a.scope, ag, why[:160])
    if stalled:
        out["stalled"] = stalled
        out["verdict"] = "stalled"
    tel.safe_emit(store.dev, "round_run", {"skill": a.skill, "scope": a.scope, "outcome": "ok" if rc == 0 else "failed",
                                           "verdict": out["verdict"], "score": out["score"], "fix_tasks": len(out["fix_tasks"]),
                                           "tasks_done": len(out["tasks_done"]), "exit_code": rc, "duration_s": out["duration_s"],
                                           "reconciled": len(rec["tasks_blocked"])})
    print(json.dumps(out, indent=2))
    if rc != 0:
        raise SystemExit(1)


# ---------------------------------------------------------------- verified facts (.dev/facts.md, conventions.md §2)
# Same high-signal patterns as checklists/security-secrets.md, plus personal data (e-mail, CPF, card-like numbers).
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    re.compile(r"sk_live_[0-9a-zA-Z]{10,}"), re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[\"']?[^\s\"']{8,}"),
]
PII_PATTERNS = [re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), re.compile(r"\b(?:\d[ -]?){13,19}\b")]


def sensitive(text: str) -> str | None:
    for rx in SECRET_PATTERNS:
        if rx.search(text):
            return "a secret (security-secrets.md patterns)"
    for rx in PII_PATTERNS:
        if rx.search(text):
            return "personal data"
    return None


def facts(store: Store) -> dict:
    return store.state.setdefault("facts", {})


def write_facts_md(store: Store) -> None:
    out = ["# Verified facts", "", "> Generated by `dev_state.py fact` (conventions.md §2); never edit by hand. One fact per line, with "
           "its evidence and the commit it was verified on. A fact proven wrong is struck through, never deleted.", ""]
    for k, f in sorted(facts(store).items(), key=lambda kv: int(kv[0][2:])):
        tags = (f" [files: {', '.join(f['files'])}]" if f.get("files") else "") + (f" [acs: {', '.join(f['acs'])}]" if f.get("acs") else "")
        line = f"{k} {f['text']} — evidence: {f['evidence']} @{f.get('sha') or '-'} — {f['date']}, {f['origin']}{tags}"
        st = f.get("stale")
        out.append(f"- ~~{line}~~ → contradicted by {st['by']} ({st['evidence']}, {st['date']})" if st else f"- {line}")
    store.stage(store.dev / "facts.md", "\n".join(out) + "\n")


def facts_for(store: Store, files: list[str], acs: list[str], limit: int = 10) -> list[tuple[str, dict]]:
    """Live facts whose files or ACs cross these (a folder tag covers what is under it), newest first."""
    want_acs = {x.upper() for a in acs for x in re.findall(r"\bAC-\d+\b", str(a), re.I)}
    fs = [f.strip().strip("/") for f in files if f.strip()]
    hits = []
    for k, f in (store.state.get("facts") or {}).items():
        if f.get("stale"):
            continue
        ff = [x.strip("/") for x in f.get("files") or []]
        if any(x == y or x.startswith(y + "/") or y.startswith(x + "/") for x in ff for y in fs) or (set(f.get("acs") or []) & want_acs):
            hits.append((k, f))
    return sorted(hits, key=lambda kv: (kv[1].get("at") or "", int(kv[0][2:])), reverse=True)[:limit]


def cmd_fact(store: Store, a: argparse.Namespace) -> None:
    """add --text --evidence [--files] [--acs] --origin [--sha] | stale K-nnn --by --evidence | list [--files] [--acs] [--all] [--json]."""
    store.load()
    split = lambda v: [x.strip() for x in re.split(r"[,\s]+", v or "") if x.strip()]  # noqa: E731
    if a.action == "add":
        text, ev = (a.text or "").strip(), (a.evidence or "").strip()
        if not text:
            fail("fact add needs --text")
        if not ev:
            fail("a fact needs --evidence: file:line or the command that shows it")
        why = sensitive(text + " " + ev)
        if why:
            fail(f"refused: the fact or its evidence contains {why}; write the fact without it")
        if not a.origin or not re.fullmatch(r"(T-\d{1,5}|F-\d{1,5}|I-\d{1,5}|qa/M\d+(?:\.\d+)?(?: R\d+)?|M\d+(?:\.\d+)?|release|user)", a.origin):
            fail("--origin is T-nnn, F-nnn, I-nnn, qa/<M> R<n>, release or user")
        n = int(store.state.get("next_fact_id", 1))
        store.state["next_fact_id"] = n + 1
        fid = f"K-{n:03d}"
        acs = [x.upper() for x in split(a.acs)]
        if any(not re.fullmatch(r"AC-\d+", x) for x in acs):
            fail("--acs takes AC ids")
        facts(store)[fid] = {"text": text.replace("\n", " ")[:400], "evidence": ev.replace("\n", " ")[:300],
                             "sha": (a.sha or _git(store, "rev-parse", "--short", "HEAD") or "")[:12] or None, "date": today(),
                             "at": now(), "origin": a.origin, "files": split(a.files), "acs": acs}
        write_facts_md(store)
        store.save()
        store.event("fact", transition="add", origin={"T": "task", "F": "finding", "I": "issue", "q": "qa", "M": "milestone"}.get(a.origin[0], a.origin))
        print(fid)
        return
    if a.action == "stale":
        if not a.id or a.id not in facts(store):
            fail(f"unknown fact {a.id}")
        if not a.by or not (a.evidence or "").strip():
            fail("fact stale needs --by <origin> and --evidence")
        if sensitive(a.evidence):
            fail("refused: the evidence contains a secret or personal data")
        facts(store)[a.id]["stale"] = {"by": a.by, "evidence": a.evidence.strip()[:300], "date": today(), "at": now()}
        write_facts_md(store)
        store.save()
        store.event("fact", transition="stale")
        print(f"{a.id} struck through: contradicted by {a.by}")
        return
    rows = facts_for(store, split(a.files), split(a.acs), limit=10 ** 6) if (a.files or a.acs) else \
        sorted(facts(store).items(), key=lambda kv: int(kv[0][2:]))
    if not a.all:
        rows = [(k, f) for k, f in rows if not f.get("stale")]
    if a.json:
        print(json.dumps([{"id": k, **f} for k, f in rows], indent=2, ensure_ascii=False))
        return
    for k, f in rows:
        print(f"{k}{' (stale)' if f.get('stale') else ''} {f['text']} — {f['evidence']} @{f.get('sha') or '-'}")


# ---------------------------------------------------------------- lessons of method per role (conventions.md §13)
LESSON_MAX = 8
AGENT_NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def lessons_path(store: Store, agent: str) -> Path:
    return store.dev / "lessons" / f"{agent}.md"


def lesson_lines(store: Store, agent: str) -> list[str]:
    p = lessons_path(store, agent)
    try:
        text = store.read_text(p) if store.file_exists(p) else ""
    except OSError:
        return []
    return [ln[2:].strip() for ln in text.splitlines() if ln.startswith("- ")]


def kit_agent_names() -> set[str]:
    d = Path(__file__).resolve().parents[3] / "agents"
    return {p.stem for p in d.glob("*.md")}


def write_lessons(store: Store, agent: str, lines: list[str]) -> None:
    body = [f"# Lessons for {agent}", "", "> Method only, never project facts (those go to .dev/facts.md). Added with the user's "
            f"confirmation by `dev_state.py lesson add`; at most {LESSON_MAX}. The kit adds them to every prompt of this agent.", ""]
    store.stage(lessons_path(store, agent), "\n".join(body + [f"- {x}" for x in lines]) + "\n")


def lesson_suggestions(store: Store) -> list[dict]:
    """Method failures the session log shows per agent (conventions.md §13): a dispute rate above 40% in two or more
    milestones, fixes that did not hold, fence denials, repeated escalations. Each cites its evidence."""
    try:
        events = tel.read_events(store.dev)[0]
    except (OSError, ValueError):
        return []
    have = {a: lesson_lines(store, a) for a in kit_agent_names()}
    dismissed = set(store.state.get("lessons_dismissed") or [])
    out = []
    rates = tel.dispute_rates(events)
    for aud, r in sorted(rates.items()):
        hot = [sc for sc, x in r["by_scope"].items() if x["challenged"] and x["disputed"] / x["challenged"] > 0.4]
        if len(hot) >= 2:
            out.append({"agent": aud, "signal": "dispute_rate", "text": "Reproduce the failure (a test run or file:line evidence) "
                        "before reporting a high or critical finding; report a suspicion as medium with confidence low.",
                        "evidence": f"{r['disputed']}/{r['challenged']} findings disputed; above 40% in {', '.join(sorted(hot))}"})
    deny: dict[str, int] = {}
    for e in events:
        if e["event"] == "fence_deny":
            deny[e.get("agent") or "implementer"] = deny.get(e.get("agent") or "implementer", 0) + 1
    for ag, n in sorted(deny.items()):
        if n >= 3:
            out.append({"agent": ag, "signal": "fence_deny", "text": "Read the task's files: list first; when the change needs "
                        "another file, stop and report the dependency instead of editing around the fence.",
                        "evidence": f"{n} edits outside the task's files denied"})
    reopened = sum(1 for e in events if e["event"] == "task" and e.get("transition") == "reopen")
    if reopened >= 2:
        out.append({"agent": "implementer", "signal": "fix_not_held", "text": "Before reporting a fix done, re-run the auditor's "
                    "reproduction or the test that showed the finding, not only the unit tests you wrote.",
                    "evidence": f"{reopened} fix tasks reopened because the finding was still open"})
    esc: dict[str, int] = {}
    for e in events:
        if e["event"] == "escalation" and e.get("agent"):
            esc[e["agent"]] = esc.get(e["agent"], 0) + 1
    for ag, n in sorted(esc.items()):
        if n >= 3:
            out.append({"agent": ag, "signal": "escalations", "text": "Read the whole scope list and the previous findings before "
                        "judging; say what you could not verify instead of guessing.", "evidence": f"{n} model escalations"})
    return [x for x in out if x["text"] not in have.get(x["agent"], []) and f"{x['agent']}:{x['signal']}" not in dismissed]


def cmd_lesson(store: Store, a: argparse.Namespace) -> None:
    """add AGENT "<text>" (the user's confirmation) | rm AGENT N | show AGENT (the block skills add to its prompt) |
    list [--json] | suggest [--json] | dismiss AGENT SIGNAL."""
    store.load()
    if a.action in ("add", "rm", "show", "dismiss") and (not a.agent or not AGENT_NAME.match(a.agent)):
        fail("give the agent's name (e.g. code-reviewer)")
    if a.action == "add":
        text = " ".join(a.rest).strip()
        if not text:
            fail('lesson add needs the text: lesson add <agent> "<method lesson>"')
        if a.agent not in kit_agent_names():
            fail(f"unknown agent {a.agent}")
        if sensitive(text):
            fail("refused: a lesson is method only; it contains a secret or personal data")
        cur = lesson_lines(store, a.agent)
        if len(cur) >= LESSON_MAX:
            fail(f"{a.agent} already has {LESSON_MAX} lessons: consolidate them first (merge similar ones with `lesson rm` and one "
                 "`lesson add`), /dev-kit:feedback proposes the consolidation")
        write_lessons(store, a.agent, cur + [text.replace("\n", " ")[:300]])
        store.event("lesson", agent=a.agent, transition="add")
        store.log(f"lesson add {a.agent}")
        print(f"{a.agent}: lesson {len(cur) + 1} of {LESSON_MAX} added")
        return
    if a.action == "rm":
        cur = lesson_lines(store, a.agent)
        try:
            i = int(a.rest[0]) - 1
            assert 0 <= i < len(cur)
        except (IndexError, ValueError, AssertionError):
            fail(f"lesson rm {a.agent} <n>, n from 1 to {len(cur)}")
        cur.pop(i)
        write_lessons(store, a.agent, cur)
        store.event("lesson", agent=a.agent, transition="rm")
        print(f"{a.agent}: {len(cur)} lesson(s) left")
        return
    if a.action == "dismiss":
        sig = (a.rest or [""])[0]
        store.state.setdefault("lessons_dismissed", []).append(f"{a.agent}:{sig}")
        store.save()
        print(f"{a.agent}: suggestion {sig} dismissed")
        return
    if a.action == "show":
        ls = lesson_lines(store, a.agent)
        if ls:
            print(f"Lessons for this role in this project (.dev/lessons/{a.agent}.md):\n" + "\n".join(f"  - {x}" for x in ls))
        return
    if a.action == "suggest":
        sug = lesson_suggestions(store)
        if a.json:
            print(json.dumps(sug, indent=2))
        else:
            for x in sug:
                print(f"{x['agent']} ({x['signal']}): {x['text']} · evidence: {x['evidence']}")
        return
    allx = {ag: lesson_lines(store, ag) for ag in sorted(kit_agent_names())}
    allx = {k: v for k, v in allx.items() if v}
    if a.json:
        print(json.dumps(allx, indent=2))
    else:
        for ag, ls in allx.items():
            print(f"{ag}: " + " | ".join(ls))


# ---------------------------------------------------------------- slots and the file fence (conventions.md §17)

def slot_path(store: Store, n: int) -> Path:
    return store.dev / "run" / "slots" / f"{n}.json"


def _gitc(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def task_target_dir(store: Store, t: dict) -> Path:
    """Where a task is integrated: the main checkout, or the worktree of its pipeline branch (§19)."""
    br = t.get("branch")
    if br:
        wt = store.dev / "run" / "worktrees" / br.replace("/", "-")
        return wt if wt.exists() else store.root
    return store.root


def check_base(store: Store, base: str, t: dict) -> str | None:
    """Why a worktree base is wrong for this project, or None. The base must hold what the main checkout holds:
    the kit's tracked state and the task's files that already exist (a base without them is another branch)."""
    if _gitc(store.root, "ls-files", "--error-unmatch", ".dev/state.json", timeout=30).returncode == 0 \
            and _gitc(store.root, "cat-file", "-e", f"{base}:.dev/state.json", timeout=30).returncode != 0:
        return f"{base} has no .dev/state.json, which the main checkout tracks"
    head_files = [f for f in t.get("files") or [] if f and not f.endswith("/")
                  and _gitc(store.root, "cat-file", "-e", f"HEAD:{f}", timeout=30).returncode == 0]
    missing = [f for f in head_files if _gitc(store.root, "cat-file", "-e", f"{base}:{f}", timeout=30).returncode != 0]
    if missing:
        return f"{base} lacks the task's files that exist on HEAD: {', '.join(missing[:5])}"
    return None


def open_worktree(store: Store, tid: str, t: dict) -> dict:
    """The task's own worktree (.dev/run/worktrees/T-nnn on dev-kit/T-nnn), created by the kit from the work branch
    (or the task's pipeline branch), never left to the agent tool. A branch left by an earlier attempt is reused."""
    wt = store.dev / "run" / "worktrees" / tid
    br = f"dev-kit/{tid}"
    base_ref = t.get("branch") or work_branch(store)
    if t.get("branch") and _gitc(store.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{base_ref}", timeout=30).returncode != 0:
        fail(f"{tid} belongs on {base_ref}, which does not exist yet: run `pipeline worktree {base_ref}` first")
    base_sha = (_gitc(store.root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}", timeout=30).stdout or "").strip()
    if not base_sha:
        fail(f"cannot resolve the work branch {base_ref} (set autonomy.git.base_branch)")
    exists = _gitc(store.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}", timeout=30).returncode == 0
    reused = foreign = False
    other = branch_worktree(store, br) if exists and not wt.exists() else None
    if other:
        # an earlier attempt made elsewhere (Claude Code's own isolation before 3.5.0: .claude/worktrees/T-nnn):
        # `git worktree add` would refuse the branch, so the kit works in that worktree instead
        why = check_base(store, br, t)
        if why:
            fail(f"refusing the worktree of {tid} at {other}: {why}")
        wt, foreign = other, True
    if wt.exists():
        reused = True
    else:
        why = check_base(store, base_sha, t)
        if why:
            fail(f"refusing the worktree of {tid}: {why}")
        wt.parent.mkdir(parents=True, exist_ok=True)
        r = _gitc(store.root, "worktree", "add", str(wt), br) if exists else _gitc(store.root, "worktree", "add", "-b", br, str(wt), base_sha)
        if r.returncode != 0:
            fail(f"git worktree add failed for {tid}: {r.stderr.strip()[:300]}")
        reused = exists
    if reused:
        mb = (_gitc(store.root, "merge-base", base_sha, br, timeout=30).stdout or "").strip()
        base_sha = mb or base_sha
    top = (_gitc(wt, "rev-parse", "--show-toplevel", timeout=30).stdout or "").strip()
    if not top or os.path.realpath(top) != os.path.realpath(wt):
        fail(f"{wt} is not a worktree of its own (git says {top or 'nothing'})")
    return {"worktree": str(wt), "branch": br, "base_ref": base_ref, "base_sha": base_sha, "reused": reused, "foreign": foreign}


def branch_worktree(store: Store, br: str) -> Path | None:
    """The worktree (other than the main checkout) that has `br` checked out, wherever it is."""
    path = None
    for line in (_gitc(store.root, "worktree", "list", "--porcelain", timeout=30).stdout or "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.strip() == f"branch refs/heads/{br}" and path and os.path.realpath(path) != os.path.realpath(store.root):
            return Path(path)
    return None


def previous_work(store: Store, tid: str) -> dict | None:
    """Where an earlier attempt of a task left its work: the kit's worktree, another worktree on dev-kit/T-nnn, or
    that branch alone. None when there is none."""
    br = f"dev-kit/{tid}"
    wt = store.dev / "run" / "worktrees" / tid
    if wt.exists():
        return {"worktree": str(wt), "branch": br}
    other = branch_worktree(store, br)
    if other:
        return {"worktree": str(other), "branch": br}
    if _gitc(store.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}", timeout=30).returncode == 0:
        return {"worktree": None, "branch": br}
    return None


def begin_task(store: Store, tid: str, via: str) -> None:
    """A command that brings a task's work into play (slot open, slot apply, reconcile --adopt) records its start
    when nobody did: the state never shows `todo` for a task being worked on. A blocked task must be unblocked
    first (its block is a decision); a finished one is refused."""
    t = store.task(tid)
    if t["status"] == "in_progress":
        return
    if t["status"] in FINISHED:
        fail(f"{tid} is {t['status']}: {via} refused")
    if t["status"] == "blocked":
        fail(f"{tid} is blocked ({t.get('blocked_reason') or '-'}): unblock it first (Needs you or `unblock {tid}`), then {via}")
    start_task(store, tid, True, keep_started=True, via=via)


def routed_model(t: dict, r: dict | None) -> str:
    """The model the task was routed to when it started (state), else the router's answer now."""
    arm = str((t.get("tier") or {}).get("arm") or "") if isinstance(t.get("tier"), dict) else ""
    return arm.split("/")[0] if arm else str((r or {}).get("final_model") or "")


def is_delegated(model: str) -> bool:
    """A task routed to speed or quality (haiku or opus) goes to an implementer in its own worktree; balanced ones
    (sonnet) are done inline (implement step 2)."""
    return model in ("haiku", "opus")


def resume_task(store: Store, tid: str, force: bool) -> None:
    """`start T-nnn --resume`: take over the work an earlier attempt left (§17). The task goes in_progress keeping its
    first start. A delegated task keeps the work in its worktree (`slot open --worktree` reuses it); an inline task
    gets it applied, staged, to the main checkout (or its pipeline worktree) after the fence check, and `done`
    removes the old worktree and branch. Never apply a worktree by hand (git apply, checkout --, cp)."""
    t = store.task(tid)
    if t["status"] in FINISHED:
        fail(f"{tid} is already {t['status']}")
    prev = previous_work(store, tid)
    r = start_task(store, tid, force, keep_started=True, via="start --resume")
    if not prev:
        print(f"{tid}: no earlier attempt found (no worktree or branch dev-kit/{tid}): start from the brief")
        return
    model = routed_model(t, r if r is not None else safe_route(store, tid))
    if is_delegated(model):
        print(f"{tid}: earlier attempt on {prev['branch']}" + (f" in {prev['worktree']}" if prev["worktree"] else "")
              + f"; delegated ({model}): `slot open N --task {tid} --worktree` reuses it for the implementer")
        return
    wt = open_worktree(store, tid, t)
    base = wt["base_sha"]
    rec = {"task": tid, "files": list(t.get("files") or []), "allow": [f".dev/qa/{tid}/"]}
    changed, outside = slot_outside(rec, Path(wt["worktree"]), base)
    if outside:
        fail(f"{tid}: the earlier attempt changed {len(outside)} file(s) outside the task: {', '.join(outside)}. Revert them in "
             f"{wt['worktree']} or replan the task's files, then run `start {tid} --resume` again")
    patch = worktree_patch(Path(wt["worktree"]), base)
    target = task_target_dir(store, t)
    if not patch.strip():
        print(f"{tid}: the earlier attempt in {wt['worktree']} has no changes: start from the brief")
        return
    tmp = store.dev / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    pf = tmp / f"resume-{tid}.patch"
    pf.write_text(patch, encoding="utf-8")
    try:
        if _gitc(target, "apply", "--reverse", "--check", "--cached", str(pf)).returncode == 0:
            print(f"{tid}: the earlier attempt is already applied (staged) in {target}")
        else:
            res = _gitc(target, "apply", "--3way", "--whitespace=nowarn", str(pf))
            if res.returncode != 0:
                fail(f"{tid}: the earlier attempt does not apply on {target}: {res.stderr.strip()[:400]}")
            print(f"{tid}: {len(changed)} file(s) of the earlier attempt applied to {target} (staged) from {wt['worktree']}; "
                  "review the diff, run the suite and commit")
    finally:
        pf.unlink(missing_ok=True)
    t["resumed_from"] = {"worktree": wt["worktree"], "branch": wt["branch"], "base_sha": base,
                         "applied": hashlib.sha256(patch.encode()).hexdigest(), "at": now()}
    store.save()
    store.log(f"resume {tid}: earlier attempt applied from {wt['worktree']} ({len(changed)} file(s))")


def slot_outside(rec: dict, cwd: Path, since: str) -> tuple[list[str], list[str]]:
    import dev_fence
    diff = _gitc(cwd, "diff", "--name-only", since, timeout=60)
    new = _gitc(cwd, "ls-files", "--others", "--exclude-standard", timeout=60)
    if diff.returncode != 0:
        fail(f"git diff {since} failed: {diff.stderr.strip()}")
    changed = sorted({x for x in (diff.stdout + "\n" + new.stdout).splitlines() if x.strip()})
    return changed, [f for f in changed if not f.startswith(".dev/") and not dev_fence.allowed(rec, f)]


def worktree_patch(wt: Path, base: str) -> str:
    """The worktree's changes since its base (committed or not, new files included, .dev/ left out)."""
    _gitc(wt, "add", "-A", "--", ".", ":(exclude).dev")
    return _gitc(wt, "diff", "--cached", "--binary", base, "--", ".", ":(exclude).dev").stdout


def remove_worktree(store: Store, wt: Path, br: str | None, applied: str | None = None, base: str | None = None) -> str | None:
    """Remove a task worktree and its branch. Refused (returns why) when it holds changes that were not applied
    (`slot apply` records the hash of what it applied)."""
    if wt.exists():
        dirty = _gitc(wt, "status", "--porcelain", "--", ".", ":(exclude).dev", timeout=60).stdout.strip()
        if dirty and not (applied and base and hashlib.sha256(worktree_patch(wt, base).encode()).hexdigest() == applied):
            return f"{wt} has changes that were not applied (slot apply)"
        r = _gitc(store.root, "worktree", "remove", "--force", str(wt))
        if r.returncode != 0:
            return r.stderr.strip()[:200] or "git worktree remove failed"
    _gitc(store.root, "worktree", "prune", timeout=30)
    if br:
        _gitc(store.root, "branch", "-D", br, timeout=30)
    return None


def cmd_slot(store: Store, a: argparse.Namespace) -> None:
    """The fence of one agent slot. open N --task T-nnn [--allow PATH…] [--agent NAME] [--worktree]: the files the
    agent of slot N may edit (the task's `files:`, their tests, changelog.d/, docs/setup.d/ and the .dev/ paths given);
    dev_fence.py enforces it as a PreToolUse hook. With --worktree the kit creates the task's worktree from the work
    branch (§17) and the fence also denies edits outside it. close N [--remove] (--remove deletes the worktree and its
    branch once integrated). show N. check N [--since SHA] [--cwd DIR]: the files changed since SHA (committed or not;
    default the worktree's base) that fall outside the fence; exit 1 when there is one. apply N: check, then apply the
    worktree's changes to the main checkout (or the task's pipeline worktree) with git apply --3way."""
    store.load()
    path = slot_path(store, a.n)
    if a.action == "open":
        files: list[str] = []
        t = None
        if a.task:
            t = store.task(a.task)
            files = list(t.get("files") or [])
        allow = [x.strip() for x in a.allow or [] if x.strip()]
        if a.task:
            allow.append(f".dev/qa/{a.task}/")
        if not files and not allow:
            fail("slot open needs --task (its files) or --allow")
        rec = {"slot": a.n, "task": a.task, "agent": a.agent, "files": files, "allow": allow, "opened_at": now()}
        wt = None
        if a.task:
            begin_task(store, a.task, "slot open")
        if a.worktree:
            if not a.task:
                fail("slot open --worktree needs --task")
            wt = open_worktree(store, a.task, t)
            rec.update({k: wt[k] for k in ("worktree", "branch", "base_ref", "base_sha")})
        store.stage(path, json.dumps(rec, indent=2) + "\n")
        store.log(f"slot {a.n} open" + (f" for {a.task}" if a.task else "") + (f" in {wt['worktree']}" if wt else ""))
        print(f"slot {a.n}: fence on {', '.join(files + allow) or '-'}" + (" (+ their tests, changelog.d/, docs/setup.d/)" if files else ""))
        if wt:
            print(f"worktree: {wt['worktree']} on {wt['branch']} from {wt['base_ref']} {wt['base_sha'][:7]}"
                  + (" (earlier attempt kept)" if wt["reused"] else "") + (" (made outside the kit, reused)" if wt.get("foreign") else ""))
        return
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail(f"slot {a.n} is not open")
    if a.action == "close":
        rec.setdefault("closed_at", now())
        if a.remove and rec.get("worktree"):
            why = remove_worktree(store, Path(rec["worktree"]), rec.get("branch"), rec.get("applied"), rec.get("base_sha"))
            if why:
                fail(f"slot {a.n}: worktree not removed ({why}); integrate or keep it, then close again")
            rec["removed_at"] = now()
        store.stage(path, json.dumps(rec, indent=2) + "\n")
        print(f"slot {a.n} closed" + (" · worktree and branch removed" if rec.get("removed_at") else ""))
        return
    if a.action == "show":
        print(json.dumps(rec, indent=2))
        return
    since = a.since or rec.get("base_sha")
    if not since:
        fail("slot check needs --since <sha>")
    cwd = Path(a.cwd) if a.cwd else Path(rec["worktree"]) if rec.get("worktree") else store.root
    changed, outside = slot_outside(rec, cwd, since)
    if outside:
        tel.safe_emit(store.dev, "fence_deny", {"agent": tel.scope_token(rec.get("agent") or "implementer"), "scope": rec.get("task"),
                                                "tool": "diff", "reason": "outside_files"})  # logged even though the command fails
        print(f"slot {a.n} ({rec.get('task') or '-'}): {len(outside)} file(s) outside the fence: {', '.join(outside)}")
        print("integration refused: revert them, or record the dependency and replan the task's files")
        raise SystemExit(1)
    if a.action == "check":
        print(f"slot {a.n} ({rec.get('task') or '-'}): {len(changed)} changed file(s), all inside the fence")
        return
    # apply
    if not rec.get("worktree"):
        fail(f"slot {a.n} has no worktree (open it with --worktree)")
    if rec.get("task"):
        begin_task(store, rec["task"], "slot apply")
    wt = Path(rec["worktree"])
    patch = worktree_patch(wt, since)
    if not patch.strip():
        print(f"slot {a.n} ({rec.get('task') or '-'}): nothing to apply")
        return
    if rec.get("applied") == hashlib.sha256(patch.encode()).hexdigest():
        print(f"slot {a.n} ({rec.get('task') or '-'}): already applied")
        return
    target = task_target_dir(store, store.task(rec["task"])) if rec.get("task") else store.root
    tmp = store.dev / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    pf = tmp / f"slot-{a.n}.patch"
    pf.write_text(patch, encoding="utf-8")
    r = _gitc(target, "apply", "--3way", "--whitespace=nowarn", str(pf))
    if r.returncode != 0:
        store.event("error", code="merge_conflict", component="slot")
        print(f"slot {a.n} ({rec.get('task') or '-'}): the changes do not apply on {target}: {r.stderr.strip()[:400]}")
        print("integration refused: run this task again alone after the others (its worktree and branch are kept)")
        raise SystemExit(1)
    pf.unlink(missing_ok=True)
    rec["applied"] = hashlib.sha256(patch.encode()).hexdigest()
    rec["applied_at"] = now()
    store.stage(path, json.dumps(rec, indent=2) + "\n")
    print(f"slot {a.n} ({rec.get('task') or '-'}): {len(changed)} file(s) applied to {target} (staged); run the suite and commit")


# ---------------------------------------------------------------- reconciliation (conventions.md §17)
def _read_json(p: Path) -> dict:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def round_marker(store: Store) -> Path:
    return store.dev / "run" / "round.json"


def _pid_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def open_slots(store: Store) -> dict[int, dict]:
    d = store.dev / "run" / "slots"
    out = {}
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if f.stem.isdigit() and not rec.get("closed_at"):
            out[int(f.stem)] = rec
    return out


def reconcile(store: Store, milestone: str | None = None, since: str | None = None, reason: str | None = None) -> dict:
    """Make the state true again after a round or a session that stopped (no model involved): every slot left open
    is closed; every task left in_progress that had a slot, or that started after `since`, is blocked with the
    reason and its attempt recorded in the ledger (Previous attempt: its branch); a clean worktree is removed,
    one with changes is kept. Called by `round run` after every round, and by `implement` before it starts."""
    ts = store.tasks()
    slots = open_slots(store)
    by_task = {r.get("task"): (n, r) for n, r in slots.items() if r.get("task")}
    why = reason or "the session that worked on it stopped before finishing"
    out = {"slots_closed": [], "tasks_blocked": [], "tasks_done": [], "worktrees_kept": [], "worktrees_removed": []}
    for n, rec in slots.items():
        if milestone and rec.get("task") and ts.get(rec["task"], {}).get("milestone") != milestone:
            continue
        rec["closed_at"] = now()
        rec["closed_by"] = "reconcile"
        store.stage(slot_path(store, n), json.dumps(rec, indent=2) + "\n")
        out["slots_closed"].append(n)
        wt = rec.get("worktree")
        if wt and Path(wt).exists():
            ahead = _gitc(Path(wt), "rev-list", "--count", f"{rec.get('base_sha')}..HEAD", timeout=30).stdout.strip() if rec.get("base_sha") else "0"
            dirty = _gitc(Path(wt), "status", "--porcelain", "--", ".", ":(exclude).dev", timeout=60).stdout.strip()
            if dirty or (ahead and ahead != "0"):
                out["worktrees_kept"].append(wt)
            elif not remove_worktree(store, Path(wt), rec.get("branch")):
                out["worktrees_removed"].append(wt)
    for tid, t in sorted(ts.items(), key=lambda kv: int(kv[0][2:])):
        if t["status"] != "in_progress" or (milestone and t["milestone"] != milestone):
            continue
        slot = by_task.get(tid)
        if not slot and not (since and (t.get("started_at") or "") >= since):
            continue
        rec = slot[1] if slot else {}
        ref = rec.get("branch") if rec.get("worktree") and rec["worktree"] in out["worktrees_kept"] else None
        note = why + (f"; partial work kept on {ref} ({rec['worktree']})" if ref else "")
        with contextlib.suppress(Exception):
            led.put(store.dev, f"task:{tid}", led.fingerprint(store.root, list(t.get("files") or [])), "failed", ref, note)
        t["status"] = "blocked"
        t["blocked_reason"] = f"reconciled: {why}"
        t["blocked_count"] = int(t.get("blocked_count", 0) or 0) + 1
        store.event("task", task=tid, transition="block", type=t.get("type"), milestone=t.get("milestone"))
        out["tasks_blocked"].append(tid)
    if since:
        unstarted(store, ts, milestone, since, why, out)
    if out["tasks_blocked"] or out["slots_closed"] or out["tasks_done"]:
        store.save()
        store.log(f"reconcile: blocked {', '.join(out['tasks_blocked']) or '-'}; closed slots {', '.join(map(str, out['slots_closed'])) or '-'}"
                  + (f"; done {', '.join(out['tasks_done'])} (committed without done)" if out["tasks_done"] else "") + f" ({why})")
        store.event("reconcile", blocked=len(out["tasks_blocked"]), slots=len(out["slots_closed"]), kept=len(out["worktrees_kept"]))
    return out


TASK_REF = r"(?:\[{tid}\]|^Refs:.*\b{tid}\b)"


def task_commit_since(store: Store, tid: str, since: str) -> str | None:
    """The newest commit on HEAD since `since` whose subject carries `[T-nnn]` or whose trailer says `Refs: T-nnn`."""
    raw = _gitc(store.root, "log", f"--since={since}", "--format=%H%x00%B%x01", "HEAD", timeout=60).stdout or ""
    rx = re.compile(TASK_REF.format(tid=re.escape(tid)), re.M)
    for chunk in raw.split("\x01"):
        sha, _, body = chunk.strip("\n").partition("\x00")
        if sha and rx.search(body):
            return sha.strip()
    return None


def unstarted(store: Store, ts: dict, milestone: str | None, since: str, why: str, out: dict) -> None:
    """Work a round did on a task it never started (§17): a `todo` task with a commit of its own since the round
    began is recorded as done with that commit; a `todo` task whose files (and only its files) were left changed in
    the main checkout gets them moved to its worktree and is blocked, its attempt in the ledger."""
    import dev_fence
    open_ts = {k: v for k, v in ts.items() if v["status"] not in FINISHED}
    dirty = [ln[3:] for ln in (_gitc(store.root, "status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude).dev",
                                     timeout=60).stdout or "").splitlines() if len(ln) > 3]
    for tid, t in sorted(ts.items(), key=lambda kv: int(kv[0][2:])):
        if t["status"] != "todo" or (milestone and t["milestone"] != milestone):
            continue
        sha = task_commit_since(store, tid, since)
        if sha:
            t["status"] = "done"
            t["done_at"] = now()
            t["commit"] = sha
            t["started_at"] = t.get("started_at") or since
            issue_sync(store, t)
            store.event("task", task=tid, transition="done", type=t.get("type"), milestone=t.get("milestone"))
            out["tasks_done"].append(tid)
            continue
        fence = {"files": list(t.get("files") or []), "allow": []}
        mine = [f for f in dirty if dev_fence.allowed(fence, f)]
        if not mine or any(dev_fence.allowed({"files": list(v.get("files") or []), "allow": []}, f)
                           for f in mine for k, v in open_ts.items() if k != tid):
            continue
        res = adopt(store, tid, start=False)
        ref = res.get("branch")
        note = f"{why}; worked on without `start`, its changes moved to {res.get('worktree') or '-'}"
        with contextlib.suppress(Exception):
            led.put(store.dev, f"task:{tid}", led.fingerprint(store.root, list(t.get("files") or [])), "failed", ref, note)
        t["status"] = "blocked"
        t["blocked_reason"] = f"reconciled: {note}"
        t["blocked_count"] = int(t.get("blocked_count", 0) or 0) + 1
        store.event("task", task=tid, transition="block", type=t.get("type"), milestone=t.get("milestone"))
        out["tasks_blocked"].append(tid)
        if res.get("worktree"):
            out["worktrees_kept"].append(res["worktree"])


def adopt(store: Store, tid: str, start: bool = True) -> dict:
    """Move a task's uncommitted changes from the main checkout into the task's worktree (created from the work
    branch when missing, or the one already on its branch). Only files inside the task's fence move; the others stay
    where they are and are listed. The task is started when nobody did (`start` False: reconcile, which blocks it)."""
    import dev_fence
    t = store.task(tid)
    if start:
        begin_task(store, tid, "reconcile --adopt")
    rec = {"task": tid, "files": list(t.get("files") or []), "allow": [f".dev/qa/{tid}/"]}
    st = _gitc(store.root, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".", ":(exclude).dev", timeout=60).stdout
    entries = [e for e in st.split("\0") if e]
    changed: list[tuple[str, str]] = []
    skip_next = False
    for e in entries:
        if skip_next:
            skip_next = False
            continue
        code, f = e[:2], e[3:]
        if code[0] in "RC":
            skip_next = True  # the rename's source follows
        changed.append((code, f))
    mine = [(c, f) for c, f in changed if dev_fence.allowed(rec, f)]
    others = [f for c, f in changed if not dev_fence.allowed(rec, f)]
    if not mine:
        return {"task": tid, "moved": [], "left": others, "worktree": None}
    wt = open_worktree(store, tid, t)
    dst = Path(wt["worktree"])
    moved = []
    for code, f in mine:
        src = store.root / f
        if src.exists() or src.is_symlink():
            (dst / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / f, follow_symlinks=False)
        else:
            (dst / f).unlink(missing_ok=True)
        moved.append(f)
    tracked = [f for c, f in mine if c != "??"]
    if tracked:
        _gitc(store.root, "restore", "--staged", "--worktree", "--source=HEAD", "--", *tracked)
    for c, f in mine:
        if c == "??":
            (store.root / f).unlink(missing_ok=True)
    store.log(f"reconcile --adopt {tid}: {len(moved)} file(s) moved to {wt['worktree']}")
    store.event("reconcile", adopted=len(moved))
    return {"task": tid, "moved": moved, "left": others, "worktree": wt["worktree"], "branch": wt["branch"]}


def cmd_reconcile(store: Store, a: argparse.Namespace) -> None:
    store.load()
    mk = _read_json(round_marker(store))
    if mk and _pid_alive(mk.get("pid")) and not a.force and mk.get("round") != os.environ.get("DEV_KIT_ROUND_ID"):
        fail(f"a round is running ({mk.get('skill')} {mk.get('scope')}, pid {mk.get('pid')}): it reconciles when it ends (--force to do it now)", 2)
    if a.adopt:
        res = adopt(store, a.adopt)
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"{a.adopt}: {len(res['moved'])} file(s) moved to {res['worktree'] or '-'}"
                  + (f" · left in the main checkout (not this task's): {', '.join(res['left'])}" if res["left"] else ""))
        return
    res = reconcile(store, a.milestone, a.since, a.reason)
    if a.json:
        print(json.dumps(res, indent=2))
        return
    if res["tasks_done"]:
        print(f"reconcile: {', '.join(res['tasks_done'])} done (committed by a run that never started them)")
    print(f"reconcile: {len(res['tasks_blocked'])} task(s) blocked ({', '.join(res['tasks_blocked']) or '-'}) · "
          f"{len(res['slots_closed'])} slot(s) closed · worktrees kept {len(res['worktrees_kept'])}, removed {len(res['worktrees_removed'])}")
    for w in res["worktrees_kept"]:
        print(f"  kept with changes: {w}")


def cmd_unblock(store: Store, a: argparse.Namespace) -> None:
    store.load()
    t = store.task(a.task)
    if t["status"] != "blocked":
        fail(f"{a.task} is {t['status']}, not blocked")
    t["status"] = "todo"
    t["blocked_reason"] = None
    t.pop("blocked_by", None)
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
    t.pop("blocked_by", None)
    t["dropped_reason"] = a.reason
    t["dropped_at"] = now()
    issue_sync(store, t)
    store.save()
    store.log(f"drop {a.task}: {a.reason}")
    store.event("task", task=a.task, transition="drop", type=t.get("type"), milestone=t.get("milestone"))
    print(f"{a.task} dropped: {a.reason}")


# ---------------------------------------------------------------- scope freeze (conventions.md §15)
FREEZE_EXEMPT_SOURCES = ("qa/", "hard_floor:", "release:")  # QA fixes, hard-floor fixes, a rejected release's fixes


def frozen(store: Store, m: str) -> bool:
    return bool((store.milestones().get(m) or {}).get("frozen_at"))


def frozen_cost(m: str) -> str:
    return f"this item enters the next QA round of {m} and invalidates the audit of the files it touches."


def drop_ledger_files(store: Store, files: list[str]) -> int:
    """Invalidate every ledger unit about one of these files (§18): work added after the freeze is audited again."""
    try:
        recs = led.load(store.dev)
    except OSError:
        return 0
    want = {f.strip("/") for f in files if f}
    keys = [k for k, r in recs.items() if r.get("result") != "dropped" and any(k.endswith(":" + f) for f in want)]
    if keys:
        led.append(store.dev, [{"key": k, "fp": "", "result": "dropped", "at": now()} for k in keys])
    return len(keys)


def cmd_freeze(store: Store, a: argparse.Namespace) -> None:
    """Freeze the scope of a milestone when its first QA round begins (qa calls it). Idempotent: the first time
    wins, and a replan or a rejected gate never unfreezes it."""
    store.load()
    m = store.milestones().get(a.milestone)
    if m is None:
        fail(f"unknown milestone {a.milestone}")
    if m.get("frozen_at"):
        print(f"{a.milestone} frozen since {m['frozen_at']}")
        return
    m["frozen_at"] = now()
    store.save()
    store.log(f"freeze {a.milestone}: scope frozen for QA")
    store.event("scope", milestone=a.milestone, transition="freeze")
    print(f"{a.milestone} frozen: from now on only QA fixes, current and expedite issues (or a confirmed item) enter it")


def closed_count(store: Store) -> int:
    return sum(1 for v in store.milestones().values() if v.get("gate") in ("passed", "skipped"))


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
        nxt = f"M{max(mmajor(m) for m in store.milestones()) + 1}"
        later = [m for m in store.milestone_order() if mkey(m) > mkey(a.milestone)
                 and store.milestones()[m].get("gate", "pending") == "pending"]
        fail(f"gate of {a.milestone} already passed; add the task to {later[0] if later else nxt}"
             + ("" if later else f" (--milestone {nxt} --milestone-title \"...\")") + ", use --lane hotfix, or --force")
    issue = None
    if getattr(a, "issue", None):
        issue = store.state.get("issues", {}).get(a.issue)
        if issue is None:
            fail(f"unknown issue {a.issue}")
    after_freeze = False
    if frozen(store, a.milestone) and a.lane != "hotfix" and (issue or {}).get("class") not in ("current", "expedite") \
            and not str(a.source or "").startswith(FREEZE_EXEMPT_SOURCES):
        if not a.confirm_frozen:
            fail(f"{a.milestone} is frozen since its QA began (§15); only QA fixes, current and expedite issues enter it. "
                 f"To add this anyway pass --confirm-frozen: {frozen_cost(a.milestone)}")
        after_freeze = True
    if getattr(a, "lane", None):
        if a.lane not in LANES:
            fail(f"--lane must be one of {', '.join(LANES)}")
        if a.lane == "hotfix" and not a.force:
            open_hot = [x for x, v in store.tasks().items() if v.get("lane") == "hotfix" and v["status"] not in FINISHED]
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
    if after_freeze:
        t["scope_after_freeze"] = True
    t.update(risk_args(a))
    probs = risk.check_risk_fields(tid, t)
    if probs:
        fail("; ".join(probs))
    store.tasks()[tid] = t
    if a.type == "fix" and t["files"]:
        back = send_back_ahead(store, a.milestone, t["files"], f"{tid} fixes a file of it")
        if back:
            store.log(f"pipeline: {', '.join(back)} back to todo ({tid} in {a.milestone} touches their files)")
            print(f"note: {', '.join(back)} ran ahead and share files with {tid}: back to todo, redone after the gate of "
                  f"{a.milestone}", file=sys.stderr)
    if issue is not None:
        link_task(store, a.issue, tid, a.milestone)
    append_task_to_plan(store, store.dev / "plan.md", a.milestone, store.milestones()[a.milestone]["title"], tid, t)
    store.save()
    store.event("task", task=tid, transition="add", type=a.type, milestone=a.milestone)
    store.log(f"add-task {tid} [{a.milestone}] ({a.type}) {a.title} source={a.source or '-'}"
              + (" · confirmed after the freeze" if after_freeze else ""))
    if after_freeze:
        store.event("scope", milestone=a.milestone, task=tid, transition="after_freeze")
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
            safe_observe(store, tid, "blocked" if returns >= 2 else "reopened")
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
            if sev in ISSUE_SEVERITIES:
                store.tasks()[new_id]["finding_severity"] = sev
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
    qid = store.new_question_id()
    path = store.dev / "open-questions.md"
    if not store.file_exists(path):
        store.stage(path, "# Open questions\n\n## Open\n| id | date | raised by | question | assumption used | impact if wrong |\n|---|---|---|---|---|---|\n\n## Resolved\n| id | resolved on | answer | ADR / task |\n|---|---|---|---|\n")
    text = store.read_text(path)
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
    store.stage(path, "\n".join(lines).rstrip("\n") + "\n")
    store.save()
    if options:  # the board shows them with the question (conventions §10)
        _write_json(question_sidecar(store, qid), store=store, obj={"id": qid, "options": options, "recommended": a.recommended,
                                                   "answered": False, "at": now()})
    task = getattr(a, "task", None)  # internal callers build their own Namespace without it
    if task:
        store.task(task)["question"] = qid  # a blocked task waiting on this answer: the board shows it inline
    store.state.setdefault("question_meta", {})[qid] = {"at": now(), "scope": current_milestone(store), **({"task": task} if task else {})}
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


# ---------------------------------------------------------------- hard floor, CI, exit check, debt (conventions.md §7)
HARD_FLOOR_CHECKS = ("tests", "lint", "typecheck", "deps", "secrets", "a11y")
FLOOR_STATUSES = ("pass", "fail", "n/a")
NEVER_FORCED = ("secrets",)  # with deps when the finding is critical


def hard_floor_on(store: Store) -> bool:
    return bool(quality_cfg(store).get("hard_floor", {}).get("enabled", True))


def cmd_hard_floor(store: Store, a: argparse.Namespace) -> None:
    """Record the deterministic checks of a round (§7): `{"tests": {"status": "pass"}, "deps": {"status": "fail",
    "severity": "high", "detail": "lodash CVE-…"}, "a11y": {"status": "n/a", "reason": "no UI"}}`. Each failure
    becomes one fix task with source hard_floor:<check> (one per check, reused while open)."""
    store.load()
    ms = store.milestones().get(a.milestone)
    if ms is None:
        fail(f"unknown milestone {a.milestone}")
    try:
        raw = json.loads(Path(a.from_file).read_text(encoding="utf-8") if a.from_file != "-" else sys.stdin.read())
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read the hard floor results: {e}")
    checks = raw.get("checks", raw) if isinstance(raw, dict) else None
    if not isinstance(checks, dict) or not checks:
        fail(f"hard floor results must be an object of checks ({', '.join(HARD_FLOOR_CHECKS)})")
    out: dict = {}
    for name, c in checks.items():
        if name not in HARD_FLOOR_CHECKS:
            fail(f"unknown hard floor check {name!r}; one of {', '.join(HARD_FLOOR_CHECKS)}")
        c = {"status": c} if isinstance(c, str) else c
        if not isinstance(c, dict) or c.get("status") not in FLOOR_STATUSES:
            fail(f"{name}: status must be one of {', '.join(FLOOR_STATUSES)}")
        if c["status"] == "n/a" and not str(c.get("reason") or "").strip():
            fail(f"{name}: n/a needs a reason (the tool is missing, no UI…)")
        sev = str(c.get("severity") or "").lower() or None
        if sev and sev not in ("critical", "high", "medium", "low"):
            fail(f"{name}: severity must be critical, high, medium or low")
        out[name] = {k: v for k, v in {"status": c["status"], "severity": sev, "detail": str(c.get("detail") or "")[:300] or None,
                                       "reason": str(c.get("reason") or "")[:300] or None, "tool": c.get("tool")}.items() if v}
    created, reused = [], []
    for name, c in out.items():
        if c["status"] != "fail":
            continue
        src = f"hard_floor:{name}"
        tid = next((k for k, v in store.tasks().items() if v.get("milestone") == a.milestone and v.get("source") == src
                    and v.get("status") not in FINISHED), None)
        if tid:
            reused.append(tid)
            c["task"] = tid
            continue
        tid = store.new_task_id()
        t = {"title": f"Hard floor: {name} fails" + (f" ({c['detail'][:80]})" if c.get("detail") else ""), "milestone": a.milestone,
             "type": "fix", "status": "todo", "deps": [], "acceptance": [f"{name} passes in the round's deterministic checks"],
             "test_notes": f"re-run the {name} check; it must pass", "files": [], "commit": None, "blocked_reason": None,
             "source": src, "started_at": None, "done_at": None}
        store.tasks()[tid] = t
        append_task_to_plan(store, store.dev / "plan.md", a.milestone, ms["title"], tid, t)
        created.append(tid)
        c["task"] = tid
    ms["hard_floor"] = {"at": now(), "checks": out}
    store.save()
    fails = [n for n, c in out.items() if c["status"] == "fail"]
    store.log(f"hard-floor {a.milestone}: " + (", ".join(f"{n} fail" for n in fails) or "all pass"))
    store.event("hard_floor", scope=a.milestone, failed=len(fails), checks=len(out))
    for n, c in out.items():
        print(f"{n}: {c['status']}" + (f" ({c.get('severity')})" if c.get("severity") else "")
              + (f" · {c.get('reason') or c.get('detail')}" if c.get("reason") or c.get("detail") else "")
              + (f" -> {c['task']}" if c.get("task") else ""))
    for n in ("tests", "lint"):
        if out.get(n, {}).get("status") == "n/a":
            print(f"finding: no {n} in the project is a high finding (record it in the round, §7)")
    print(f"{a.milestone} hard floor: " + (f"{len(fails)} failing ({', '.join(fails)}); the gate cannot pass" if fails else "pass"))


def floor_problems(ms: dict) -> list[tuple[str, bool]]:
    """(problem, may be forced) for the recorded hard floor of a milestone."""
    out = []
    for n, c in ((ms.get("hard_floor") or {}).get("checks") or {}).items():
        if c.get("status") == "fail":
            hard = n in NEVER_FORCED or (n == "deps" and c.get("severity") == "critical")
            out.append((f"hard floor: {n} fails" + (f" ({c['severity']})" if c.get("severity") else "")
                        + (f" -> {c['task']}" if c.get("task") else ""), not hard))
    return out


def ci_provider(store: Store) -> str:
    cfg = {**DEFAULT_AUTONOMY["ci"], **(store.state.get("autonomy", {}).get("ci") or {})}
    p = cfg["provider"]
    if p != "auto":
        return p
    wf = store.root / ".github" / "workflows"
    if wf.is_dir() and any(wf.glob("*.y*ml")):
        return "github"
    if (store.root / ".gitlab-ci.yml").exists():
        return "gitlab"
    return "none"


def ci_cfg(store: Store) -> dict:
    return {**DEFAULT_AUTONOMY["ci"], **(store.state.get("autonomy", {}).get("ci") or {})}


CI_STATUSES = ("success", "failure", "pending", "none")


def _gh_status(store: Store, sha: str) -> tuple[str | None, str | None]:
    """Aggregate GitHub Actions runs of one commit: failure if any failed, pending if any is not finished."""
    try:
        r = subprocess.run(["gh", "run", "list", "--commit", sha, "--json", "status,conclusion,url"], cwd=store.root,
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None, None
    if r.returncode != 0:
        return None, None
    try:
        runs = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None, None
    if not runs:
        return "none", None
    if any(x.get("conclusion") in ("failure", "cancelled", "timed_out", "startup_failure") for x in runs):
        return "failure", next((x.get("url") for x in runs if x.get("conclusion") not in ("success", "skipped", "neutral")), None)
    if any(x.get("status") != "completed" for x in runs):
        return "pending", runs[0].get("url")
    return "success", runs[0].get("url")


def record_ci(store: Store, m: str, sha: str, status: str, url: str | None) -> dict:
    ms = store.milestones()[m]
    prev = ms.get("ci") or {}
    since = prev.get("since") if prev.get("sha") == sha and prev.get("status") == "pending" else None
    rec = {"provider": ci_provider(store), "sha": sha, "status": status, "at": now(), **({"url": url} if url else {})}
    if status == "pending":
        rec["since"] = since or now()
    ms["ci"] = rec
    return rec


def cmd_ci(store: Store, a: argparse.Namespace) -> None:
    """CI as the verdict of the gate's deterministic signals (§7). `check` asks the provider (gh for GitHub) about the
    round's commit and records the status; `record` stores a status read elsewhere; `status` prints what is recorded."""
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    ms = store.milestones()[a.milestone]
    prov, cfg = ci_provider(store), ci_cfg(store)
    if a.action == "status":
        rec = ms.get("ci") or {}
        print(f"ci provider {prov} · required {str(cfg['required']).lower()} · " + (f"{a.milestone} {rec.get('status')} at {rec.get('sha', '?')[:12]}" if rec else "nothing recorded"))
        return
    sha = a.sha or _git(store, "rev-parse", "HEAD")
    if not sha:
        fail("no commit: pass --sha")
    if a.action == "record":
        if a.status not in CI_STATUSES:
            fail(f"--status must be one of {', '.join(CI_STATUSES)}")
        status, url = a.status, a.url
    else:
        if prov == "none":
            print("ci: none (no CI detected" + (", autonomy.ci.required is on: ask the user once and record an ADR)" if cfg["required"] else ")"))
            return
        if prov != "github":
            fail(f"ci check reads GitHub only; read the {prov} pipeline of {sha[:12]} and run `ci record {a.milestone} --sha {sha} --status <s>`")
        status, url = _gh_status(store, sha)
        if status is None:
            fail(f"gh could not read the runs of {sha[:12]}; read them another way and run `ci record {a.milestone} --sha {sha} --status <s>`")
    rec = record_ci(store, a.milestone, sha, status, url)
    store.save()
    store.log(f"ci {a.milestone} {status} at {sha[:12]}")
    store.event("ci", scope=a.milestone, status=status, provider=prov)
    print(f"{a.milestone} ci {status} at {sha[:12]}" + (f" · {url}" if url else ""))
    if status == "pending":
        waited = _secs_between(rec["since"], now()) or 0
        if waited >= int(cfg["timeout_min"]) * 60:
            print(f"ci_timeout: pending for {waited // 60} min (limit {cfg['timeout_min']}); pause point ci_timeout "
                  f"({pause_action(store.state, 'ci_timeout')})")
        else:
            print(f"ci pending: check again (timeout in {max(0, int(cfg['timeout_min']) * 60 - waited) // 60} min)")


def ci_problems(store: Store, ms: dict) -> list[tuple[str, bool]]:
    cfg = ci_cfg(store)
    prov = ci_provider(store)
    if not cfg["required"] or prov == "none":
        return []
    rec = ms.get("ci") or {}
    if rec.get("status") == "success":
        return []
    if not rec:
        return [(f"ci: no {prov} result recorded for the round's commit (run `ci check <M>`)", True)]
    return [(f"ci: {prov} is {rec['status']} at {str(rec.get('sha'))[:12]} (the CI verdict wins over local runs)", True)]


def exit_result(store: Store, m: str, scores: str | None) -> dict | None:
    path = Path(scores) if scores else store.dev / "qa" / m / "scores.json"
    if not path.is_absolute():
        path = store.root / path
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("exit")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def gate_problems(store: Store, m: str, a: argparse.Namespace) -> list[tuple[str, bool]]:
    """What stops a gate from passing besides the score: the hard floor, CI and the exit check (§7)."""
    ms = store.milestones()[m]
    out: list[tuple[str, bool]] = []
    if hard_floor_on(store):
        if ms.get("hard_floor"):
            out += floor_problems(ms)
        elif store.state.get("exit_checks"):
            out.append((f"hard floor: no deterministic checks recorded for {m} (run `hard-floor {m} --from <json>`)", True))
    out += ci_problems(store, ms)
    if explicit_exit(ms):
        ex = exit_result(store, m, a.scores)
        if not ex:
            out.append((f"exit_check: no result in scores.json (spec-tracer runs {m}'s exit_check)", True))
        elif ex.get("result") != "pass":
            failed = [c.get("check") for c in ex.get("checks") or [] if c.get("result") != "pass"]
            out.append(("exit_check failed" + (f": {', '.join(map(str, failed))}" if failed else ""), True))
    return out


def debt_counts(store: Store) -> dict:
    seen, total, medium = set(), 0, 0
    for f in deferred_findings(store):
        key = (f.get("scope"), f.get("id"))
        if key in seen:
            continue
        seen.add(key)
        total += 1
        medium += f.get("severity") == "medium"
    cap = quality_cfg(store).get("deferred_cap") or {}
    over = (bool(cap.get("total")) and total > cap["total"]) or (bool(cap.get("medium")) and medium > cap["medium"])
    return {"total": total, "medium": medium, "cap_total": cap.get("total"), "cap_medium": cap.get("medium"), "over": over}


def debt_needs(store: Store) -> list[dict]:
    """The Needs-you item for deferred debt above the cap (§7), raised at a gate close until the user decides."""
    al = store.state.get("debt_alert")
    if not al or al.get("decided_at"):
        return []
    d = debt_counts(store)
    if not d["over"]:
        return []
    return [{"kind": "debt_over_cap", "total": d["total"], "medium": d["medium"], "cap_total": d["cap_total"],
             "cap_medium": d["cap_medium"], "since": al.get("at"), "milestone": al.get("milestone"),
             "text": f"Deferred debt above the cap: {d['total']} open (cap {d['cap_total']}), {d['medium']} medium (cap {d['cap_medium']})",
             "actions": ["promote", "accept", "cooldown"]}]


def check_debt(store: Store, m: str) -> dict | None:
    d = debt_counts(store)
    al = store.state.get("debt_alert")
    if d["over"] and (not al or al.get("decided_at")) and (not al or d["total"] > int(al.get("total_at_decision") or 0)):
        store.state["debt_alert"] = {"at": now(), "milestone": m, "total": d["total"], "medium": d["medium"]}
        return d
    return None


def cmd_debt(store: Store, a: argparse.Namespace) -> None:
    """Deferred debt (§7). status: the counts and the cap. decide promote|accept|cooldown: the user's decision on the
    Needs-you item (promote = the chosen findings become standard issues, through the issue skill; accept = an ADR
    lists them; cooldown = cool-down is turned on for the next milestone with these items)."""
    store.load()
    d = debt_counts(store)
    if a.action == "status":
        if a.json:
            print(json.dumps({**d, "needs": debt_needs(store)}, indent=2))
        else:
            print(f"deferred debt: {d['total']} open (cap {d['cap_total']}) · {d['medium']} medium (cap {d['cap_medium']})"
                  + (" · above the cap" if d["over"] else ""))
        return
    decision, ref = a.decision, None
    if decision not in ("promote", "accept", "cooldown"):
        fail("decide needs promote, accept or cooldown")
    al = store.state.setdefault("debt_alert", {"at": now(), "milestone": None, "total": d["total"], "medium": d["medium"]})
    al.update(decided_at=now(), decision=decision, total_at_decision=d["total"], **({"request": ref} if ref else {}))
    if decision == "cooldown":
        auto = store.state.setdefault("autonomy", _copy(DEFAULT_AUTONOMY))
        auto["cooldown"] = {**DEFAULT_AUTONOMY["cooldown"], **(auto.get("cooldown") or {}), "enabled": True}
    store.save()
    store.log(f"debt decide {decision}" + (f" ({ref})" if ref else ""))
    store.event("debt", transition=decision, total=d["total"], medium=d["medium"])
    print({"promote": "debt: promote the chosen deferred findings with /dev-kit:issue --from <F-id> <M> (class standard)",
           "accept": "debt: accepted; record an ADR listing the open deferred findings (DS deferred lists them)",
           "cooldown": "debt: cool-down is on; after the next gate `cooldown <M>` takes these items into the next milestone"}[decision])


def fix_rounds_allowed(store: Store, m: str) -> int:
    """The agreed fix rounds of a milestone's gate: the project's setting plus the rounds the user added for it."""
    base = int((store.state.get("autonomy") or {}).get("max_fix_rounds_per_gate") or DEFAULT_AUTONOMY["max_fix_rounds_per_gate"])
    return base + int((store.milestones().get(m) or {}).get("extra_fix_rounds") or 0)


def cmd_qa_decide(store: Store, a: argparse.Namespace) -> None:
    """Needs you › QA rounds used up (§7): continue fixing with more rounds, accept the milestone as it is with an ADR,
    or replan."""
    store.load()
    m_id, decision, rounds, note = a.milestone, a.decision, a.rounds, a.note
    if m_id not in store.milestones():
        fail(f"unknown milestone {m_id}")
    if decision not in ("continue", "accept", "replan"):
        fail("qa-decide needs continue, accept or replan")
    m = store.milestones()[m_id]
    if m.get("gate") in ("passed", "skipped"):
        fail(f"{m_id} is already closed")
    held = [k for k, t in sorted(store.tasks().items()) if t["milestone"] == m_id and t["status"] == "blocked"
            and "rounds_exhausted" in str(t.get("blocked_reason") or "")]
    out = ""
    if decision == "continue":
        if not 1 <= rounds <= 5:
            fail("--rounds takes 1 to 5")
        m["extra_fix_rounds"] = int(m.get("extra_fix_rounds") or 0) + rounds
        for k in held:
            t = store.tasks()[k]
            t["status"], t["blocked_reason"] = "todo", None
        out = f"{m_id}: +{rounds} fix round(s) ({fix_rounds_allowed(store, m_id)} in all); next: /dev-kit:qa {m_id}"
    elif decision == "accept":
        if not note:
            fail("accepting with an ADR needs --note: why the milestone ships as it is")
        adr = append_adr(store, f"Accept {m_id} after the QA rounds were used up", [
            f"- context: {int(m.get('qa_runs') or 0) - 1} fix rounds used of {fix_rounds_allowed(store, m_id)}; open fixes: {', '.join(held) or 'none'}",
            f"- decision: {note}", "- consequence: the open fixes are dropped; the gate is forced with this ADR"], source="user")
        for k in held:
            t = store.tasks()[k]
            t.update(status="dropped", blocked_reason=None, dropped_reason=f"accepted with {adr}", dropped_at=now())
        m["accepted_adr"] = adr
        out = f"{m_id}: accepted with {adr}; next: DS gate {m_id} passed --force --note \"{adr}: accepted after the QA rounds\""
    else:
        m["replan_requested"] = now()
        out = f"{m_id}: replan; next: /dev-kit:plan {m_id} (the blocked fixes wait for the new plan)"
    store.save()
    store.log(f"qa-decide {m_id} {decision}")
    store.event("qa_decision", scope=m_id, decision=decision, rounds=rounds if decision == "continue" else None)
    print(out)


def cmd_task_decide(store: Store, a: argparse.Namespace) -> None:
    """Needs you › a blocked task (unblock with a note, skip to the next milestone, drop with a reason) or an open
    hotfix (run it now, drop it)."""
    store.load()
    tid, decision, note = a.task, a.decision, a.note
    t = store.task(tid)
    if t["status"] in FINISHED:
        fail(f"{tid} is {t['status']}")
    if decision == "unblock":
        if t["status"] != "blocked":
            fail(f"{tid} is {t['status']}, not blocked")
        t.update(status="todo", blocked_reason=None)
        t.pop("blocked_by", None)
        if note:
            t["unblock_note"] = note
        out = f"{tid} todo" + (f" (note: {note})" if note else "")
    elif decision == "skip":
        order = store.milestone_order()
        later = [x for x in order[order.index(t["milestone"]) + 1:] if store.milestones()[x].get("gate", "pending") == "pending"]
        if not later:
            fail(f"no open milestone after {t['milestone']}: replan with /dev-kit:plan")
        held = (t["status"], t.get("blocked_reason"))
        t["status"] = "todo"  # only a task not started moves; it stays blocked in the milestone it goes to
        apply_plan_ops(store, [{"op": "move_task", "task": tid, "milestone": later[0]}], dry_run=False, as_json=False, label="task-decide")
        t = store.task(tid)
        if held[0] == "blocked":
            t["status"], t["blocked_reason"] = held
            store.save()
        store.log(f"task-decide {tid} skip to {later[0]}")
        return
    elif decision == "drop":
        if not note:
            fail("dropping a task needs --note: the reason")
        t.update(status="dropped", blocked_reason=None, dropped_reason=note, dropped_at=now())
        t.pop("blocked_by", None)
        issue_sync(store, t)
        out = f"{tid} dropped: {note}"
    elif decision == "run":
        if t.get("lane") != "hotfix":
            fail(f"{tid} is not a hotfix: run is for the hotfix lane")
        if t["status"] == "blocked":
            t.update(status="todo", blocked_reason=None)
        out = f"{tid}: next: /dev-kit:implement {tid}"
    else:
        fail("task-decide needs unblock, skip, drop or run")
    store.save()
    store.log(f"task-decide {tid} {decision}" + (f": {note}" if note else ""))
    store.event("task", task=tid, transition={"unblock": "unblock", "drop": "drop"}.get(decision, decision), type=t.get("type"),
                milestone=t.get("milestone"))
    print(out)


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
        probs = gate_problems(store, a.milestone, a)
        hard = [p for p, ok in probs if not ok]
        if hard:
            fail(f"gate {a.milestone} cannot pass, not even with --force: " + "; ".join(hard))
        if probs and not a.force:
            fail(f"gate {a.milestone} cannot pass: " + "; ".join(p for p, _ in probs) + " (whatever the score; --force only with a recorded decision)")
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
        if a.note and a.value != "passed":  # why the round failed, for its chip on the board ("2 blockers", "floor: deps")
            m.setdefault("round_reasons", {})[str(m["qa_runs"])] = a.note[:80]
    # past the agreed number of fix rounds the next round is the user's (or the policy's) decision, not automatic:
    # the open fix tasks of this milestone go to Blocked with the reason, so `next` stops picking them
    max_rounds = fix_rounds_allowed(store, a.milestone)
    exhausted = []
    if a.count_run and a.value == "pending" and m["qa_runs"] > max_rounds:
        for tid, t in store.tasks().items():
            if t.get("milestone") == a.milestone and t.get("type") == "fix" and t.get("status") in ("todo", "in_progress"):
                t["status"] = "blocked"
                t["blocked_reason"] = (f"QA round limit reached ({m['qa_runs'] - 1} fix rounds of {max_rounds}; rounds_exhausted): "
                                       f"keep fixing, accept with an ADR, or replan")
                exhausted.append(tid)
    flow = write_flow(store, a.milestone) if a.value == "passed" else None
    debt = check_debt(store, a.milestone) if a.value == "passed" or a.count_run else None
    store.save()
    for tid in exhausted:
        store.log(f"block {tid}: {store.tasks()[tid]['blocked_reason']}")
        store.event("task", task=tid, transition="block", type="fix", milestone=a.milestone)
    if flow:
        store.event("flow", scope=a.milestone, **{k: flow[k] for k in tel.SCHEMA["flow"] if k != "scope" and flow.get(k) is not None})
    store.event("gate", scope=a.milestone, value=a.value, score=a.score, qa_runs=m.get("qa_runs", 0),
                forced=bool(a.force and a.value == "passed"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "passed" else None)
    store.log(f"gate {a.milestone} {a.value}" + (f" score={a.score}" if a.score is not None else "") + (f" ({a.note})" if a.note else ""))
    print(f"{a.milestone} gate: {a.value}" + (f" (score {a.score})" if a.score is not None else ""))
    if exhausted:
        print(f"{a.milestone}: {m['qa_runs'] - 1} fix rounds used of {max_rounds} (rounds_exhausted); blocked {', '.join(exhausted)}")
    if debt:
        store.event("debt", transition="over_cap", total=debt["total"], medium=debt["medium"])
        print(f"debt_over_cap: {debt['total']} deferred findings open (cap {debt['cap_total']}), {debt['medium']} medium "
              f"(cap {debt['cap_medium']}); Needs you: promote to issues, accept with an ADR, or use the next cool-down")
    if a.value == "passed" or a.count_run:
        queue_notice(store, f"dev-kit · {a.milestone} gate {a.value}" + (f" ({a.score})" if a.score is not None else "")
                     + f" · {next_command(store)}")
    if a.value == "passed":
        close_loop(store, a.milestone)
        print_tip(store, "gate_passed", a)


# ---------------------------------------------------------------- flow metrics (conventions.md §13)

def _secs_between(a: object, b: object) -> int | None:
    try:
        x = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        y = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, round((y - x).total_seconds()))


def flow_metrics(store: Store, m: str, events: list[dict] | None = None) -> dict:
    """Cycle of one milestone over its whole history (every session): time, QA rounds, fixes, deferred findings,
    cost and scope added after the freeze. Written to .dev/qa/<M>/flow.json when the gate passes; read by feedback.
    The gate itself uses only the last round (the final state); this is for improving the kit."""
    if events is None:
        events, _ = tel.read_events(store.dev)
    ms = store.milestones().get(m) or {}
    ts = {k: v for k, v in store.tasks().items() if v.get("milestone") == m and v.get("status") != "dropped"}
    starts = sorted(str(v["started_at"]) for v in ts.values() if v.get("started_at"))
    end = ms.get("passed_at") or now()
    planned = [k for k, v in ts.items() if not (v.get("type") == "fix" and str(v.get("source") or "").startswith(("qa/", "hard_floor:")))]
    fixes = [k for k, v in ts.items() if v.get("type") == "fix" and str(v.get("source") or "").startswith(("qa/", "hard_floor:"))]
    scopes = {m, *ts}
    working = sum(float(e.get("duration_s") or 0) for e in events if e["event"] == "skill_end" and e.get("scope") in scopes)
    if not working:  # no skill windows logged: the agents' own time
        working = sum(float(e.get("duration_s") or 0) for e in events if e["event"] == "agent_end" and e.get("scope") in scopes)
    deferred = [f for f in deferred_findings(store) if f.get("scope") == m]
    out = {
        "milestone": m, "at": now(), "gate": ms.get("gate", "pending"), "score": ms.get("score"),
        "tasks": len(planned), "cycle_time_s": _secs_between(starts[0], end) if starts else None,
        "working_time_s": round(working), "qa_rounds": int(ms.get("qa_runs", 0)),
        "fix_tasks": len(fixes), "fixes_per_task": round(len(fixes) / len(planned), 2) if planned else 0.0,
        "deferred_open": len({str(f.get("id")) for f in deferred}),
        "scope_added_after_freeze": sum(1 for v in ts.values() if v.get("scope_after_freeze")),
        "human_wait_s": human_wait(events, scopes),  # questions, permissions, checkpoints raised during it (§19)
        "cost_usd": None, "tokens": None, "cost_per_task": None, "orchestration_usd": None, "agents_usd": None,
    }
    try:
        import dev_cost
        c = dev_cost.milestone_split(store.dev, m)
        if c["requests"]:
            out.update(cost_usd=c["usd"], tokens=c["tokens"], orchestration_usd=c["orchestration_usd"], agents_usd=c["agents_usd"],
                       cost_per_task=round(c["usd"] / len(planned), 4) if planned else None)
    except Exception:  # noqa: BLE001 - cost is best effort (no transcripts, no prices)
        pass
    return out


def cycle_grade(f: dict) -> tuple[int, list[str]]:
    """The kit's grade of a milestone's cycle (§13): 100 − 10 per QA round beyond the first − fixes per task × 20
    (max 20) − 2 per deferred finding left open (max 20) − 5 per item added after the freeze (max 15)."""
    reasons, score = [], 100
    rounds = int(f.get("qa_rounds") or 0)
    if rounds > 1:
        score -= 10 * (rounds - 1)
        reasons.append(f"{rounds} rounds (-{10 * (rounds - 1)})")
    pen = min(20, round(20 * float(f.get("fixes_per_task") or 0)))
    if pen:
        score -= pen
        reasons.append(f"{f.get('fix_tasks')} fixes (-{pen})")
    pen = min(20, 2 * int(f.get("deferred_open") or 0))
    if pen:
        score -= pen
        reasons.append(f"{f.get('deferred_open')} deferred (-{pen})")
    pen = min(15, 5 * int(f.get("scope_added_after_freeze") or 0))
    if pen:
        score -= pen
        reasons.append(f"{f.get('scope_added_after_freeze')} added after freeze (-{pen})")
    return max(0, score), reasons


def write_flow(store: Store, m: str) -> dict:
    f = flow_metrics(store, m)
    store.stage(store.dev / "qa" / m / "flow.json", json.dumps(f, indent=2) + "\n")
    return f


def close_loop(store: Store, m: str) -> None:
    """Slow feedback loop at a passed gate: the predicted × real report and dev_router.py learn (never fails the gate)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            cmd_risk_report(store, argparse.Namespace(milestone=m, all=False, json=False))
        print(buf.getvalue().strip())
        if risk.model_policy(store.state)["router"].get("mode") != "off":
            r = router.learn(store, m)
            print(f"router learned {', '.join(r['milestones'])}: {r['records']} record(s)"
                  + "".join(f"; weight {c['signal']} {c['from']:+d} -> {c['to']:+d}" for c in r["weight_changes"]))
    except Exception as e:  # noqa: BLE001
        print(f"note: risk report or router learn skipped ({type(e).__name__}: {e})", file=sys.stderr)


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
    gap = False
    if a.type in ("skill_start", "skill_end"):
        # the duration is measured here, never taken from the skill (§13)
        fields.pop("duration_s", None)
        try:
            tel.validate(a.type, fields, set())
        except ValueError as e:
            fail(f"event rejected: {e}")
        dur = tel.skill_clock(store.dev, a.type, fields.get("skill"), fields.get("scope"))
        if a.type == "skill_end":
            fields["duration_s"] = dur
            gap = dur is None
    try:
        rec = tel.emit(store.dev, a.type, fields, rotate_session=(a.type == "session_start"))
        if gap:
            tel.emit(store.dev, "telemetry_gap", {"kind": "skill_end_without_start", "skill": fields.get("skill"),
                                                  "scope": fields.get("scope")})
    except ValueError as e:
        fail(f"event rejected: {e}")
    print(f"event {rec['event']} recorded (session {rec['session']})"
          + (f" · {rec['duration_s']} s" if a.type == "skill_end" and rec.get("duration_s") is not None else "")
          + (" · no matching skill_start: duration not measured (telemetry_gap)" if gap else ""))


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


def _stage_tokens(store: Store, mode: str, since: str | None) -> dict | None:
    try:
        import dev_cost
        return dev_cost.stage_tokens(store.dev, mode, since) or None
    except Exception:  # noqa: BLE001
        return None


def session_cycles(store: Store, period_events: list[dict]) -> list[dict]:
    """Every milestone the period touched, read over its whole history: the final state (last round's score, as the
    gate) and the cycle (rounds, fixes, deferred, time, cost), with the kit's cycle grade (§13)."""
    touched: list[str] = []
    for e in period_events:
        for k in ("scope", "milestone"):
            v = str(e.get(k) or "")
            v = v if v in store.milestones() else (store.tasks().get(v) or {}).get("milestone") or ""
            if v and v not in touched:
                touched.append(v)
    all_events, _ = tel.read_events(store.dev)
    out = []
    for m in sorted(touched, key=mkey):
        p = store.dev / "qa" / m / "flow.json"
        try:
            f = json.loads(p.read_text(encoding="utf-8")) if store.milestones()[m].get("gate") == "passed" else None
        except (OSError, json.JSONDecodeError):
            f = None
        if f is None and store.milestones()[m].get("gate") == "passed" and not (store.dev / "qa" / m / "flow.json").exists() \
                and (store.milestones()[m].get("passed_at") or "") < str((store.state.get("migrated") or {}).get("v2_at") or "0"):
            out.append({"milestone": m, "gate": "passed", "score": store.milestones()[m].get("score"), "no_data": True,
                        "cycle_grade": None, "cycle_reasons": ["closed before 3.0: no cycle data"]})
            continue
        f = f or flow_metrics(store, m, all_events)
        g, why = cycle_grade(f)
        out.append({**f, "cycle_grade": g, "cycle_reasons": why})
    return out


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
        rep = tel.stage_report(events, store.state, cycles=session_cycles(store, events), tokens=_stage_tokens(store, mode, a.since))
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
              "report": tel.stage_report(events, store.state, cycles=session_cycles(store, events), tokens=_stage_tokens(store, mode, a.since)),
              "events": events if a.events else []}
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
    why_dep = parse_dep_reasons(t.get("dep_reasons"))
    deps = [f"{d} ({(store.tasks()[d].get('commit') or '')[:7] or 'no commit'}) {store.tasks()[d]['title']}" + (f" - needed because {why_dep[d]}" if why_dep.get(d) else "")
            for d in t.get("deps") or [] if d in store.tasks()]
    hist = led.load(store.dev).get(f"task:{a.task}")
    kit = Path(__file__).resolve().parents[1]
    out = [f"Task: {a.task} — {t['title']} (milestone {t['milestone']}, type {t['type']})",
           f"Scope: {a.task}", f"Kit root: {kit}", f"Project root: {store.root}",
           f"Language for prose (report): {store.state.get('language') or 'en'} · application language (UI copy): {app_lang}",
           f"Base commit: {_git(store, 'rev-parse', '--short', 'HEAD') or '-'}"]
    wts = [r for r in open_slots(store).values() if r.get("task") == a.task and r.get("worktree")]
    if wts:
        out[-1] = f"Base commit: {wts[0]['base_sha'][:7]} ({wts[0]['base_ref']})"
        out += [f"Worktree: {wts[0]['worktree']} (branch {wts[0]['branch']}). Work only there: first `cd {wts[0]['worktree']}`; "
                "never edit the main checkout (the fence denies it)."]
    out += ["", "Acceptance:"]
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
    known = facts_for(store, t.get("files") or [], t.get("acceptance") or [])
    if known:
        out += ["", "Verified facts (.dev/facts.md; trust them, and record what you verify with `dev_state.py fact add`):"]
        out += [f"  - {k} {f['text']} (evidence: {f['evidence']} @{f.get('sha') or '-'})" for k, f in known]
    lessons = lesson_lines(store, "implementer")
    if lessons:
        out += ["", "Lessons for this role in this project (.dev/lessons/implementer.md):"] + [f"  - {x}" for x in lessons]
    r = safe_route(store, a.task)
    if r:
        out += ["", risk.tier_line(r), router.route_line(r)]
    print("\n".join(out))


def risk_args(a: argparse.Namespace) -> dict:
    """Risk fields given on the command line (add-task, set-risk), normalised as parse_plan stores them."""
    out: dict = {}
    for k in ("risk", "complexity", "uncertainty", "tier"):
        v = getattr(a, k, None)
        if v not in (None, ""):
            out[k] = v.strip().lower()
    for k in ("risk_reasons", "tier_reason"):
        v = getattr(a, k, None)
        if v not in (None, ""):
            out[k] = v.strip()
    if getattr(a, "opportunity", None) not in (None, ""):
        out["opportunity"] = [o for o in risk.parse_opportunity(a.opportunity) if o != "none"]
    return out


def cmd_tier(store: Store, a: argparse.Namespace) -> None:
    """Risk tier of a task and its model/effort route (the orchestrator passes final_model and final_effort)."""
    store.load()
    store.task(a.task)
    r = router.route_task(store, a.task)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print(risk.tier_line(r))
        print(router.route_line(r))


def cmd_set_risk(store: Store, a: argparse.Namespace) -> None:
    """Set or clear (value `-`) the risk fields of a planned task in plan.md and state together (conventions.md §4)."""
    store.load()
    t = store.task(a.task)
    vals = risk_args(a)
    clear = [k for k in risk.RISK_FIELDS if getattr(a, k, None) == "-"]
    for k in clear:
        vals.pop(k, None)
    if not vals and not clear:
        fail("nothing to set: pass --risk, --complexity, --uncertainty, --opportunity, --risk-reasons or --tier/--tier-reason")
    new = {**t, **vals}
    for k in clear:
        new.pop(k, None)
    probs = risk.check_risk_fields(a.task, new)
    if probs:
        fail("; ".join(probs))
    plan = store.dev / "plan.md"
    if plan.exists():
        doc = PlanDoc(store.read_text(plan))
        i = doc.find(a.task)
        if i is None:
            fail(f"{a.task} has no section in plan.md")
        kept, skip = [], False  # a risk field goes with its sub-items (multi-line risk_reasons)
        for ln in doc.segs[i]["lines"]:
            m = FIELD_RE.match(ln)
            if m:
                skip = m.group(1) in risk.RISK_FIELDS
            if not skip:
                kept.append(ln)
        doc.segs[i]["lines"] = kept + risk_lines(new)
        store.stage(plan, doc.text())
    for k in risk.RISK_FIELDS:
        if k in new:
            t[k] = new[k]
        else:
            t.pop(k, None)
    store.save()
    store.log(f"set-risk {a.task} " + " ".join(f"{k}={v}" for k, v in vals.items()) + (f" cleared={','.join(clear)}" if clear else ""))
    info = risk.task_tier(store, a.task)
    print(f"{a.task}: " + risk.tier_line(info))


def cmd_risk_profile(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone}")
    prof = risk.risk_profile(store, a.milestone)
    if a.json:
        print(json.dumps(prof, indent=2))
        return
    flags = [k.replace("touches_", "") for k in ("touches_auth_send_secrets", "touches_schema", "touches_data_jobs_send") if prof[k]]
    print(f"{a.milestone} risk profile: {prof['profile']} · max tier {prof['max_tier'] or '-'} · touches {', '.join(flags) or 'nothing risky'}")
    if prof["high_risk_tasks"]:
        print(f"  high-risk tasks: {', '.join(prof['high_risk_tasks'])}"
              + (f" · seams: {', '.join(f'{x}→{y}' for x, y in prof['seams'])}" if prof["seams"] else ""))
    print("  round-1 auditors: " + ", ".join(f"{k} {v}" for k, v in prof["auditors"].items()))


def risk_report_md(store: Store, m: str, rows: list[dict], summ: dict) -> str:
    mm = store.milestones().get(m, {})
    retro = any(r["retro"] for r in rows)
    out = [f"# Risk report — {m}", "",
           f"> Predicted tier (dev_risk.py rule, router route) against what happened. Generated {today()} by `dev_state.py risk-report`.",
           "> Findings are attributed by file (a finding belongs to every task whose files or commit contain its file).", ""]
    if retro:
        out += ["> predicted tier is retroactive (computed after the fact) for tasks started before the risk rule existed.", ""]
    out += ["| task | tier (score) | arm | findings c/h/m/l | rounds | time | tokens | readings |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        f = r["findings"]
        out.append(f"| {r['task']} | {r['tier']} ({r['score']}){' retro' if r['retro'] else ''} | {r['arm'] or '-'}"
                   f"{' routed' if r['routed'] else ''} | {f['critical']}/{f['high']}/{f['medium']}/{f['low']} | {r['rounds']} | "
                   f"{str(round(r['duration_s'] / 60, 1)) + ' min' if r['duration_s'] else '-'} | {r['tokens'] or '-'} | "
                   f"{', '.join(r['readings']) or '-'} |")
    out += ["", "## Per tier", "", "| tier | tasks | escape rate | rounds per task | tokens | agent time |", "|---|---|---|---|---|---|"]
    for tier, b in summ.items():
        out.append(f"| {tier} | {b['tasks']} | {b['escape_rate']:.0%} | {b['rounds_per_task']} | {b['tokens']} | {round(b['duration_s'] / 60, 1)} min |")
    agent_s = sum(r["duration_s"] for r in rows)
    out += ["", f"QA rounds: {mm.get('qa_runs', 0)} · implementer agent time {round(agent_s / 60, 1)} min "
            "(the rest of the milestone's wall time is platform time: tests, deploys, jobs, QA)", ""]
    reads = sorted({x for r in rows for x in r["readings"]})
    if reads:
        out += ["## Readings", ""] + [f"- **{x}**: {risk.READING_TEXT[x]} ({', '.join(r['task'] for r in rows if x in r['readings'])})" for x in reads] + [""]
    return "\n".join(out)


def cmd_risk_report(store: Store, a: argparse.Namespace) -> None:
    """Predicted tier × real outcome per task and per tier (conventions.md §9 "Calibration")."""
    store.load()
    try:
        events, _ = tel.read_events(store.dev)
    except Exception:  # noqa: BLE001
        events = []
    ms = store.milestone_order() if a.all else [a.milestone]
    if not a.all and a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone} (or use --all)")
    rows_all, by_m = [], {}
    for m in ms:
        rows = risk.risk_rows(store, m, events)
        by_m[m] = rows
        rows_all += rows
    summ = risk.summarize_rows(rows_all)
    if a.json:
        print(json.dumps({"milestones": by_m, "per_tier": summ}, indent=2))
        return
    if a.all:
        path = store.dev / "qa" / "risk-report.md"
        text = "\n".join(risk_report_md(store, m, by_m[m], risk.summarize_rows(by_m[m])) for m in ms if by_m[m])
    else:
        path = store.dev / "qa" / a.milestone / "risk-report.md"
        text = risk_report_md(store, a.milestone, rows_all, summ)
    store.stage(path, text + "\n")
    esc = sum(1 for r in rows_all if r["escape"])
    print(f"risk report: {len(rows_all)} task(s), {esc} with a high finding; "
          + ", ".join(f"{t} {b['tasks']} (escape {b['escape_rate']:.0%})" for t, b in summ.items()) + f" -> {path.relative_to(store.root)}")


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
    pw = ((store.state.get("autonomy") or {}).get("production") or {}).get("when")
    rid = release_of(store, a.milestone) if a.milestone else None
    f = (store.state.get("flags") or {}).get(flag_name(rid)) if rid else None
    if f and a.env == "production":
        rec["flag"] = {"name": flag_name(rid), "state": f["state"]}  # what users see of it: nothing while it is off
        if pw == "per_milestone_flagged" and f["state"] == "on" and release_status(store, rid)["status"] not in ("deploying_prod", "released"):
            fail(f"{flag_name(rid)} is on before {rid} is approved; turn it off first (DS flag set {flag_name(rid)} off)")
    d["history"] = (d.get("history") or [])[-19:] + [rec]
    if a.status == "ok":
        d["current"] = rec
    store.save()
    store.log(f"deploy {a.env} {a.status} {a.sha[:7]}" + (f" migr={a.migration}" if a.migration else ""))
    store.event("deploy", scope=a.milestone or "other", env=tel.scope_token(a.env), status=a.status)
    print(f"deploy {a.env}: {a.status} ({a.sha[:7]})" + (f" · {rec['flag']['name']} {rec['flag']['state']}" if rec.get("flag") else ""))


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
    store.stage(store.dev / "issues.md", "\n".join(out) + "\n")


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


def check_issue_class(iclass: str | None, severity: str | None, reason: str | None) -> None:
    """§15: a low-severity item is intangible, a high/critical one is never intangible (unless --force-class "<reason>")."""
    if reason:
        return
    if iclass == "standard" and severity == "low":
        fail("class standard with severity low: low bugs, polish and debt are intangible (--class intangible), "
             'or keep standard with --force-class "<reason>"')
    if iclass == "intangible" and severity in ("high", "critical"):
        fail(f"class intangible with severity {severity}: use standard (or expedite/current for a bug), "
             'or keep intangible with --force-class "<reason>"')


def cmd_add_issue(store: Store, a: argparse.Namespace) -> None:
    store.load()
    check_issue_fields(a.type, a.cls, a.severity, a.effort, a.force)
    check_issue_class(a.cls, a.severity, a.force_class)
    if a.origin not in ISSUE_ORIGINS:
        fail(f"--origin must be one of {', '.join(ISSUE_ORIGINS)}")
    iid = new_issue_id(store)
    issues(store)[iid] = {
        "title": a.title, "type": a.type, "class": a.cls, "severity": a.severity, "effort": a.effort,
        "status": "open", "affects": [x.strip() for x in (a.affects or "").split(",") if x.strip()],
        "acceptance": a.acceptance or [], "origin": a.origin, "tasks": [], "scheduled_in": None,
        "duplicate_of": None, "created_at": now(), "closed_at": None, "note": a.note,
        "closed_milestones_at_creation": closed_count(store),
        **({"class_reason": a.force_class} if a.force_class else {}),
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
    if a.cls is not None or a.severity is not None:
        check_issue_class(a.cls or i.get("class"), a.severity or i.get("severity"), a.force_class or i.get("class_reason"))
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
        if a.status == "parked" and i["status"] not in ("open", "parked"):
            fail(f"{a.id} is {i['status']}; only an open issue is parked")
        if i["status"] == "parked" and a.status not in ("open", "parked", "wontfix", "duplicate"):
            fail(f"{a.id} is parked; make it open first (it leaves parked only by your decision or a replan)")
        i["status"] = a.status
        if a.status == "parked":
            i["parked_at"] = now()
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
    append_task_to_plan(store, store.dev / "plan.md", milestone, store.milestones()[milestone]["title"], tid, t)
    link_task(store, iid, tid, milestone)
    return tid


def buffer_info(store: Store, m: str) -> dict:
    pct = int(store.state.get("autonomy", {}).get("issue_buffer_pct", DEFAULT_AUTONOMY["issue_buffer_pct"]))
    floor = int(queue_cfg(store.state)["buffer_floor"]) if pct > 0 else 0
    cap = max(floor, -(-planned_count(store, m) * pct // 100))  # ceil, never below the floor (§15)
    used = sum(1 for v in store.tasks().values() if v["milestone"] == m and str(v.get("source") or "").startswith("issue:")
               and v.get("lane") not in ("hotfix", "cooldown"))
    return {"milestone": m, "pct": pct, "capacity": cap, "used": used, "free": max(0, cap - used)}


def cmd_pull_issues(store: Store, a: argparse.Namespace) -> None:
    store.load()
    if a.milestone not in store.milestones():
        fail(f"unknown milestone {a.milestone} (issues never create milestones)")
    if frozen(store, a.milestone):
        print(f"{a.milestone} is frozen since its QA began: no issue is pulled into it (the queue waits for the next milestone)")
        return
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
    if frozen(store, nxt):
        print(f"{nxt} is frozen (its QA began): the cool-down takes nothing into it")
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
            items += [{**f, "disputed": True} for f in ((data.get("disputed") or []) if isinstance(data, dict) else [])]  # §7
            items += [f for f in ((data.get("findings") or []) if isinstance(data, dict) else data)
                      if isinstance(f, dict) and str(f.get("severity")) in ("medium", "low")]
            for f in items:
                if isinstance(f, dict) and not f.get("legacy") and f.get("status") != "closed":
                    out.append({"scope": scope_dir.name, "id": f.get("id"), "severity": f.get("severity"), "title": f.get("title"),
                                **({"disputed": True} if f.get("disputed") else {})})
    return out


def queue_needs(store: Store) -> list[dict]:
    """Needs-you items about the issue queue (§15): the queue above its limit (with the draft of a milestone of the
    queue, sent only by the user) and issues aging without being scheduled. Nothing here changes the plan."""
    cfg = queue_cfg(store.state)
    iss = issues(store)
    waiting = [k for k, v in iss.items() if v["status"] in ("open", "scheduled")]
    remaining = sum(1 for v in store.tasks().values() if v["status"] not in FINISHED)
    out: list[dict] = []
    over_pct = remaining and len(waiting) * 100 > cfg["limit_pct_remaining"] * remaining
    if len(waiting) > cfg["limit"] or (waiting and over_pct):
        size_max = int(((store.state.get("autonomy") or {}).get("milestone_size") or {}).get("max", 12))
        pick = [k for k in queue(store, ("standard", "intangible"))][:size_max]
        pick.sort(key=lambda k: (SEV_RANK.get(iss[k].get("severity"), 4), iss[k]["created_at"], k))
        nxt = f"M{max([mmajor(x) for x in store.milestones()] or [0]) + 1}"
        out.append({"kind": "queue_over_limit", "count": len(waiting), "limit": cfg["limit"],
                    "limit_pct_remaining": cfg["limit_pct_remaining"], "remaining_tasks": remaining,
                    "milestone": nxt, "issues": pick,
                    "draft": {"ops": [{"op": "new_milestone", "milestone": nxt, "title": "Issues"}]
                              + [{"op": "schedule_issue", "issue": k, "milestone": nxt, "force": True} for k in pick]}})
    closed = [v.get("passed_at") for v in store.milestones().values() if v.get("gate") in ("passed", "skipped")]
    for k, v in sorted(iss.items()):
        if v["status"] != "open" or v.get("class") in ("expedite", "change"):
            continue
        base = v.get("closed_milestones_at_creation")
        age = (len(closed) - int(base)) if isinstance(base, int) else sum(1 for p in closed if p and str(p) > str(v.get("created_at")))
        if age >= cfg["aging_milestones"]:
            out.append({"kind": "issue_aging", "issue": k, "milestones": age, "actions": ["schedule_next", "park", "wontfix"]})
    return out


def backlog_data(store: Store) -> dict:
    ts = store.tasks()
    iss = issues(store)
    cur = current_milestone(store)
    hot_open = [k for k, v in ts.items() if v.get("lane") == "hotfix" and v["status"] not in FINISHED]
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
        "needs": all_needs(store), "parked": [k for k, v in iss.items() if v["status"] == "parked"],
        "debt": debt_counts(store),
        "paused": {k: v["blocked_by"] for k, v in store.tasks().items() if v.get("status") == "blocked" and v.get("blocked_by")},
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
    atomic_write(seen_path, json.dumps(seen, indent=1) + "\n")
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


_DEP_LINE = re.compile(r"^-\s+(deps|dep_reasons):")


def artifact_hash(store: Store, name: str) -> str | None:
    paths = artifact_paths(store, name)
    if not paths:
        return None
    h = hashlib.sha256()
    for path in paths:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        body = [ln.rstrip() for i, ln in enumerate(lines) if not (i < 12 and _VOLATILE.match(ln))]
        if name == "plan":  # dependency-only edits are not scope: they keep the plan review valid
            body = [ln for ln in body if not _DEP_LINE.match(ln)]
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
        r = (store.state.get("reviews") or {}).get(rname) or {}
        if r.get("verdict") == "pass" and r.get("stale_reason"):
            reviews.append({"review": rname, "changed": list(arts), "stale_artifacts": [], "reason": r["stale_reason"]})
            continue
        if built and rname == "plan":
            continue
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
    notes: list[str] = []
    pending = {k: v for k, v in tasks.items() if v.get("status") in ("todo", "blocked")}
    for tid, t in pending.items():
        if t.get("risk") not in ("low", "medium"):
            continue
        try:
            info = risk.task_tier(store, tid)
        except Exception:  # noqa: BLE001
            continue
        objective = [s for s in info["reasons"] if s["signal"] not in ("planner_high", "complex", "downgrade_ok")]
        obj_score = sum(s["weight"] for s in objective)
        objective_tier = risk.tier_of_score(obj_score)
        if (t["risk"] == "low" and risk.TIERS.index(objective_tier) >= 2) or (t["risk"] == "medium" and objective_tier == "quality"):
            problems.append({"check": "risk_disagrees", "id": tid,
                             "detail": f"plan says risk {t['risk']} but objective signals give {objective_tier} "
                                       f"({', '.join(s['signal'] for s in objective)})"})
    unjust = unjustified_deps(store.tasks())
    for tid, d in unjust:
        notes.append(f"unjustified_dep: {tid} depends on {d} with no consumes, no common file, not shared and no dep_reasons entry "
                     "(remove the dependency, or add consumes or dep_reasons)")
    try:
        denied: dict[str, int] = {}
        for e in tel.read_events(store.dev)[0]:
            if e["event"] == "fence_deny" and re.fullmatch(r"T-\d+", str(e.get("scope") or "")):
                denied[e["scope"]] = denied.get(e["scope"], 0) + 1
        for tid, n in sorted(denied.items()):
            notes.append(f"fence_denied: {tid} was denied {n} edit(s) outside its files (its files: may be incomplete; "
                         "plan the next tasks of that area with the files they really touch)")
    except (OSError, ValueError):
        pass
    paths = critical_paths(store.tasks())
    for mid, e in paths.items():
        if e["tasks"] >= 3 and e["critical_path"] * 2 > e["tasks"]:
            notes.append(f"critical_path: {mid} has a chain of {e['critical_path']} of {e['tasks']} tasks ({' -> '.join(e['chain'])})")
    without = [k for k, v in pending.items() if not risk.has_planner_fields(v)]
    if without:
        notes.append(f"{len(without)} pending task(s) without risk fields (run plan --annotate-risk to add them)")
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
    return {"problems": problems, "counts": counts, "notes": notes,
            "unjustified_deps": [{"task": t, "dep": d} for t, d in unjust], "critical_path": paths,
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
        for mid, e in (rep.get("critical_path") or {}).items():
            print(f"  {mid}: {e['tasks']} task(s), critical path {e['critical_path']}")
        for x in rep.get("notes") or []:
            print(f"  note: {x}")
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
    r.pop("stale_reason", None)
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
    cp = open_checkpoint(store, a.name) if a.value == "pass" and a.name in CHECKPOINT_TARGETS else None
    store.save()
    if cp:
        store.event("checkpoint", target=a.name, transition="open", round=cp.get("round"))
    store.event("review", scope=tel.scope_token(a.name), value="na" if a.value == "n/a" else a.value, score=a.score, round=r.get("rounds", 0),
                forced=bool(a.force and a.value == "pass"),
                force_source=("policy" if (a.note or "").startswith("policy:") else "user") if a.force and a.value == "pass" else None)
    store.log(f"review {a.name} {a.value}" + (f" score={a.score}" if a.score is not None else ""))
    print(f"review {a.name}: {a.value}" + (f" (score {a.score})" if a.score is not None else "") + f" · rounds {r['rounds']}")
    if cp:
        print(f"checkpoint {a.name}: waiting for the user's confirmation ({CHECKPOINT_TITLE[a.name]}: "
              f"`checkpoint confirm {a.name}` after the user says so); " + ("no milestone that has not started begins before it"
                                                                           if a.name == "plan" else "architecture waits for it"))
        queue_notice(store, f"dev-kit: {CHECKPOINT_TITLE[a.name]} waits for you")
    if a.value == "pass" and a.name == "plan":
        paused = sorted((k for k, v in store.tasks().items() if v.get("status") == "blocked" and v.get("blocked_by")), key=lambda k: int(k[2:]))
        if paused:
            print("paused by a scope change: " + ", ".join(f"{k} ({store.tasks()[k]['blocked_by']})" for k in paused)
                  + "; the replan resolves each one: `unblock T-nnn` (still valid) or `drop T-nnn --reason`")


# ---------------------------------------------------------------- human checkpoints on the PRD and the plan (§19)
CHECKPOINT_TARGETS = ("prd", "plan")
CHECKPOINT_TITLE = {"prd": "Confirm PRD", "plan": "Confirm plan"}
CHECKPOINT_DOC = {"prd": "prd.md", "plan": "plan.md"}


def checkpoints(store: Store) -> dict:
    return store.state.setdefault("checkpoints", {})


def open_checkpoint(store: Store, target: str) -> dict | None:
    """A passed review of the PRD or the plan opens its checkpoint, unless the same version was already confirmed."""
    ver = artifact_hash(store, target)
    cp = checkpoints(store).get(target)
    if cp and cp.get("status") == "confirmed" and cp.get("version") == ver:
        return None
    rnd = int((cp or {}).get("round") or 0) + 1
    hist = (cp or {}).get("history") or []
    checkpoints(store)[target] = {"status": "pending", "version": ver, "created_at": now(), "round": rnd, "history": hist}
    return checkpoints(store)[target]


def checkpoint_pending(store: Store, target: str) -> bool:
    return ((store.state.get("checkpoints") or {}).get(target) or {}).get("status") in ("pending", "adjust")


def checkpoint_needs(store: Store) -> list[dict]:
    out = []
    for t in CHECKPOINT_TARGETS:
        cp = (store.state.get("checkpoints") or {}).get(t) or {}
        if cp.get("status") == "pending":
            out.append({"kind": "checkpoint", "target": t, "title": CHECKPOINT_TITLE[t], "doc": CHECKPOINT_DOC[t],
                        "summary": cp.get("summary"), "version": cp.get("version"), "since": cp.get("created_at"),
                        "round": cp.get("round"), "actions": ["confirm", "adjust"]})
    return out


def all_needs(store: Store) -> list[dict]:
    """Needs-you items the state derives (production health, checkpoints, deferred debt, proposed lessons, the issue
    queue), in that order."""
    return health_needs(store) + checkpoint_needs(store) + debt_needs(store) + lesson_needs(store) + queue_needs(store)


def lesson_needs(store: Store) -> list[dict]:
    """The Needs-you items for proposed lessons of method (§13): each one the user approves or dismisses."""
    try:
        return [{"kind": "lesson", **x, "actions": ["approve", "dismiss"]} for x in lesson_suggestions(store)]
    except Exception:  # noqa: BLE001 - a status read never fails on the session log
        return []


def cmd_checkpoint(store: Store, a: argparse.Namespace) -> None:
    """The user's confirmation of the PRD or the plan (§19). confirm | adjust --feedback | summary --text (what the
    board shows) | status."""
    store.load()
    if a.target not in CHECKPOINT_TARGETS:
        fail(f"checkpoint target must be {' or '.join(CHECKPOINT_TARGETS)}")
    cp = checkpoints(store).get(a.target)
    if a.action == "status":
        print(f"checkpoint {a.target}: " + ((cp or {}).get("status") or "none (no passed review since 3.0)")
              + (f" · version {cp.get('version')}" if cp and cp.get("version") else "")
              + (f" · confirmed {cp.get('confirmed_at')} by {cp.get('by')}" if cp and cp.get("status") == "confirmed" else ""))
        return
    if not cp:
        fail(f"no checkpoint for {a.target}: it opens when review {a.target} passes")
    if a.action == "summary":
        if not (a.text or "").strip():
            fail("summary needs --text")
        cp["summary"] = a.text.strip()[:4000]
        store.save()
        print(f"checkpoint {a.target}: summary recorded")
        return
    decision, feedback, by = a.action, (a.feedback or "").strip(), a.by or "user"
    if cp.get("status") != "pending":
        fail(f"checkpoint {a.target} is {cp.get('status')}, not waiting for a decision")
    if decision == "adjust" and not feedback:
        fail("adjust needs --feedback: what must change")
    entry = {"at": now(), "decision": decision, "by": by, "version": cp.get("version"),
             **({"feedback": feedback[:4000]} if feedback else {})}
    cp.setdefault("history", []).append(entry)
    if decision == "confirm":
        cp.update(status="confirmed", confirmed_at=now(), by=by)
        cp.pop("feedback", None)
    else:
        cp.update(status="adjust", feedback=feedback[:4000], adjusted_at=now())
    store.save()
    store.log(f"checkpoint {a.target} {decision} by {by}")
    store.event("checkpoint", target=a.target, transition=decision, round=cp.get("round"))
    record_wait(store, "checkpoint", cp.get("created_at"), a.target)
    if decision == "confirm":
        print(f"checkpoint {a.target}: confirmed by {by} (version {cp.get('version')})")
    else:
        print(f"checkpoint {a.target}: changes asked; run /dev-kit:{a.target} with the feedback, then review {a.target} again "
              f"(a new checkpoint follows)")


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
        elif top in ("production", "local_deploy", "cooldown", "quality", "model_policy", "ui", "queue", "milestone_size", "ci", "pipeline",
                     "release_flags", "git"):
            if top == "local_deploy" and not isinstance(parsed, dict):
                parsed = {"mode": val}
            elif top == "model_policy" and not isinstance(parsed, dict):
                parsed = {"mode": val}
            elif top == "ci" and not isinstance(parsed, dict):
                parsed = {"provider": val}
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
    if ((store.state.get("autonomy") or {}).get("production") or {}).get("when") == "per_milestone_flagged" \
            and not flags_cfg(store)["enabled"]:
        fail("production.when per_milestone_flagged needs autonomy.release_flags enabled (with its provider) first")
    if key == "autonomy.release_flags" and flags_cfg(store)["enabled"]:
        ensure_flags(store)
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
        dflt = DEFAULT_AUTONOMY["model_policy"]
        obj = {"mode": obj.get("mode", "ask"), "tiers": obj.get("tiers", {}),
               "risk_tiers": obj.get("risk_tiers", dflt["risk_tiers"]), "risk_weights": obj.get("risk_weights", {}),
               "router": {**dflt["router"], **(obj.get("router") or {})}}
    elif top == "local_deploy":
        check_local_deploy(obj)
        obj = {**DEFAULT_AUTONOMY["local_deploy"], **obj}
    elif top in ("cooldown", "quality"):
        check_autonomy_field(top, obj)
    elif top in ("queue", "milestone_size", "ci", "pipeline", "release_flags", "git"):
        obj = {**DEFAULT_AUTONOMY[top], **obj}
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


# ---------------------------------------------------------------- .dev/.gitignore and state versions (conventions.md §2)
GITIGNORE_BEGIN = "# >>> dev-kit: machine-local files (managed by dev_state.py; put your own rules outside this block)"
GITIGNORE_END = "# <<< dev-kit"
GITIGNORE_RULES = [
    "run/", "preview/", "tmp/", "backup/",        # board, locks, slots, skill stack, PIDs; local preview; scratch; backups
    "telemetry-session", "telemetry.jsonl",        # the session id and the raw session log (exports go to feedback/)
    "tips-seen.json", "state.json.bak",            # per-user tips; the previous copy of state.json
    "costs/*", "!costs/prices.json",               # usage caches rebuilt from the transcripts; the prices you edit are kept
]
LEGACY_GITIGNORE = {"# written by dev_state.py init", "run/", "preview/", "tmp/", "telemetry-session"}


def gitignore_text(old: str) -> str:
    """The .dev/.gitignore with the kit's block refreshed and every rule of the user kept as it was."""
    lines = old.splitlines()
    keep: list[str] = []
    inside = False
    legacy = bool(lines) and lines[0].strip() == "# written by dev_state.py init"
    for ln in lines:
        if ln.strip() == GITIGNORE_BEGIN:
            inside = True
            continue
        if inside:
            inside = ln.strip() != GITIGNORE_END
            continue
        if legacy and ln.strip() in LEGACY_GITIGNORE:
            continue  # the 2.x file the kit wrote: its lines are in the block now
        keep.append(ln)
    while keep and not keep[-1].strip():
        keep.pop()
    while keep and not keep[0].strip():
        keep.pop(0)
    block = [GITIGNORE_BEGIN, *GITIGNORE_RULES, GITIGNORE_END]
    return "\n".join(block + ([""] + keep if keep else [])) + "\n"


def stage_gitignore(store: Store) -> bool:
    gi = store.dev / ".gitignore"
    old = store.read_text(gi) if store.file_exists(gi) else ""
    new = gitignore_text(old)
    if new != old:
        store.stage(gi, new)
        return True
    return False


def kit_version() -> str | None:
    try:
        return tel.kit_version()
    except Exception:  # noqa: BLE001
        return None


def migrate_state(store: Store) -> None:
    """state.json from before 3.0 (version 1): a copy is kept in .dev/backup/ before anything changes it, the version
    goes to 2 and the kit's version is recorded; the plan itself migrates at the next sync-plan (§19). In memory only:
    the next command that saves writes it."""
    s = store.state
    if isinstance(s.get("autonomy"), dict):
        s["autonomy"].pop("board_executor", None)  # 3.12: the board no longer runs anything
    for g in (s.get("release_state") or {}).values():  # 3.0.0-alpha.6 renamed the "dossier" to the release review
        if isinstance(g, dict):
            for x in [g, *(g.get("history") or [])]:
                if isinstance(x, dict) and "dossier" in x:
                    x.setdefault("review_doc", x.pop("dossier"))
    if int(s.get("version") or 1) >= STATE_VERSION:
        return
    bdir = store.dev / "backup"
    try:
        if not any(bdir.glob("state-v1-*.json")):
            bdir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            (bdir / f"state-v1-{stamp}.json").write_text(store.path.read_text(encoding="utf-8"), encoding="utf-8")
            if (store.dev / "plan.md").exists():
                (bdir / f"plan-v1-{stamp}.md").write_text((store.dev / "plan.md").read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass
    s["version"] = STATE_VERSION
    s["migrated"] = {**(s.get("migrated") or {}), "v2_at": now(), "from_kit": s.get("kit_version")}
    s["needs_release_migration"] = bool(s.get("milestones")) and not s.get("release_plan")
    s["needs_gitignore"] = True


def migrate_releases(store: Store, text: str) -> tuple[str, list[str]] | None:
    """A plan without `## R<n>` (the 2.x cut model) gets planned releases (§19): the milestones already released go
    under `## R0 — Released before 3.0` (marked released, every 2.x version and tag kept), the others under
    `## R1 — <project>`; maintenance milestones under `## R<k> — Maintenance`. None when there is nothing to do."""
    if any(RELEASE_RE.match(ln.rstrip()) for ln in text.splitlines()):
        return None
    milestones, _ = parse_plan(text)
    if not milestones:
        return None
    released = {m for r in store.state.get("releases") or [] if not r.get("hotfix") for m in r.get("milestones") or []}
    order = list(milestones)
    lead = []
    for m in order:
        if m not in released:
            break
        lead.append(m)
    groups: list[tuple[str, str, list[str]]] = []
    if lead:
        groups.append(("R0", "Released before 3.0", lead))
    n = 1
    head = next((ln for ln in text.splitlines() if ln.startswith("# ")), "")
    hm = re.search(r"[—–-]\s*(.+?)\s*$", head)
    project = (hm.group(1) if hm else None) or store.state.get("project") or "First release"
    for m in order[len(lead):]:
        maint = bool(re.search(r"\bmaintenance\b", milestones[m]["title"], re.I))
        title = "Maintenance" if maint else str(project)
        if groups and groups[-1][0] != "R0" and groups[-1][1] == title and (not maint or len(groups[-1][2]) < RELEASE_SIZE[1]):
            groups[-1][2].append(m)
        else:
            groups.append((f"R{n}", title, [m]))
            n += 1
    first = {g[2][0]: g for g in groups}
    out = []
    for ln in text.splitlines():
        mm = MILESTONE_RE.match(ln.rstrip())
        if mm and mm.group(1) in first:
            rid, title, _ = first[mm.group(1)]
            if out and out[-1].strip():
                out.append("")
            out += [f"## {rid} — {title}", ""]
        out.append(ln)
    notes = [f"{rid} — {title}: {', '.join(ms)}" for rid, title, ms in groups]
    if lead:
        g = release_gate(store, "R0")
        g.update(status="released", historic=True)
        vers = []
        for r in store.state.get("releases") or []:
            if not r.get("hotfix") and r.get("milestones") and set(r["milestones"]) <= set(lead) and not r.get("release"):
                r["release"] = "R0"
                vers.append(r.get("tag") or r.get("version") or "?")
        g.setdefault("history", []).append({"at": now(), "event": "released", "version": ", ".join(map(str, vers)) or None,
                                            "note": "released before 3.0"})
    return "\n".join(out).rstrip("\n") + "\n", notes


def append_adr(store: Store, title: str, body: list[str], source: str = "auto") -> str:
    path = store.dev / "decisions.md"
    text = store.read_text(path) if store.file_exists(path) else "# Decisions\n"
    n = max([int(x) for x in re.findall(r"^###\s+ADR-(\d+)", text, re.M)] + [0]) + 1
    adr = f"ADR-{n:03d}"
    block = [f"### {adr} — {title} ({source})", f"- date: {today()} · status: accepted · source: {source}", *body]
    store.stage(path, text.rstrip("\n") + "\n\n" + "\n".join(block) + "\n")
    return adr



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
        closed = [m for m, v in sorted((s.get("milestones") or {}).items(), key=lambda kv: mkey(kv[0]))
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
        elif step in CHECKPOINT_TARGETS and checkpoint_pending(store, step):
            cp = (store.state.get("checkpoints") or {})[step]
            st = "checkpoint"
            note = (f"changes asked: {cp.get('feedback')}" if cp.get("status") == "adjust"
                    else f"waiting for your confirmation ({CHECKPOINT_TITLE[step]})")
        else:
            st = "done"
        out[step] = {"key": step, "state": st, "note": note}
    return out


# ---------------------------------------------------------------- planned releases and their human gate (§19)

def release_of(store: Store, m: str) -> str | None:
    """The planned release a milestone belongs to (None without a release plan)."""
    for r in store.state.get("release_plan") or []:
        if m in (r.get("milestones") or []):
            return r["id"]
    return None


def release_gate(store: Store, rid: str) -> dict:
    return store.state.setdefault("release_state", {}).setdefault(rid, {"status": None, "rounds": 0, "history": []})


def release_status(store: Store, rid: str) -> dict:
    """Where a planned release stands: in_progress -> ready_for_review -> awaiting_approval -> deploying_prod ->
    released. in_progress and ready_for_review are derived from its milestones; the others come from
    `release-submit`, `release-decide` and `release-record`."""
    r = next((x for x in store.state.get("release_plan") or [] if x["id"] == rid), None)
    mids = (r or {}).get("milestones") or []
    ts, ms = store.tasks(), store.milestones()
    live = {m: [v for v in ts.values() if v["milestone"] == m and v["status"] != "dropped"] for m in mids}
    closed = [m for m in mids if live[m] and ms.get(m, {}).get("gate") in ("passed", "skipped")]
    open_ = [m for m in mids if live[m] and m not in closed]
    rs = (store.state.get("release_state") or {}).get(rid) or {}
    shipped = any(x.get("release") == rid for x in store.state.get("releases") or []) or rs.get("status") == "released"
    if shipped:
        st = "released"
    elif open_ or not closed or store.in_progress() and any(ts[t]["milestone"] in mids for t in store.in_progress()):
        st = "in_progress"
    elif rs.get("status") == "approved":
        st = "deploying_prod"
    elif rs.get("status") == "awaiting_approval":
        st = "awaiting_approval"
    else:
        st = "ready_for_review"
    return {"id": rid, "title": (r or {}).get("title") or rid, "status": st, "milestones": mids, "closed": closed, "open": open_,
            "rounds": rs.get("rounds", 0), "review_doc": rs.get("review_doc"), "submitted_at": rs.get("submitted_at"),
            "decided_at": rs.get("decided_at"), "history": (rs.get("history") or [])[-5:]}


def release_plan_status(store: Store) -> list[dict]:
    return [release_status(store, r["id"]) for r in store.state.get("release_plan") or []]


def current_release(store: Store) -> dict | None:
    """The first planned release not released yet."""
    return next((x for x in release_plan_status(store) if x["status"] != "released"), None)


def pending_release(store: Store, mlist: list[dict]) -> dict:
    """Milestones closed since the last release and what the next release still needs (usability, docs). With
    planned releases the next release is the current one: its closed milestones, and it is ready once all are closed."""
    revs = store.state.get("reviews") or {}
    releases = store.state.get("releases") or []
    ms = store.milestones()
    pending = [x["id"] for x in mlist if x["state"] == "closed"]
    building = [x["id"] for x in mlist if x["state"] == "open" and x["started"]]
    cur = current_release(store) if store.state.get("release_plan") else None
    if cur:
        pending = [m for m in cur["closed"] if any(x["id"] == m and x["state"] == "closed" for x in mlist)]
        building = cur["open"]
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
            "count": len(releases), "release": cur["id"] if cur else None, "status": cur["status"] if cur else None,
            "title": cur["title"] if cur else None}


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
    train = pending_release(store, mlist)
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
    live = [x for x in mlist if x["total"]]
    phases = [
        {"key": "conception", "state": pstate("conception"), "reopened": bool(pending["conception"]) and ever_built,
         "steps": [steps[k] for k in CONCEPTION_STEPS]},
        {"key": "planning", "state": pstate("planning"), "reopened": bool(pending["planning"]) and ever_built,
         "steps": [steps[k] for k in PLANNING_STEPS]},
        {"key": "construction", "state": pstate("construction"), "reopened": False, "current_milestone": cur,
         "milestones": mlist, "closed": closed, "queue": queue, "release": train,
         "steps": construction_steps(live, closed, open_ms, cur, train, queue, ever_built)},
        {"key": "stable", "state": pstate("stable"), "reopened": False},
    ]
    return {"phase": phase, "step": step, "reopened": phase in ("conception", "planning") and ever_built,
            "steps": steps, "phases": phases, "release": train, "queue": queue, "releases": release_plan_status(store)}


def _ms_range(ids: list[str]) -> str:
    """M1, M2, M3, M5 -> "M1–M3, M5": a short label however many milestones wait."""
    nums = sorted(mmajor(m) for m in ids if mkey(m)[1] == 0)
    subs = sorted((m for m in ids if mkey(m)[1]), key=mkey)
    runs: list[list[int]] = []
    for n in nums:
        if runs and n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return ", ".join([f"M{r[0]}" if len(r) == 1 else f"M{r[0]}–M{r[-1]}" for r in runs] + subs)


def construction_steps(live: list[dict], closed: int, open_ms: list[str], cur: str | None, train: dict,
                       queue: list[str], ever_built: bool) -> list[dict]:
    """The two finite sub-stages of construction for the board: milestones and release, each with a short count;
    milestone ids and the queue go only into the note (a tooltip), so the bar never grows with the project."""
    ms_state = "doing" if open_ms else "done" if ever_built else "todo"
    note = (f"{cur} in progress · " if open_ms and cur else "") + f"{closed} of {len(live)} closed"
    if queue:
        note += f" · {len(queue)} issue{'s' if len(queue) != 1 else ''} queued"
    waiting = train["milestones"]
    if train.get("status") == "awaiting_approval":
        return [{"key": "milestones", "state": ms_state, "count": f"{closed}/{len(live)}" if live else None, "note": note},
                {"key": "release", "state": "review", "count": train["release"], "note": f"{train['release']} waits for your approval"}]
    if waiting:
        rel_state = "doing" if train["ready"] else "todo"
        rel_note = (f"{train['release']}: " if train.get("release") else "") + f"{_ms_range(waiting)} waiting for the release" + (
            "" if train["ready"] else f" · after {', '.join(train['waiting_for'])}")
    else:
        last = train["last"]
        rel_state = "done" if last else "todo"
        rel_note = (f"last: {last.get('tag') or last.get('version') or 'released'}" if last else "no release yet")
    return [{"key": "milestones", "state": ms_state, "count": f"{closed}/{len(live)}" if live else None, "note": note},
            {"key": "release", "state": rel_state, "count": str(len(waiting)) if waiting else None, "note": rel_note}]


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
        if lc["steps"][step]["state"] == "checkpoint":  # pending: review asks the user; adjust: the skill revises
            return f"/dev-kit:review {step}" if checkpoints(store)[step]["status"] == "pending" else f"/dev-kit:{step}"
        return f"/dev-kit:{step}"
    if lc["phase"] == "stable":
        return "/dev-kit:backlog"
    if store.in_progress():
        return "/dev-kit:implement"
    for m in store.milestone_order():
        live = gate_tasks(store, m)
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
    if rel.get("status") in ("awaiting_approval", "deploying_prod"):
        return "/dev-kit:release"  # the release asks for the decision, or finishes the approved one
    if rel["milestones"] and rel["ready"]:
        if rel["usability"] == "todo":
            return "/dev-kit:usability"
        if rel["docs"] == "review":
            return "/dev-kit:review docs"
        if rel["docs"] == "todo":
            return "/dev-kit:docs"
        return "/dev-kit:release"
    return "/dev-kit:plan" if not ts else "/dev-kit:backlog"


def _planned(store: Store, rid: str) -> dict:
    if not re.fullmatch(r"R\d{1,3}", rid or ""):
        fail(f"invalid release id {rid!r} (R1, R2…)")
    if not any(r["id"] == rid for r in store.state.get("release_plan") or []):
        fail(f"{rid} is not a planned release (plan.md has no '## {rid} — …' heading)")
    return release_status(store, rid)


def cmd_release_submit(store: Store, a: argparse.Namespace) -> None:
    """Freeze a release candidate: every milestone of the release closed, the release review written; the release then waits
    for the user's approval, the one human gate of construction (conventions.md §19)."""
    store.load()
    st = _planned(store, a.release)
    if st["status"] not in ("ready_for_review", "awaiting_approval"):
        fail(f"{a.release} is {st['status'].replace('_', ' ')}" + (f"; still open: {', '.join(st['open'])}" if st["open"] else ""))
    if a.review and not (store.root / a.review).exists():
        fail(f"release review not found: {a.review}")
    g = release_gate(store, a.release)
    resumed = resume_ahead(store, a.release)
    g.update(status="awaiting_approval", submitted_at=now(), review_doc=a.review or g.get("review_doc"))
    g.setdefault("history", []).append({"at": now(), "event": "submitted", "review_doc": a.review})
    store.save()
    store.log(f"release {a.release} submitted for approval" + (f" ({a.review})" if a.review else ""))
    store.event("release_gate", scope=a.release, transition="submit")
    queue_notice(store, f"dev-kit: {a.release} waits for your approval")
    print(f"{a.release}: awaiting approval · approve or reject with /dev-kit:release"
          + (f" · resumed ahead: {', '.join(resumed)}" if resumed else ""))


def _decision_args(store: Store, a: argparse.Namespace) -> tuple[str, list[str], str | None]:
    """--approve/--reject with --feedback."""
    if a.approve == a.reject:
        fail("give exactly one of --approve or --reject")
    return ("approve" if a.approve else "reject"), [f.strip() for f in a.feedback or [] if f.strip()], None


def cmd_release_decide(store: Store, a: argparse.Namespace) -> None:
    """The user's decision on a release waiting for approval. Approve: production deploy, smoke and release-record
    follow. Reject: the feedback becomes a fixes milestone at the end of the same release, one fix task per item,
    and the release goes back to construction (the only case where a milestone is created outside plan, §15)."""
    store.load()
    st = _planned(store, a.release)
    if st["status"] != "awaiting_approval":
        fail(f"{a.release} is {st['status'].replace('_', ' ')}, not awaiting approval")
    decision, feedback, ref = _decision_args(store, a)
    g = release_gate(store, a.release)
    record_wait(store, "release", g.get("submitted_at"), a.release)
    if decision == "approve":
        g.update(status="approved", decided_at=now())
        g.setdefault("history", []).append({"at": now(), "event": "approved", **({"ref": ref} if ref else {})})
        store.save()
        store.log(f"release {a.release} approved" + (f" ({ref})" if ref else ""))
        store.event("release_gate", scope=a.release, transition="approve")
        fc = flags_cfg(store)
        if fc["enabled"] and flag_name(a.release) in (store.state.get("flags") or {}):
            print(f"{a.release}: approved · next: turn {flag_name(a.release)} on in production ({fc['provider']}), run the "
                  f"smoke checks, then DS flag set {flag_name(a.release)} on and release-record (/dev-kit:release)")
        else:
            print(f"{a.release}: approved · next: production deploy, smoke and release-record (/dev-kit:release)")
        return
    if not feedback:
        fail("a rejection needs feedback: at least one --feedback item (each becomes a fix task)")
    if len(feedback) > 20:
        fail("at most 20 feedback items per rejection")
    plan_path = store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    rnd = int(g.get("rounds", 0)) + 1
    doc = PlanDoc(store.read_text(plan_path))
    last = sorted((m for m in st["milestones"] if doc.has_milestone(m)), key=mkey)
    if not last:
        fail(f"no milestone of {a.release} found in plan.md")
    # M<k>.<i>: k = the release's last milestone, i = the next free suffix (§3), so the id shows the order it runs in
    base = mmajor(last[-1])
    used = [mkey(x)[1] for x in store.milestones() if mmajor(x) == base]
    sfx = max(used + [0]) + 1
    mid = f"M{base}.{sfx}"
    title = f"{a.release} · Fixes {sfx}"
    doc.add_milestone(mid, title, after=last[-1])
    n = int(store.state.get("next_task_id", 1))
    existing = {int(x[2:]) for x in store.tasks()}
    tids = []
    for item_text in feedback:
        while n in existing:
            n += 1
        tid = f"T-{n:03d}"
        existing.add(n)
        tids.append(tid)
        block = task_block(tid, {"title": item_text[:100], "type": "fix", "deps": [], "acceptance": [item_text],
                                 "test_notes": f"From the rejection of {a.release}: show the reviewer it is fixed.", "files": []})
        doc.put({"kind": "task", "id": tid, "lines": block.rstrip("\n").splitlines()}, mid)
    text = doc.text()
    try:
        _, _, problems = sync_plan_text(store, text)
    except ValueError as e:
        fail(f"the edited plan does not parse: {e}")
    for tid in tids:
        store.tasks()[tid]["source"] = f"release:{a.release}"
    paused = pause_ahead(store, a.release)
    g.update(status=None, rounds=rnd, decided_at=now())
    g.setdefault("history", []).append({"at": now(), "event": "rejected", "milestone": mid, "tasks": tids, **({"ref": ref} if ref else {})})
    store.stage(plan_path, text)
    store.save()
    store.log(f"release {a.release} rejected: {mid} — {title} with {', '.join(tids)}" + (f" ({ref})" if ref else ""))
    store.event("release_gate", scope=a.release, transition="reject", tasks=len(tids))
    print(f"{a.release}: rejected · {mid} {title}: {', '.join(tids)}" + (f" · paused ahead: {', '.join(paused)}" if paused else ""))
    for w in problems:
        print(f"  warning: {w}")


def cmd_release_record(store: Store, a: argparse.Namespace) -> None:
    """Record a cut release: the milestones it ships no longer wait for a release (conventions.md §19). A planned
    release is recorded only after its approval (`release-decide --approve`)."""
    store.load()
    ms = store.milestones()
    rid = None
    if a.release:
        st = _planned(store, a.release)
        if st["status"] != "deploying_prod":
            fail(f"{a.release} is {st['status'].replace('_', ' ')}; it is recorded after its approval (release-decide {a.release} --approve)")
        rid, names = a.release, st["closed"]
    elif not a.hotfix:
        cur = current_release(store) if store.state.get("release_plan") else None
        if cur:
            fail(f"releases are planned: record {cur['id']} with --release {cur['id']} after its approval")
        fail("every release is planned since 3.0 (conventions.md §19): group the milestones under `## R<n>` in plan.md "
             "(sync-plan does it for an older plan), then release-submit, release-decide --approve and release-record "
             "--release R<n>; only a hotfix (--hotfix T-nnn) is recorded without approval")
    if rid:
        pass
    elif a.hotfix:
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
    if rid:
        rel["release"] = rid
        try:
            evs = tel.read_events(store.dev)[0]
        except (OSError, ValueError):
            evs = []
        scopes = {rid, *names, *(t for t, v in store.tasks().items() if v["milestone"] in names)}
        store.stage(store.dev / "releases" / rid / "flow.json", json.dumps({
            "release": rid, "version": a.version, "milestones": names, "at": now(), "human_wait_s": human_wait(evs, scopes),
            "milestones_wait_s": {m: _flow_field(store, m, "human_wait_s") for m in names}}, indent=2) + "\n")
        g = release_gate(store, rid)
        g.update(status="released")
        g.setdefault("history", []).append({"at": now(), "event": "released", "version": a.version})
        f = (store.state.get("flags") or {}).get(flag_name(rid))
        if f and f.get("state") != "on":
            print(f"warning: {flag_name(rid)} is {f.get('state')}: the release is recorded with its behaviour switched off "
                  f"(DS flag set {flag_name(rid)} on once it is on in production)", file=sys.stderr)
        cleanup = flag_cleanup_task(store, rid) if f else None
    if a.hotfix:
        rel["hotfix"] = a.hotfix
    store.state.setdefault("releases", []).append(rel)
    store.save()
    store.log(f"release {rel['version']} ({rel['tag']}): {', '.join(names) or 'hotfix ' + str(a.hotfix)}")
    print(f"release {rel['version']} recorded ({rel['tag']}): {', '.join(names) or 'hotfix ' + a.hotfix} · phase {phase_label(store)}")
    if rid and (store.state.get("flags") or {}).get(flag_name(rid)):
        ct = store.state["flags"][flag_name(rid)].get("cleanup_task")
        print(f"{ct}: Remove flag {flag_name(rid)}" if ct and ct != "pending"
              else f"Remove flag {flag_name(rid)}: added to the next release once it is planned")


# --------------------------------------------------------------------------- release flags (conventions.md §21)
def flags_cfg(store: Store) -> dict:
    return {**DEFAULT_AUTONOMY["release_flags"], **((store.state.get("autonomy") or {}).get("release_flags") or {})}


def flag_name(rid: str) -> str:
    return f"release_{rid}"


def ensure_flags(store: Store) -> list[str]:
    """With release flags on, every planned release not released yet has its flag, created off."""
    if not flags_cfg(store)["enabled"]:
        return []
    reg = store.state.setdefault("flags", {})
    made = []
    for r in store.state.get("release_plan") or []:
        name = flag_name(r["id"])
        if name not in reg and release_status(store, r["id"])["status"] != "released":
            reg[name] = {"release": r["id"], "state": "off", "created_at": now(), "history": []}
            made.append(name)
    return made


def flag_problems(store: Store) -> list[str]:
    """Feature tasks of a release that do not wrap their behaviour in its flag (warnings of sync-plan)."""
    if not flags_cfg(store)["enabled"]:
        return []
    out = []
    for tid, t in store.tasks().items():
        rid = release_of(store, t["milestone"])
        if not rid or t.get("type") != "feature" or t.get("status") in FINISHED or t.get("lane") == "hotfix":
            continue
        if t.get("flag") != flag_name(rid):
            out.append(f"{tid}: feature task of {rid} without `flag: {flag_name(rid)}` (release flags are on, §21)"
                       if not t.get("flag") else f"{tid}: flag {t['flag']} is not the flag of its release ({flag_name(rid)})")
    return out


def cmd_flag(store: Store, a: argparse.Namespace) -> None:
    """list [--json] | set NAME on|off [--rollback] [--note]: what is switched where. The switch itself is done by
    `release` (on, after the approval) and `deploy --rollback R<n>` (off) with the project's provider; this records it."""
    store.load()
    reg = store.state.setdefault("flags", {})
    if a.action == "list":
        rows = [{"name": k, **{x: v.get(x) for x in ("release", "state", "created_at", "removed_at")},
                 "last": (v.get("history") or [None])[-1]} for k, v in sorted(reg.items())]
        if a.json:
            print(json.dumps({"config": flags_cfg(store), "flags": rows}, indent=2))
        else:
            print("\n".join(f"{r['name']}: {r['state']} ({r['release']})" for r in rows) or "no release flags")
        return
    if not a.name or a.value not in ("on", "off", "removed"):
        fail("usage: flag set release_R<n> on|off|removed [--rollback] [--note]")
    f = reg.get(a.name)
    if f is None:
        fail(f"unknown flag {a.name}" + (f"; flags: {', '.join(sorted(reg))}" if reg else " (release flags are off)"))
    if a.value == "on":
        st = release_status(store, f["release"])["status"]
        if st not in ("deploying_prod", "released"):
            fail(f"{a.name} turns on only after {f['release']} is approved (it is {st.replace('_', ' ')}): "
                 f"release-decide {f['release']} --approve")
    event = "rollback" if a.rollback else a.value
    f["state"] = a.value
    if a.value == "removed":
        f["removed_at"] = now()
    f.setdefault("history", []).append({"at": now(), "event": event, **({"note": a.note[:200]} if a.note else {})})
    store.save()
    store.log(f"flag {a.name} {event}" + (f": {a.note}" if a.note else ""))
    store.event("flag", scope=f["release"], transition=event)
    print(f"{a.name}: {f['state']}" + (" (rolled back)" if a.rollback else ""))


def flag_cleanup_task(store: Store, rid: str) -> str | None:
    """After a flagged release ships, the chore that removes its flag goes to the first open milestone of the next
    release (§12). None (and a pending mark) when no later release is planned yet: sync-plan adds it then."""
    name = flag_name(rid)
    f = (store.state.get("flags") or {}).get(name)
    if not f or f.get("cleanup_task"):
        return None
    rels = [r["id"] for r in store.state.get("release_plan") or []]
    later = rels[rels.index(rid) + 1:] if rid in rels else []
    target = next((m for r in later for m in next(x for x in store.state["release_plan"] if x["id"] == r)["milestones"]
                   if store.milestones().get(m, {}).get("gate", "pending") == "pending"), None)
    plan_path = store.dev / "plan.md"
    if target is None or not plan_path.exists():
        f["cleanup_task"] = "pending"
        return None
    doc = PlanDoc(store.read_text(plan_path))
    if not doc.has_milestone(target):
        f["cleanup_task"] = "pending"
        return None
    n = int(store.state.get("next_task_id", 1))
    while f"T-{n:03d}" in store.tasks():
        n += 1
    tid = f"T-{n:03d}"
    block = task_block(tid, {"title": f"Remove flag {name}", "type": "chore", "deps": [],
                             "acceptance": [f"{name} and the code paths for its off state are gone; the suite passes"],
                             "test_notes": f"{rid} is released with {name} on: delete the flag and its old branch.", "files": []})
    doc.put({"kind": "task", "id": tid, "lines": block.rstrip("\n").splitlines()}, target)
    text = doc.text()
    try:
        sync_plan_text(store, text)
    except ValueError:
        f["cleanup_task"] = "pending"
        return None
    store.tasks()[tid]["source"] = f"flag:{name}"
    store.stage(plan_path, text)
    f["cleanup_task"] = tid
    return tid


# --------------------------------------------------------------------------- production health (conventions.md §21)
HEALTH_FILE = "prod-health.json"
HEALTH_KEEP = 30


def health_cfg(store: Store) -> dict | None:
    pr = (store.state.get("autonomy") or {}).get("production") or {}
    hc = {**HEALTH_DEFAULTS, **(pr.get("health") or {})}
    return hc if (hc.get("command") or hc.get("url")) else None


def health_log(root: Path) -> dict:
    try:
        d = json.loads((root / ".dev" / "run" / HEALTH_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def run_health(root: Path, hc: dict) -> dict:
    """One health check: the command (exit 0) or the URL (a 2xx/3xx answer), with a time limit."""
    t0 = time.monotonic()
    if hc.get("command"):
        target = hc["command"]
        try:
            p = subprocess.run(hc["command"], shell=True, cwd=root, capture_output=True, text=True, timeout=120)
            out = (p.stderr or p.stdout or "").strip()[-200:]
            ok, detail = p.returncode == 0, f"exit {p.returncode}" + (f": {out}" if out and p.returncode else "")
        except subprocess.TimeoutExpired:
            ok, detail = False, "timed out after 120 s"
    else:
        import urllib.request
        import urllib.error
        target = hc["url"]
        try:
            with urllib.request.urlopen(urllib.request.Request(hc["url"], headers={"User-Agent": "dev-kit-health"}), timeout=20) as r:
                ok, detail = 200 <= r.status < 400, f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            ok, detail = False, f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            ok, detail = False, str(getattr(e, "reason", e))[:200]
    return {"at": now(), "ok": ok, "target": target[:200], "detail": detail.strip()[:240], "duration_s": round(time.monotonic() - t0, 2)}


def health_issue(store: Store, res: dict) -> tuple[str, bool]:
    """A failed check opens one expedite issue per check; while it is open, the next failures update it."""
    key = hashlib.sha1(res["target"].encode()).hexdigest()[:10]
    for iid, i in issues(store).items():
        if i.get("health_check") == key and i["status"] not in ("done", "wontfix", "duplicate"):
            i["failures"] = int(i.get("failures") or 1) + 1
            i["last_failed_at"], i["last_detail"] = res["at"], res["detail"]
            write_issues_md(store)
            return iid, False
    iid = new_issue_id(store)
    issues(store)[iid] = {
        "title": f"Production health check failing: {res['target'][:80]}", "type": "bug", "class": "expedite",
        "severity": "high", "effort": None, "status": "open", "affects": [],
        "acceptance": [f"the production health check passes ({res['target'][:120]})"], "origin": "deploy", "tasks": [],
        "scheduled_in": None, "duplicate_of": None, "created_at": now(), "closed_at": None, "note": res["detail"],
        "closed_milestones_at_creation": closed_count(store), "health_check": key, "failures": 1,
        "last_failed_at": res["at"], "last_detail": res["detail"]}
    write_issues_md(store)
    return iid, True


def cmd_prod_check(store: Store, a: argparse.Namespace) -> None:
    """Run the production health check (autonomy.production.health) once and record it in .dev/run/prod-health.json;
    a failure opens (or updates) an expedite issue and shows in Needs you. `--due` runs it only when interval_min
    passed since the last check (autopilot and status run it so); `deploy` can offer a scheduled task."""
    store.load()
    hc = health_cfg(store)
    if hc is None:
        fail('no production health check: set autonomy.production.health {"command": "..."} or {"url": "https://..."}')
    if a.due:
        last = (health_log(store.root).get("checks") or [None])[-1]
        at = datetime.fromisoformat(str(last["at"]).replace("Z", "+00:00")) if last else None
        if at and (_clock() - at).total_seconds() < hc["interval_min"] * 60:
            print("prod-check: not due")
            return
    res = run_health(store.root, hc)  # outside the state lock: a slow check never holds other commands
    with store.transaction():
        log = health_log(store.root)
        checks = (log.get("checks") or [])[-(HEALTH_KEEP - 1):] + [res]
        issue, created = (None, False)
        if not res["ok"]:
            issue, created = health_issue(store, res)
            res["issue"] = issue
            store.save()
        streak = 0
        for c in reversed(checks):
            if c["ok"] != res["ok"]:
                break
            streak += 1
        out = {"checks": checks, "last": res, "streak": streak}
        store.stage(store.dev / "run" / HEALTH_FILE, json.dumps(out, indent=2) + "\n")
        store.save()
        store.event("prod_check", status="ok" if res["ok"] else "failed")
        if not res["ok"]:
            store.log(f"prod-check failed ({res['detail']}): {issue}" + (" opened" if created else " updated"))
            if created:
                queue_notice(store, f"dev-kit: production health check failing ({issue})")
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"prod-check: {'ok' if res['ok'] else 'FAILED'} · {res['detail']}"
              + (f" · {issue} {'opened' if created else 'updated'} (expedite)" if issue else ""))
    if not res["ok"]:
        sys.exit(1)


def health_needs(store: Store) -> list[dict]:
    """Needs you: the last health check failed and its issue is still open."""
    last = health_log(store.root).get("last") or {}
    i = issues(store).get(last.get("issue") or "")
    if last.get("ok") is not False or not i or i["status"] in ("done", "wontfix", "duplicate"):
        return []
    return [{"kind": "prod_health", "issue": last["issue"], "failures": i.get("failures", 1), "since": i.get("created_at"),
             "detail": last.get("detail"), "target": last.get("target"), "tasks": i.get("tasks") or []}]


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
        out["queue_needs"] = queue_needs(store)
        out["needs"] = all_needs(store)
        out["stale"] = stale_report(store)
        try:
            out["forecast"] = forecast(store)
        except Exception:  # noqa: BLE001
            out["forecast"] = None
        lc = lifecycle(store)
        out["phase"], out["step"], out["reopened"] = lc["phase"], lc["step"], lc["reopened"]
        out["lifecycle"] = {k: lc[k] for k in ("phases", "release", "queue", "releases")}
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
    if lc.get("releases"):
        print("Releases: " + " · ".join(f"{x['id']} {x['status'].replace('_', ' ')} ({len(x['closed'])}/{len([m for m in x['milestones']])})"
                                        for x in lc["releases"]))
        if rel.get("status") == "awaiting_approval":
            g = (s.get("release_state") or {}).get(rel["release"]) or {}
            print(f"Needs your approval: {rel['release']}" + (f" · release review {g['review_doc']}" if g.get("review_doc") else "")
                  + " · approve or reject with /dev-kit:release")
    if rel["milestones"] or rel["last"]:
        last = rel["last"]
        print("Next release: " + (f"{', '.join(rel['milestones'])} closed since the last release" if rel["milestones"] else "nothing to release")
              + (f" · usability {rel['usability']} · docs {rel['docs']}" if rel["milestones"] else "")
              + (f" · waiting for {', '.join(rel['waiting_for'])}" if rel["waiting_for"] else "")
              + (f" · last: {last.get('tag') or last.get('version') or 'before 1.30'} ({str(last.get('at'))[:10]})" if last else ""))
    try:
        print(forecast_line(forecast(store)))
    except Exception:  # noqa: BLE001 - the status never fails on a forecast
        pass
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
        hot = sum(1 for v in store.tasks().values() if v.get("lane") == "hotfix" and v["status"] not in FINISHED)
        queued = [v for v in iss if v["status"] == "open"]
        parked = sum(1 for v in iss if v["status"] == "parked")
        by = {}
        for v in queued:
            by[v.get("class")] = by.get(v.get("class"), 0) + 1
        print(f"Issues: {hot} hotfix · {len(queued)} queued (" + ", ".join(f"{n} {c}" for c, n in sorted(by.items())) +
              f") · {len(iss) - len(queued) - parked} scheduled" + (f" · {parked} parked" if parked else "") + " · run /dev-kit:backlog")
        for n in queue_needs(store):
            if n["kind"] == "queue_over_limit":
                print(f"Needs you: issue queue above the limit ({n['count']} > {n['limit']}) · plan {n['milestone']} — Issues "
                      f"with {len(n['issues'])} of them (/dev-kit:backlog)")
            else:
                print(f"Needs you: {n['issue']} waited {n['milestones']} closed milestones · schedule it next, park it or wontfix")
    for n in checkpoint_needs(store) + debt_needs(store):
        if n["kind"] == "checkpoint":
            print(f"Needs you: {n['title']} (review {n['target']} passed) · say so here to confirm it, or what must change")
        else:
            print(f"Needs you: {n['text']} · promote to issues, accept with an ADR, or use the next cool-down")
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


# --------------------------------------------------------------------------- questions with options

def question_sidecar(store: Store, qid: str) -> Path:
    return store.dev / "run" / "questions" / f"{qid}.json"


def _write_json(path: Path, obj: object, store: "Store | None" = None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if store is not None:
        store.stage(path, text)
    else:
        atomic_write(path, text)


def cmd_answer_question(store: Store, a: argparse.Namespace) -> None:
    """Move a question from Open to Resolved in open-questions.md with its answer (interview --gaps and every
    skill that asks use it)."""
    store.load()
    if not re.fullmatch(r"Q-\d{1,5}", a.id):
        fail("question ids look like Q-3")
    answer = re.sub(r"\s+", " ", a.answer).strip().replace("|", "/")
    if not answer:
        fail("--answer is empty")
    path = store.dev / "open-questions.md"
    lines = store.read_text(path).splitlines() if store.file_exists(path) else []
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
    store.stage(path, "\n".join(lines).rstrip("\n") + "\n")
    side = question_sidecar(store, a.id)
    try:
        q = json.loads(store.read_text(side))
    except (OSError, json.JSONDecodeError):
        q = {"id": a.id}
    _write_json(side, store=store, obj={**q, "answered": True, "answer": answer, "answered_at": now()})
    meta = (store.state.get("question_meta") or {}).pop(a.id, None) or {}
    record_wait(store, "question", meta.get("at") or q.get("at"), meta.get("scope"))
    store.save()
    store.log(f"answer-question {a.id}: {answer}")
    print(f"{a.id} resolved: {answer}")


# --------------------------------------------------------------------------- plan edits (plan-apply, move-task, new-milestone, reorder)

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

    def add_milestone(self, m: str, title: str, after: str | None = None) -> None:
        owners = self.milestone_of()
        nums = [(mkey(o), i) for i, o in enumerate(owners) if o]
        if after:
            at = self._end_of(after)
        else:
            at = (max(i for n, i in nums if n == max(n for n, _ in nums)) + 1) if nums else len(self.segs)
        self.segs.insert(at, {"kind": "text", "lines": [f"## {m} — {title}", ""]})

    @staticmethod
    def _first(s: dict) -> str:
        return s["lines"][0] if s["lines"] else ""

    def _is_top(self, s: dict) -> bool:
        return s["kind"] == "text" and bool(TOP_HEADING_RE.match(self._first(s)))

    def release_map(self) -> tuple[dict, list[str]]:
        """({milestone: release or None}, release ids in plan order), read the way parse_plan reads them."""
        rmap: dict = {}
        rids: list[str] = []
        cur: str | None = None
        for s in self.segs:
            if s["kind"] != "text":
                continue
            first = self._first(s)
            r, m = RELEASE_RE.match(first), MILESTONE_RE.match(first)
            if r:
                cur = r.group(1)
                rids.append(cur)
            elif m:
                rmap[m.group(1)] = cur
            elif first.startswith("# "):
                cur = None
        return rmap, rids

    def _block(self, m: str) -> tuple[int, int] | None:
        """The segments of a milestone: its heading and the tasks below it, up to the next `#`/`##` heading."""
        for i, s in enumerate(self.segs):
            mm = MILESTONE_RE.match(self._first(s)) if s["kind"] == "text" else None
            if mm and mm.group(1) == m:
                j = i + 1
                while j < len(self.segs) and not self._is_top(self.segs[j]):
                    j += 1
                return i, j
        return None

    def _release_at(self, rid: str) -> int | None:
        return next((i for i, s in enumerate(self.segs) if s["kind"] == "text" and (r := RELEASE_RE.match(self._first(s))) and r.group(1) == rid), None)

    def move_milestone(self, m: str, rid: str) -> None:
        """Move a milestone with its tasks under release `rid`, in milestone-number order among the ones already there."""
        i, j = self._block(m)  # type: ignore[misc]
        blk = self.segs[i:j]
        del self.segs[i:j]
        pos = k = (self._release_at(rid) or 0) + 1
        n = mkey(m)
        while k < len(self.segs):
            s = self.segs[k]
            if self._is_top(s):
                mm = MILESTONE_RE.match(self._first(s))
                if not mm:
                    break
                e = k + 1
                while e < len(self.segs) and not self._is_top(self.segs[e]):
                    e += 1
                if mkey(mm.group(1)) < n:
                    pos = e
                k = e
                continue
            k += 1
        self.segs[pos:pos] = blk

    def add_release(self, rid: str, title: str) -> None:
        self.segs.append({"kind": "text", "lines": [f"## {rid} — {title}" if title else f"## {rid}", ""]})

    def drop_release(self, rid: str) -> None:
        del self.segs[self._release_at(rid)]  # type: ignore[arg-type]

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
    """Apply plan edits to state (in memory) and to plan.md text. Every operation is checked against the state
    as the earlier ones left it; nothing is written here. Returns (new plan text, changes, errors, effects)."""
    doc = PlanDoc(text)
    ts, ms = store.tasks(), store.milestones()
    errors: list[str] = []
    changes: list[str] = []
    moved: set[str] = set()
    effects: dict = {"new_milestones": [], "scheduled": [], "moved": [], "moved_milestones": [], "new_releases": [],
                     "dropped_releases": []}
    touched: set[str] = set()  # releases a change of this draft touched: their size is checked at the end
    moved_ms: set[str] = set()

    def gate(m: str) -> str:
        return ms[m].get("gate", "pending") if m in ms else "missing"

    def open_m(m: str, where: str, op: dict | None = None) -> bool:
        if m not in ms or not doc.has_milestone(m):
            errors.append(f"{where}: milestone {m} does not exist")
            return False
        if op is not None and ms[m].get("frozen_at") and not op.get("confirm_frozen"):
            errors.append(f"{where}: {m} is frozen since its QA began; confirm to add it anyway ({frozen_cost(m)})")
            return False
        if gate(m) != "pending":
            errors.append(f"{where}: the gate of {m} is {gate(m)}; a closed milestone takes no change")
            return False
        return True

    def rel_status(rid: str | None) -> str:
        return "in_progress" if not rid or rid in effects["new_releases"] else release_status(store, rid)["status"]

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
            nxt = f"M{max([mmajor(x) for x in ms] or [0]) + 1}"
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
        elif kind == "move_milestone":
            m, rid = op.get("milestone", ""), op.get("release", "")
            rmap, rids = doc.release_map()
            if not rids:
                errors.append(f"{where}: the plan has no planned releases; group the milestones with /dev-kit:plan first")
            elif rid not in rids:
                errors.append(f"{where}: release {rid} does not exist")
            elif open_m(m, where):
                old = rmap.get(m)
                busy = [t for t, v in ts.items() if v["milestone"] == m and v["status"] == "in_progress"]
                if old == rid:
                    errors.append(f"{where}: {m} is already in {rid}")
                elif busy:
                    errors.append(f"{where}: {busy[0]} of {m} is running; the milestone stays where it is")
                elif rel_status(old) != "in_progress":
                    errors.append(f"{where}: {old} is {rel_status(old).replace('_', ' ')}; its milestones stay where they are")
                elif rel_status(rid) != "in_progress":
                    errors.append(f"{where}: {rid} is {rel_status(rid).replace('_', ' ')}; it takes no new milestone")
                else:
                    doc.move_milestone(m, rid)
                    ms[m]["release"] = rid
                    moved_ms.add(m)
                    touched.update(x for x in (old, rid) if x)
                    effects["moved_milestones"].append((m, old, rid))
                    changes.append(f"{m} {old or 'no release'} → {rid}")
        elif kind == "new_release":
            rid, title = op.get("release", ""), str(op.get("title") or "").strip()
            _, rids = doc.release_map()
            nxt = f"R{max([int(x[1:]) for x in rids] or [0]) + 1}"
            if not rids:
                errors.append(f"{where}: the plan has no planned releases; group the milestones with /dev-kit:plan first")
            elif rid != nxt:
                errors.append(f"{where}: the new release must be {nxt} (releases are never inserted or renumbered)")
            else:
                doc.add_release(rid, title)
                effects["new_releases"].append(rid)
                touched.add(rid)
                changes.append(f"new release {rid}" + (f" — {title}" if title else ""))
        elif kind == "drop_release":
            rid = op.get("release", "")
            rmap, rids = doc.release_map()
            left = [x for x, r in rmap.items() if r == rid]
            if rid not in rids:
                errors.append(f"{where}: release {rid} does not exist")
            elif left:
                errors.append(f"{where}: {rid} still holds {', '.join(left)}; move them out first")
            elif rel_status(rid) == "released":
                errors.append(f"{where}: {rid} is released and stays in the plan")
            else:
                doc.drop_release(rid)
                touched.discard(rid)
                effects["dropped_releases"].append(rid)
                changes.append(f"release {rid} removed")
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
            elif open_m(m, where, op if m != t["milestone"] else None) and before_ok(before, m, where, tid):
                old = t["milestone"]
                doc.move(tid, m, before)
                t["milestone"] = m
                if old != m and ms[m].get("frozen_at"):
                    t["scope_after_freeze"] = True
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
        elif kind == "set_issue_status":
            iid, to = op.get("issue", ""), op.get("status", "")
            i = issues(store).get(iid)
            if i is None:
                errors.append(f"{where}: unknown issue {iid}")
            elif to == "parked" and i["status"] != "open":
                errors.append(f"{where}: {iid} is {i['status']}; only an open issue is parked")
            elif to == "open" and i["status"] != "parked":
                errors.append(f"{where}: {iid} is {i['status']}, not parked")
            elif to == "wontfix" and i["status"] not in ("open", "parked"):
                errors.append(f"{where}: {iid} is {i['status']}; only an open or parked issue is closed as wontfix")
            else:
                i["status"] = to
                if to == "parked":
                    i["parked_at"] = now()
                if to == "wontfix":
                    i["closed_at"] = now()
                effects.setdefault("issue_status", []).append((iid, to))
                changes.append(f"{iid} → {to}")
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
            elif open_m(m, where, op) and before_ok(before, m, where):
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
                     "started_at": None, "done_at": None, **({"scope_after_freeze": True} if ms[m].get("frozen_at") else {})}
                ts[tid] = t
                doc.put({"kind": "task", "id": tid, "lines": task_block(tid, t).rstrip("\n").splitlines()}, m, before)
                i.setdefault("tasks", []).append(tid)
                i["status"], i["scheduled_in"] = "scheduled", m
                effects["scheduled"].append((iid, tid, m))
                changes.append(f"{iid} → {tid} in {m}" + (" (over the issue buffer)" if info["free"] <= 0 and m not in effects["new_milestones"] else ""))
        else:
            errors.append(f"{where}: unknown operation {kind}")

    # a release holds RELEASE_SIZE milestones: checked once the whole draft is in place
    rmap, rids = doc.release_map()
    for rid in sorted(touched):
        n = sum(1 for r in rmap.values() if r == rid)
        if rid in rids and not RELEASE_SIZE[0] <= n <= RELEASE_SIZE[1]:
            errors.append(f"{rid} would hold {n} milestone{'s' if n != 1 else ''}; a release holds {RELEASE_SIZE[0]} to {RELEASE_SIZE[1]}")

    # a task never sits in an earlier milestone (or release) than a task it depends on (done dependencies do not count)
    ridx = {r: i for i, r in enumerate(rids)}
    rank = {m: (ridx.get(rmap.get(m), len(rids)) if rids else 0, mkey(m)) for m in ms}
    moved |= {t for t, v in ts.items() if v["milestone"] in moved_ms and v["status"] not in FINISHED}
    for tid in sorted(moved):
        t = ts[tid]
        for d in sorted(set(t.get("deps", [])) | set(t.get("consumes") or [])):
            dt = ts.get(d)
            if dt and dt["status"] != "done" and rank.get(dt["milestone"], (0, 0)) > rank[t["milestone"]]:
                errors.append(f"{tid} depends on {d}, which is in a later milestone ({dt['milestone']})")
        for x, xt in sorted(ts.items()):
            if tid in (xt.get("deps") or []) and xt["status"] not in FINISHED and rank.get(xt["milestone"], (0, 0)) < rank[t["milestone"]]:
                errors.append(f"{x} depends on {tid}, which would come after it ({t['milestone']} after {xt['milestone']})")
    return doc.text(), changes, sorted(set(errors), key=errors.index), effects


PLAN_TASK, PLAN_MS = r"T-\d{3,5}", r"M\d{1,3}(?:\.\d{1,2})?"
PLAN_OPS = {
    "schedule_issue": {"issue": r"^I-\d{3,5}$", "milestone": rf"^{PLAN_MS}$"},
    "move_task": {"task": rf"^{PLAN_TASK}$", "milestone": rf"^{PLAN_MS}$"},
    "reorder": {"milestone": rf"^{PLAN_MS}$"},
    "new_milestone": {"milestone": rf"^{PLAN_MS}$"},
    "move_milestone": {"milestone": rf"^{PLAN_MS}$", "release": r"^R\d{1,3}$"},
    "new_release": {"release": r"^R\d{1,3}$"},
    "drop_release": {"release": r"^R\d{1,3}$"},
    # an issue left waiting (conventions §15): park it, close it as wontfix, or open it again
    "set_issue_status": {"issue": r"^I-\d{3,5}$", "status": r"^(parked|wontfix|open)$"},
}
PLAN_MAX_OPS = 100
_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")  # direction overrides hide what text says


def _plan_text(v: object, field: str, max_len: int, errors: list[str], required: bool = True) -> str:
    """A title in a plan operation: a string, no control or bidi-override characters, within its length."""
    if v is None or v == "":
        if required:
            errors.append(f"{field} is required")
        return ""
    if not isinstance(v, str):
        errors.append(f"{field} must be text")
        return ""
    t = "".join(c for c in _BIDI.sub("", unicodedata.normalize("NFC", v)) if unicodedata.category(c) != "Cc").strip()
    if len(t) > max_len:
        errors.append(f"{field} is longer than {max_len} characters")
    if not t and required:
        errors.append(f"{field} is required")
    return t


def plan_ops_valid(ops: object) -> tuple[list[dict], list[str]]:
    """The canonical plan operations of plan-apply, with every reason they are not valid."""
    errors: list[str] = []
    if not isinstance(ops, list) or not ops:
        return [], ["ops must be a non-empty list"]
    if len(ops) > PLAN_MAX_OPS:
        return [], [f"at most {PLAN_MAX_OPS} operations at once"]

    def pat(v: object, field: str, rx: str) -> str:
        if not isinstance(v, str) or not re.fullmatch(rx, v):
            errors.append(f"{field} is not valid")
            return ""
        return v
    out = []
    for i, op in enumerate(ops, 1):
        where = f"operation {i}"
        if not isinstance(op, dict) or op.get("op") not in PLAN_OPS:
            errors.append(f"{where}: op must be one of {', '.join(PLAN_OPS)}")
            continue
        kind = op["op"]
        o: dict = {"op": kind}
        for k, rx in PLAN_OPS[kind].items():
            o[k] = pat(op.get(k), f"{where}: {k}", rx)
        if kind in ("move_task", "schedule_issue") and op.get("before") is not None:
            o["before"] = pat(op.get("before"), f"{where}: before", rf"^{PLAN_TASK}$")
        if kind == "schedule_issue":
            o["force"] = op.get("force") is True
        if kind in ("schedule_issue", "move_task") and op.get("confirm_frozen") is True:
            o["confirm_frozen"] = True  # the user confirmed adding to a milestone frozen for QA (§15)
        if kind == "reorder":
            ts = op.get("tasks")
            if not isinstance(ts, list) or not ts or len(ts) > 200:
                errors.append(f"{where}: tasks must be a list of task ids")
            else:
                o["tasks"] = [pat(t, f"{where}: tasks", rf"^{PLAN_TASK}$") for t in ts]
        if kind == "new_milestone":
            o["title"] = _plan_text(op.get("title"), f"{where}: title", 80, errors).replace("|", "/")
        if kind == "new_release":
            o["title"] = _plan_text(op.get("title"), f"{where}: title", 80, errors, required=False).replace("|", "/")
        unknown = set(op) - {"op", "before", "force", "confirm_frozen", "tasks", "title", *PLAN_OPS[kind]}
        if unknown:
            errors.append(f"{where}: unknown field {sorted(unknown)[0]}")
        out.append(o)
    return out, errors


def _load_ops(a: argparse.Namespace) -> list[dict]:
    try:
        raw = json.loads(Path(a.ops_file).read_text(encoding="utf-8") if a.ops_file else a.ops)
    except (OSError, TypeError, json.JSONDecodeError) as e:
        fail(f"the operations are not valid JSON: {e}")
    ops, errors = plan_ops_valid(raw if isinstance(raw, list) else raw.get("ops") if isinstance(raw, dict) else None)
    if errors:
        fail("; ".join(errors))
    return ops


def apply_plan_ops(store: Store, ops: list[dict], *, dry_run: bool, as_json: bool, label: str = "plan-apply") -> None:
    plan_path = store.dev / "plan.md"
    if not plan_path.exists():
        fail(f"plan not found: {plan_path}")
    text, changes, errors, eff = plan_edit(store, ops, store.read_text(plan_path))
    out = {"ok": not errors, "changes": changes, "errors": errors, "applied": False}
    if not errors and not dry_run:
        try:
            _, _, problems = sync_plan_text(store, text)
        except ValueError as e:
            fail(f"the edited plan does not parse: {e}")
        store.stage(plan_path, text)
        store.save()
        write_issues_md(store)
        for tid, old, new in eff["moved"]:
            store.event("task", task=tid, transition="move", milestone=new)
        for iid, tid, m in eff["scheduled"]:
            issue_event(store, iid, "scheduled")
        for iid, to in eff.get("issue_status") or []:
            issue_event(store, iid, to)
        store.log(f"{label}: " + "; ".join(changes))
        out.update(applied=True, warnings=problems + [f"{x['check']}: {x['id']} - {x['detail']}" for x in xref_report(store)["problems"]])
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if errors:
            print("nothing changed:\n  " + "\n  ".join(errors))
        else:
            print(("would apply" if dry_run else "applied") + ":\n  " + "\n  ".join(changes))
            for w in out.get("warnings") or []:
                print(f"  warning: {w}")
    if errors:
        sys.exit(1)


def cmd_plan_apply(store: Store, a: argparse.Namespace) -> None:
    """Apply plan edits given as JSON: every change is checked first, then all are written together (plan.md and
    state), or none."""
    store.load()
    if sum(bool(x) for x in (a.ops, a.ops_file)) != 1:
        fail("give exactly one of --ops JSON or --ops-file FILE")
    apply_plan_ops(store, _load_ops(a), dry_run=a.dry_run, as_json=a.json)


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

def add_risk_flags(s: argparse.ArgumentParser, tier: bool) -> None:
    s.add_argument("--risk", help="low | medium | high"); s.add_argument("--complexity", help="low | medium | high")
    s.add_argument("--uncertainty", help="low | medium | high (new API, preview, spike)")
    s.add_argument("--opportunity", help="downgrade-ok, parallel-safe, batchable, reuse:<module> (comma-separated)")
    s.add_argument("--risk-reasons", dest="risk_reasons", help="why, separated by ;")
    if tier:
        s.add_argument("--tier", help="override: speed | balanced | balanced+ | quality (needs --tier-reason)")
        s.add_argument("--tier-reason", dest="tier_reason")


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
    s = sub.add_parser("tier"); s.set_defaults(fn=cmd_tier); s.add_argument("task"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("set-risk"); s.set_defaults(fn=cmd_set_risk); s.add_argument("task"); add_risk_flags(s, tier=True)
    s = sub.add_parser("risk-profile"); s.set_defaults(fn=cmd_risk_profile); s.add_argument("milestone")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("risk-report"); s.set_defaults(fn=cmd_risk_report); s.add_argument("milestone", nargs="?")
    s.add_argument("--all", action="store_true"); s.add_argument("--json", action="store_true")
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
    s.add_argument("--batch", help="up to N ready tasks that can run in parallel; auto = 3")

    s = sub.add_parser("start"); s.set_defaults(fn=cmd_start); s.add_argument("task"); s.add_argument("--force", action="store_true")
    s.add_argument("--resume", action="store_true", help="take over the work an earlier attempt left (worktree or dev-kit/T-nnn)")
    s = sub.add_parser("done"); s.set_defaults(fn=cmd_done); s.add_argument("task"); s.add_argument("--commit"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("block"); s.set_defaults(fn=cmd_block); s.add_argument("task"); s.add_argument("--reason")
    s.add_argument("--blocked-by", help="I-nnn: paused until the replan of this scope change")
    s = sub.add_parser("unblock"); s.set_defaults(fn=cmd_unblock); s.add_argument("task")
    s = sub.add_parser("drop"); s.set_defaults(fn=cmd_drop); s.add_argument("task"); s.add_argument("--reason", required=True)

    s = sub.add_parser("add-task"); s.set_defaults(fn=cmd_add_task)
    s.add_argument("--milestone", required=True); s.add_argument("--milestone-title")
    s.add_argument("--title", required=True); s.add_argument("--type", default="feature")
    s.add_argument("--deps"); s.add_argument("--acceptance", action="append"); s.add_argument("--test-notes")
    s.add_argument("--files"); s.add_argument("--source"); s.add_argument("--issue"); s.add_argument("--lane")
    s.add_argument("--force", action="store_true"); add_risk_flags(s, tier=True)
    s.add_argument("--confirm-frozen", action="store_true", help="add to a milestone frozen for QA (it re-enters the next round)")
    s = sub.add_parser("freeze"); s.set_defaults(fn=cmd_freeze); s.add_argument("milestone")
    s = sub.add_parser("forecast"); s.set_defaults(fn=cmd_forecast); s.add_argument("--json", action="store_true")
    s = sub.add_parser("pipeline"); s.set_defaults(fn=cmd_pipeline)
    s.add_argument("action", choices=["status", "worktree", "integrate"]); s.add_argument("branch", nargs="?")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("qa-watch"); s.set_defaults(fn=cmd_qa_watch); s.add_argument("milestone")
    s.add_argument("--wait", type=int, default=0, help="seconds to wait while auditors work (at most 540)")
    s.add_argument("--since", help="ISO time the round started (default: the last 12 hours)")
    s.add_argument("--settle", action="store_true", help="write stalled auditors' results as incomplete")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("round"); s.set_defaults(fn=cmd_round); s.add_argument("action", choices=["run"])
    s.add_argument("skill"); s.add_argument("scope"); s.add_argument("--permission-mode")
    s.add_argument("--timeout", type=int, default=180, help="minutes (default 180)")
    s = sub.add_parser("fact"); s.set_defaults(fn=cmd_fact); s.add_argument("action", choices=["add", "stale", "list"])
    s.add_argument("id", nargs="?"); s.add_argument("--text"); s.add_argument("--evidence"); s.add_argument("--files")
    s.add_argument("--acs"); s.add_argument("--origin"); s.add_argument("--sha"); s.add_argument("--by")
    s.add_argument("--all", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("lesson"); s.set_defaults(fn=cmd_lesson)
    s.add_argument("action", choices=["add", "rm", "show", "list", "suggest", "dismiss"]); s.add_argument("agent", nargs="?")
    s.add_argument("rest", nargs="*"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("challenger"); s.set_defaults(fn=cmd_challenger); s.add_argument("milestone"); s.add_argument("finding")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("challenge"); s.set_defaults(fn=cmd_challenge); s.add_argument("action", choices=["record"])
    s.add_argument("milestone"); s.add_argument("--from", dest="from_file", required=True)
    s = sub.add_parser("slot"); s.set_defaults(fn=cmd_slot); s.add_argument("action", choices=["open", "close", "show", "check", "apply"])
    s.add_argument("n", type=int); s.add_argument("--task"); s.add_argument("--agent"); s.add_argument("--allow", action="append")
    s.add_argument("--since"); s.add_argument("--cwd"); s.add_argument("--worktree", action="store_true")
    s.add_argument("--remove", action="store_true")
    s = sub.add_parser("reconcile"); s.set_defaults(fn=cmd_reconcile); s.add_argument("--milestone"); s.add_argument("--since")
    s.add_argument("--reason"); s.add_argument("--adopt"); s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("affected"); s.set_defaults(fn=cmd_affected); s.add_argument("--acs", required=True); s.add_argument("--json", action="store_true")
    s = sub.add_parser("hard-floor"); s.set_defaults(fn=cmd_hard_floor); s.add_argument("milestone")
    s.add_argument("--from", dest="from_file", required=True, help="JSON file of the checks (- for stdin)")
    s = sub.add_parser("ci"); s.set_defaults(fn=cmd_ci); s.add_argument("action", choices=["check", "record", "status"])
    s.add_argument("milestone"); s.add_argument("--sha"); s.add_argument("--status"); s.add_argument("--url")
    s = sub.add_parser("debt"); s.set_defaults(fn=cmd_debt); s.add_argument("action", choices=["status", "decide"])
    s.add_argument("decision", nargs="?"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("checkpoint"); s.set_defaults(fn=cmd_checkpoint)
    s.add_argument("action", choices=["status", "confirm", "adjust", "summary"]); s.add_argument("target")
    s.add_argument("--feedback"); s.add_argument("--text"); s.add_argument("--by")

    s = sub.add_parser("fix-tasks"); s.set_defaults(fn=cmd_fix_tasks)
    s.add_argument("--from", dest="src_file", required=True); s.add_argument("--milestone", required=True)
    s.add_argument("--source"); s.add_argument("--include", help="comma-separated non-blocking finding ids to include")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("add-question"); s.set_defaults(fn=cmd_add_question)
    s.add_argument("text"); s.add_argument("--skill"); s.add_argument("--assumption"); s.add_argument("--impact")
    s.add_argument("--options", help="the answers offered, separated by | (2 to 6; the board shows them)")
    s.add_argument("--recommended", help="the option recommended, shown first")
    s.add_argument("--task", help="the task waiting on the answer (the board shows the question on it)")
    s = sub.add_parser("answer-question"); s.set_defaults(fn=cmd_answer_question)
    s.add_argument("id"); s.add_argument("--answer", required=True); s.add_argument("--ref")
    s = sub.add_parser("plan-apply"); s.set_defaults(fn=cmd_plan_apply)
    s.add_argument("--ops"); s.add_argument("--ops-file")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("qa-decide"); s.set_defaults(fn=cmd_qa_decide)
    s.add_argument("milestone", nargs="?"); s.add_argument("decision", nargs="?", choices=["continue", "accept", "replan"])
    s.add_argument("--rounds", type=int, default=1); s.add_argument("--note")
    s = sub.add_parser("task-decide"); s.set_defaults(fn=cmd_task_decide)
    s.add_argument("task", nargs="?"); s.add_argument("decision", nargs="?", choices=["unblock", "skip", "drop", "run"])
    s.add_argument("--note")
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
    s = sub.add_parser("release-submit"); s.set_defaults(fn=cmd_release_submit)
    s.add_argument("release"); s.add_argument("--review", "--dossier", dest="review",
                                             help="path of the release review, relative to the project root (--dossier: old name)")
    s = sub.add_parser("release-decide"); s.set_defaults(fn=cmd_release_decide)
    s.add_argument("release"); s.add_argument("--approve", action="store_true"); s.add_argument("--reject", action="store_true")
    s.add_argument("--feedback", action="append", help="one rejection item (repeat); each becomes a fix task")
    s = sub.add_parser("release-record"); s.set_defaults(fn=cmd_release_record)
    s.add_argument("--version", required=True); s.add_argument("--tag")
    s.add_argument("--release", help="the planned release (R1…) being recorded, after its approval")
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
    s = sub.add_parser("flag"); s.set_defaults(fn=cmd_flag)
    s.add_argument("action", choices=("list", "set")); s.add_argument("name", nargs="?"); s.add_argument("value", nargs="?")
    s.add_argument("--rollback", action="store_true", help="the switch off is a rollback (deploy --rollback R<n>)")
    s.add_argument("--note"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("prod-check"); s.set_defaults(fn=cmd_prod_check)
    s.add_argument("--json", action="store_true"); s.add_argument("--due", action="store_true", help="only when interval_min has passed")
    s = sub.add_parser("preview"); s.set_defaults(fn=cmd_preview)
    s.add_argument("milestone"); s.add_argument("--url"); s.add_argument("--sha"); s.add_argument("--pid", type=int)
    s.add_argument("--stopped", action="store_true")
    s = sub.add_parser("add-issue"); s.set_defaults(fn=cmd_add_issue)
    s.add_argument("--type", required=True); s.add_argument("--title", required=True)
    s.add_argument("--class", dest="cls", required=True); s.add_argument("--severity"); s.add_argument("--effort")
    s.add_argument("--affects"); s.add_argument("--origin", default="user"); s.add_argument("--acceptance", action="append")
    s.add_argument("--note"); s.add_argument("--force", action="store_true")
    s.add_argument("--force-class", metavar="REASON", help="keep a class the severity does not suggest (§15), with the reason")
    s = sub.add_parser("issue"); s.set_defaults(fn=cmd_issue); s.add_argument("id")
    s.add_argument("--status"); s.add_argument("--class", dest="cls"); s.add_argument("--severity"); s.add_argument("--effort")
    s.add_argument("--force-class", metavar="REASON")
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


# Commands that change state.json or the artifacts the kit keeps in step with it: each runs as one transaction.
MUTATING = frozenset({
    cmd_init, cmd_sync_plan, cmd_set_risk, cmd_risk_report, cmd_start, cmd_done, cmd_block, cmd_unblock, cmd_drop,
    cmd_add_task, cmd_fix_tasks, cmd_add_question, cmd_answer_question, cmd_plan_apply, cmd_move_task,
    cmd_new_milestone, cmd_reorder, cmd_gate, cmd_review, cmd_artifact, cmd_release_submit, cmd_release_decide,
    cmd_release_record, cmd_set, cmd_deploy, cmd_preview, cmd_add_issue, cmd_issue, cmd_pull_issues, cmd_cooldown,
    cmd_freeze, cmd_hard_floor, cmd_ci, cmd_debt, cmd_checkpoint, cmd_slot, cmd_challenge, cmd_fact, cmd_lesson, cmd_pipeline,
    cmd_qa_decide, cmd_task_decide, cmd_flag, cmd_reconcile,
})


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    store = Store(find_root(args.root))
    if args.fn in MUTATING:
        with store.transaction():
            args.fn(store, args)
        if getattr(store, "exit_code", 0):  # a refusal whose record (a question, an event) must still be committed
            sys.exit(store.exit_code)
    else:
        args.fn(store, args)


if __name__ == "__main__":
    main()
