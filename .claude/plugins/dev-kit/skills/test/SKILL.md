---
name: test
description: Test strategy and test writing for dev-kit projects - writes or updates .dev/qa/test-plan.md (pyramid per layer, tools, mandatory e2e flows, coverage target) and adds or repairs tests for a task, module or path, mapping them to acceptance criteria. Use when tests are missing, failing, flaky, or when the user asks to improve coverage or define the testing approach.
argument-hint: "[T-003 | path | 'plan' | 'fix-flaky']"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# test

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status` and a brief `feedback` on the dev-kit itself; the script measures the duration and the plugin hooks log every agent) and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says (allowed keys: `${CLAUDE_SKILL_DIR}/../core/shared/telemetry-schema.json`), with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/checklists/test-pyramid.md`, `.dev/brief.md` block 8, `.dev/architecture.md` §8 and `.dev/qa/test-plan.md` if it exists.
2. **`plan` mode** (or no test plan yet): write `.dev/qa/test-plan.md`: tools per layer for this stack, how to run each (exact commands), test data strategy (fixtures/factories, DB isolation), mandatory e2e flows from the brief with their AC ids, coverage target, CI integration, conventions (naming with AC ids, folder layout). Add the commands to `architecture.md` §8 if missing.
3. **Task or path mode**: list the ACs involved (from `dev_state.py status --json` or the PRD). For each AC without a meaningful test, write one at the lowest layer that can prove it; add edge cases from the checklist. Run the suite; make the tests pass by fixing the code only if the failure is a genuine bug (record it: if the task is `done`, create a fix task via `dev_state.py add-task --type fix --milestone <M> --title ... --acceptance "AC-n: ..." --source test`).
4. **`fix-flaky` mode**: run the suite three times; collect intermittent failures; fix root causes (timing, order, shared state, real network) following the checklist; never add retries as the fix.
5. Report: tests added/changed with file names, AC coverage before/after, suite result, and any fix tasks created.

## Rules
- Behaviour over implementation; one reason to fail per test; deterministic data.
- Do not change production code for testability without a note in the report; keep public contracts stable.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:implement`. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): in `plan` mode, `test-plan.md` first documents what exists (framework, layout, commands, coverage and failures from `.dev/qa/baseline.md`) and then proposes only the gaps for `new` ACs; never replace the project's framework or move existing tests. Coverage targets apply to code changed since `brownfield.baseline_ref`. Characterisation tests for legacy behaviour that a `new` task touches are welcome (name the `existing` AC they pin down).
