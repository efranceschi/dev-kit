---
name: implement
description: Executes plan tasks autonomously - picks the next ready task, implements it test-first per architecture and design specs, runs the suite, records state and makes one git commit per task - until the milestone ends, a task count is reached, or a blocking decision appears. Use to build or continue building; pass a task id, --tasks N, --milestone Mn, or --parallel N.
argument-hint: "[T-003 | --tasks N | --milestone M1 | --parallel N | --skip-gate]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# implement

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`
Git: !`git status --short 2>/dev/null | head -20`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Setup (once per run)
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` (§5 commits, §6 autonomy), `${CLAUDE_SKILL_DIR}/../core/shared/checklists/test-pyramid.md`, `.dev/architecture.md`, `.dev/decisions.md`; keep `.dev/design/*.md` and `.dev/prd.md` at hand for the tasks touched. Load the autonomy policy from `DS status --json`.
2. Reconcile: if the working tree has uncommitted changes that belong to an `in_progress` task, continue that task. If they belong to nothing known, apply `pause_policy.dirty_tree` (`conventions.md` §10): `ask` → stop and ask what to do; `auto_recommend` → `git stash push -u -m "dev-kit auto <date>" -- . ':(exclude).dev'` and log it (never stash `.dev/`, `conventions.md` §5). Never commit unknown changes.
3. Parse arguments: a specific task id; `--tasks N` (default: until the current milestone's tasks are all done); `--milestone Mn`; `--parallel N` (use `implementer` agents for independent ready tasks, max N); `--skip-gate` (writes an ADR `(user)` and runs `DS gate <prev> skipped`).

## Loop per task
Hotfix tasks (`lane: hotfix`, `conventions.md` §15) come first from `DS next`, even with a pending gate; only one is open at a time. When a hotfix is done, the next step is `qa --scope <task>`, then `release --hotfix` (which deploys it when there is production). Cool-down tasks (`lane: cooldown`) come next. End the run report with one tip from `DS tip implement`.
Log `skill_start`/`skill_end` once per run (`conventions.md` §13); the task transitions are logged by `dev_state.py` itself.
1. `DS next [--milestone Mn] --json` → if exit code 3, read the reason: milestone complete → stop and say "run `qa <M>`" (`DS done` already moved the phase to `qa`; continue into `qa` when invoked by `autopilot`); gate pending → stop unless `--skip-gate`; only blocked tasks → report them and stop.
2. `DS start T-xxx`. Read the task's acceptance, test_notes, files; read the relevant spec sections and the existing code you will touch (reuse utilities; follow architecture layout).
3. Tests first: write failing tests per AC (name/comment with `AC-n`), then implement until green. Run the **full** suite plus lint/type-check. Fix regressions you caused.
4. Decisions: apply the autonomy rule. `decide_alone` → decide, append `ADR-nnn (auto)` to `.dev/decisions.md`, optionally `DS add-question`. `always_ask` → first apply the category's `pause_policy` action (`conventions.md` §10: `preauthorize` within its limit, `auto_recommend`, or `park`); only for `ask`: if running under `autopilot` and the task can be finished without the answer, finish it with the safest assumption and queue the question; otherwise `DS block T-xxx --reason "needs decision: ..."` and ask the user with AskUserQuestion (recommended option first), then `DS unblock` and continue.
5. Time budget: if the task is not converging after roughly `task_time_budget_min` of effort (many failed attempts, environment problems), `DS block T-xxx --reason "<concrete blocker>"`, write what you tried in `.dev/log.md` via the block reason, and move to the next ready task.
6. Commit (when `commit_per_task` is true; if a hook rejects it, fix and retry, and only then take the SHA): `git add` only the task's files (and lockfiles/config it legitimately changed) plus the tracked `.dev/` files (state, plan, decisions, log of the previous step); subject from `autonomy.commit_style` (default `[T-xxx] <type>: <summary>`; trailer `Refs: T-xxx` when the template has no `{task}`, `conventions.md` §5): `git commit -m "<subject>" -m "<body: what, ACs, how verified>"`. Then `DS done T-xxx --commit $(git rev-parse HEAD)`. If committing is disabled, just `DS done T-xxx`.
7. One-line progress note to the user (task, tests count, commit short SHA). Repeat.

## `--parallel N`
Pick up to N ready tasks whose `files` do not overlap. **Serialize** (never run two at once) tasks that touch shared files: route/registry indexes, package `__init__`/barrel files, the migrations head (any task that adds a migration), lockfiles and manifests, shared config.
- Spawn one `implementer` per task with the Agent tool, `run_in_background: true` and **`isolation: "worktree"`**, so each works in its own git worktree; give each the task id, the language, `Project root: ${CLAUDE_PROJECT_DIR}` (it runs `dev_state.py --root` on it from its worktree), a distinct `Slot: N` and the isolation line (`resource-isolation.md`: own port, database, scratch folder and PIDs). `DS start` each with `--force`. Log `agent_spawn`/`agent_end` (`conventions.md` §13).
- When a report arrives, integrate **one at a time** in the main checkout: merge the worktree's branch (on conflict, log `error code=merge_conflict` and re-run that task alone after the others), run the full suite and the type-check yourself, review the diff briefly, commit (hooks run only here, sequentially) and `DS done`. If a hook rejects the commit, fix and commit again, then record the SHA of the commit that landed (`git rev-parse HEAD` after it succeeds).
- `needs_decision` → handle per step 4; `blocked` → `DS block`. A `spec_deviation` in the report → update the spec file or create a fix task, never leave spec and code silently apart.
- After each batch run `DS cleanup`. Keep the main context for coordination only.

## Stop conditions and report
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
Stop when: requested tasks done; milestone complete (announce the gate); an `always_ask` question with action `ask` cannot be deferred; three consecutive tasks blocked (environment problem; `pause_policy.blocked_env`). Always end with: tasks completed (ids + SHAs), tasks blocked (reasons), decisions taken (ADR ids), open questions added, and the next command.

## Never
- Never skip or weaken tests to pass; never commit with failing tests; never edit `state.json` manually; never push unless `may_push` is true and the brief asked for it.

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): follow the folder layout, test framework, test location and naming, and the build/test/lint commands in `.dev/discovery.md` §3–4 (they override `test-pyramid.md` defaults and `architecture.md` §8 where they differ); never add a runner, linter, formatter or build tool without an `always_ask` decision. Uncommitted changes that belong to no task are the user's work: always ask (never stash them on your own). In `maintenance` mode the tasks come from `issue` in the open maintenance milestone (`M<n> — Maintenance`, numbered from `brownfield.first_milestone`); when its tasks are done, the milestone goes to `qa M<n>` like any other, and new issues then open `M<n+1> — Maintenance`. With no task at all, suggest `/dev-kit:issue`.
