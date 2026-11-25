"""Build a stress project for the board: far more of everything than a normal project, to see where the board breaks.

usage: python3 -I build_stress.py SCENARIO PROJECT_DIR      SCENARIO = onerel | huge | text
  onerel  one release holding 20 milestones (the field report that started 3.14.0), then a short second release
  huge    20 releases, 60 milestones, about 1,200 tasks, 60 questions, 120 issues, 30 blocked cards, 16 implementers at work
  text    very long names, unbroken words, emoji, accents and CJK; a QA round with 7 auditors; 25 denied permissions
Like build_demo.py it drives the project only through dev_state.py, with made-up data; it reuses that file's helpers.
Then serve the board on PROJECT_DIR and run node stress.js (see docs/maintainers.md, "Stress the board").
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if len(sys.argv) != 3 or sys.argv[1] not in ("onerel", "huge", "text"):
    sys.exit(__doc__)
SCEN, OUT_ARG = sys.argv[1], sys.argv[2]
sys.argv = ["build_demo.py", OUT_ARG]  # build_demo reads its project dir from argv
spec = importlib.util.spec_from_file_location("build_demo", Path(__file__).resolve().parents[1] / "build_demo.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)
ds, OUT = bd.ds, bd.OUT

TITLES = ["Walking skeleton and overview", "Attribution and exploration", "Budgets and alerts", "Anomalies",
          "Governance, recommendations and user guide", "Should: forecast and assistant", "Warehouse attribution and activity split",
          "Tag taxonomy and guardrails", "Monthly showback and shared cost split", "Alerts that reach people",
          "Configuration changes, access and delegated permissions", "Warehouse operations", "Improvements 1st round",
          "Improvements 2nd round", "Export for finance", "Chargeback per cost center", "Quarterly forecast",
          "Executive dashboard", "Security hardening", "Improvements 3rd round"]
LONGW = "Integration-with-the-cloud-provider-billing-service-via-https://billing.example.com/api/v2/accounts/{id}/usage?granularity=hourly"
ACCENTS = "Fun" + chr(0xE7) + chr(0xE3) + "o de exporta" + chr(0xE7) + chr(0xE3) + "o"  # accented letters (kit files are English)

if SCEN == "onerel":
    REL = {"R1": "v1.0.0 Serverless Cost Control", "R2": "v1.1.0 Multi-cloud"}
    sizes = [24, 9, 8, 9, 9, 6, 12, 7, 7, 14, 14, 19, 7, 14, 10, 8, 9, 7, 11, 12]
    MS = [("R1", k, TITLES[k - 1], sizes[k - 1]) for k in range(1, 21)] + [("R2", 20 + k, f"Multi-cloud part {k}", 6) for k in range(1, 4)]
    CLOSE, RELEASE_EVERY, CURRENT, CUR_DONE = 19, None, "M20", 5
elif SCEN == "huge":
    REL = {f"R{i}": f"Release {i}" for i in range(1, 21)}
    MS = [(f"R{(k - 1) // 3 + 1}", k, f"Milestone {k}", 5 if k <= 40 else (120 if k == 41 else 45)) for k in range(1, 61)]
    CLOSE, RELEASE_EVERY, CURRENT, CUR_DONE = 40, 3, "M41", 60
else:
    REL = {"R1": "First public version for every enterprise customer in Latin America and Europe \U0001F680",
           "R2": "多云成本控制 - international edition with Asian languages"}
    MS = [("R1", 1, "Foundation: " + "authentication, authorization, auditing and compliance trail " * 3, 6),
          ("R1", 2, LONGW, 8), ("R1", 3, "Reports \U0001F4CA " + "with export " * 6, 40), ("R2", 4, "国际化与本地化 " * 6, 10)]
    CLOSE, RELEASE_EVERY, CURRENT, CUR_DONE = 2, None, "M3", 10

bd.RELEASES = REL


def title(k: int, i: int) -> str:
    if SCEN == "text":
        return [LONGW, "A task with an extremely long title that describes in detail everything that has to be done " * 2,
                "✅ emoji \U0001F525 in the title \U0001F9EA", "短标题", ACCENTS, f"T {i}"][i % 6]
    return f"Task {k}.{i}" + (" with a long title that the cards have to cut" if i % 5 == 0 else "")


bd.MILESTONES = [(r, k, t, f"Goal of milestone {k}.", [(title(k, i), f"src/m{k}/f{i}.ts") for i in range(n)]) for r, k, t, n in MS]


def at(day: datetime, minutes: int) -> str:
    return (day + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:00Z")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=OUT, check=True)
    name = {"onerel": "Serverless Cost Control", "huge": "Larder Huge",
            "text": "Enterprise Cloud Cost Control Platform - International Edition with a very long name"}[SCEN]
    ds("init", "--language", "en", "--project", name, now="2026-03-01T09:00:00Z")
    d = OUT / ".dev"
    for f, body in (("brief.md", "# Brief\nx\n"), ("prd.md", "# PRD\n" + "".join(f"- AC-{i}: c{i}\n" for i in range(1, 2500))),
                    ("architecture.md", "# Architecture\nx\n")):
        (d / f).write_text(body, encoding="utf-8")
    for a in ("brief", "prd", "architecture"):
        ds("artifact", "mark", a, now="2026-03-01T10:00:00Z")
    ds("review", "prd", "pass", "--score", "94", now="2026-03-01T13:00:00Z")
    (d / "design").mkdir()
    for a, f in (("ux", "ux-flows.md"), ("ui", "ui-spec.md")):
        (d / "design" / f).write_text("# x\n", encoding="utf-8")
        ds("artifact", "mark", a, now="2026-03-02T14:00:00Z")
    ds("review", "design", "pass", "--score", "91", now="2026-03-02T16:00:00Z")
    ds("set", "autonomy.release_flags", '{"enabled": true, "provider": "env var FLAG_<NAME>"}')
    ds("set", "autonomy.production", '{"when": "per_milestone_flagged", "method": "docker compose", "host": "remote", "smoke": ["/health"]}')
    ds("set", "autonomy.production.health", '{"url": "https://x.example/health", "interval_min": 60}')
    (d / "plan.md").write_text(bd.plan_text(), encoding="utf-8")
    ds("sync-plan", now="2026-03-03T09:00:00Z")
    ds("artifact", "mark", "plan", now="2026-03-03T09:00:00Z")
    ds("review", "plan", "pass", "--score", "93", now="2026-03-03T11:00:00Z")
    ds("checkpoint", "confirm", "plan", now="2026-03-03T12:00:00Z", ok=False)
    ds("checkpoint", "confirm", "prd", now="2026-03-03T12:00:00Z", ok=False)
    day0, ver = datetime(2026, 3, 5, 9), 0
    for k in range(1, CLOSE + 1):
        m, day = f"M{k}", day0 + timedelta(days=k * 4)
        for i, t in enumerate(bd.tasks_of(m)):
            ds("start", t, now=at(day, 30 * i))
            ds("done", t, "--commit", f"{(k * 1000 + i) % 0xfffffff:07x}", now=at(day, 30 * i + 20))
        g = (day + timedelta(days=2)).strftime("%Y-%m-%d")
        bd.gate(m, g, 90, rounds=(10 if SCEN == "text" and k == 2 else (3 if k % 6 == 0 else 1)), reason="flaky e2e on CI")
        ds("deploy", "production", "--sha", f"{k:07x}", "--milestone", m, "--status", "ok" if k % 7 else "failed", now=f"{g}T17:00:00Z", ok=False)
        if RELEASE_EVERY and k % RELEASE_EVERY == 0:
            r = f"R{k // RELEASE_EVERY}"
            rr = d / "releases" / r / "review.md"
            rr.parent.mkdir(parents=True, exist_ok=True)
            rr.write_text(f"# Release {r}\n\n## Summary\nx\n", encoding="utf-8")
            ds("release-submit", r, "--review", f".dev/releases/{r}/review.md", now=f"{g}T18:00:00Z")
            ds("release-decide", r, "--approve", now=f"{g}T19:00:00Z")
            ds("flag", "set", f"release_{r}", "on", now=f"{g}T19:10:00Z", ok=False)
            ver += 1
            ds("release-record", "--version", f"1.{ver}.0", "--release", r, now=f"{g}T19:30:00Z")
        print("closed", m, flush=True)
    for t in bd.tasks_of(CURRENT)[:CUR_DONE]:
        ds("start", t, now="2026-11-20T09:00:00Z")
        ds("done", t, "--commit", "abcdef1", now="2026-11-20T10:00:00Z")
    left = bd.tasks_of(CURRENT)
    par = 16 if SCEN != "onerel" else 3
    for t in left[:par]:
        ds("start", t, "--force")
    for t in left[par:par + (30 if SCEN == "huge" else 6)]:
        ds("block", t, "--reason", "waiting for an answer about the split rule " + ("between shared cost centers " * (3 if SCEN == "text" else 0)))
    for i, t in enumerate(bd.tasks_of(CURRENT, "in_progress")):
        ds("event", "agent_spawn", "--set", "agent=implementer", "--set", "model=sonnet", "--set", "effort=medium",
           "--set", f"scope={t}", "--set", f"slot={i + 1}")
    ds("event", "skill_start", "--set", "skill=implement", "--set", "args_kind=milestone", "--set", f"scope={CURRENT}")
    for i in range({"onerel": 4, "huge": 60, "text": 8}[SCEN]):
        q = f"Question {i + 1}: should the shared cost split use the moving average or the month's value?"
        if SCEN == "text":
            q = "A very long question " + "with many details about the context and the consequences of each choice " * 12 + LONGW
        ds("add-question", q, "--options", "|".join(f"Option {c} with a description" for c in "ABCDEF"[: (6 if SCEN == "text" else 3)]),
           "--recommended", "Option A with a description", "--skill", "implement")
    for i in range({"onerel": 5, "huge": 120, "text": 12}[SCEN]):
        ds("add-issue", "--type", ["bug", "improvement", "change"][i % 3], "--title",
           f"Issue {i + 1}: " + ("field report " * (15 if SCEN == "text" else 1)), "--class",
           ["standard", "expedite", "standard", "standard"][i % 4] if i < 8 else "standard", "--severity", ["low", "medium", "high"][i % 3], ok=False)
    if SCEN == "text":  # a QA round with 7 auditors at work and 25 permissions denied because nobody answered
        ds("event", "skill_start", "--set", "skill=qa", "--set", "scope=M2")
        for a in ("code-reviewer", "security-auditor", "test-auditor", "spec-tracer", "deps-auditor", "a11y-auditor", "data-reviewer"):
            ds("event", "agent_spawn", "--set", f"agent={a}", "--set", "model=opus", "--set", "scope=M2")
        perms = {f"k{i}": {"key": f"k{i}", "tool": "Bash", "count": i + 1, "how": "timeout", "agent": "test-auditor",
                           "rule": f"Bash(npx playwright-{i} *)", "target": "npx playwright test --project=chromium " + "--grep x " * 20, "last": i}
                 for i in range(25)}
        (d / "run").mkdir(exist_ok=True)
        (d / "run" / "permission-misses.json").write_text(json.dumps(perms), encoding="utf-8")
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    log = {"checks": [{"at": (t0 - timedelta(minutes=15 * i)).isoformat(), "ok": i % 9 != 7, "target": "https://x.example/health",
                       "detail": "HTTP 200", "duration_s": 0.21} for i in reversed(range(500))]}
    log["last"], log["streak"] = log["checks"][-1], 7
    (d / "run").mkdir(exist_ok=True)
    (d / "run" / "prod-health.json").write_text(json.dumps(log), encoding="utf-8")
    print("done", SCEN)


main()
