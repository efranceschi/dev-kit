"""Build realistic dev-kit 2.6.1 projects with the 2.6.1 scripts (the 3.0 migration fixtures of test_v3_migration.py).
usage: python3 -I build_fixture_261.py <2.6.1 kit>/skills/core/scripts/dev_state.py OUTDIR
Get the 2.6.1 kit with: git archive 2f52a93 .claude/plugins/dev-kit | tar -x -C /tmp/k261
Copy each project's .dev/ here without its .git, *.lock and state.json.bak, with .dev/run/ renamed .dev/run-fixture/
(git ignores run/; the test renames it back)."""
import json, os, subprocess, sys, shutil
from pathlib import Path
K, OUT = sys.argv[1], Path(sys.argv[2])
env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
def ds(root, *a, ok=True):
    p = subprocess.run([sys.executable, "-I", K, "--root", str(root), *a], capture_output=True, text=True, cwd=root, env=env)
    tag = "OK " if p.returncode == 0 else f"RC{p.returncode}"
    print(f"[{root.name}] {tag} {' '.join(a)}" + ("" if p.returncode == 0 else f"\n   {p.stdout.strip()[-300:]} {p.stderr.strip()[-400:]}"))
    return p
def task(n, title, ac, deps="", files=None):
    return (f"### T-{n:03d} {title}\n- status: todo\n- deps: {deps}\n" + (f"- dep_reasons: T-{n-1:03d}: uses its model\n" if deps else "") +
            f"- type: feature\n- acceptance:\n  - {ac}\n- test_notes: unit\n- files: {files or f'src/f{n}.py'}\n\n")
def ms(k, title, goal, start, n):
    return f"## M{k} — {title}\n{goal}\n\n" + "".join(task(i, f"{title} step {i}", f"AC-{i}: {title.lower()} step {i} works", f"T-{i-1:03d}" if i > start else "") for i in range(start, start + n))
def base(root, plan_text):
    if root.exists(): shutil.rmtree(root)
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root); 
    ds(root, "init", "--language", "pt", "--project", root.name)
    d = root / ".dev"
    (d / "brief.md").write_text("# Brief\nShop app.\n"); ds(root, "artifact", "mark", "brief")
    (d / "prd.md").write_text("# PRD\n" + "".join(f"- AC-{i}: x\n" for i in range(1, 30)))
    ds(root, "artifact", "mark", "prd"); ds(root, "review", "prd", "pass", "--score", "96")
    (d / "architecture.md").write_text("# Architecture\n"); ds(root, "artifact", "mark", "architecture")
    ds(root, "review", "design", "n/a", "--note", "no UI")
    (d / "plan.md").write_text(plan_text); ds(root, "sync-plan"); ds(root, "artifact", "mark", "plan")
    ds(root, "review", "plan", "pass", "--score", "95")
def finish(root, m, partial=None):
    st = json.loads((root / ".dev/state.json").read_text())
    tids = [t for t, v in sorted(st["tasks"].items()) if v["milestone"] == m and v["status"] == "todo"]
    for t in tids[:partial] if partial else tids:
        ds(root, "start", t); ds(root, "done", t, "--commit", "abc1234")
def gate(root, m):
    ds(root, "gate", m, "passed", "--score", "95")

# A: no planned releases (cut model), M1 released as v1.0.0, M2 half done, M3 todo, open issue, board request
A = OUT / "proj-cut-releases"
base(A, "# Implementation plan — shop\n\n" + ms(1, "Catalog", "Browse products.", 1, 6) + ms(2, "Cart", "Add to cart.", 7, 6) + ms(3, "Checkout", "Pay.", 13, 5) + ms(4, "Orders", "Order history.", 18, 5))
finish(A, "M1"); gate(A, "M1"); ds(A, "release-record", "--version", "1.0.0", "--milestones", "M1")
finish(A, "M2"); gate(A, "M2"); ds(A, "release-record", "--version", "1.1.0", "--milestones", "M2")
finish(A, "M3", partial=3)
ds(A, "add-issue", "--type", "bug", "--title", "Price rounding", "--class", "standard", "--severity", "medium")
(A / ".dev/requests").mkdir(exist_ok=True)

# B: planned releases; R1 (M1,M2) released, R2 (M3) rejected -> fixes milestone M5 (after M4 in R3), R3 (M4) todo
B = OUT / "proj-planned-releases"
base(B, "# Implementation plan — shop\n\n## R1 — First sale\n\n" + ms(1, "Catalog", "Browse.", 1, 5) + ms(2, "Cart", "Cart.", 6, 5)
     + "## R2 — Payments\n\n" + ms(3, "Checkout", "Pay.", 11, 5) + "## R3 — Accounts\n\n" + ms(4, "Accounts", "Login.", 16, 5))
for m in ("M1", "M2"): finish(B, m); gate(B, m)
ds(B, "release-submit", "R1"); ds(B, "release-decide", "R1", "--approve"); ds(B, "release-record", "--version", "1.0.0", "--release", "R1")
finish(B, "M3"); gate(B, "M3"); ds(B, "release-submit", "R2"); ds(B, "release-decide", "R2", "--reject", "--feedback", "Receipt total wrong")
# C: brownfield maintenance: M7 — Maintenance gated and cut as v2.3.1, M8 — Maintenance open with one task
C = OUT / "proj-maintenance"
if C.exists(): shutil.rmtree(C)
C.mkdir(parents=True); subprocess.run(["git", "init", "-q"], cwd=C)
ds(C, "init", "--language", "pt", "--project", C.name, "--brownfield-json", '{"mode": "maintenance", "baseline_ref": "v2.3.0", "first_milestone": 7}')
(C / ".dev/plan.md").write_text("# Plan\n\n## M7 — Maintenance\n"); ds(C, "sync-plan")
for r in ("prd", "design", "plan"): ds(C, "review", r, "n/a", "--note", "maintenance mode")
ds(C, "add-task", "--milestone", "M7", "--title", "Fix rounding", "--type", "fix", "--files", "src/price.py")
ds(C, "start", "T-001"); ds(C, "done", "T-001", "--commit", "abc1234"); gate(C, "M7")
ds(C, "release-record", "--version", "2.3.1", "--milestones", "M7")
ds(C, "add-task", "--milestone", "M8", "--milestone-title", "Maintenance", "--title", "Fix tax label", "--type", "fix", "--files", "src/tax.py")
sys.path.insert(0, str(Path(K).parent)); import dev_worker as w
for root in (A, B):
    r = w.submit(root, "issue_new", {"title": "Search is slow", "type": "bug"})
    print(root.name, "request", r)
