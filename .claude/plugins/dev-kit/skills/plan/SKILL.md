---
name: plan
description: Turns PRD, architecture and design into an executable implementation plan (.dev/plan.md) of milestones and small vertical-slice tasks with ids, dependencies, acceptance criteria, test notes and files, then syncs it into .dev/state.json. Use after ui (or architecture for UI-less products), when scope changes, or to re-plan remaining work.
argument-hint: "[milestone focus | 'replan']"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# plan

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Preconditions
`.dev/prd.md` and `.dev/architecture.md` exist; `.dev/design/*.md` exist for UI products.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §3–4 (ids and parser contract), `${CLAUDE_SKILL_DIR}/../core/shared/templates/plan.md`, `${CLAUDE_SKILL_DIR}/../core/shared/checklists/test-pyramid.md`, the PRD (stories, ACs, priorities), architecture (layout, contracts, CI), design specs (screens), brief block 3 (priority order) and block 8 (mandatory e2e flows).
2. Milestones: M1 is always the walking skeleton (scaffold, tooling, CI, lint/test commands, one thin end-to-end slice of the top must-have). Following milestones group must-haves by priority order; should/could features come last. Each milestone has an exit criterion and a QA gate.
3. Tasks: vertical slices (schema + API + UI + tests for one capability) sized for one sitting; each lists the ACs it fulfils, `test_notes` naming the layers to test, and the files it will likely touch. Infrastructure tasks only when a feature needs them. Every AC in the PRD appears in at least one task; every mandatory e2e flow has a task that writes it.
4. Dependencies: minimal and explicit; avoid long chains so `implement --parallel` can work.
5. Write `.dev/plan.md` **exactly** in the parser format (`## M1 — Title`, `### T-001 Title`, fields `status/deps/type/acceptance/test_notes/files`). Task ids continue from `next_task_id` in state when replanning; never renumber.
6. Run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" sync-plan` and fix any warnings it prints (unknown deps, undeclared milestones). Then `dev_state.py set phase implement`.
7. Report: milestones with task counts, estimated sessions, ACs without tasks (must be none), and the first task. Next: `review plan` (independent score against the cut-off), then `implement` or `autopilot`.

## `replan`
Keep done/in_progress tasks untouched; rewrite only `todo` tasks of remaining milestones; new tasks get new ids; mark dropped tasks by deleting their section (state keeps them as `todo`; block them with reason "dropped in replan ADR-nnn" to keep history consistent).
