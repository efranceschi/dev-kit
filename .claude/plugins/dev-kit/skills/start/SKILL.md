---
name: start
description: Entry point and resume for dev-kit projects. Detects whether .dev/ exists, reconciles state with git, reports where the project is (interview, PRD, plan, implementation, QA...) and routes to the next skill. For an existing codebase without .dev/ it runs the onboarding first (git baseline tag, discovery, test baseline, retroactive ADRs). Use when the user wants to start building an application, adopt the kit in an existing project, continue a project, or asks "where were we" / "what's next". Also use to kick off a new project idea.
argument-hint: "[project idea or goal, or empty to resume]"
allowed-tools: Read, Grep, Glob, Bash, AskUserQuestion, Skill
---

# start — router and resume

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: for a new project, create the state first with a minimal `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" init --project "<folder name>"` (the lifecycle starts at conception · interview; the interview's `init` later completes it; `init` is idempotent), so the first events are not lost; an existing project gets its state at onboarding step 2. Then record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event. When you resume or start a project, begin a new session with `event session_start --set trigger=start`.

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
   - Housekeeping, so the user never has to run anything by hand: `dev_state.py cleanup` (stops processes left by a crashed run, only inside the project, and frees expired locks); `dev_state.py stale --json`: when it lists artifacts as `untracked` (a project created before kit 1.16), record the current documents as the reference with `dev_state.py artifact mark all` and say so in one line; for each `done` task whose recorded commit no longer exists (`git cat-file -e <sha>` fails, e.g. after a hook rewrote it), find the commit that carries it (`git log --grep T-xxx`, or the trailer) and, after confirming with the user, `dev_state.py done T-xxx --commit <sha> --force`.
   - Risk tiers (kit 1.32, `conventions.md` §9): when the project is in construction and `dev_state.py xref --json` → `notes` says pending tasks have no risk fields, say once in one line that their tiers use objective signals only and that `/dev-kit:plan --annotate-risk` adds the fields without replanning (optional; never run it without the user). When the project has passed gates and no `.dev/router.json`, the next passed gate backfills the router from the history by itself.
   - Show the three-line status and open questions count, and one line: "Not sure what to do? /dev-kit:help".
   - Claude Code interface, offered once (`conventions.md` §15): run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_ui.py" --root "${CLAUDE_PROJECT_DIR}" repair` (it rewrites the status line path after a plugin update, silent otherwise). Then, when `autonomy.ui.offered` in `dev_state.py status --json` is false and the session is interactive, ask one AskUserQuestion (multiSelect, in the user's language) explaining in one line that the choices go to the project's personal `.claude/settings.local.json`, which stays out of git: spinner tips while Claude works, the status line (phase, milestone, running task, next command) and desktop notifications for gates and blocks. Apply what was picked with `dev_ui.py apply` plus `--tips`, `--statusline` and `--notify`. For `--tips`, translate the texts from `dev_ui.py tips` into the user's language, keep commands and file names as they are, write them as a JSON array of strings to `.dev/tmp/spinner-tips.json`, and pass `--tips-file .dev/tmp/spinner-tips.json`. Nothing picked: `dev_ui.py decline`. Say in one line that spinner tips show from the next session and that `/dev-kit:settings` changes any of it. Never ask again once offered.
   - Existing project (state has `brownfield`; the status line says `existing project`, `conventions.md` §16): before the table, check the artifacts in order — `brief.md` → `prd.md` → `architecture.md` → `design/ux-flows.md` and `design/ui-spec.md` (only if a `new` AC touches the UI and review `design` is not `n/a`) → `plan.md` — and route to the skill that writes the first one missing (the lifecycle step says the same; say which stage was skipped). In `maintenance` mode with no `todo` tasks, route to `qa M<n>` when the open maintenance milestone has done tasks and a pending gate, otherwise to `issue` (or `backlog`).
   - Decide the next skill from the lifecycle (`conventions.md` §19): `phase` and `step` in `dev_state.py status --json`; `status --next` gives the same command:
     | phase · step | next |
     |---|---|
     | conception · interview | `interview` (resumes at the first missing block) |
     | conception · prd / architecture / ux / ui | the step's skill, or its review (`review prd`, `review design`) when the step waits for it; a reopened step (scope change) is refreshed the same way |
     | planning · plan | `plan` (`plan replan` after a scope change), then `review plan` |
     | construction · M<n> | `implement` (or `autopilot` to run until the next gate); `qa <M>` when the milestone's tasks are done and its gate is pending |
     | construction · release | the release train: `usability` (UI products), `docs`, `review docs`, then `release` |
     | construction · issues | `backlog` (queued issues wait to be scheduled) |
     | stable | nothing open: `issue` for new work, `backlog` to look |
   - If the user's input names a different intent (e.g. "add feature X", "run QA"), honour it instead: a bug, improvement or scope change goes through `issue` (a scope change is class `change`: `prd` → `review prd` → `plan` replan); open questions go through `interview --gaps`. Existing project in `maintenance` mode and the user asks for a feature: switch with `DS init --brownfield-json '{"mode":"feature"}'` (it reopens the `n/a` reviews), then `interview --express` on the change, `prd` revision and `plan replan`.
4. Offer two options, recommended first: run the whole pipeline autonomously or run only the next step (invoke that skill). When you report instead of invoking, end with the next command alone on the last line (`conventions.md` §15). `autopilot` can only be started by the user: when it is the recommendation (always when the brief's autonomy level is `high` or `unattended` and the user gave no instruction), end with the command in a fenced block, `/dev-kit:autopilot`, and say in one line what it will do; never try to invoke it with the Skill tool.

## Never
- Never edit `.dev/state.json` by hand; use the script.
- Never move or recreate the `dev-kit-baseline` tag, and never modify existing source or docs during onboarding.
- Never skip the interview for a new project unless the user explicitly says "skip the interview" (then run `interview` in express mode: one round with the four most critical questions).

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the next skill from the lifecycle table, unless you invoke it. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
