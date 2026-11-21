#!/usr/bin/env python3
"""dev_risk.py - risk tier of a task and risk profile of a milestone (conventions.md §9 "Tier per task").

Standard library only. Imported by dev_state.py (brief, tier, start, risk-report, risk-profile, set-risk, xref) and by
dev_router.py; it has no command line of its own and never imports dev_state.py (it receives the Store).

The tier is computed by a deterministic rule from objective signals (paths in `files`, deps and consumes, type,
ledger history, reopen count, the finding a fix comes from) plus the planner's optional fields (`risk`,
`complexity`, `uncertainty`, `opportunity`). Missing planner fields count 0, so plans written before 1.32 work.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_ledger as led  # noqa: E402

TIERS = ("speed", "balanced", "balanced+", "quality")
LEVELS = ("low", "medium", "high")
OPPORTUNITIES = ("none", "downgrade-ok", "parallel-safe", "batchable")  # plus reuse:<module>
RISK_FIELDS = ("risk", "complexity", "uncertainty", "risk_reasons", "opportunity", "tier", "tier_reason")
# model/effort of each tier for the implementer; `speed-fix` is the fix of a low finding (mechanical change)
TIER_ARM = {"speed": "haiku/medium", "balanced": "sonnet/medium", "balanced+": "sonnet/high", "quality": "opus/high"}
FIX_LOW_ARM = "haiku/low"
BASE_ARM = "sonnet/medium"  # the implementer's frontmatter (1.31 behaviour)

# signal -> (default weight, label). Floor signals: the router never routes a task with one below its rule tier.
RISK_WEIGHTS = {
    "auth": (3, "auth, permissions or secrets"),
    "external_send": (3, "external send or production action"),
    "schema": (2, "migration or schema change"),
    "new_api": (2, "new, preview or undocumented API"),
    "integration": (2, "integrates 2+ tasks"),
    "wide": (1, "more than 10 files or 3 areas"),
    "failed_before": (2, "failed or blocked before"),
    "reopened_high": (2, "reopened, or fixes a high finding"),
    "planner_high": (1, "planner risk high"),
    "complex": (1, "planner complexity high"),
    "downgrade_ok": (-2, "planner: downgrade-ok"),
    "docs_tests_only": (-2, "docs, tests or copy only"),
}
FLOOR_SIGNALS = ("auth", "external_send", "schema")
# Base score by task type: ordinary work starts in balanced (sonnet), so only mechanical or downgrade-ok work reaches
# speed; the signals then move it up or down. Not learned.
TYPE_BASE = {"feature": 1, "fix": 1, "chore": 1, "test": 0, "docs": 0}
WEIGHT_BOUND = 2  # learned adjustments stay within ±2 of the default weight

_SEP = r"(?:^|[/_.\-])"
_END = r"(?:[/_.\-]|$)"
AUTH_FILE = re.compile(_SEP + r"(auth\w*|login|logout|signin|signup|sessions?|permissions?|rbac|acl|roles?|secrets?|"
                       r"credentials?|passwords?|guards?|guardrails?|oauth\w*|jwt|crypto|api[-_]?keys?|access[-_]?tokens?)" + _END, re.I)
AUTH_TEXT = re.compile(r"\b(auth\w*|login|permissions?|secrets?|credentials?|passwords?|guardrails?|oauth|jwt|"
                       r"encryption|access control|autentica\w*|permiss\w*|senhas?)\b", re.I)
SEND_FILE = re.compile(_SEP + r"(e?mails?|mailers?|smtp|webhooks?|notif\w*|sms|outbox|send\w*|deploy\w*|prod|production|"
                       r"payments?|billing)" + _END, re.I)
SEND_TEXT = re.compile(r"\b(e-?mails?|webhooks?|notifications?|sms|send(ing)?|deploy\w*|production|payments?|billing|"
                       r"envio|enviar|produção)\b", re.I)
SCHEMA_FILE = re.compile(r"(^|/)(migrations?|alembic|prisma|db/schema)(/|$)|\.sql$|(^|/)schema\.(prisma|rb|py|ts|js|graphql)$", re.I)
SCHEMA_TEXT = re.compile(r"\b(migrations?|schema|migração)\b", re.I)
NEW_API_TEXT = re.compile(r"\b(preview|beta|experimental|undocumented|spike|não documentad\w*)\b", re.I)
JOBS_FILE = re.compile(_SEP + r"(jobs?|workers?|cron\w*|queues?|tasks?|etl|pipelines?|schedul\w*|consumers?)" + _END, re.I)

AREAS = (
    ("docs", re.compile(r"(^|/)docs?/|\.(md|mdx|rst|txt|adoc)$|(^|/)(README|CHANGELOG|changelog\.d)", re.I)),
    ("tests", re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress|playwright)/|([._-](test|spec))\.\w+$|(^|/)test_\w+\.py$", re.I)),
    ("sql", re.compile(r"(^|/)(migrations?|alembic|prisma|db|sql|models?)/|\.sql$|schema\.\w+$", re.I)),
    ("infra", re.compile(r"(^|/)(\.github|\.gitlab|infra|deploy|k8s|helm|terraform|ansible|docker)/|Dockerfile|docker-compose|"
                         r"\.ya?ml$|\.tf$|Makefile$|Procfile$", re.I)),
    ("ui", re.compile(r"\.(tsx|jsx|vue|svelte|astro|html?|css|scss|sass|less|hbs|ejs|erb|jinja2?|liquid|twig)$|"
                      r"(^|/)(components|pages|views|screens|templates|layouts|styles|public|static)/|(^|/)(locales?|i18n)/", re.I)),
)
COPY_ONLY = re.compile(r"(^|/)(locales?|i18n|lang|messages|translations)/|\.(po|pot|arb|strings|xliff)$", re.I)


# --------------------------------------------------------------------------- helpers

def area_of(path: str) -> str:
    for name, rx in AREAS:
        if rx.search(path):
            return name
    return "backend"


def areas_of(files: list[str]) -> list[str]:
    seen: list[str] = []
    for f in files:
        a = area_of(f)
        if a not in seen:
            seen.append(a)
    return seen


def dominant_area(files: list[str]) -> str:
    if not files:
        return "none"
    counts: dict[str, int] = {}
    for f in files:
        a = area_of(f)
        counts[a] = counts.get(a, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def tier_token(tier: str | None) -> str | None:
    """Telemetry tokens cannot hold `+`."""
    return tier.replace("+", "-plus") if tier else None


def parse_opportunity(val: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[,\s]+", val or "") if x.strip()]


def check_risk_fields(tid: str, t: dict) -> list[str]:
    """Problems with the optional risk fields of one task (sync-plan, add-task, set-risk)."""
    out = []
    for k in ("risk", "complexity", "uncertainty"):
        if t.get(k) not in (None, "") and t[k] not in LEVELS:
            out.append(f"{tid}: {k} must be one of {', '.join(LEVELS)} (got '{t[k]}')")
    for o in t.get("opportunity") or []:
        if o not in OPPORTUNITIES and not re.fullmatch(r"reuse:[\w./-]+", o):
            out.append(f"{tid}: opportunity '{o}' is not one of {', '.join(OPPORTUNITIES)} or reuse:<module>")
    if t.get("tier") not in (None, ""):
        if t["tier"] not in TIERS:
            out.append(f"{tid}: tier must be one of {', '.join(TIERS)} (got '{t['tier']}')")
        elif not str(t.get("tier_reason") or "").strip():
            out.append(f"{tid}: tier override needs tier_reason (why the rule is not enough)")
    return out


def model_policy(state: dict) -> dict:
    mp = dict((state.get("autonomy") or {}).get("model_policy") or {})
    mp.setdefault("mode", "ask")
    mp.setdefault("tiers", {})
    mp.setdefault("risk_tiers", "apply")
    mp.setdefault("risk_weights", {})
    r = dict(mp.get("router") or {})
    r.setdefault("mode", "apply")
    r.setdefault("balance", "balanced")
    r.setdefault("budget_usd_per_milestone", None)
    mp["router"] = r
    return mp


def router_file(dev: Path) -> Path:
    return dev / "router.json"


def learned_weights(dev: Path) -> dict:
    try:
        data = json.loads(router_file(dev).read_text(encoding="utf-8"))
        w = data.get("weights") or {}
        return {k: int(v) for k, v in w.items() if k in RISK_WEIGHTS and isinstance(v, (int, float))}
    except (OSError, json.JSONDecodeError, AttributeError, ValueError):
        return {}


def weights(store) -> dict[str, int]:
    """Default weights + learned deltas (router.json, bounded) + the project's explicit overrides (settings win)."""
    w = {k: v[0] for k, v in RISK_WEIGHTS.items()}
    for k, d in learned_weights(store.dev).items():
        lo, hi = RISK_WEIGHTS[k][0] - WEIGHT_BOUND, RISK_WEIGHTS[k][0] + WEIGHT_BOUND
        nv = max(lo, min(hi, RISK_WEIGHTS[k][0] + d))
        if k in FLOOR_SIGNALS:
            nv = max(nv, RISK_WEIGHTS[k][0])  # floor signals never get cheaper
        w[k] = nv
    for k, v in (model_policy(store.state).get("risk_weights") or {}).items():
        if k in w and isinstance(v, (int, float)) and not isinstance(v, bool):
            w[k] = int(v)
    return w


def finding_severity(store, t: dict) -> str | None:
    """Severity of the finding a fix task comes from: recorded since 1.32, else looked up from its source anchor."""
    if t.get("finding_severity"):
        return t["finding_severity"]
    src = str(t.get("source") or "")
    m = re.match(r"^qa/(M\d+)/report\.md#([\w.-]+?)(?:-r\d+)?$", src)
    if not m:
        return None
    for f in findings_of(store, m.group(1)).values():
        if f.get("id") == m.group(2):
            return f.get("severity")
    return None


def findings_of(store, milestone: str) -> dict[str, dict]:
    """Every finding of a milestone's QA rounds by id (latest round wins), from findings-round-*.json."""
    out: dict[str, dict] = {}
    qa = store.dev / "qa" / milestone
    if not qa.is_dir():
        return out
    files = sorted(qa.glob("findings-round-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if not files and (qa / "findings.json").exists():
        files = [qa / "findings.json"]
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rnd = data.get("round") if isinstance(data, dict) else None
        for f in (data.get("findings") if isinstance(data, dict) else data) or []:
            if isinstance(f, dict) and f.get("id") and not f.get("legacy"):
                prev = out.get(f["id"])
                out[f["id"]] = {**f, "round": rnd, "first_round": (prev or {}).get("first_round", rnd)}
    return out


# --------------------------------------------------------------------------- the rule

def signals(store, tid: str) -> list[dict]:
    """The signals present in a task, each with its weight and a short detail (deterministic)."""
    t = store.tasks()[tid]
    w = weights(store)
    files = [str(f) for f in t.get("files") or []]
    text = " ".join([str(t.get("title") or ""), str(t.get("risk_reasons") or "")])
    out: list[dict] = []
    base = TYPE_BASE.get(str(t.get("type") or "feature"), 1)
    if base:
        out.append({"signal": "base", "weight": base, "detail": f"base ({t.get('type') or 'feature'})", "label": "base by task type"})

    def add(sig: str, detail: str) -> None:
        out.append({"signal": sig, "weight": w[sig], "detail": detail, "label": RISK_WEIGHTS[sig][1]})

    hit = [f for f in files if AUTH_FILE.search(f)]
    if hit or AUTH_TEXT.search(text):
        add("auth", f"auth path {hit[0]}" if hit else "auth in title or risk_reasons")
    hit = [f for f in files if SEND_FILE.search(f)]
    if hit or SEND_TEXT.search(text):
        add("external_send", f"send path {hit[0]}" if hit else "send in title or risk_reasons")
    hit = [f for f in files if SCHEMA_FILE.search(f)]
    if hit or SCHEMA_TEXT.search(text):
        add("schema", f"schema path {hit[0]}" if hit else "migration in title or risk_reasons")
    if t.get("uncertainty") == "high" or NEW_API_TEXT.search(text):
        add("new_api", "uncertainty high" if t.get("uncertainty") == "high" else "preview/spike in title or risk_reasons")
    joined = list(dict.fromkeys(list(t.get("deps") or []) + list(t.get("consumes") or [])))
    joined = [d for d in joined if d in store.tasks()]
    if len(joined) >= 2:
        add("integration", "integrates " + ", ".join(joined[:4]) + ("…" if len(joined) > 4 else ""))
    code_areas = [a for a in areas_of(files) if a not in ("docs", "tests")]
    if len(files) > 10 or len(code_areas) > 3:
        add("wide", f"{len(files)} files" if len(files) > 10 else f"{len(code_areas)} areas")
    hist = led.load(store.dev).get(f"task:{tid}") or {}
    if hist.get("result") in ("failed", "blocked") or int(t.get("blocked_count", 0) or 0) > 0:
        add("failed_before", "ledger " + (hist.get("result") or "blocked"))
    sev = finding_severity(store, t) if t.get("type") == "fix" else None
    if int(t.get("returns", 0) or 0) > 0 or sev in ("critical", "high"):
        add("reopened_high", f"reopened {t['returns']}x" if t.get("returns") else f"fixes a {sev} finding")
    if t.get("risk") == "high":
        add("planner_high", "risk: high")
    if t.get("complexity") == "high":
        add("complex", "complexity: high")
    if "downgrade-ok" in (t.get("opportunity") or []):
        add("downgrade_ok", "opportunity: downgrade-ok")
    only = files and all(area_of(f) in ("docs", "tests") or COPY_ONLY.search(f) for f in files)
    if t.get("type") in ("docs", "test") or only:
        add("docs_tests_only", f"type {t.get('type')}" if t.get("type") in ("docs", "test") else "docs/tests/copy files only")
    return [s for s in out if s["weight"] != 0]


def tier_of_score(score: int) -> str:
    if score <= 0:
        return "speed"
    if score <= 3:
        return "balanced"
    if score <= 5:
        return "balanced+"
    return "quality"


def has_planner_fields(t: dict) -> bool:
    return any(t.get(k) not in (None, "", []) for k in ("risk", "complexity", "uncertainty", "opportunity", "risk_reasons", "tier"))


def task_tier(store, tid: str) -> dict:
    """{tier, score, reasons, floor, source, arm, model, effort, applied, mode, context, planner_fields}.

    source: rule | plan (override) | retry (one step above the previous attempt) | fix-low (mechanical fix)."""
    t = store.tasks()[tid]
    sigs = signals(store, tid)
    score = sum(s["weight"] for s in sigs)
    tier = tier_of_score(score)
    source = "rule"
    floor = any(s["signal"] in FLOOR_SIGNALS for s in sigs)
    arm = TIER_ARM[tier]
    prev = (t.get("tier") or {}).get("rule") if isinstance(t.get("tier"), dict) else None
    retried = any(s["signal"] in ("failed_before", "reopened_high") for s in sigs) and int(t.get("returns", 0) or 0) + \
        int(t.get("blocked_count", 0) or 0) > 0
    if retried and prev in TIERS:
        up = TIERS[min(TIERS.index(prev) + 1, len(TIERS) - 1)]
        if TIERS.index(up) > TIERS.index(tier):
            tier, source, arm = up, "retry", TIER_ARM[up]
    sev = finding_severity(store, t) if t.get("type") == "fix" else None
    if sev == "low" and not floor and source == "rule":
        tier, source, arm = "speed", "fix-low", FIX_LOW_ARM
    if t.get("tier") in TIERS and isinstance(t.get("tier"), str):
        tier, source, arm = t["tier"], "plan", TIER_ARM[t["tier"]]
    mp = model_policy(store.state)
    applied = mp.get("risk_tiers") == "apply"
    model, effort = arm.split("/")
    return {"task": tid, "tier": tier, "score": score, "reasons": sigs, "floor": floor, "source": source,
            "arm": arm, "model": model, "effort": effort, "mode": mp.get("risk_tiers"), "applied": applied,
            "base_arm": BASE_ARM, "context": task_context(tier, t), "planner_fields": has_planner_fields(t),
            "tier_reason": t.get("tier_reason") if source == "plan" else None}


def task_context(tier: str, t: dict) -> str:
    return f"task:{tier}:{dominant_area([str(f) for f in t.get('files') or []])}:{t.get('type') or 'feature'}"


def reasons_text(info: dict) -> str:
    parts = [f"{s['detail']} {s['weight']:+d}" for s in info["reasons"]]
    if info["source"] == "plan":
        parts.append(f"plan override ({info.get('tier_reason') or '-'})")
    elif info["source"] == "retry":
        parts.append("one step above the previous attempt")
    elif info["source"] == "fix-low":
        parts.append("fix of a low finding")
    if not info["planner_fields"]:
        parts.append("planner fields: none (objective signals only)")
    return ", ".join(parts) or "no signal"


def tier_line(info: dict) -> str:
    return (f"Tier: {info['tier']} ({info['score']}) → {info['model']} / {info['effort']}: {reasons_text(info)}"
            + ("" if info["applied"] else f" · risk_tiers {info['mode']}: use {info['base_arm'].replace('/', ' / ')}"))


# --------------------------------------------------------------------------- milestone profile and auditors

AGENT_BASE = {
    "deps-auditor": "haiku/medium", "docs-reviewer": "haiku/medium",
    "copy-reviewer": "sonnet/medium", "code-reviewer": "sonnet/medium", "test-auditor": "sonnet/medium",
    "performance-auditor": "sonnet/medium", "a11y-auditor": "sonnet/medium", "usability-auditor": "sonnet/medium",
    "visual-reviewer": "sonnet/medium", "design-reviewer": "sonnet/medium", "ops-reviewer": "sonnet/medium",
    "data-reviewer": "sonnet/medium", "implementer": "sonnet/medium",
    "security-auditor": "opus/high", "spec-tracer": "opus/high", "architect": "opus/high", "requirements-reviewer": "opus/high",
}
TIER_OF_POLICY = {"speed": "haiku/medium", "balanced": "sonnet/medium", "quality": "opus/high"}


def recorded_or_computed(store, tid: str) -> tuple[dict, bool]:
    """(tier info, retro). The tier recorded at `start` wins; a task started before 1.32 gets a retroactive one."""
    t = store.tasks()[tid]
    rec = t.get("tier") if isinstance(t.get("tier"), dict) else None
    if rec and rec.get("rule") in TIERS:
        info = task_tier(store, tid)
        info.update({"tier": rec["rule"], "score": rec.get("score", info["score"]), "arm": rec.get("arm", info["arm"]),
                     "context": rec.get("context", info["context"])})
        return info, False
    return task_tier(store, tid), True


def risk_profile(store, milestone: str) -> dict:
    tasks = {k: v for k, v in store.tasks().items() if v.get("milestone") == milestone and v.get("status") != "dropped"}
    rows, sigs_all = [], set()
    jobs = False
    for tid in sorted(tasks, key=lambda x: (tasks[x].get("seq", 0), x)):
        info, retro = recorded_or_computed(store, tid)
        names = {s["signal"] for s in info["reasons"]}
        sigs_all |= names
        jobs = jobs or any(JOBS_FILE.search(str(f)) for f in tasks[tid].get("files") or [])
        rows.append({"task": tid, "tier": info["tier"], "score": info["score"], "signals": sorted(names), "retro": retro})
    max_tier = max((r["tier"] for r in rows), key=TIERS.index, default=None)
    high = [r["task"] for r in rows if r["tier"] in ("balanced+", "quality")]
    seams = []
    for tid in high:
        t = tasks[tid]
        for d in dict.fromkeys(list(t.get("deps") or []) + list(t.get("consumes") or [])):
            if d in tasks:
                seams.append([d, tid])
    flags = {"touches_auth_send_secrets": bool(sigs_all & {"auth", "external_send"}),
             "touches_schema": "schema" in sigs_all,
             "touches_data_jobs_send": bool(sigs_all & {"schema", "external_send"}) or jobs}
    prof = {"milestone": milestone, "max_tier": max_tier, "high_risk_tasks": high, "seams": seams, **flags, "tasks": rows}
    prof["auditors"] = {a: audit_rule_arm(store, a, prof) for a in AGENT_BASE if a not in ("implementer", "architect", "requirements-reviewer", "design-reviewer")}
    prof["profile"] = profile_tag(prof)
    return prof


def profile_tag(prof: dict) -> str:
    if prof.get("touches_auth_send_secrets") or prof.get("max_tier") == "quality":
        return "risky"
    if prof.get("touches_data_jobs_send"):
        return "data"
    return "plain"


def audit_rule_arm(store, agent: str, prof: dict) -> str:
    """Round-1 model/effort of an auditor for this milestone's risk profile (Passo 6)."""
    if agent == "spec-tracer":
        return "opus/high"
    if agent == "security-auditor":
        risky = prof.get("touches_auth_send_secrets") or prof.get("max_tier") == "quality"
        return "opus/high" if risky else "sonnet/high"
    over = (model_policy(store.state).get("tiers") or {}).get(agent)
    base = TIER_OF_POLICY.get(over) if over else AGENT_BASE.get(agent, "sonnet/medium")
    if agent == "data-reviewer" and not prof.get("touches_schema"):
        return "haiku/medium"
    if agent in ("code-reviewer", "ops-reviewer", "performance-auditor", "data-reviewer") and prof.get("touches_data_jobs_send") \
            and base == "sonnet/medium":
        return "sonnet/high"
    return base


# --------------------------------------------------------------------------- predicted vs actual

def _git_files(root: Path, sha: str | None) -> list[str]:
    if not sha:
        return []
    try:
        r = subprocess.run(["git", "-C", str(root), "show", "--name-only", "--format=", sha],
                           capture_output=True, text=True, timeout=20)
        return [x.strip() for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def _norm(p: str) -> str:
    return str(p or "").split(":")[0].lstrip("./")


def agent_usage(events: list[dict], scope: str) -> dict:
    """Implementer time and tokens of one task, from the agent_end events whose scope is the task."""
    out = {"duration_s": 0.0, "tokens": 0, "tokens_in": 0, "tokens_out": 0, "agents": 0, "models": []}
    for e in events:
        if e.get("event") == "agent_end" and e.get("scope") == scope:
            out["agents"] += 1
            out["duration_s"] += float(e.get("duration_s") or 0)
            for k in ("tokens", "tokens_in", "tokens_out"):
                out[k] += int(e.get(k) or 0)
            arm = f"{e.get('model') or '?'}/{e.get('effort') or '?'}"
            if arm not in out["models"]:
                out["models"].append(arm)
    return out


def risk_rows(store, milestone: str, events: list[dict] | None = None) -> list[dict]:
    """Per task of a milestone: predicted tier, attributed findings, rounds, ledger result, time and tokens, readings.

    Attribution is a heuristic: a finding belongs to every task whose `files` or commit files contain the finding's
    file. A fix task never takes its own source finding."""
    events = events or []
    tasks = {k: v for k, v in store.tasks().items() if v.get("milestone") == milestone and v.get("status") != "dropped"}
    findings = findings_of(store, milestone)
    fix_src = {}
    for k, v in tasks.items():
        m = re.match(r"^qa/M\d+/report\.md#([\w.-]+?)(?:-r\d+)?$", str(v.get("source") or ""))
        if m:
            fix_src[k] = m.group(1)
    ledger = led.load(store.dev)
    rows = []
    for tid in sorted(tasks, key=lambda x: (tasks[x].get("seq", 0), x)):
        t = tasks[tid]
        info, retro = recorded_or_computed(store, tid)
        files = {_norm(f) for f in (t.get("files") or [])} | {_norm(f) for f in _git_files(store.root, t.get("commit"))}
        mine = []
        for fid, f in findings.items():
            if fix_src.get(tid) == fid:
                continue
            ff = _norm(f.get("file") or "")
            if ff and (ff in files or any(ff.endswith("/" + x) or x.endswith("/" + ff) for x in files if x)):
                mine.append(f)
        sev = {s: sum(1 for f in mine if f.get("severity") == s) for s in ("critical", "high", "medium", "low")}
        fixes = [k for k, src in fix_src.items() if src in {f["id"] for f in mine}]
        rounds = int(t.get("returns", 0) or 0) + len(fixes)
        hist = ledger.get(f"task:{tid}") or {}
        use = agent_usage(events, tid)
        escape = sev["critical"] + sev["high"] > 0
        files_n = len(t.get("files") or [])
        areas = [a for a in areas_of([str(f) for f in t.get("files") or []])]
        readings = []
        if info["tier"] in ("speed", "balanced") and info["score"] <= 1 and escape:
            readings.append("loose_rule")
        if info["tier"] == "quality" and not mine:
            readings.append("maybe_overpaid")
        if info["tier"] in ("balanced", "balanced+") and rounds >= 2:
            readings.append("lacked_effort")
        if TIERS.index(info["tier"]) >= 1 and not mine and rounds == 0 and files_n <= 3 and len(areas) <= 1 and not info["floor"]:
            readings.append("missed_opportunity")
        rows.append({"task": tid, "type": t.get("type"), "status": t.get("status"), "tier": info["tier"],
                     "score": info["score"], "arm": (t.get("tier") or {}).get("arm") if isinstance(t.get("tier"), dict) else None,
                     "routed": bool((t.get("tier") or {}).get("routed")) if isinstance(t.get("tier"), dict) else False,
                     "context": info["context"], "signals": sorted({s["signal"] for s in info["reasons"]}),
                     "floor": info["floor"], "retro": retro, "findings": sev, "finding_ids": sorted(f["id"] for f in mine),
                     "escape": escape, "rounds": rounds, "fix_tasks": sorted(fixes), "ledger": hist.get("result"),
                     "blocked": int(t.get("blocked_count", 0) or 0), **use, "readings": readings})
    return rows


def summarize_rows(rows: list[dict]) -> dict:
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r["tier"], {"tasks": 0, "escapes": 0, "rounds": 0, "tokens": 0, "duration_s": 0.0})
        b["tasks"] += 1
        b["escapes"] += 1 if r["escape"] else 0
        b["rounds"] += r["rounds"]
        b["tokens"] += r["tokens"]
        b["duration_s"] += r["duration_s"]
    for b in by.values():
        b["escape_rate"] = round(b["escapes"] / b["tasks"], 2) if b["tasks"] else 0.0
        b["rounds_per_task"] = round(b["rounds"] / b["tasks"], 2) if b["tasks"] else 0.0
    return {t: by[t] for t in TIERS if t in by}


READING_TEXT = {
    "loose_rule": "predicted low, produced a high finding: a signal's weight should go up",
    "maybe_overpaid": "predicted quality, passed with no finding: the expensive model may not have been needed",
    "lacked_effort": "predicted medium, took 2+ rounds: effort or model was short for the case",
    "missed_opportunity": "small, single-area, no finding: could have gone one tier lower",
}
