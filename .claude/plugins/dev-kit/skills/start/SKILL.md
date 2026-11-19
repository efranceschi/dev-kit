---
name: start
description: Entry point and resume for dev-kit projects. Detects whether .dev/ exists, reconciles state with git, reports where the project is (interview, PRD, plan, implementation, QA...) and routes to the next * skill. For an existing codebase without .dev/ it runs the onboarding first (git baseline tag, discovery, test baseline, retroactive ADRs). Use when the user wants to start building an application, adopt the kit in an existing project, continue a project, or asks "where were we" / "what's next". Also use to kick off a new project idea.
argument-hint: "[project idea or goal, or empty to resume]"
allowed-tools: Read, Grep, Glob, Bash, AskUserQuestion, Skill
---

# start — router and resume

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event. When you resume or start a project, begin a new session with `event session_start --set trigger=start`.

Current state (empty when this is a new project):
!`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Stack detection of the current directory:
!`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_detect_stack.py" "${CLAUDE_PROJECT_DIR}"`

User input: $ARGUMENTS

## Preflight
If the injected output above contains a Python "can't open file" error, the kit is incomplete: tell the user that the `core` skill (it holds the scripts and shared templates) must be installed in the same place as the other dev-kit skills, and stop.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` (language rule, layout, autonomy summary). Apply the language rule now: converse in the user's language.
2. **Existing codebase, no state above** (detection says `"greenfield": false`): follow `${CLAUDE_SKILL_DIR}/../core/shared/onboarding.md` end to end (git baseline tag, `.dev/discovery.md` with the project's own conventions, existing docs and ADRs, test baseline, entry mode `feature` / `maintenance` / `import`, `brownfield` marker in state), then hand over as the chosen mode says. Tell the user in three lines what the onboarding will do and that nothing in the existing code, docs or history is modified. The user's input is the goal of the change. Skip the rest of this step.
2b. **New project (no state above, `"greenfield": true`):**
   - If the directory is not a git repository, initialise one (`git init`) unless the user objects; dev-kit commits per task.
   - Explain in three lines how the kit works: one thorough interview, then autonomous build with checkpoints only on always-ask decisions; artifacts live in `.dev/`. Mention that `/dev-kit:help` answers any "how do I…?" at any time.
   - Invoke `interview` with the user's input as the initial idea (Skill tool: `interview`). Do not ask questions here; the interview owns them.
3. **Existing project (state above):**
   - Reconcile with git: run `git status --short` and `git log -5 --format='%h %s'`. If a task is `in_progress`:
     - a commit for it exists (subject `[T-xxx]`, or trailer `Refs: T-xxx` when `autonomy.commit_style` has no `{task}`; `git log --grep T-xxx`) → run `dev_state.py done T-xxx --commit <sha>`.
     - uncommitted changes exist for it → tell the user you will continue it (default) unless they prefer to reset (`unblock`/`--force`); when running autonomously, continue.
     - no changes at all → `dev_state.py set` nothing; just note the task will restart.
   - Show the three-line status and open questions count, and one line: "Not sure what to do? /dev-kit:help".
   - Existing project (state has `brownfield`, `conventions.md` §16): before the table, check the artifacts in order — `brief.md` → `prd.md` → `architecture.md` → `design/ux-flows.md` and `design/ui-spec.md` (only if a `new` AC touches the UI and review `design` is not `n/a`) → `plan.md` — and route to the skill that writes the first one missing, whatever the phase says (say which stage was skipped). In `maintenance` mode with phase `implement` and no `todo` tasks, route to `issue` (or `backlog`) instead of `implement`.
   - Decide the next skill from `phase`:
     | phase | next |
     |---|---|
     | init / interview | `interview` (resumes at first missing block) |
     | prd | `prd` |
     | architecture | `architecture` |
     | ux | `ux` |
     | ui | `ui` |
     | plan | `plan` |
     | implement | `implement` (or `autopilot` to run until the next gate) |
     | qa | `qa <milestone>` |
     | usability | `usability` |
     | docs | `docs` |
     | done | `release` or nothing |
   - If the user's input names a different intent (e.g. "add feature X", "run QA"), honour it instead: a scope change goes through `interview --gaps` then `plan`.
4. Offer two options, recommended first: run the whole pipeline autonomously (`autopilot`) or run only the next step. If the brief's autonomy level is `high` and the user gave no instruction, invoke `autopilot` directly.

## Never
- Never edit `.dev/state.json` by hand; use the script.
- Never move or recreate the `dev-kit-baseline` tag, and never modify existing source or docs during onboarding.
- Never skip the interview for a new project unless the user explicitly says "skip the interview" (then run `interview` in express mode: one round with the four most critical questions).
