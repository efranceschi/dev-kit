#!/usr/bin/env python3
"""dev_router.py - model/effort router that learns from the project's own runs (conventions.md §9 "Router").

Standard library only. Run with: python3 -I dev_router.py [--root DIR] <subcommand> [...]

The rule tier of a task (dev_risk.py) is the starting point. The router keeps, in .dev/router.json, one record per
observed task or audit (context, model/effort used, cost, time, extra rounds, escapes, failures) and derives from
them, deterministically, which model/effort is cheapest for each context once QA rounds and escapes are priced in:
one extra round costs the measured time and money of a QA round plus its fixes, not only tokens.

Subcommands
  route T | --audit AGENT M   model/effort for a task (or an auditor of milestone M) and why (--json)
  observe T                   record a task outcome now (--outcome done|blocked|reopened); dev_state.py calls it on
                              done, block and reopen (fast loop: two failures in a row raise the context one tier
                              for the rest of the milestone; a routed downgrade that failed reverts it, with cooldown)
  learn M                     after M's gate: re-read findings, telemetry and ledger, update the records, the context
                              offsets and the rule's learned weights (slow loop); --backfill also seeds every closed
                              milestone that has no record yet (projects older than the router)
  explain                     contexts, arms, offsets, mistakes, learned weights, savings against the rule (--json)
  reset                       forget what was learned (--context K for one context)

Floors it never breaks: a task with an auth, external-send or schema signal is never routed below its rule tier;
security-auditor never below sonnet/high; spec-tracer always opus/high; no route more than one tier away from the
rule; a `tier:` override in the plan wins. xhigh stays an escalation (§9 ladder) and max is never routed.
Exit codes: 0 ok · 1 usage · 2 state not found
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_risk as risk  # noqa: E402

ARMS = ("haiku/low", "haiku/medium", "sonnet/medium", "sonnet/high", "opus/medium", "opus/high")
ARM_TIER = {"haiku/low": 0, "haiku/medium": 0, "sonnet/medium": 1, "sonnet/high": 2, "opus/medium": 3, "opus/high": 3}
TIER_ARMS = [risk.TIER_ARM[t] for t in risk.TIERS]  # one arm per tier step
BALANCE = {
    "balanced": {"cost": 1.0, "time": 1.0, "quality": 1.0},
    "speed": {"cost": 0.5, "time": 2.0, "quality": 1.0},
    "cost": {"cost": 2.0, "time": 0.5, "quality": 1.0},
    "quality": {"cost": 0.5, "time": 0.5, "quality": 2.5},
}
MIN_N = 3            # observations of an arm in a context before it can win over the rule
PRIOR_N = 1          # pseudo-observations of the pessimistic prior for arms below the rule
PRIOR_ESCAPE = 0.25  # assumed escape rate of an untested cheaper arm (it fades as clean runs accumulate)
ALPHA = 0.3          # exponential moving average: recent runs weigh more
COOLDOWN = 5         # tasks of a context without downgrades after a routed mistake
EXPLORE_EVERY = 4    # deterministic exploration: every 4th eligible observation of a context
DEFAULT_ROUND = {"usd": 2.0, "s": 1800.0}  # one QA round + fixes, until the project has measured its own
ESCAPE_ROUNDS = 1.5  # an escape costs a fix task and a re-audit: 1.5 rounds
QUALITY_ESCAPE = 3.0


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- storage

def empty() -> dict:
    return {"version": 1, "records": {}, "contexts": {}, "mistakes": [], "weights": {}, "weight_log": [],
            "norms": dict(DEFAULT_ROUND), "learned": []}


def load(dev: Path) -> dict:
    try:
        data = json.loads(risk.router_file(dev).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == 1:
            base = empty()
            base.update(data)
            return base
    except (OSError, json.JSONDecodeError):
        pass
    return empty()


def save(dev: Path, data: dict) -> None:
    dev.mkdir(parents=True, exist_ok=True)
    p = risk.router_file(dev)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- statistics

def price_usd(dev: Path, arm: str, tokens_in: int, tokens_out: int, tokens: int) -> float:
    """API-equivalent cost of one run, priced with dev_cost.py's table (.dev/costs/prices.json)."""
    try:
        import dev_cost
        prices = dev_cost.load_prices(dev)
        p = dev_cost.price_for(arm.split("/")[0], prices) or {}
    except Exception:  # noqa: BLE001 - pricing is an estimate; never stop the router
        p = {}
    pin, pout = float(p.get("input", 3)), float(p.get("output", 15))
    if tokens_in or tokens_out:
        return round((tokens_in * pin + tokens_out * pout) / 1e6, 4)
    return round(tokens * (0.85 * pin + 0.15 * pout) / 1e6, 4)


def relative_cost(dev: Path, arm: str, ref_arm: str, ref_cost: float) -> float:
    """Estimated cost of an arm with no data, scaled from a measured arm by the price ratio."""
    a = price_usd(dev, arm, 0, 0, 1_000_000) or 1.0
    b = price_usd(dev, ref_arm, 0, 0, 1_000_000) or 1.0
    eff = {"low": 0.7, "medium": 1.0, "high": 1.4}
    return ref_cost * (a / b) * eff.get(arm.split("/")[1], 1.0) / eff.get(ref_arm.split("/")[1], 1.0)


def fold(records: list[dict]) -> dict:
    """Per arm: n and moving averages of cost, time, rounds, escapes and failures (records in time order)."""
    out: dict[str, dict] = {}
    for r in sorted(records, key=lambda x: (x.get("at") or "", x.get("key") or "")):
        s = out.setdefault(r["arm"], {"n": 0, "usd": 0.0, "s": 0.0, "rounds": 0.0, "escapes": 0.0, "fails": 0.0, "measured": 0})
        s["n"] += 1
        k = max(1.0 / s["n"], ALPHA)
        for f, v in (("rounds", r.get("rounds", 0)), ("escapes", 1.0 if r.get("escape") else 0.0), ("fails", r.get("fails", 0))):
            s[f] += k * (float(v) - s[f])
        if r.get("usd") is not None or r.get("s"):
            s["measured"] += 1
            km = max(1.0 / s["measured"], ALPHA)
            s["usd"] += km * (float(r.get("usd") or 0) - s["usd"])
            s["s"] += km * (float(r.get("s") or 0) - s["s"])
    return out


def expected(stats: dict, arm: str, rule_arm: str, norms: dict, w: dict, dev: Path) -> float | None:
    """Expected cost of an arm, in QA-round units: E = wc·cost/round_usd + wt·time/round_s + wq·quality."""
    s = stats.get(arm)
    ref = stats.get(rule_arm) or {}
    if not s:
        return None
    n = s["n"]
    below = ARM_TIER[arm] < ARM_TIER[rule_arm]
    esc = (s["escapes"] * n + (PRIOR_ESCAPE * PRIOR_N if below else 0)) / (n + (PRIOR_N if below else 0))
    rounds, fails = s["rounds"], s["fails"]
    usd = s["usd"] if s["measured"] else (relative_cost(dev, arm, rule_arm, ref.get("usd", 0)) if ref.get("measured") else 0.0)
    sec = s["s"] if s["measured"] else ref.get("s", 0.0)
    extra = rounds + ESCAPE_ROUNDS * esc
    cost = (usd + extra * norms["usd"]) / max(norms["usd"], 0.01)
    time = (sec + extra * norms["s"] + fails * norms["s"]) / max(norms["s"], 1.0)
    quality = rounds + QUALITY_ESCAPE * esc + fails
    return round(w["cost"] * cost + w["time"] * time + w["quality"] * quality, 4)


def balance_weights(cfg: dict) -> dict:
    b = cfg.get("balance", "balanced")
    if isinstance(b, dict):
        return {k: float(b.get(k, 1.0)) for k in ("cost", "time", "quality")}
    return dict(BALANCE.get(b, BALANCE["balanced"]))


# --------------------------------------------------------------------------- the decision

def candidates(rule_arm: str, floor_idx: int, fixed: bool) -> list[str]:
    if fixed:
        return [rule_arm]
    i = ARM_TIER[rule_arm]
    out = [rule_arm]
    for j in (i - 1, i + 1):
        if 0 <= j < len(TIER_ARMS) and j >= floor_idx:
            arm = TIER_ARMS[j]
            if arm not in out:
                out.append(arm)
    return out


def decide(dev: Path, data: dict, ctx: str, rule_arm: str, *, floor_idx: int, fixed: bool, cfg: dict,
           milestone: str | None, spent: float, override: bool = False) -> dict:
    """Pure decision from router.json: {arm, reason, explore, offset, reason_code, candidates}."""
    mode = cfg.get("mode", "apply")
    res = {"context": ctx, "rule_arm": rule_arm, "arm": rule_arm, "explore": False, "reason_code": "rule",
           "candidates": [], "mode": mode}
    if mode == "off" or override or fixed:
        res["reason"] = "plan override" if override else ("fixed by floor" if fixed else "router off")
        res["reason_code"] = "override" if override else ("fixed" if fixed else "off")
        res["applied_arm"] = rule_arm
        return res
    c = data["contexts"].get(ctx, {})
    recs = [r for r in data["records"].values() if r.get("context") == ctx]
    stats = fold(recs)
    w = balance_weights(cfg)
    budget = cfg.get("budget_usd_per_milestone")
    if isinstance(budget, (int, float)) and budget > 0 and spent >= 0.8 * budget:
        w["cost"] *= 2 if spent < budget else 4
    cand = candidates(rule_arm, floor_idx, fixed)
    scored = []
    for arm in cand:
        e = expected(stats, arm, rule_arm, data["norms"], w, dev)
        n = stats.get(arm, {}).get("n", 0)
        scored.append({"arm": arm, "n": n, "E": e})
    res["candidates"] = scored
    n_ctx = len(recs)
    # 1) fast loop: two failures in a row in this milestone raise the context one tier
    bump = c.get("bump") or {}
    if bump.get("milestone") and bump.get("milestone") == milestone:
        up = next((x["arm"] for x in scored if ARM_TIER[x["arm"]] == ARM_TIER[rule_arm] + 1), None)
        if up:
            res.update(arm=up, reason_code="fast_bump", reason=f"two failures in a row in {milestone}: one tier up")
            return _finish(res, rule_arm, stats)
    # 2) learned offset (slow loop): the rule arm keeps needing extra rounds
    if c.get("offset", 0) > 0:
        up = next((x["arm"] for x in scored if ARM_TIER[x["arm"]] == ARM_TIER[rule_arm] + 1), None)
        if up:
            res.update(arm=up, reason_code="learned_up", reason=f"learned: rule arm needed extra rounds (n={n_ctx})")
            return _finish(res, rule_arm, stats)
    if n_ctx < MIN_N:
        res["reason"] = f"rule (context n={n_ctx} < {MIN_N})"
        return _finish(res, rule_arm, stats)
    cooling = int(c.get("cooldown", 0) or 0) > 0
    # 3) budget exhausted: cheapest allowed arm
    if isinstance(budget, (int, float)) and budget > 0 and spent >= budget and not cooling:
        cheap = min(cand, key=lambda a: ARM_TIER[a])
        res.update(arm=cheap, reason_code="budget", reason=f"budget US${budget:g} for {milestone} used (US${spent:.2f})")
        return _finish(res, rule_arm, stats)
    # 4) lowest expected cost among arms with enough data
    ok = [x for x in scored if x["E"] is not None and (x["n"] >= MIN_N or x["arm"] == rule_arm)]
    if cooling:
        ok = [x for x in ok if ARM_TIER[x["arm"]] >= ARM_TIER[rule_arm]]
    best = min(ok, key=lambda x: (x["E"], ARM_TIER[x["arm"]]), default=None)
    if best and best["arm"] != rule_arm:
        res.update(arm=best["arm"], reason_code="learned",
                   reason=f"lower expected cost (E {best['E']} vs rule {next((x['E'] for x in scored if x['arm'] == rule_arm), '-')}, n={best['n']})")
        return _finish(res, rule_arm, stats)
    # 5) deterministic exploration one tier down, only when the rule arm is consistently more than needed
    rs = stats.get(rule_arm, {})
    lower = next((x["arm"] for x in scored if ARM_TIER[x["arm"]] == ARM_TIER[rule_arm] - 1), None)
    consistent = rs.get("n", 0) >= MIN_N and rs.get("escapes", 1) == 0 and rs.get("rounds", 1) == 0 and rs.get("fails", 1) == 0
    if lower and consistent and not cooling and stats.get(lower, {}).get("n", 0) < MIN_N and n_ctx % EXPLORE_EVERY == EXPLORE_EVERY - 1:
        res.update(arm=lower, explore=True, reason_code="explore",
                   reason=f"exploring one tier down: rule arm had no rounds, escapes or failures in {rs['n']} runs")
        return _finish(res, rule_arm, stats)
    res["reason"] = "rule" + (" (cooldown after a mistake)" if cooling else f" (best expected cost, n={n_ctx})")
    if cooling:
        res["reason_code"] = "cooldown"
    return _finish(res, rule_arm, stats)


def _finish(res: dict, rule_arm: str, stats: dict) -> dict:
    a, r = stats.get(res["arm"], {}), stats.get(rule_arm, {})
    if res["arm"] != rule_arm and a.get("measured") and r.get("measured"):
        res["saves_usd"] = round(r["usd"] - a["usd"], 2)
        res["saves_min"] = round((r["s"] - a["s"]) / 60, 1)
    res["applied_arm"] = res["arm"] if res["mode"] == "apply" else rule_arm
    return res


def spent_in(data: dict, milestone: str | None) -> float:
    return round(sum(float(r.get("usd") or 0) for r in data["records"].values() if milestone and r.get("milestone") == milestone), 4)


def route_task(store, tid: str, data: dict | None = None) -> dict:
    """Rule tier + router decision for a task (used by dev_state.py brief, tier and start)."""
    info = risk.task_tier(store, tid)
    data = data if data is not None else load(store.dev)
    cfg = risk.model_policy(store.state)["router"]
    t = store.tasks()[tid]
    floor_idx = ARM_TIER[info["arm"]] if info["floor"] else 0
    d = decide(store.dev, data, info["context"], info["arm"], floor_idx=floor_idx, fixed=False, cfg=cfg,
               milestone=t.get("milestone"), spent=spent_in(data, t.get("milestone")), override=info["source"] == "plan")
    if not info["applied"]:
        d["applied_arm"] = risk.BASE_ARM
        d["reason"] = f"risk_tiers {info['mode']}: agent base"
    model, effort = d["applied_arm"].split("/")
    return {**info, "route": d, "final_arm": d["applied_arm"], "final_model": model, "final_effort": effort}


def route_audit(store, agent: str, milestone: str, data: dict | None = None) -> dict:
    prof = risk.risk_profile(store, milestone)
    rule = prof["auditors"].get(agent) or risk.AGENT_BASE.get(agent, "sonnet/medium")
    data = data if data is not None else load(store.dev)
    cfg = risk.model_policy(store.state)["router"]
    fixed = agent == "spec-tracer"
    floor_idx = ARM_TIER[rule] if prof["profile"] == "risky" else 0
    if agent == "security-auditor":
        floor_idx = max(floor_idx, ARM_TIER["sonnet/high"])
    ctx = f"audit:{agent.split('-')[0]}:{prof['profile']}"
    d = decide(store.dev, data, ctx, rule, floor_idx=floor_idx, fixed=fixed, cfg=cfg, milestone=milestone,
               spent=spent_in(data, milestone))
    model, effort = d["applied_arm"].split("/")
    return {"agent": agent, "milestone": milestone, "profile": prof["profile"], "rule_arm": rule, "route": d,
            "final_arm": d["applied_arm"], "final_model": model, "final_effort": effort,
            "high_risk_tasks": prof["high_risk_tasks"], "seams": prof["seams"]}


def route_line(r: dict) -> str:
    d = r["route"]
    extra = ""
    if d.get("saves_usd") is not None:
        extra = f"; saves ~US${d['saves_usd']:.2f} and ~{d['saves_min']:g} min per task"
    mode = "" if d["mode"] == "apply" else "; router " + str(d["mode"]) + ": rule applies"
    return (f"Route: {r['final_model']} / {r['final_effort']} ({d.get('reason', d['reason_code'])}; context {d['context']}"
            f"{extra}{'; exploration' if d.get('explore') else ''}{mode})")


# --------------------------------------------------------------------------- feedback loops

def observe(store, tid: str, outcome: str, data: dict | None = None, *, save_now: bool = True) -> dict:
    """Fast loop. done: record the run; blocked/reopened: count a failure, raise the context after two in a row,
    and treat a failed routed downgrade as a mistake (revert to the rule, cooldown)."""
    data = data if data is not None else load(store.dev)
    t = store.tasks()[tid]
    rec_t = t.get("tier") if isinstance(t.get("tier"), dict) else {}
    info = risk.task_tier(store, tid)
    ctx = rec_t.get("context") or info["context"]
    arm = rec_t.get("arm") or info["arm"]
    rule_arm = rec_t.get("rule_arm") or risk.TIER_ARM.get(rec_t.get("rule") or info["tier"], info["arm"])
    key = f"{tid}#{int(t.get('returns', 0) or 0)}.{int(t.get('blocked_count', 0) or 0)}"
    c = data["contexts"].setdefault(ctx, {"streak_fail": 0, "cooldown": 0, "offset": 0})
    failed = outcome in ("blocked", "reopened")
    if outcome == "done":
        c["streak_fail"] = 0
        if c.get("cooldown"):
            c["cooldown"] = max(0, int(c["cooldown"]) - 1)
    elif failed:
        c["streak_fail"] = int(c.get("streak_fail", 0)) + 1
        if c["streak_fail"] >= 2:
            c["bump"] = {"milestone": t.get("milestone"), "at": now()}
            c["streak_fail"] = 0
        if ARM_TIER.get(arm, 1) < ARM_TIER.get(rule_arm, 1):
            mistake(data, ctx, tid, arm, rule_arm, f"routed below the rule and {outcome}")
    rec = data["records"].get(key) or {"key": key, "task": tid, "kind": "task", "context": ctx, "arm": arm,
                                       "rule_arm": rule_arm, "milestone": t.get("milestone"), "at": now()}
    rec.update({"outcome": outcome, "fails": 1 if failed else 0, "rounds": int(t.get("returns", 0) or 0)})
    data["records"][key] = rec
    if save_now:
        save(store.dev, data)
    return {"task": tid, "context": ctx, "arm": arm, "outcome": outcome, "streak_fail": c.get("streak_fail", 0),
            "bump": c.get("bump"), "cooldown": c.get("cooldown", 0)}


def mistake(data: dict, ctx: str, tid: str, arm: str, rule_arm: str, why: str) -> None:
    c = data["contexts"].setdefault(ctx, {"streak_fail": 0, "cooldown": 0, "offset": 0})
    c["cooldown"] = COOLDOWN
    c["offset"] = max(0, int(c.get("offset", 0)))
    if not any(m.get("task") == tid and m.get("why") == why for m in data["mistakes"]):
        data["mistakes"].append({"task": tid, "context": ctx, "arm": arm, "rule_arm": rule_arm, "why": why, "at": now()})


def measure_norms(events: list[dict], milestones: dict) -> dict:
    """Measured cost of one QA round + fixes: qa skill time and qa/fix agent tokens per run, else the defaults."""
    secs, runs = 0.0, 0
    for e in events:
        if e.get("event") == "skill_end" and e.get("skill") == "qa" and e.get("duration_s"):
            secs += float(e["duration_s"])
            runs += 1
    out = dict(DEFAULT_ROUND)
    if runs >= 2:
        out["s"] = round(secs / runs, 1)
    return out


def learn(store, milestone: str, *, backfill: bool = False, events: list[dict] | None = None, data: dict | None = None) -> dict:
    """Slow loop: rebuild the milestone's records from findings, telemetry and ledger; update offsets, mistakes and
    the rule's learned weights. Idempotent: learning the same milestone twice gives the same router.json."""
    if events is None:
        try:
            import dev_telemetry as tel
            events, _ = tel.read_events(store.dev)
        except Exception:  # noqa: BLE001
            events = []
    first = data is None and not risk.router_file(store.dev).exists()
    data = data if data is not None else load(store.dev)
    targets = [milestone]
    if backfill or first:
        targets = [m for m in store.milestone_order() if store.milestones()[m].get("gate") in ("passed", "skipped")
                   and m not in data["learned"]] + ([milestone] if milestone else [])
    targets = list(dict.fromkeys(x for x in targets if x in store.milestones()))
    added = 0
    for m in targets:
        rows = risk.risk_rows(store, m, events)
        for r in rows:
            if r["status"] != "done":
                continue
            key = f"{r['task']}#final"
            arm = r["arm"] or _arm_from_models(r["models"]) or risk.TIER_ARM[r["tier"]]
            rule_arm = risk.TIER_ARM[r["tier"]]
            # the fast-loop records of this task are replaced by its final record
            for k in [k for k in data["records"] if k.startswith(r["task"] + "#") and k != key]:
                data["records"].pop(k)
            usd = price_usd(store.dev, arm, r["tokens_in"], r["tokens_out"], r["tokens"]) if r["tokens"] or r["tokens_in"] else None
            data["records"][key] = {"key": key, "task": r["task"], "kind": "task", "context": r["context"], "arm": arm,
                                    "rule_arm": rule_arm, "milestone": m, "at": store.tasks()[r["task"]].get("done_at") or now(),
                                    "usd": usd, "s": r["duration_s"] or None, "rounds": r["rounds"], "escape": r["escape"],
                                    "fails": 1 if r["blocked"] or r["ledger"] in ("failed", "blocked") else 0,
                                    "signals": r["signals"], "tier": r["tier"], "floor": r["floor"], "retro": r["retro"]}
            added += 1
            if r["escape"] and ARM_TIER.get(arm, 1) < ARM_TIER[rule_arm]:
                mistake(data, r["context"], r["task"], arm, rule_arm, "routed below the rule and a high finding escaped")
        added += _learn_audits(store, data, m, events)
        if m not in data["learned"]:
            data["learned"].append(m)
        for c in data["contexts"].values():  # a fast bump lasts only for its milestone
            if (c.get("bump") or {}).get("milestone") == m:
                c.pop("bump", None)
    data["norms"] = measure_norms(events, store.milestones())
    _learn_offsets(data)
    changes = _learn_weights(data)
    save(store.dev, data)
    return {"milestones": targets, "records": added, "weights": data["weights"], "weight_changes": changes,
            "mistakes": len(data["mistakes"]), "contexts": len({r["context"] for r in data["records"].values()})}


def _arm_from_models(models: list[str]) -> str | None:
    for m in models:
        model, _, effort = m.partition("/")
        fam = next((f for f in ("haiku", "sonnet", "opus") if f in model.lower()), None)
        arm = f"{fam}/{effort}" if fam else None
        if arm in ARM_TIER:
            return arm
    return None


def _learn_audits(store, data: dict, milestone: str, events: list[dict]) -> int:
    """One record per auditor of the milestone: arm of its first run, extra runs = rounds."""
    prof = risk.risk_profile(store, milestone)
    runs: dict[str, list[dict]] = {}
    for e in events:
        if e.get("event") == "agent_end" and e.get("scope") == milestone and e.get("agent") in risk.AGENT_BASE:
            runs.setdefault(e["agent"], []).append(e)
    n = 0
    for agent, rs in runs.items():
        if agent == "implementer":
            continue
        first = rs[0]
        arm = _arm_from_models([f"{first.get('model') or ''}/{first.get('effort') or ''}"]) or risk.AGENT_BASE[agent]
        rule = prof["auditors"].get(agent) or risk.AGENT_BASE[agent]
        tokens_in = sum(int(e.get("tokens_in") or 0) for e in rs)
        tokens_out = sum(int(e.get("tokens_out") or 0) for e in rs)
        tokens = sum(int(e.get("tokens") or 0) for e in rs)
        key = f"{milestone}:{agent}"
        data["records"][key] = {"key": key, "kind": "audit", "agent": agent, "context": f"audit:{agent.split('-')[0]}:{prof['profile']}",
                                "arm": arm, "rule_arm": rule, "milestone": milestone, "at": first.get("ts") or now(),
                                "usd": price_usd(store.dev, arm, tokens_in, tokens_out, tokens) if tokens else None,
                                "s": sum(float(e.get("duration_s") or 0) for e in rs) or None,
                                "rounds": len(rs) - 1, "escape": False, "fails": 0}
        n += 1
    return n


def _learn_offsets(data: dict) -> None:
    """A context whose rule arm keeps needing extra rounds (mean ≥ 1 over ≥ 3 runs) goes one tier up; a context
    that has been fine for 3 runs since then comes back to the rule."""
    by: dict[str, list[dict]] = {}
    for r in data["records"].values():
        by.setdefault(r["context"], []).append(r)
    for ctx, recs in by.items():
        c = data["contexts"].setdefault(ctx, {"streak_fail": 0, "cooldown": 0, "offset": 0})
        at_rule = [r for r in recs if r["arm"] == r.get("rule_arm")]
        st = fold(at_rule).get(at_rule[0]["arm"]) if at_rule else None
        if st and st["n"] >= MIN_N and st["rounds"] + st["fails"] + st["escapes"] >= 1:
            c["offset"] = 1
        elif c.get("offset", 0) > 0:
            above = [r for r in recs if ARM_TIER.get(r["arm"], 0) > ARM_TIER.get(r.get("rule_arm", ""), 0)]
            sa = fold(above)
            if any(v["n"] >= MIN_N and v["rounds"] + v["fails"] + v["escapes"] < 0.34 for v in sa.values()) and \
                    (not st or st["rounds"] + st["fails"] + st["escapes"] < 1):
                c["offset"] = 0


def _learn_weights(data: dict) -> list[dict]:
    """Learned deltas of the rule's weights, recomputed from every task record (bounded ±2; floor signals never go
    down): a signal in ≥ 3 tasks with escape rate ≥ 50% goes +1 (+2 with ≥ 6 tasks); a signal seen only in ≥ 3
    quality tasks that all passed with no finding and no round goes -1."""
    recs = [r for r in data["records"].values() if r.get("kind") == "task"]
    old = dict(data.get("weights") or {})
    new: dict[str, int] = {}
    for sig in risk.RISK_WEIGHTS:
        with_sig = [r for r in recs if sig in (r.get("signals") or [])]
        if len(with_sig) >= 3:
            rate = sum(1 for r in with_sig if r.get("escape")) / len(with_sig)
            if rate >= 0.5:
                new[sig] = 2 if len(with_sig) >= 6 else 1
                continue
            if sig not in risk.FLOOR_SIGNALS and all(r.get("tier") == "quality" for r in with_sig) and \
                    not any(r.get("escape") or r.get("rounds") for r in with_sig):
                new[sig] = -1
    changes = []
    for sig in sorted(set(old) | set(new)):
        if old.get(sig, 0) != new.get(sig, 0):
            changes.append({"signal": sig, "from": old.get(sig, 0), "to": new.get(sig, 0), "at": now()})
    data["weights"] = new
    data["weight_log"] = (data.get("weight_log") or []) + changes
    return changes


def explain(store, data: dict | None = None) -> dict:
    data = data if data is not None else load(store.dev)
    by: dict[str, list[dict]] = {}
    for r in data["records"].values():
        by.setdefault(r["context"], []).append(r)
    ctxs = []
    for ctx in sorted(set(by) | set(data["contexts"])):
        st = fold(by.get(ctx, []))
        c = data["contexts"].get(ctx, {})
        ctxs.append({"context": ctx, "n": len(by.get(ctx, [])), "offset": c.get("offset", 0), "cooldown": c.get("cooldown", 0),
                     "bump": c.get("bump"), "arms": {a: {k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()}
                                                     for a, s in st.items()}})
    saved_usd = 0.0
    routed = 0
    for r in data["records"].values():
        if r.get("arm") != r.get("rule_arm") and r.get("usd") is not None:
            routed += 1
            ref = relative_cost(store.dev, r["rule_arm"], r["arm"], float(r["usd"]))
            saved_usd += ref - float(r["usd"])
    return {"contexts": ctxs, "mistakes": data["mistakes"], "weights": data["weights"], "weight_log": data["weight_log"],
            "norms": data["norms"], "learned": data["learned"], "records": len(data["records"]),
            "savings": {"routed_runs": routed, "usd_vs_rule": round(saved_usd, 2)}}


# --------------------------------------------------------------------------- CLI

def _store(root: str | None):
    import dev_state as ds
    store = ds.Store(ds.find_root(root))
    store.load()
    return store, ds


def cmd_route(a: argparse.Namespace) -> None:
    store, ds = _store(a.root)
    if a.audit:
        if not a.milestone or a.milestone not in store.milestones():
            ds.fail("--audit needs an agent and an existing milestone: route --audit security-auditor M3")
        r = route_audit(store, a.audit, a.milestone)
        print(json.dumps(r, indent=2) if a.json else f"{a.audit} {a.milestone}: " + route_line(r)
              + (f"\nHigh-risk tasks: {', '.join(r['high_risk_tasks'])} (check the seams between them first)" if r["high_risk_tasks"] else ""))
        return
    if not a.task or a.task not in store.tasks():
        ds.fail("usage: route T-xxx | route --audit AGENT M")
    r = route_task(store, a.task)
    print(json.dumps(r, indent=2, ensure_ascii=False) if a.json else risk.tier_line(r) + "\n" + route_line(r))


def cmd_observe(a: argparse.Namespace) -> None:
    store, ds = _store(a.root)
    if a.task not in store.tasks():
        ds.fail(f"unknown task {a.task}")
    r = observe(store, a.task, a.outcome)
    print(json.dumps(r, indent=2) if a.json else f"{a.task} {a.outcome} · context {r['context']} · arm {r['arm']}"
          + (f" · {r['context']} raised one tier for {r['bump']['milestone']}" if r.get("bump") else ""))


def cmd_learn(a: argparse.Namespace) -> None:
    store, ds = _store(a.root)
    if a.milestone and a.milestone not in store.milestones():
        ds.fail(f"unknown milestone {a.milestone}")
    if not a.milestone and not a.backfill:
        ds.fail("usage: learn M | learn --backfill")
    r = learn(store, a.milestone, backfill=a.backfill)
    if a.json:
        print(json.dumps(r, indent=2))
        return
    print(f"router learned {', '.join(r['milestones']) or '-'}: {r['records']} record(s), {r['contexts']} context(s), "
          f"{r['mistakes']} mistake(s) on file")
    for c in r["weight_changes"]:
        print(f"  weight {c['signal']}: {c['from']:+d} -> {c['to']:+d}")


def cmd_explain(a: argparse.Namespace) -> None:
    store, _ = _store(a.root)
    r = explain(store)
    if a.json:
        print(json.dumps(r, indent=2))
        return
    print(f"router: {r['records']} record(s), learned {', '.join(r['learned']) or 'nothing yet'}; "
          f"one QA round ≈ US${r['norms']['usd']:.2f} and {r['norms']['s'] / 60:.0f} min")
    for c in r["contexts"]:
        arms = ", ".join(f"{k} n={v['n']} rounds={v['rounds']} esc={v['escapes']}" for k, v in c["arms"].items())
        flags = " ".join(x for x in (f"offset +{c['offset']}" if c["offset"] else "", f"cooldown {c['cooldown']}" if c["cooldown"] else "",
                                     f"raised in {c['bump']['milestone']}" if c.get("bump") else "") if x)
        print(f"  {c['context']}: {arms or 'no runs'}" + (f" [{flags}]" if flags else ""))
    for m in r["mistakes"][-10:]:
        print(f"  mistake {m['task']}: {m['arm']} instead of {m['rule_arm']} — {m['why']}")
    for k, v in sorted(r["weights"].items()):
        print(f"  learned weight {k}: {v:+d}")
    print(f"  savings against the rule: US${r['savings']['usd_vs_rule']:.2f} over {r['savings']['routed_runs']} routed run(s)")


def cmd_reset(a: argparse.Namespace) -> None:
    store, _ = _store(a.root)
    data = load(store.dev)
    if a.context:
        data["records"] = {k: v for k, v in data["records"].items() if v.get("context") != a.context}
        data["contexts"].pop(a.context, None)
        data["mistakes"] = [m for m in data["mistakes"] if m.get("context") != a.context]
        save(store.dev, data)
        print(f"router: forgot {a.context}")
    else:
        save(store.dev, empty())
        print("router: forgot everything (the rule applies until it learns again)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev_router.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: walk up from cwd to find .dev/state.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("route"); s.set_defaults(fn=cmd_route)
    s.add_argument("task", nargs="?"); s.add_argument("milestone", nargs="?")
    s.add_argument("--audit", metavar="AGENT"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("observe"); s.set_defaults(fn=cmd_observe); s.add_argument("task")
    s.add_argument("--outcome", choices=["done", "blocked", "reopened"], required=True); s.add_argument("--json", action="store_true")
    s = sub.add_parser("learn"); s.set_defaults(fn=cmd_learn); s.add_argument("milestone", nargs="?")
    s.add_argument("--backfill", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("explain"); s.set_defaults(fn=cmd_explain); s.add_argument("--json", action="store_true")
    s = sub.add_parser("reset"); s.set_defaults(fn=cmd_reset); s.add_argument("--context")
    return p


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if a.cmd == "route" and a.audit and a.task and not a.milestone:
        a.milestone, a.task = a.task, None  # route --audit AGENT M
    a.fn(a)


if __name__ == "__main__":
    main()
