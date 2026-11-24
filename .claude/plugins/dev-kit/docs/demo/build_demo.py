"""Build "Larder", a fictional project with made-up data, for the documentation's board screenshots.

usage: python3 -I build_demo.py PROJECT_DIR
Every number, name and finding here is invented. The project is driven only through the kit's own scripts
(dev_state.py), so the board shows exactly what a real project in that state would show.
Then start the board on PROJECT_DIR and run node capture.js <board url> <images dir> (needs Playwright): see docs/maintainers.md.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
DS = KIT / "skills" / "core" / "scripts" / "dev_state.py"
sys.path.insert(0, str(DS.parent))
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("larder")
ENV = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "DEV_KIT_NOW",
                                                         "DEV_KIT_PARENT_SESSION")}

MILESTONES = [  # release, id, title, goal, tasks (title, files)
    ("R1", 1, "Skeleton and sign-in", "A household member signs in and sees an empty pantry.",
     [("Project skeleton and CI", "package.json, .github/workflows/ci.yml"), ("Email sign-in", "src/auth/signin.ts"),
      ("Session and sign-out", "src/auth/session.ts"), ("Empty pantry screen", "src/pantry/Empty.tsx"),
      ("QA harness", "e2e/harness.ts")]),
    ("R1", 2, "Pantry items", "Add, edit and remove what is in the pantry, with quantities and dates.",
     [("Item model and storage", "src/pantry/item.ts"), ("Add item form", "src/pantry/AddItem.tsx"),
      ("Edit and remove", "src/pantry/EditItem.tsx"), ("Quantities and units", "src/pantry/units.ts"),
      ("Best-before dates", "src/pantry/dates.ts"), ("Search the pantry", "src/pantry/search.ts")]),
    ("R2", 3, "Households", "Invite the people you live with; everyone sees the same pantry.",
     [("Household model", "src/household/model.ts"), ("Invite by link", "src/household/invite.ts"),
      ("Accept an invitation", "src/household/accept.ts"), ("Members screen", "src/household/Members.tsx"),
      ("Leave a household", "src/household/leave.ts"), ("Per-household data access", "src/household/access.ts")]),
    ("R2", 4, "Shopping list", "A shared shopping list that fills itself from what runs out.",
     [("List model and sync", "src/list/model.ts"), ("Add from the pantry", "src/list/fromPantry.ts"),
      ("Check off while shopping", "src/list/CheckOff.tsx"), ("Offline queue", "src/list/offline.ts"),
      ("Low-stock suggestions", "src/list/suggest.ts"), ("Restock after shopping", "src/list/restock.ts")]),
    ("R3", 5, "Expiry alerts", "Get told before food goes off.",
     [("Expiry rules", "src/alerts/rules.ts"), ("Daily digest email", "src/alerts/digest.ts"),
      ("Alert settings", "src/alerts/Settings.tsx"), ("Snooze an alert", "src/alerts/snooze.ts"),
      ("Push notifications", "src/alerts/push.ts")]),
    ("R3", 6, "Monthly report", "See what was used, wasted and bought each month.",
     [("Usage events", "src/report/events.ts"), ("Monthly totals", "src/report/totals.ts"),
      ("Waste chart", "src/report/WasteChart.tsx"), ("Export as CSV", "src/report/csv.ts"),
      ("Report email", "src/report/email.ts")]),
]
RELEASES = {"R1": "First shopping list", "R2": "Shared household", "R3": "Insights"}


def ds(*a: str, ok: bool = True, now: str | None = None) -> subprocess.CompletedProcess:
    env = dict(ENV, **({"DEV_KIT_NOW": now} if now else {}))
    p = subprocess.run([sys.executable, "-I", str(DS), "--root", str(OUT), *a], capture_output=True, text=True, cwd=OUT, env=env)
    if ok and p.returncode != 0:
        sys.exit(f"failed: {' '.join(a)}\n{p.stdout}\n{p.stderr}")
    return p


def plan_text() -> str:
    out, n, cur = ["# Implementation plan — Larder\n"], 1, None
    for rid, k, title, goal, tasks in MILESTONES:
        if rid != cur:
            out.append(f"## {rid} — {RELEASES[rid]}\n")
            cur = rid
        out.append(f"## M{k} — {title}\n{goal}\n- exit_check: e2e: m{k}.spec; acs: AC-{n}\n")
        for i, (tt, files) in enumerate(tasks):
            kind = "chore" if tt in ("Project skeleton and CI", "QA harness") else "feature"
            out.append(f"### T-{n:03d} {tt}\n- status: todo\n- deps: {f'T-{n - 1:03d}' if i and not (k == 4 and i >= 3) else ''}\n- type: {kind}\n"
                       f"- acceptance:\n  - AC-{n}: {tt.lower()} works\n- test_notes: unit and e2e\n- files: {files}\n"
                       + (f"- flag: release_{rid}\n" if kind == "feature" and rid != "R1" else "")
                       + f"- risk: {'high' if 'access' in tt or 'sign-in' in tt.lower() else 'low'}\n- complexity: medium\n- uncertainty: low\n\n")
            n += 1
    return "\n".join(out)


def tasks_of(m: str, status: str = "todo") -> list[str]:
    st = json.loads((OUT / ".dev" / "state.json").read_text(encoding="utf-8"))
    return [t for t, v in sorted(st["tasks"].items()) if v["milestone"] == m and v["status"] == status]


def build(m: str, day: str, n: int | None = None) -> None:
    for i, t in enumerate(tasks_of(m)[:n]):
        ds("start", t, now=f"{day}T{9 + i:02d}:00:00Z")
        ds("done", t, "--commit", f"{abs(hash(t)) % 0xfffffff:07x}", now=f"{day}T{9 + i:02d}:40:00Z")


SCORE = KIT / "skills" / "core" / "scripts" / "dev_score.py"


def audit(m: str, k: int, finding: str | None) -> int:
    """Invented auditor outputs for one QA round, scored by the kit's own dev_score.py; returns the overall score."""
    raw = OUT / ".dev" / "qa" / m / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    found = [{"id": "F-001", "severity": "high", "dimension": "tests", "title": finding, "file": "src/x.ts", "evidence": "e2e run"}] if finding else []
    outs = {"spec-tracer": {"findings": [], "exit_check": {"result": "pass", "checks": [{"check": f"e2e: m{k}.spec", "result": "pass", "detail": "12 passed"}]}},
            "code-reviewer": {"findings": [{"id": "F-002", "severity": "low", "dimension": "code", "title": "long function", "file": "src/x.ts"}]},
            "test-auditor": {"findings": found}, "security-auditor": {"findings": []}, "a11y-auditor": {"findings": []}}
    for name, body in outs.items():
        (raw / f"{name}.json").write_text(json.dumps({"auditor": name, **body}), encoding="utf-8")
    out = OUT / ".dev" / "qa" / m / "scores.json"
    subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", m, "--kind", "gate", "--root", str(OUT), "--out", str(out),
                    *map(str, sorted(raw.glob("*.json")))], capture_output=True, text=True, cwd=OUT, env=ENV)
    try:
        return int(round(json.loads(out.read_text(encoding="utf-8"))["overall"]))
    except (OSError, ValueError, KeyError, TypeError):
        return 90


def gate(m: str, day: str, score: int, rounds: int = 1, reason: str | None = None) -> None:
    k = int(m[1:])
    floor = OUT / ".dev" / "run" / "floor.json"
    floor.parent.mkdir(parents=True, exist_ok=True)
    floor.write_text(json.dumps({**{c: {"status": "pass"} for c in ("tests", "lint", "typecheck", "deps", "secrets")},
                                 "a11y": {"status": "pass"}}), encoding="utf-8")
    ds("hard-floor", m, "--from", str(floor), now=f"{day}T14:00:00Z")
    for r in range(1, rounds):
        sc = audit(m, k, reason)
        ds("gate", m, "pending", "--score", str(min(sc, score - 9)), "--count-run", "--note", reason or "tests", now=f"{day}T15:0{r}:00Z")
    sc = audit(m, k, None)
    ds("gate", m, "passed", "--score", str(sc), "--count-run", now=f"{day}T16:00:00Z")
    flow = OUT / ".dev" / "qa" / m / "flow.json"  # invented cycle numbers, so the forecast has data
    f = json.loads(flow.read_text(encoding="utf-8")) if flow.exists() else {}
    f.update(tasks=6, cycle_time_s=6 * 3600 * (3 + k), working_time_s=6 * 3600 * (1 + k / 4), human_wait_s=3600 * (2 + k),
             cost_per_task=0.35 + k / 10)
    flow.parent.mkdir(parents=True, exist_ok=True)
    flow.write_text(json.dumps(f), encoding="utf-8")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=OUT, check=True)
    ds("init", "--language", "en", "--project", "Larder", now="2026-11-02T09:00:00Z")
    d = OUT / ".dev"
    (d / "brief.md").write_text("# Brief — Larder\nA shared pantry and shopping list for a household.\n", encoding="utf-8")
    ds("artifact", "mark", "brief", now="2026-11-02T10:00:00Z")
    (d / "prd.md").write_text("# PRD — Larder\n" + "".join(f"- AC-{i}: acceptance criterion {i}\n" for i in range(1, 40)), encoding="utf-8")
    ds("artifact", "mark", "prd", now="2026-11-02T12:00:00Z")
    ds("review", "prd", "pass", "--score", "94", now="2026-11-02T13:00:00Z")
    (d / "architecture.md").write_text("# Architecture — Larder\nTypeScript, React, SQLite. Release flags: env var FLAG_<NAME>.\n", encoding="utf-8")
    ds("artifact", "mark", "architecture", now="2026-11-03T10:00:00Z")
    (d / "design").mkdir()
    for a, f in (("ux", "ux-flows.md"), ("ui", "ui-spec.md")):
        (d / "design" / f).write_text(f"# {a.upper()} — Larder\n", encoding="utf-8")
        ds("artifact", "mark", a, now="2026-11-03T14:00:00Z")
    ds("review", "design", "pass", "--score", "91", now="2026-11-03T16:00:00Z")
    ds("set", "autonomy.release_flags", '{"enabled": true, "provider": "env var FLAG_<NAME>"}')
    ds("set", "autonomy.production", '{"when": "per_milestone_flagged", "method": "docker compose", "host": "remote", "smoke": ["/health"]}')
    ds("set", "autonomy.production.health", '{"url": "https://larder.example/health", "interval_min": 60}')
    (d / "plan.md").write_text(plan_text(), encoding="utf-8")
    ds("sync-plan", now="2026-11-04T09:00:00Z")
    ds("artifact", "mark", "plan", now="2026-11-04T09:00:00Z")
    ds("review", "plan", "pass", "--score", "93", now="2026-11-04T11:00:00Z")
    ds("checkpoint", "confirm", "plan", now="2026-11-04T12:00:00Z", ok=False)
    ds("checkpoint", "confirm", "prd", now="2026-11-04T12:00:00Z", ok=False)
    build("M1", "2026-11-05"); gate("M1", "2026-11-05", 92)
    build("M2", "2026-11-07"); gate("M2", "2026-11-08", 90, rounds=2, reason="search misses accents")
    ds("review", "docs", "pass", "--score", "88", now="2026-11-09T10:00:00Z", ok=False)
    ds("review", "ux", "pass", "--score", "90", now="2026-11-09T10:00:00Z", ok=False)
    rr = d / "releases" / "R1" / "review.md"
    rr.parent.mkdir(parents=True, exist_ok=True)
    rr.write_text("# Release R1 — First shopping list · release review\n\n## Summary\nA household member signs in and keeps the pantry.\n", encoding="utf-8")
    ds("release-submit", "R1", "--review", ".dev/releases/R1/review.md", now="2026-11-09T12:00:00Z")
    ds("release-decide", "R1", "--approve", now="2026-11-09T18:00:00Z")
    ds("flag", "set", "release_R1", "on", now="2026-11-09T18:20:00Z")
    ds("release-record", "--version", "1.0.0", "--release", "R1", now="2026-11-09T18:30:00Z")
    build("M3", "2026-11-12"); gate("M3", "2026-11-14", 91, rounds=2, reason="invite link reusable")
    ds("deploy", "production", "--sha", "5d1c9a2", "--milestone", "M3", "--status", "ok", now="2026-11-14T17:00:00Z")
    build("M4", "2026-11-17", n=3)
    left = tasks_of("M4")
    ds("start", left[0]); ds("start", left[1], "--force")  # two implementers in parallel, now, on the real clock
    ds("add-issue", "--type", "bug", "--title", "Units shown as 'pcs' in Portuguese", "--class", "standard", "--severity", "medium")
    ds("add-question", "Should a household have more than one shopping list?", "--options", "One list|One list per store",
       "--recommended", "One list", "--skill", "implement")
    for t in left[:2]:
        ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "model=sonnet", "--set", "effort=medium",
           "--set", f"scope={t}", "--set", f"slot={left.index(t) + 1}")
    ds("event", "skill_start", "--set", "skill=implement", "--set", "args_kind=milestone", "--set", "scope=M4")
    # a short, healthy production history
    # (the last one a few minutes ago and an hourly interval, so the board does not run it against the made-up URL)
    from datetime import datetime, timedelta, timezone
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    log = {"checks": [{"at": (t0 - timedelta(minutes=15 * i)).isoformat(), "ok": i != 7, "target": "https://larder.example/health",
                       "detail": "HTTP 200" if i != 7 else "HTTP 502", "duration_s": 0.21} for i in reversed(range(12))]}
    log["last"], log["streak"] = log["checks"][-1], 7
    (d / "run").mkdir(exist_ok=True)
    (d / "run" / "prod-health.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
