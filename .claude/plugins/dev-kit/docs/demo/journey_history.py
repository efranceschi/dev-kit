"""Give the demo project the session history a real one has, for the board's Journey tab.

usage: python3 -I journey_history.py PROJECT_DIR
Run it after build_demo.py. build_demo.py moves the state with the kit's commands but runs no skill and spawns no
agent, so its session log has almost no skill runs or agents. This writes the skill runs and agents that would have
produced its log.md (interview, PRD, reviews, plan, one implementer per task, the QA auditors of each gate, the
release checks), each at the time of the log line it belongs to, through the kit's own telemetry writer, and an
estimated cost per milestone in .dev/costs/milestones.json. Made-up data, for the documentation only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT / "skills" / "core" / "scripts"))
import dev_telemetry as tel  # noqa: E402

AUDITORS = ("spec-tracer", "code-reviewer", "test-auditor", "security-auditor", "a11y-auditor")
COSTS = {"M1": 3.84, "M2": 5.12, "M3": 6.47, "M4": 2.95}


def at(v: str, minutes: int = 0) -> str:
    d = datetime.fromisoformat(v.replace("Z", "+00:00")) + timedelta(minutes=minutes)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    dev = root / ".dev"
    out: list[tuple[str, str, dict]] = []

    def run(skill: str, start: str, end: str | None, scope: str = "", agents: tuple = (), status: str = "ok") -> None:
        out.append((start, "skill_start", {"skill": skill, **({"scope": scope} if scope else {})}))
        for i, (agent, model, effort, ascope, a0, a1) in enumerate(agents):
            where = {"scope": ascope or scope} if ascope or scope else {}
            out.append((a0, "agent_spawn", {"agent": agent, "model": model, "effort": effort, **where, "skill": skill, "slot": i + 1}))
            out.append((a1, "agent_end", {"agent": agent, "model": model, "effort": effort, **where, "skill": skill, "slot": i + 1,
                                           "status": "ok", "tokens": 18000 + 7919 * (i + 1) % 40000}))
        if end:
            out.append((end, "skill_end", {"skill": skill, "status": status, **({"scope": scope} if scope else {})}))

    d = "2026-11-02T00:00:00Z"
    day = lambda n, hh, mm=0: at(d, ((n - 2) * 24 + hh) * 60 + mm)  # noqa: E731 - day n of November, hh:mm UTC
    run("start", day(2, 8, 40), day(2, 9, 0))
    run("interview", day(2, 9, 0), day(2, 10, 0))
    run("prd", day(2, 10, 5), day(2, 12, 0))
    run("review", day(2, 12, 20), day(2, 13, 0), "prd", (("requirements-reviewer", "opus", "high", "prd", day(2, 12, 22), day(2, 12, 58)),))
    run("architecture", day(3, 9, 0), day(3, 10, 0), "", (("architect", "opus", "high", "", day(3, 9, 5), day(3, 9, 55)),))
    run("diagram", day(3, 10, 10), day(3, 10, 30))
    run("ux", day(3, 11, 0), day(3, 13, 0))
    run("ui", day(3, 13, 0), day(3, 14, 0))
    run("review", day(3, 15, 10), day(3, 16, 0), "design", (("design-reviewer", "opus", "high", "design", day(3, 15, 12), day(3, 15, 58)),))
    run("plan", day(4, 8, 10), day(4, 9, 0))
    run("review", day(4, 10, 20), day(4, 11, 0), "plan", (("requirements-reviewer", "sonnet", "high", "plan", day(4, 10, 22), day(4, 10, 58)),))

    # one implement run per milestone, one implementer per task (start to done in log.md), the QA auditors of each gate
    log = (dev / "log.md").read_text(encoding="utf-8").splitlines()
    starts, by_ms = {}, {}
    state = json.loads((dev / "state.json").read_text(encoding="utf-8"))
    for line in log:
        m = re.match(r"^- (\S+) (start|done) (T-\d+)", line)
        if m and m[1] < "2026-11-20":
            t, what, tid = m.groups()
            ms = state["tasks"][tid]["milestone"]
            if what == "start":
                starts[tid] = t
            elif tid in starts:
                arm = re.search(r"arm=(\w+)/(\w+)", next((x for x in log if f"start {tid} " in x), "")) or None
                by_ms.setdefault(ms, []).append(("implementer", arm[1] if arm else "sonnet", arm[2] if arm else "medium", tid, at(starts[tid], 1), at(t, -1)))
    for ms, agents in by_ms.items():
        run("implement", at(agents[0][4], -5), at(agents[-1][5], 5), ms, tuple(agents))
    for line in log:
        g = re.match(r"^- (\S+) hard-floor (M\d+)", line)
        if g:
            t, ms = g.groups()
            gate = [x for x in log if re.match(rf"^- \S+ gate {ms} (passed|pending)", x)]
            for n, gl in enumerate(gate):
                gt = gl.split(" ")[1]
                g0 = t if n == 0 else at(gate[n - 1].split(" ")[1], 10)
                run("qa", g0, gt, ms, tuple((a, "sonnet", "high", ms, at(g0, 5 + i), at(gt, -10 + i)) for i, a in enumerate(AUDITORS)))
    run("usability", day(9, 8, 0), day(9, 10, 0), "", (("usability-auditor", "sonnet", "high", "", day(9, 8, 5), day(9, 9, 50)),))
    run("docs", day(9, 9, 0), day(9, 10, 0), "", (("docs-reviewer", "haiku", "medium", "", day(9, 9, 5), day(9, 9, 55)),))
    run("release", day(9, 11, 0), day(9, 12, 0), "R1", (("security-auditor", "opus", "high", "", day(9, 11, 5), day(9, 11, 50)),))
    run("release", day(9, 18, 5), day(9, 18, 30), "R1")
    run("deploy", day(14, 16, 40), day(14, 17, 0), "", status="ok")
    run("issue", day(17, 12, 0), day(17, 12, 10))

    for ts, event, fields in sorted(out, key=lambda x: x[0]):
        os.environ["DEV_KIT_NOW"] = ts
        tel.emit(dev, event, fields)
    os.environ.pop("DEV_KIT_NOW", None)
    costs = dev / "costs"
    costs.mkdir(exist_ok=True)
    (costs / "milestones.json").write_text(json.dumps({"milestones": {m: {"usd": u, "tokens": int(u * 61000), "partial": m == "M4"}
                                                                      for m, u in COSTS.items()}}, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out)} session events written")


if __name__ == "__main__":
    main()
