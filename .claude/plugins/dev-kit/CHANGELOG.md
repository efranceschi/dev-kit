# Changelog

All notable changes to the dev-kit plugin. Versions follow `.claude-plugin/plugin.json`. Entries before 1.12.0 were reconstructed from the git history.

## 3.6.0 — 2026-11-24

Field report: after a question answered "adopt the work in the worktree", an autopilot implement round applied the earlier attempt of a task (a worktree Claude Code's own isolation had made in `.claude/worktrees/`) to the main checkout and ran the pipeline, while the state still said `todo`. The board showed nothing in progress and the Autopilot card only "finishing the step".

### Fixed
- **Work on a task is always started.** `slot open --task`, `slot apply` and `reconcile --adopt` record the start of a `todo` task when nobody did (the first start is kept); a blocked task is refused until it is unblocked. `done` on a task that is not in progress now says to run `start` first instead of suggesting `--force`.
- **Worktrees made outside the kit are reused.** When `dev-kit/T-nnn` is already checked out in another worktree (such as `.claude/worktrees/T-nnn` from before 3.5.0), `slot open --worktree`, `reconcile --adopt` and `start --resume` work in it instead of failing on `git worktree add`; its branch must still hold `.dev/state.json` and the task's files.
- **A round's reconcile catches work done without a start.** With `--since` (what `round run` passes), a `todo` task with a commit of its own since the round began (`[T-nnn]` or `Refs: T-nnn`) is recorded as done with that commit, so the next run does not pick it again; a `todo` task whose files were left changed in the main checkout gets them moved to its worktree and is blocked, its attempt in the ledger. The summary's `reconciled` gains `tasks_done`.
- **No manual adoption in a round.** In a headless round the fence hook denies the orchestrator `git apply`/`am`/`cherry-pick`, `git checkout|restore|merge` of a `dev-kit/T-nnn` branch and `cp`/`rsync` out of a `worktrees/` folder, and points to the kit's commands; `git apply` is no longer in the round's allowed tools.

### Added
- `dev_state.py start T-nnn --resume`: takes over an earlier attempt (the kit's worktree, another worktree on `dev-kit/T-nnn`, or the branch alone) and keeps the first start. An inline task gets the work applied, staged, to the main checkout after the fence check, and `done` then removes the old worktree and branch; for a delegated task `slot open --worktree` reuses the worktree.
- **The board sees the round.** The Autopilot card shows the round running now (skill, milestone, for how long), its tasks (each opens its card) and its last action, recorded by the fence hook in `.dev/run/round-activity.json`; it warns when an implement round runs with no task started, the switch reads "finishing implement M4" instead of "finishing the step", and the Live list names the round.
- **`/dev-kit:debug`** (26 skills now) and `dev_debug.py`: `check` compares the state with git and the running processes (round marker left by a dead round, a round with no task started, slots of tasks not started, worktrees made outside the kit, tasks committed but not done, uncommitted files of a task not started, among others; exit 1 on an error); `dump` writes `.dev/run/debug/dump-<stamp>.md` with the versions, the checks, git, the open tasks, the run files, the ends of the log, autopilot and round logs, the ledger's task records and the last telemetry events, never source files or the environment, and the home folder as `~`. The skill explains what is happening, separates a project problem from a kit gap after reading the kit's code, gives the recovery commands without running them, and drafts a report for a dev-kit patch with the dump as its attachment.

### Docs
- `conventions.md` §17 (work is always started, `start --resume`, reconcile of unstarted work, the round's activity), `implement` (setup step 2 and round child), help, maintainers.

### Tests
- `test_adopt_start.py`: the field case (a foreign worktree resumed with the first start kept, then removed at `done`), a resume with files outside the task, `slot open` and `adopt` starting the task and refusing a blocked one, a round that commits a task and leaves another's file changed without starting either, the round fence and its activity, the board's round view, and the debug checks and dump.

## 3.5.0 — 2026-11-24

Field report: on a project that works on `new_version` (with an old `main`), an autopilot implement round got worktrees of `main`, its permission requests waited 10 minutes each and were denied, the tasks stayed in progress with their slots open, and an implementer then edited the main checkout.

### Fixed
- **Worktrees from the work branch, created by the kit.** `implement` no longer uses Claude Code's own worktree isolation (it picks its base itself). `dev_state.py slot open N --task T-nnn --worktree` creates `.dev/run/worktrees/T-nnn` on `dev-kit/T-nnn` from the work branch (or the task's pipeline branch), reuses the branch of an earlier attempt, refuses a base without `.dev/state.json` or without the task's files that exist on HEAD, and records the worktree, branch and base in the slot; `brief` prints the `Worktree:` line.
- **The work branch is no longer always `main`.** New `autonomy.git.base_branch` (default null = the branch checked out in the main checkout); `pipeline worktree` and `pipeline integrate` use it, and `pipeline status --json` shows it.
- **The fence keeps an agent in its worktree.** With a worktree, `dev_fence.py` denies an edit outside it (the main checkout included) and a Bash command run from outside it, except `cd` into it, a read-only look, a kit script or a command that names the worktree. The implementer checks `git rev-parse --show-toplevel` first and stops as blocked without a worktree of its own.
- **A round that stops leaves a true state.** New `dev_state.py reconcile [--milestone M] [--since ISO] [--reason TEXT] [--json]`: closes the slots left open, blocks the tasks left in progress with the reason (their attempt in the ledger, with the branch when the worktree has changes), removes clean worktrees and keeps the others. `round run` calls it after every round and adds `reconciled` to its summary; `implement` runs it before it starts, and a task's changes left in the main checkout go to its worktree with `reconcile --adopt T-nnn` instead of being continued there.
- **Headless permissions.** `round run` and the board's autopilot start the child with `--allowedTools` for the kit's scripts, `cd`, the orchestrator's git commands and the project's `architecture.md` §8 commands. The first permission nobody answers on the board stops the round (`verdict: parked`, with the permission in the summary); later requests of that round are denied at once instead of waiting 10 minutes each, and the denial no longer asks the agent to run `block` itself.

### Added
- `slot apply N` (fence check from the worktree's base, then `git apply --3way` of the worktree's changes into the main checkout or the task's pipeline worktree, staged) and `slot close N --remove` (deletes the worktree and its branch once applied). `slot check` defaults to the worktree and its base.

### Docs
- `conventions.md` §17 (worktrees, reconcile, headless permissions), `implement`, `autopilot`, `implementer`, `resource-isolation.md`, `settings` (`autonomy.git`) and troubleshooting.

### Tests
- `test_worktree_isolation.py`: the field report's case (old `main`, work on `new_version`), a refused base, `slot apply` and `--remove`, the worktree fence, a round that dies, an unanswered permission that stops the round, and `reconcile --adopt`.

## 3.4.0 — 2026-11-24

### Added
- **Execution time on finished work** (board): a done task card shows how long the task took ("took 40m", from `started_at` to `done_at`), in the task details too; a closed milestone says it next to "closed" in its header, on its Closed step, in the milestone picker's tooltip, on the Replan screen and in its release's Milestones block ("took 7.0 h", from its first task's start to the gate); a released release says it next to "released" ("released in 4.4 d", from the first task of its milestones to the release) and in the release picker's tooltip. The tooltips add the working time (parallel work counted once). Spans of two days or more read in days; durations of a day or more on the live timers read as `1d02h`.

### Docs
- `stages.md` and `concepts.md` describe the execution time; new screenshot `board-release-done.png` (R1 released), and the others taken again on 3.4.0. `capture.js` takes the new shot.

### Tests
- `test_v3_board.py`: the board shows the execution time on done cards, closed milestones and released releases, with its strings in both catalogs.

## 3.3.1 — 2026-11-24

### Docs
- **Stage by stage** (`docs/stages.md`), a new page that walks through every stage of the flow diagram (conception, planning, milestones, releases, stable and maintenance) with the same four parts each: what to run, what the board shows, what needs you (the interview, Confirm PRD, Confirm plan, questions and permissions in Needs you, decisions after failed gates, Approve or Reject a release) and how to get unstuck. It opens with the two ways to drive (the board's Autopilot switch or a session), what each word next to the switch means and what to do, Implementers at once, Needs you and Live, and ends with coming from 2.x (the in-place migration: backup, R0, review and Confirm plan, `--annotate-exit`). Linked from both READMEs, `GET_STARTED.md` and `getting-started.md`.
- **3.2 and 3.3 in the docs**: `GET_STARTED.md` and `getting-started.md` show how to let the board drive the build with the Autopilot switch and set the implementers at once; `concepts.md` describes the switch and the top bar instead of the removed "running" chip and "Go on by itself"; both READMEs list the Autopilot; troubleshooting has rows for "waiting for you", "stopped", "waiting for another session", a manual autopilot that defers to the board and an overloaded machine; the recipe "Drive the work from the board" no longer mentions "Go on by itself", and a new recipe "Let the board drive the build" and glossary entries (Autopilot switch, implementers at once, Needs you) come from `help.json`; the e2e and autonomy checklists check the switch instead of continuous mode.
- **Screenshots** taken again on 3.3.1 (the top bar now has the Autopilot switch), with four new ones: the Conception and Milestones lanes, the Autopilot card and the Needs you drawer. `docs/demo/autopilot_running.py` shows the demo board's Autopilot as running without starting Claude Code, and `capture.js` takes the new shots.

### Tests
- `test_v3_docs.py`: every stage of `stages.md` has its four parts, every state of the Autopilot switch in `board.js` is explained there, and the entry pages link it.

## 3.3.0 — 2026-11-24

### Added
- **Implementers at once** on the Autopilot card: − N + from 1 to 6 (default 3; 1 = one task at a time), with how many implementers run now. Kept on this machine in `.dev/run/autopilot.json` (`parallel`), next to the switch; `dev_worker.py autopilot parallel N` and `POST /api/autopilot {"parallel": N}` do the same. Only implementers: QA keeps its rule (light auditors together, heavy ones `nproc ÷ 3`).
- `dev_state.py next --batch auto`: the batch size is that number (the JSON says `batch_size`). `implement --parallel auto` runs it again before every batch, so a change on the card applies from the next batch while running implementers finish; `--parallel N` given by hand still wins for its run. The autopilot (board or by hand) and its implement rounds use `auto`, so the "N from the brief" that no question ever set is gone.
- `/dev-kit:autopilot --parallel N`.

### Changed
- **One autopilot per project**: `/dev-kit:autopilot` started by hand while the board's Autopilot is running no longer tries to start a second driver. With only `--parallel N` it applies N to the run in progress (from its next batch) and says so; otherwise it says the board's Autopilot drives the project and how to turn it off.

## 3.2.0 — 2026-11-24

The board drives the project: an **Autopilot** switch in the top bar runs `/dev-kit:autopilot` from the board. Until now nothing moved unless a session ran the autopilot or a request was queued, and the top bar suggested otherwise.

### Added
- **Autopilot switch** (top bar, where the "running" chip was): on, the board's server runs the kit's own `/dev-kit:autopilot --milestones 1 --board` headless (`claude -p`, output in `.dev/run/autopilot.log`), one milestone per run with a fresh context, and starts the next run when one closes a milestone, until a release waits for your approval or the project is stable. Next to it, what it is doing: running (for how long), finishing the step, waiting for you (with the Needs-you count), waiting for your approval, waiting for another session, retrying soon, stopped (and why). Its popover has Turn on/off, Start again, Open Needs you and Force stop.
- **`/dev-kit:autopilot --board`** (board mode): every question, here or in a skill it invokes, goes to Needs you as a question with answers to pick (AskUserQuestion does not exist in `claude -p`), the task that waits is blocked, and the run goes on with independent work; when only such work is left it ends with `dev_worker.py autopilot-exit --reason waiting_for_user`, and the board starts it again once you answer or decide something. At every safe point it checks `dev_worker.py autopilot status`: switched off, it finishes the step in progress (green work only) and ends. Permission prompts of the run go to Needs you like a request's (no answer in 10 minutes = denied, and the task is blocked with the reason).
- `dev_worker.py autopilot on|off|status` and `autopilot-exit --reason milestone_done|waiting_for_user|release_approval|stable|stopped|until_reached`; board API `POST /api/autopilot` (`{"on": bool}` or `{"force_stop": true}`).
- **Live** opens, on hover or click, the list of what runs now: the autopilot run and the headless worker the board started (with the request), the skills of the session log and the agents, with a count on the pill.

### Changed
- One `claude` changes the project at a time: board requests run first, between autopilot runs; a `/dev-kit:autopilot` you run yourself in a session is never doubled (the board waits for it). The switch is kept in `.dev/run/autopilot.json`, so a board restart resumes it (a run still going is adopted, not started twice), and the board does not stop for idleness while it is on.
- `autonomy.board_executor`: `permission_mode` defaults to `acceptEdits` (the worker too; projects still on the untouched 3.x default get it), and `autopilot_timeout_min` (default 360) bounds one autopilot run.
- A run that ends without progress (state and plan unchanged) stops the autopilot with that reason instead of looping; three failed runs in a row stop it too (30 s, 2 min, 10 min apart).

### Removed
- **"Go on by itself"** (continuous mode) on the Requests card and `dev_worker.py continue-next`: the Autopilot switch replaces it. A project that had it on starts with the Autopilot on.
- The "running" chip of the top bar (its list moved under Live).

### Fixed
- `/dev-kit:board` logs its `skill_end`: the board showed itself as a skill running for up to 4 hours (`/dev-kit:board › /dev-kit:board 2h13m`); the board's own runs are no longer listed as work.

## 3.1.1 — 2026-11-24

### Docs
- **README**: the top picture is now the flow diagram (`docs/dev-kit-flow.svg`) instead of the four lifecycle chevrons, and the text under it follows its lanes (conception, planning, milestones, releases, stable); the Live board bullet describes the 3.1 board (a tab per lane, Map, Needs you button, panels and Metrics modal). The old `.github/assets/dev-kit-lifecycle.svg` is removed.
- **concepts.md**: the board section describes the 3.1 board instead of the 2.x chevron tabs; `e2e-checklist.md` points to the "Replan the milestones" screen instead of the Plan tab.

## 3.1.0 — 2026-11-23

The board, redrawn after the flow diagram (`docs/dev-kit-flow.svg`): one screen per lane, in the diagram's order and colours, each fitting the window.

### Changed
- **Tabs are the lanes of the diagram**: 1 Conception, 2 Planning, 3 Milestones and 3 Releases (construction in two) and 4 Stable, joined by arrows, each with its state, a "now" label where the project is, a badge with what waits on you and a dot while something runs there. A **Map** button shows the five lanes at once, with an "anytime" bar (Needs you, requests, new issue, activity). The board always opens on the lane where the project is.
- **Each screen fits the window** (no page scroll from 1024×640 up): on top the lane's strip, its steps as a flow coloured by who does them (yours yellow, agents orange, delivery green, gates red) with where the project is and a line on what happens there; below, blocks of the same size. What does not fit in a block or a kanban column is cut at a whole row and opens with "See all" / "+N more" in a modal, so neighbouring blocks never leave gaps. Every step of a flow opens its details in a modal.
- **Needs you is a button** in the top bar: calm when nothing waits, red when something does (it rings once when a new item arrives; the tab title and favicon still change). It opens a drawer with every item and its buttons; the badges sit on the lane and on the step the item belongs to. Requests and Activity are drawers too.
- **Milestones**: the milestone picker groups milestones by release; one line holds the title, goal (the whole goal opens in a modal), progress and forecast; the task board fills the rest of the screen in four columns of equal height, or the QA rounds. Burndown, velocity and gates moved to a **Metrics** modal.
- **Planning**: roadmap by release, backlog and plan review side by side; dragging tasks, issues and milestones has a screen of its own ("Replan the milestones").
- **Releases**: the release picked with its six stages and the rejection loop, then its numbers, milestones, what holds it back, and its quality and documents.
- **Stable**: the flow ends in the three classes of service (expedite, standard, change) with their queues; project, production, health check, release flags, release checks and releases as six blocks.
- The sticky, compacting chevron strips of 2.x are gone (nothing scrolls under them any more).

### Tests
- `test_v3_board.py` opens the Needs you, Activity and Requests drawers where it reads them, and checks release ids on the Map.

## 3.0.0 — 2026-11-23

dev-kit 3.0: every release planned and approved by you, milestones that end on an executable exit check, quality gates with a deterministic floor, your confirmation of the PRD and the plan, a board that forecasts, speaks your language and runs its own worker, deploys separated from releases by flags, and a production health check. The alpha line (3.0.0-alpha.1 to alpha.8, below) holds the details; this entry closes it with the documentation.

### Breaking
- **Every release is planned and approved** (item 5, conventions §19). The plan groups milestones under `## R<n>`; `release-record` needs `--release R<n>` after `release-decide --approve` (only `--hotfix T-nnn` goes without); `--milestones` is gone. There is no "next release" cut between milestones any more.
- **The gate needs the exit check** (item 7, §4, §7). Once a plan uses `exit_check` (every plan written by 3.0, or an older one after `plan --annotate-exit`), `sync-plan` refuses a new milestone without one and `gate <M> passed` refuses anything but `exit: pass`, besides the hard floor and, when CI is detected, a green run.
- **New fixes milestone ids** (item 9, §3): a rejected release gets `M<k>.<i>` (`M5.1`) right after its last milestone, titled `R<n> · Fixes <i>` (was `M<last+1>`).
- **Board requests are `P-nnn`** (item 15): `R<n>` now always means a release. QA rounds read "Round 1", "Round 2".
- The release dossier is now the **release review** (`releases/R<n>/review.md`, `release-submit --review`, state key `review_doc`), and the board starts a headless worker itself when no session listens (`autonomy.board_executor`, on by default).

### Added
- Documentation for 3.0: a quickstart (`GET_STARTED.md`) and getting-started guide that walk through checkpoints, releases, release flags and the health check, with screenshots of the real board fed by a fictional project (`docs/demo/build_demo.py` builds it through the kit's own commands; `docs/demo/capture.js` captures it with Playwright); `concepts.md` covers the release review, checkpoints, hard floor and exit check, release flags and production health (§21), the board's worker, forecast and language.
- `docs/dev-kit-flow.svg`: the whole flow as a hand-written vector diagram (viewBox only, text as text, a dark variant), replacing the Graphviz `.dot` and `.png`.
- Recipe "Deploy each milestone before its release (release flags)"; glossary entries release review, release flag, production health check, exit check, hard floor, checkpoint and forecast; the recipe "Ship a version" is now "Ship a release".

### Fixed
- Board text found untranslated in the screenshots now goes through the catalogs ("running", the gate and building labels, health details, document panel lines), and the board's text lint also catches a lone word left in an element.
- Board layout: Needs you lists wrap side by side, release stages and cards no longer stretch, and a milestone's goal on the board leaves out its plan fields (`exit_check:`, `size_reason:`).

### Tests
- `test_v3_docs.py`: the flow diagram is a true vector covering the whole flow, every image the docs embed exists, and the demo project still builds with releases, flags and health.

### Migration
Automatic, on the first command after updating (tested on projects written by 2.6.1, `test_v3_migration.py`):
- The first read of a 2.x `state.json` copies it and `plan.md` to `.dev/backup/`; the state moves to version 2 on the next write, and a `dossier` key becomes `review_doc`.
- The next `sync-plan` (any skill that syncs the plan runs it) puts the milestones already released under `## R0 — Released before 3.0`, keeping every version and tag, groups the rest into `R1`, records ADR-001 (auto), and marks the plan review stale.
- Request files named `R-nnn` are read as `P-nnn`; fixes milestones that already exist keep their ids.
- `.dev/.gitignore` gets its managed block; your own rules stay.

What is left to you: review the release grouping with `/dev-kit:review plan` and confirm the plan on the board; add `exit_check` to the open milestones with `/dev-kit:plan --annotate-exit` when you want the gate to require it; and, with CI in the project, record a green run at the gate (`DS ci check <M>`) or turn `autonomy.ci.required` off.

## 3.0.0-alpha.8 — 2026-11-23

Cross-cutting changes of the 3.0 specification.

### Changed
- conventions.md gets §21 "Release flags and production health": the rules of `autonomy.release_flags` and `production.health` moved there from §12, which now points to it; every reference was updated.
- `/dev-kit:settings` exposes every `autonomy.*` key, the older ones included (`decide_alone`/`always_ask`, `on_park`/`notify_on_park`, `task_time_budget_min`, `commit_per_task`).
- The lint rejects a skill that measures time or agents by hand in prose (note a start time, log how long something took, count the agents it spawned), not only one that names `agent_spawn`/`duration_s`.

### Tests
- `test_v3_cross.py`: every autonomy key is in settings, the lint catches manual measuring on a copy of the kit, and §21 holds the flags and the health check.

## 3.0.0-alpha.7 — 2026-11-23

Fifth phase of 3.0 (operations, item 12): release flags separate the deploy from the release, and production health becomes feedback instead of silence.

### Added
- **Release flags** (`autonomy.release_flags` `{"enabled": false, "provider": null}`, conventions §21). `architecture` records the mechanism (env var, config file, flag service) and turns them on; `sync-plan` creates `release_R<n>` (off) for every release not released and warns about a `feature` task of R<n> without `flag: release_R<n>` (new task field, §4); `plan` writes the field and `code-reviewer` checks that the new behaviour runs only with the flag on.
- `production.when` `per_milestone_flagged` (needs release flags): each milestone goes to production after its gate with its release's flag off; `DS deploy` records the flag's state with the deploy and refuses a flag turned on before its release is approved.
- `DS flag list [--json]` and `DS flag set release_R<n> on|off|removed [--rollback] [--note]`. Approving a flagged release prints the switch to make; `release` turns the flag on in production, runs the smoke checks, then records `flag set … on` and the release. `deploy --rollback R<n>` turns it off without a redeploy (`--rollback` in its history).
- Once a flagged release is recorded, a `chore` task "Remove flag release_R<n>" goes into the first open milestone of the next release (`source: flag:release_R<n>`); with no next release yet, the next `sync-plan` adds it.
- **Production health check** (`autonomy.production.health` `{"command" | "url", "interval_min": 15}`): `DS prod-check [--json] [--due]` runs it (a command exits 0, a URL answers 2xx/3xx) and keeps the last 30 results in `.dev/run/prod-health.json`. A failure opens one `expedite` issue per check (later failures update it: count, last result) and a Needs-you item until the issue is closed. The board's server runs it while it is up, `deploy --health` runs it and offers a scheduled task, and the Stable phase shows the last check, a short history and the release flags.
- Telemetry events `flag` and `prod_check`.

### Tests
- `test_v3_ops.py`: the acceptance criteria of item 12 (M3 deployed with `release_R2` off, approval turns it on, rollback turns it off; two failed checks make a single expedite issue), plus the removal task, the health history and interval, and the board's Stable phase rendered.

## 3.0.0-alpha.6 — 2026-11-23

Fourth phase of 3.0 (board): a delivery forecast, a way out of every item of Needs you, a cleaner board, the board in the user's language, and the worker inside the board, so a click never waits for a manual step.

### Breaking
- **The dossier is now the release review.** `release` writes `.dev/releases/<R>/review.md` from `templates/release-review.md` (was `release-dossier.md`), `release-submit --review PATH` (`--dossier` is still accepted), the state keeps the path as `review_doc`, and the board, docs and glossary say "Release review" (and its translation in the pt-BR catalog). Projects with a `dossier.md` keep it: the recorded path stays valid, and the old `dossier` key of `release_state` is read as `review_doc` and written under the new name at the next save.
- **The board starts the worker itself** (conventions §10, §17). When a request waits and no Claude Code session listens, the board's server runs `claude -p "/dev-kit:worker" --plugin-dir <kit>` headless after a few seconds and lets it work through the queue; a session that listens keeps priority, a paused queue is left alone, and permissions still come to Needs you. New `autonomy.board_executor` `{"auto": true, "permission_mode": "default", "timeout_min": 180}` (`off` turns it off). A run that fails, or leaves its request pending, backs off 30 s, 2 min, then 10 min; the top bar says what it is doing, and a missing `claude` binary is shown instead of a silent queue. Output in `.dev/run/worker-auto.log`.

### Added
- Delivery forecast (item 13): `DS forecast [--json]`, from the measured milestones (at least 2): from the cycle time, human wait and cost per task of those milestones and the tasks left, a probable date (median) and a "by" date (85th percentile) for each open release and milestone, with the cost to finish when costs are measured; `status` prints it and the board shows it as a chip. Below 2 measured milestones it says so instead of guessing.
- Every item of Needs you has an action (item 16): a QA gate out of fix rounds offers Continue (1–5 more rounds), Accept with a note (an ADR, then a forced gate) or Replan (`DS qa-decide M continue|accept|replan`, board action `qa_decision`); a blocked task offers Unblock, Skip to the next milestone, Drop with a note, or Run (hotfix lane) (`DS task-decide T …`, board action `task_decision`); a question raised by a task is linked to it (`add-question --task T`). Telemetry event `qa_decision`.
- Board cleanup (item 15): a QA tab with the rounds of the milestone (each with why it ran, its auditors, model, time and findings, and what blocks the gate); the gate checks, hard floor and exit check of each milestone; progress weighted by task size; a feed of what happened in user terms (the full log one click away); clearer selection and stage colours; "About the server" in the menu.
- The board in the user's language (item 14): catalogs `shared/board/i18n/en.json` and `pt-BR.json`, every visible string through `tr()`; it follows the project's `language`, and the menu's Language entry overrides it per browser. `test_v3_board.py` fails on any visible text outside the catalog.

### Tests
- `test_v3_board.py`: the acceptance criteria of items 13–16, the release review rename and its compatibility, and the board's own executor (with a fake `claude` through `DEV_KIT_CLAUDE`); the board tests never start the real `claude`.

## 3.0.0-alpha.5 — 2026-11-23

### Fixed
- The 2.6.1 migration fixtures now carry their board requests in a fresh clone (`.dev/run/` is kept as `run-fixture/`, since git ignores `run/`), so `test_v3_migration.py` passes outside the machine that built them.

## 3.0.0-alpha.4 — 2026-11-23

Third phase of 3.0 (flow): one release model, every release planned and approved; QA rounds and milestone builds in a child session with a clean context; work that goes on while a person decides; and the migration of 2.x projects.

### Breaking
- **Every release is planned** (item 5, conventions §19). `sync-plan` groups a plan without `## R<n>`; `release-record` without `--release R<n>` (after `release-decide --approve`) is refused, except `--hotfix T-nnn`; `--milestones` is gone. `plan` always writes `## R<n>` (a single release is one `R1`), and maintenance mode is `## R<k> — Maintenance`.
- **Migration of 2.x projects** (state version 2). The first command that reads a 2.x `state.json` copies it and `plan.md` to `.dev/backup/`. The next `sync-plan` puts the released milestones under `## R0 — Released before 3.0` (every 2.x version and tag kept), the others under `## R1 — <project>` (maintenance milestones under `## R<k> — Maintenance`), records an ADR (`auto`) and makes `review plan` stale. **When that review passes, Confirm plan holds every milestone not started yet until you confirm it** (the milestone in progress goes on).
- `.dev/.gitignore` now has a managed block (conventions §2): besides `run/`, `preview/` and `tmp/` it ignores `backup/`, the raw session log `telemetry.jsonl`, `tips-seen.json`, `state.json.bak` and `costs/*` (except `prices.json`). Your own rules outside the block are kept; files git already tracks are listed once to `git rm --cached`.

### Added
- Rounds in a child session (item 1a, conventions §17): `DS round run <qa|implement> <M> [--permission-mode MODE] [--timeout MIN]` runs `claude -p "/dev-kit:<skill> <M> --round-child" --plugin-dir <kit>` with a clean context and prints a JSON summary (`verdict`, `score`, `fix_tasks`, `tasks_done`, `deferred`, `gate`, `cost`, `duration_s`, `report`, `next`); the child logs into the parent's telemetry session (`parent_session`) and its permission requests go through Needs you. `autopilot` uses it for every QA round and every milestone build; without `claude` on PATH (exit 3) it falls back to plan B (`--milestones 1`). `qa` and `implement` take `--round-child`.
- Pipeline (item 4, `autonomy.pipeline = {releases_ahead: 1, milestone_overlap: true}`): while a release waits for approval, the next release's first milestone runs on `dev-kit/R<n+1>`; while a milestone is in QA, the next milestone's independent tasks (no dependency on it, no file in common, not `shared`) run on `dev-kit/M<n+1>`. `next --json` carries `branch`/`ahead_of`, `start` records them; `DS pipeline status|worktree|integrate`. Nothing ahead reaches the main branch before what it waits for is released or gated; `integrate` rebases (a conflict is a question in Needs you), invalidates the ledger of the files the rebase changed, sends gated milestones back to QA on the delta and fast-forwards. A rejection blocks the work ahead until the release is submitted again; a QA fix that touches a file of a task run ahead sends it back to `todo` (`redo_after`).
- `human_wait_s` is measured: every answer to an item of Needs you (question, permission, checkpoint, release approval) logs a `human_wait` event; `qa/<M>/flow.json` and the new `.dev/releases/R<n>/flow.json` sum it. Not shown on the board.
- Telemetry events `round_run`, `pipeline`, `human_wait`, `migration`; common key `parent_session`.

### Fixed
- `sync-plan` warns "no exit_check" only for milestones still open, and says when the first `exit_check` turns the checks (and the hard floor) on for the whole project, listing the open milestones without one.
- Feedback shows "no data" for the cycle of a milestone closed before 3.0, never zeros, and those milestones no longer cap the `qa` grade.

### Migration
- Run `DS sync-plan` once after updating (any skill that syncs the plan does it), review the release grouping with `/dev-kit:review plan`, then confirm the plan. Tests: `test_v3_migration.py` runs this on three projects written by 2.6.1.

## 3.0.0-alpha.3 — 2026-11-23

Four items added to the 3.0 specification, delivered before phase 3: blocking findings are challenged before they cost a fix round, what agents verify is kept as facts, implementers are fenced to their task's files by a hook, and each role can learn method lessons the user approves.

### Breaking
- With plugin hooks on, a kit agent spawned with a `Slot:` whose slot is open (`DS slot open N --task T-xxx`) cannot Edit/Write outside the task's `files:` (their tests by name, `changelog.d/`, `docs/setup.d/` and the slot's `.dev/` outputs allowed), and no kit agent may run `git commit --no-verify`, `git push --force`, `git rebase` or `git reset --hard` (conventions §17).
- `implement --parallel` runs `DS slot check N --since <base>` before merging a worktree: a changed file outside the task fails the integration.

### Added
- Challenge of blocking findings (item 17, conventions §7): `DS challenger <M> <F-id> [--json]` picks a challenger that is never the author's agent and model (another role covering the dimension, or the same role on another model family); `DS challenge record <M> --from <json>` stores agree / dispute / refine with evidence in `.dev/qa/<M>/challenges.json`, fingerprinted by the cited files. `dev_score.py score|consolidate --challenges` applies it: a disputed finding is not scored, gets no fix task, is listed as **Contested** (new section of the QA report) with both evidences and counts toward the debt cap; refine rewrites the severity. A disputed critical security finding keeps blocking and opens a question ("keep blocking" recommended). Changing the judged files reopens the finding. Prompt `shared/prompts/challenge.md`; qa and release run it before making fix tasks; `DS telemetry report` shows the dispute rate per auditor.
- Verified facts (item 18, conventions §2): `DS fact add --text --evidence --origin [--files --acs --sha]`, `fact stale K-nnn --by --evidence`, `fact list [--files --acs --all --json]`, generating `.dev/facts.md` (ids `K-001`…). No evidence, a secret or personal data is refused; a contradicted fact stays, struck through. `brief` lists up to 10 live facts tagged with the task's files or ACs; qa gives auditors the facts of their files; implementer and auditor outputs gain `facts` (and `facts_contradicted`), recorded by the orchestrator; the release dossier lists the release's facts; the board shows them under Conception › Facts with search.
- File fence (item 19, conventions §17): new hook script `dev_fence.py` (PreToolUse of Edit, Write, MultiEdit, NotebookEdit and Bash); `DS slot open|close|show|check`; the agent hook binds each subagent to the `Slot:` of its prompt (`.dev/run/agent-slots.json`); every denial is a `fence_deny` event, shown in `DS xref` and the telemetry report.
- Lessons per role (item 20, conventions §13): `.dev/lessons/<agent>.md`, at most 8 each; `DS lesson add|rm|show|list|suggest|dismiss` (add and dismiss take `--request P-nnn`). `lesson suggest` proposes one with its evidence for an auditor disputed above 40% in two milestones, 3+ fence denials, 2+ reopened fixes or 3+ escalations; each is a Needs-you item (**Proposed lessons**: approve, possibly edited, or dismiss; board request `lesson_decision`). `brief` includes the implementer's lessons and every skill that spawns a kit agent adds `lesson show <agent>`; `feedback` proposes them and lists them in its report.
- Telemetry events `fence_deny`, `challenge`, `fact`, `lesson`.

### Migration
- Nothing to do: without `slot open` no agent is fenced (only the four git commands are denied for kit agents), projects without challenges score as before, and `facts.md` and `lessons/` appear on first use.

## 3.0.0-alpha.2 — 2026-11-23

Second phase of 3.0 (quality and process gates): an executable exit check, a deterministic floor with CI as the verdict, a cap on deferred debt, the user's confirmation of the PRD and the plan, scope changes that reach the milestone being built, and a size range for milestones.

### Breaking
- `review prd pass` and `review plan pass` open a checkpoint (**Confirm PRD**, **Confirm plan**); with the plan's pending, `next` and `start` refuse every milestone that has not started, and the lifecycle holds architecture until the PRD is confirmed (conventions §19). Confirm with `DS checkpoint confirm <prd|plan>`, the board's Needs you, or the review skill's question.
- In a plan that uses `exit_check` (a 3.0 plan), `sync-plan` refuses a new milestone without one, and `gate <M> passed` refuses unless `scores.json` → `exit` is `pass` (conventions §4, §7).
- `gate <M> passed` refuses a failing hard floor and, when CI is detected and `autonomy.ci.required` (default), anything but a green CI run, whatever the score. `--force` never passes a failing secrets check or a critical dependency.

### Added
- Exit check (item 7): milestone field `exit_check: e2e: <test>; cmd: <command>; acs: AC-n` (release fixes and maintenance milestones exempt). The qa baseline runs it, `spec-tracer` checks it and reports `exit_check`, `dev_score.py` adds the `exit` dimension (pass or fail, never partial) and fails the verdict on it. `plan --annotate-exit` proposes it for older plans; the plan review rates a missing one `high` and one that does not verify the goal `medium`; the release dossier lists each milestone's check and result.
- Hard floor (item 10, `autonomy.quality.hard_floor`, on): `DS hard-floor <M> --from <json>` records tests, lint, type-check, dependency scan, secret scan and axe; each failure becomes one `hard_floor:<check>` fix task (reused while open); `n/a` needs a reason; no tests or no lint is a high finding.
- CI as the verdict (item 10, `autonomy.ci = {provider: auto, required: true, timeout_min: 30}`): `DS ci check <M>` (GitHub through `gh`), `ci record <M> --sha --status`, `ci status`; new pause point `ci_timeout` (park in `unattended`).
- Deferred debt cap (item 10, `autonomy.quality.deferred_cap = {total: 20, medium: 10}`): checked at every gate close; above it Needs you shows **Deferred debt above the cap** with Promote to issues, Accept formally (ADR) and Use the next cool-down (`DS debt status|decide`, board request `debt_decision`). The board shows the total on the gates tab and in Stable.
- Checkpoints (item 11): `DS checkpoint status|confirm|adjust|summary <prd|plan>` with who, when, version and feedback in `checkpoints`; board Needs you **Confirm** / **Ask for changes** with a link that opens the document formatted (`#doc:prd.md`, `#doc:plan.md`) and the review's summary; board request `checkpoint`; continuous mode stops on a pending checkpoint; autopilot parks it in `unattended`.
- Scope change reaches the current milestone (item 8): `DS affected --acs AC-4,AC-7 [--json]` lists the pending tasks that cite them; `issue` offers to pause them (`block T-nnn --blocked-by I-nnn`, uncommitted work to `dev-kit/paused/T-nnn` first); paused tasks do not count for a frozen milestone's gate; a passed `review plan` lists them for the replan to `unblock` or `drop`; `backlog --json` → `paused`.
- Milestone size (item 1b, `autonomy.milestone_size = {min: 5, max: 12}`): `sync-plan` warns when planned tasks + buffer slots + cool-down fall outside it and the milestone has no `size_reason:`; the plan review rates it `medium`.
- Telemetry events `hard_floor`, `ci`, `debt`, `checkpoint`.

### Migration
- Plans without `exit_check` keep working: `sync-plan` warns and the gate does not ask for `exit: pass` until `plan --annotate-exit` adds it. Their gates also do not require a recorded hard floor (a failing one recorded still blocks).
- Projects whose PRD and plan were reviewed before this version have no checkpoint and are not held; the next passed review opens one.
- A project with `.github/workflows` or `.gitlab-ci.yml` now needs a green CI result at the gate: run `DS ci check <M>`, or `DS set autonomy.ci.required false` / `autonomy.ci.provider none`.

## 3.0.0-alpha.1 — 2026-11-23

First phase of 3.0 (foundation: data and cheap rules). The 3.0 line is delivered phase by phase; 3.0.0 closes it.

### Breaking
- Fixes milestone of a rejected release: `M<k>.<i>` (`M5.1`, `M5.2`), right after the release's last milestone `M<k>`, titled `R<n> · Fixes <i>` (was `M<last+1>`). Every parser, sort, regex and the board accept the new form; order is `M5 < M5.1 < M5.2 < M6`. Fixes milestones created before keep their id (conventions §3, §15).
- Board requests are `P-nnn` (were `R-nnn`): `R<n>` is reserved for releases. Request files from before keep their name and are shown and accepted as `P-nnn`. QA rounds on the board read "Round 1", "Round 2" (were `R1`, `R2`).
- Skills no longer log `agent_spawn` / `agent_end` or `duration_s`: the scripts and the plugin hooks do (below). The lint rejects a SKILL.md that asks for them.

### Added
- Reliable telemetry (conventions §13):
  - `shared/telemetry-schema.json` is the allowlist of every event; `DS event` validates against it and a refused key prints the accepted ones.
  - `skill_start` / `skill_end` durations are measured by `dev_state.py` (`.dev/run/skills.json`, a stack per session and skill+scope); any `duration_s` sent is ignored; an end without a start records `duration_s: null` and a `telemetry_gap` event.
  - `agent_spawn` / `agent_end` come from the hooks (new `PreToolUse` hook on the Agent tool, plus `SubagentStart` / `SubagentStop`): agent, agent id, model and effort (kit frontmatter or the call's model), skill, scope (the prompt's `Scope:` line), QA round, duration and tokens from the subagent's transcript. New `agent_result` event for an agent without parsable JSON.
  - `dev_cost.py` attributes each subagent's tokens to the skill it ran under (by agent id), and `telemetry report` takes tokens per stage from the same source as the cost report.
  - Flow per milestone, `.dev/qa/<M>/flow.json` and a `flow` event at the gate: cycle and working time, QA rounds, fix tasks, fixes per task, deferred findings left open, cost and tokens (orchestration and agents apart), cost per task, scope added after the freeze (`human_wait_s` comes with phase 3).
  - Feedback in two readings: for each milestone the period touched, the final state (the gate's score) and the cycle over its whole history, with a cycle grade that caps the `qa` stage grade (formula in §13). The gate's score never changes.
- Scope freeze at QA (§15): `DS freeze <M>` (run by `qa` before the first round; never undone by a replan or a failed gate). `pull-issues`, `cooldown`, `add-task` and `plan-apply` refuse new items in a frozen milestone, except QA fixes, `current`/`expedite` issues, the hotfix lane and confirmed items (`add-task --confirm-frozen`; on the board "Confirm adding to M<n> and send again", which states the cost). Confirmed items are marked `scope_after_freeze`, counted in `flow.json`, and their files' ledger units are dropped when they are done. The board marks a frozen milestone with a lock in the plan view.
- Issue state `parked` (§15): never pulled by the buffer, the cool-down or the queue milestone; leaves only by the user. `issue` offers it for "future / coming soon" items.
- Queue throughput (§15), `autonomy.queue = {limit: 15, limit_pct_remaining: 50, aging_milestones: 3, buffer_floor: 1}` (in `/dev-kit:settings`):
  - above the limit, `status`, `backlog --json` (`needs`) and the board's Needs you offer **Plan the queue milestone** (a draft `M<last+1> — Issues` with the oldest and most severe queued issues, up to 12, sent only by the user);
  - an issue unscheduled after `aging_milestones` closed milestones gets **Schedule in M<n>**, **Park**, **Won't fix** (new plan op `set_issue_status`);
  - `add-issue` refuses `standard` + `low` and `intangible` + `high`/`critical` unless `--force-class "<reason>"`;
  - the issue buffer never drops below `buffer_floor` (a 3-task milestone keeps 1 slot).
- Plan review, mode plan (`requirements-review.md`): a **Releases** section with four rules (complete journey → high; risk ends a release → medium; no phase milestones such as "Release check" → medium; 2–5 milestones → medium). `plan` step 2b says not to plan phase milestones.

### Fixed
- `backlog.hotfix_open` (and the status line and WIP check) no longer counts dropped hotfix tasks, so a discarded hotfix leaves Needs you.

### Migration
- Nothing to run: old `R-nnn` request files are read as `P-nnn`; old fixes milestones keep their ids; milestones already in QA are not frozen until their next `qa` run.

## 2.6.1 — 2026-11-23

### Added
- Dependencies need a reason (conventions §4): the optional plan field `dep_reasons: T-nnn=<text>; …` is parsed, stored and kept by every command that rewrites `plan.md`; `brief` prints it ("needed because") and the board shows it with the dependencies.
- `xref` reports `unjustified_dep` notes (no `consumes`, no common file, not `shared`, no reason) and the `critical_path` of each milestone; both are report-only, so `--strict` is unchanged.
- `next --batch` lists `maybe_false_deps` when the batch is short, and `implement --parallel` tells the model to review each one before waiting.
- A change that only touches `deps` or `dep_reasons` no longer makes review `plan` stale.

## 2.6.0 — 2026-11-23

### Changed
- State changes are now transactional (conventions §20). Every `dev_state.py` command that changes anything runs under an exclusive project lock (`.dev/run/state.lock`) on a freshly loaded state, so concurrent writers no longer overwrite each other and ids are never reused.
- A command writes `state.json` and the files that must agree with it (`plan.md`, `issues.md`, `open-questions.md`, question sidecars, the plan baseline) together: all or none, `state.json` last, with a journal (`run/txn.json`) that the next command rolls forward after a kill. A failed command writes nothing, and log and telemetry lines are written only after the commit. `fix-tasks` is all-or-nothing across its batch.
- Writes are durable and collision-free (unique temp name, fsync); the previous good state is kept as `state.json.bak` and named in the error when `state.json` is corrupt.
- Deterministic: one clock, which `DEV_KIT_NOW` pins (also for telemetry timestamps and the session id), so the same commands give byte-identical artifacts.
- `dev_ui.py` records its settings in a transaction.

## 2.5.0 — 2026-11-21

### Added
- Terminal status pane, a Claude Code function-hooks module (`hooks/status-pane.tsx`), for Claude Code builds that load them. In a dev-kit project it opens beside the chat (when the terminal has room) and stays up to date:
  - the project, phase and step; the current milestone with a progress bar, done/total, gate and QA score
  - the milestone's task cards grouped like the board's kanban: Running (with time since start), Blocked (with the reason), To do (the next task marked, with why) and Done (most recent first, short commit)
  - Needs you: releases waiting for approval, hotfixes, open questions, blocked tasks
  - issues scheduled in the milestone and open issues per class of service; the other milestones one line each; the next command
  - keys: `m` current milestone or all of them, `d` show or hide done tasks, `r` refresh; `/dev-kit-pane` opens or closes it
  - on the desktop app's widget, a one-line summary
- It reads the state through `dev_state.py status --json` after each turn and every 5 s while open, only when `.dev/state.json` or `open-questions.md` changed. Optional: a Claude Code without function hooks ignores it and the existing hooks run as before.

## 2.4.0 — 2026-11-21

### Added
- Board: a **Releases** tab, next to the four phases, once the plan has planned releases. It is a view, not a lifecycle phase: the project's phase never says "releases", and the tab keeps its own red count (releases waiting for your approval).
  - One card per release: status, tasks, milestones closed, QA gates passed, cost, working time and pace (tasks per working hour, parallel work counted once), and for the next release its usability and docs checks.
  - The page of the release picked (linkable as `#release:R2`): its stages, milestones with gate and score, fix tasks (from a rejection or from QA), issues scheduled in it, what holds it back (blocked tasks, QA rounds used up, hotfixes), QA scores against their cut-off, the full gate history (every submission, approval and rejection, with the fixes milestone it created), its documents, and Approve and Reject when it waits for you.
  - Releases waiting for approval in Needs you open the new tab.
- Board data: `release_history`, the full history of each release's gate (`cycle.releases` keeps the last five).

### Changed
- Board: the release stages are built by one function shared by Construction and the Releases tab.

## 2.3.0 — 2026-11-21

### Added
- Board: release planning in the Plan view (Planning tab). When `plan.md` has planned releases, a "Releases" switch next to "Tasks and issues" shows one lane per release with its milestones as cards.
  - Drag a milestone to another release (or use Move…), create the next release (`R<n>`), or remove an empty one. Nothing changes until you send the draft; it goes through the same worker as every plan draft.
  - New plan operations `move_milestone`, `new_release` and `drop_release` in `dev_state.py plan-apply` and in the draft validation. They are checked together and applied all or nothing.
  - Refused: milestones whose gate is not pending, with a task running, or in a release that is in review, approved or released; a release left with fewer than 2 or more than 5 milestones; a dependency that would end up in a later release; a first release in a plan that has none (group with `/dev-kit:plan`).

## 2.2.4 — 2026-11-21

### Changed
- Board: the "Next release" card is gone from Construction. It took the middle of the screen to list closed milestones and checks that rarely asked for anything. Each of its parts already has another place:
  - The count of closed milestones waiting is on the Construction tab (`N to release`).
  - The usability and docs checks are in Stable › Release checks.
  - `/dev-kit:release`, when it is the next step, shows in the milestone card and in the top bar.
  - A planned release's state and milestones are in the release strip and its stages.
  - A release waiting for approval shows in Needs you, with the dossier, Approve and Reject.
- Board: a running `/dev-kit:release` shows in Stable › Releases, and as a "running" tag on the release stage in progress in Construction.

## 2.2.3 — 2026-11-21

### Added
- Board: work that is not a task card shows where it happens, not only in the top bar. Each running skill has a place.
  - Interview, PRD, architecture, UX, UI and plan, and the review of each (`review design` lights UX and UI): the step card gets a "Running now" banner with the command, its time and its agents.
  - `qa`: the QA & fixes stage (as before). `deploy`: the milestone's Deploy stage and Stable › Production.
  - `release`, `usability` and `docs`: the release card in Construction and Stable › Release checks and Releases.
  - `issue`: Planning › Backlog.
  - Orchestrators (autopilot, worker, start…) show only in the top bar; the work they start shows in its place.
- Board: a "● running" tag on the lifecycle tab of each phase where something runs. The running stage of a milestone also gets the tag and an outline.
- Board: an agent with no task or QA gate is shown under the skill that called it. The agent type names the skills that can call it, and of those the run that started latest before the agent owns it; an unknown agent goes to the latest run.

## 2.2.2 — 2026-11-21

### Added
- Board: the top bar always shows what Claude Code is running now, for example `/dev-kit:autopilot › /dev-kit:qa M12` with its agent count and time. It reads the open skill runs and the active agents. A click lists each skill (nested under the one that started it) with its time, and each agent with the task or QA gate it works on. With nothing running it says "Idle" and shows the next step.

### Changed
- Board: the gate badge says what the gate waits for. "Gate pending" is now "◌ Waiting for QA" once every task is done, with how to run it in the tooltip, and "Gate after the build" while tasks are open.
- Board: Requests no longer says "open, not listening" while a skill runs in that session; it says which one, and that requests wait for it.
- Board: the QA & fixes stage says "autopilot runs QA round N next" while autopilot is running, instead of asking you to run it.
- Board: a milestone made only of issue tasks shows "5 issue tasks" instead of "Issue buffer 5/0". Its reserve is computed on planned tasks, which it has none of.

## 2.2.1 — 2026-11-21

### Fixed
- Board: the pinned strips no longer flicker while scrolling. Shrinking them made the page shorter above the content, and the browser lowered the scroll position by that much to keep the content still. With a fixed threshold that drop crossed it back, so the strips switched sizes over and over. Now the compact strip starts only past the height it will lose (measured per phase, plus a margin) and the full one returns only at the very top, so each switch lands on the same side.
- Board: the shrink is smooth.
  - The parts that go away (lifecycle caption, badges, stage notes, QA rounds, running chips, milestone facts, top-bar kicker and "updated") collapse with an animated height or width and fade, instead of disappearing at once.
  - The offsets of the stacked strips follow their height on every frame (ResizeObserver), so construction's strip slides under the lifecycle tabs instead of jumping at the end.
  - The pinned layers are opaque and filter-free: no backdrop blur on the top bar and no drop-shadow filter on the lifecycle tabs, which were repainted on every scrolled frame.

## 2.2.0 — 2026-11-21

The board opens the project's documents in place, lists milestones newest first, and shows how long each milestone took and what it cost.

### Added
- Board: every card that points to a markdown file of `.dev/` opens it, formatted, in a side panel with the same layout as the task details. It is linkable as `#doc:<path>[:<anchor>]`, has Back for documents opened from inside it, and updates while it is open.
  - Conception steps: their files (brief, PRD, architecture, UX flows, UI spec). Planning: `plan.md`.
  - Review rows: the document reviewed and the review report. Gates rows and the QA & fixes stage: `qa/<M>/report.md` and the risk report.
  - Decisions: `decisions.md` at the ADR. Issues and hotfixes: `issues.md` at the issue. Open questions: `open-questions.md` at the question.
  - Release card and Needs you: the dossier. Stable › Releases: the release notes. Release checks: the usability and docs reports.
  - Task details › Origin: the QA report, or the dossier of a rejected release. Activity: the full `log.md`.
  - The renderer builds the page element by element (no HTML from the file is ever inserted). It handles headings, lists and checkboxes, tables, code, quotes, rules, inline code, bold, italic and links. Web links open in a new tab, and links to other `.dev` documents open in the panel.
- `dev_board.py`:
  - `GET /api/doc?path=` serves one `.md` file of `.dev/`, behind the same access check as the rest of the API. It refuses paths outside `.dev` (including through symlinks), other file types and files over 1 MB.
  - `/api/state` gains `docs` (the `.md` files that exist, without `run/` and `costs/`) and `milestone_costs`.
- Board › Velocity: a second chart under the bars, with the same milestones and the same one-axis rule as the dataviz guidance.
  - Two lines: elapsed hours (first task start → gate, or so far) and working hours (time with a task in progress, parallel tasks counted once). The new series colour (`--series-2`, orange) was validated for colour-blind safety in light and dark.
  - Under each milestone: its cost, or its tokens when no cost was measured.
  - The tooltip and the table add both hours and the cost or tokens.
- `dev_cost.py`:
  - Each request is attributed to a milestone (the task in progress at that moment, or the milestone's QA window).
  - `report --by milestone`.
  - `ingest` writes `.dev/costs/milestones.json` over all of the project's usage. Without transcripts, it uses the tokens the skills reported per scope, flagged partial.

### Changed
- Board: milestone lists read newest first: roadmap (releases and their milestones), later milestones, the Plan view's columns, the earlier/later milestone popovers and the velocity table. The chevron strips and the charts keep time order.

## 2.1.2 — 2026-11-21

### Changed
- Docs: the ASCII diagrams of the READMEs are now SVG. Both follow the reader's light or dark theme and show the current model, including planned releases and the approval gate.
  - Repository README: `.github/assets/dev-kit-lifecycle.svg`, the lifecycle with the two levels of construction.
  - Plugin README: `docs/how-it-works.svg`, the steps of each phase.
  - The repository README's lifecycle paragraph now describes planned releases and the approval instead of closed milestones waiting.

## 2.1.1 — 2026-11-21

### Fixed
- Board: the top bar stays pinned again while scrolling. The lifecycle tabs were pinned at the very top and covered it. The three strips now stack: top bar, then the lifecycle tabs under it, then Construction's releases, milestones and stages. Once scrolled, the top bar also slims down (kicker and "updated" hidden, smaller project name).

## 2.1.0 — 2026-11-21

Releases are planned, and approving them is the one human gate of construction. The plan groups milestones into releases (R1, R2…). Milestones still run on their own. When every milestone of a release is closed, `release` audits it, writes an approval dossier and waits. The user then approves it (production deploy, smoke, record) or rejects it with what must change, which becomes a fixes milestone inside the same release. On the board, the Plan view now lives only in Planning, and every chevron stays on screen while scrolling. "Release train" is no longer used anywhere: the term suggests a human-run train, and this kit has none.

### Added
- Planned releases (`conventions.md` §4): `## R<n> — title` headings in `plan.md` group the milestones below them.
  - `sync-plan` records `release_plan` and each milestone's `release`. It warns about a release with no milestone or more than 5, and about milestones outside any release.
  - Milestones follow release order.
  - No milestone of a later release starts while an earlier one is not released. `next` and `start` say why.
- `plan` groups the milestones by three rules: a complete value journey per release, a risky delivery (payments, auth, sensitive migration) ends a release, and 2–5 milestones each. It also explains each cut. The template has an R1 heading, and requirements-reviewer (mode plan) checks the grouping.
- Release gate (`conventions.md` §19): `in_progress → ready_for_review → awaiting_approval → deploying_prod → released`, in `status --json` → `lifecycle.releases` and in `status`, which shows "Needs your approval".
  - `dev_state.py release-submit R --dossier PATH` freezes the candidate.
  - `release-decide R --approve`, `--reject --feedback ITEM…` or `--request R-nnn` (the decision made on the board, read from the request, so the feedback is never retyped into a shell).
  - `release-record --release R` refuses a planned release before its approval.
  - Each step is logged as a `release_gate` telemetry event.
- Rejecting a release adds `M<last+1> — R<n> · Fixes` at the end of that release, with one `fix` task per feedback line (`source: release:R<n>`). This is the one documented exception to "issues never create milestones" (§15).
- `release` runs in two passes for a planned release.
  - Pass 1: checklist, suite, secrets and release audit, then the dossier `.dev/releases/R<n>/dossier.md` (new template `release-dossier.md`), `release-submit`, and stop.
  - Decision: from the board, or in the chat with `--approve` / `--reject "…"` or a question.
  - Pass 2, once approved: version, tag, production deploy and its smoke checks, then `release-record --release`. The approval also confirms `production_deploy` for that commit. Every other pause point is unchanged.
  - `autopilot` stops at the submission and never decides.
- Board request `release_decision` (`dev_worker.py`, `/dev-kit:worker`): approve, or reject with feedback. The server queues it only while the release waits for approval, and only once.
- Board › Construction:
  - Planned releases as chevrons (R1 ✓ › R2 ● › R3 ○) with the stages of the release shown: milestones, dossier, your approval, production, released.
  - The milestone tabs show that release's milestones.
  - A release card shows its milestones, the dossier path, the last rejection, and Approve / Reject when it waits for you.
  - Needs you lists the releases waiting for approval, with the same buttons. The Construction tab says "R1 awaits you".
- Board › Planning: the roadmap is grouped by release, with each release's state.
- Board: the lifecycle tabs, and in Construction the releases, milestones and stages, stay pinned while the page scrolls. They shrink to a compact strip (badges and stage notes hidden). On narrow screens only the stage in progress stays.
- Glossary: "planned release" and "release gate".

### Changed
- Board: the Plan view (drag and draft) lives only in Planning. Construction's tabs are Tasks, Burndown, Velocity and Gates.
- Board: the Construction controls (releases, milestone tabs, milestone stages) are one strip above the milestone card. The separate "Milestone stages" card is gone.
- "Release train" is renamed "next release" in skills, docs, status output and code (`dev_state.pending_release`).
- The fix tasks of a rejected release count as the build of its fixes milestone on the board's stages, not as QA fixes.

## 2.0.0 — 2026-11-21

The board is navigated by lifecycle phase. The four lifecycle chevrons are now the page's tabs, and the panel below shows only what belongs to the phase chosen. That cuts most of the scrolling and leaves room to improve each phase on its own. It opens the 2.x line, which also brings planned releases and a human release gate. The last 1.x is tagged `dev-kit-v1.32.0`.

### Breaking
- Board: the Quality and Backlog tabs are gone. Their parts moved to the phase they belong to.
  - The PRD and design reviews moved to Conception.
  - The plan review, the issue queue, scheduled issues and later milestones moved to Planning.
  - Milestone gates moved to Construction, as the Gates tab.
  - The usability and docs reviews moved to Stable, as release checks.
- Board: the milestone card no longer shows the project's task count and cost. They moved to Stable › Project. The card now shows the milestone's issue buffer and the issues scheduled in it.
- Board: the remembered view key changed (`board-view-v2`), so the first visit opens on Tasks.

### Added
- Board: lifecycle chevrons as tabs (`role=tab`, arrow keys, Home and End).
  - Each tab shows its name, its state and one short badge: steps done, the plan's state, milestones closed and waiting for a release, or the number of releases. The sub-stages are in the tooltip.
  - A "now" tag marks the phase the project is in.
  - A red count shows how many Needs-you items belong to the phase.
  - The board follows the project's phase until you pick another one. The choice is remembered, and "Back to the current phase" returns.
- Board › Conception:
  - One card per step (interview, PRD, architecture, UX, UI) with its state, why it is out of date, its files in `.dev/` and the command that moves it on (▶ when the board takes requests).
  - The PRD and design reviews.
  - The decisions of `decisions.md`, newest first, superseded ones dimmed.
  - The scope-change issues.
- Board › Planning:
  - The plan step and its review.
  - A roadmap of every milestone (goal, done/total, gate). Opening a milestone shows it in Construction.
  - The backlog.
  - The Plan view (drag and draft). It is the same draft as Construction › Plan.
- Board › Construction: a "Next release" card while closed milestones wait for a release. It shows their ids, the usability and docs checks and `/dev-kit:release` when the release is ready.
- Board › Stable:
  - The project's tasks, milestones closed, releases and cost.
  - Production: the commit that runs, the last failed attempt and how far behind the checkout it is.
  - The usability, docs and other reviews.
  - The releases, newest first.
- Board: each Needs-you block, and each open question, has a tag that opens its phase. The phase of a question comes from the skill that raised it.
- `dev_board.py` `/api/state`: `decisions` (id, title, status, date), `releases`, `production` (current and last deploy, drift) and `artifacts` (the files of each step).

## 1.32.0 — 2026-11-20

Model and effort are chosen per task, before it starts, by a deterministic risk rule. A router then learns from the project's own runs which model and effort is cheapest once QA rounds and escaped findings are priced in, and corrects itself when it gets one wrong. The same risk profile sets the round-1 model of the auditors in the gate.

### Added
- Plan risk fields (`conventions.md` §4): `risk`, `complexity`, `uncertainty`, `risk_reasons`, `opportunity` (`downgrade-ok`, `parallel-safe`, `batchable`, `reuse:<module>`), and an override `tier:` that requires a `tier_reason:`. `plan` fills them. `plan --annotate-risk` adds them to tasks already planned without replanning, through the new `dev_state.py set-risk`. `add-task` takes the same flags, and `issue` uses them.
- `dev_risk.py`: the tier rule (`conventions.md` §9 "Tier per task").
  - The score is a base by type plus the weights of objective signals: auth or secrets paths, external send or production, migrations, new or preview API, integration of 2+ tasks, wide change, failed before, reopened or fixing a high finding, plus the planner's `risk: high`, `complexity: high` and `downgrade-ok`.
  - The tier then sets the implementer: `speed` haiku / medium (haiku / low for the fix of a low finding), `balanced` sonnet / medium, `balanced+` sonnet / high, `quality` opus / high.
  - A task that failed before starts at least one tier above its previous attempt.
- `dev_state.py tier T` and a `Tier:`/`Route:` pair in `brief` (for example `Tier: quality (7) → opus / high: auth path +3, integrates T-101, T-118 +2, …`). `start` records the tier and the route in the task and logs a `route` event.
- `dev_router.py` (`route`, `observe`, `learn`, `explain`, `reset`): a model/effort router with two feedback loops over `.dev/router.json` (`conventions.md` §9 "Router").
  - It picks the arm with the lowest expected cost in QA-round units (US$, time, rounds, escapes, failures), weighted by `autonomy.model_policy.router.balance` (`balanced`, `speed`, `cost`, `quality`). An arm needs 3 runs before it can replace the rule.
  - Fast loop: two failures in a row raise a context for the rest of the milestone. A routed downgrade that fails is recorded as a mistake, reverts the context to the rule and blocks downgrades for 5 tasks.
  - Slow loop, at every passed gate: the records are rebuilt, and contexts that keep needing rounds go one tier up. The rule's weights are learned within ±2.
  - Exploration is deterministic. Optional budget per milestone.
  - Floors it never breaks: tasks with auth, send or schema signals never go below their rule tier, security-auditor never below sonnet / high, spec-tracer always opus / high, at most one tier from the rule.
- `dev_state.py risk-report M [--all]`: predicted tier against what happened, per task and per tier. It shows the findings attributed by file, rounds, time and tokens, and the readings `loose_rule`, `maybe_overpaid`, `lacked_effort` and `missed_opportunity`. A passed gate writes it to `.dev/qa/M/risk-report.md` and runs `dev_router.py learn M` by itself.
- `dev_state.py risk-profile M`: the milestone's high-risk tasks, the seams between them and the round-1 model/effort of each auditor. `qa` uses it with `dev_router.py route --audit` and gives every auditor the high-risk tasks to check first.
- `xref` reports `risk_disagrees` when a plan's `risk` contradicts the objective signals, and notes pending tasks without risk fields.
- Telemetry: `tier` and `risk_score` on `task`, `agent_spawn` and `agent_end`, and a new `route` event.

### Changed
- `copy-reviewer` runs on sonnet from round 1 (it was the weakest dimension of every gate on haiku), including the task checks. The §9 ladder gains the `balanced+` row (sonnet / high → opus / medium → opus / high). Effort is raised for lack of care and the model for lack of understanding; `xhigh` is only an escalation and `max` is never used by default.
- `implement`: in sequential mode, tasks routed to `speed` or `quality` go to one implementer with that model. In `--parallel`, every implementer gets its task's route. `fix-tasks` records the `finding_severity` of each fix task. `block` counts attempts.

### Existing projects
- Nothing needs to be replanned. Tasks without risk fields get their tier from the objective signals alone (the brief says so), and old fix tasks take the severity of their source finding. A `state.json` without the new keys uses the defaults.
- The first passed gate (or `dev_router.py learn --backfill`) seeds the router from the history that already exists. Tasks started before this version get a retroactive tier, marked as such in the report.
- The rule applies from this version on, so models change for some work: docs and test tasks can go to haiku, tasks touching auth or external sends to opus, and copy review to sonnet. To go back to the 1.31 models, set `autonomy.model_policy.risk_tiers off` and `autonomy.model_policy.router.mode off` (`/dev-kit:settings`).

## 1.31.0 — 2026-11-20

The board drains requests queued before it started and follows plugin updates.

### Changed
- `/dev-kit:board` runs `dev_worker.py list` after arming and invokes `/dev-kit:worker` at once when a request is pending or answered, instead of waiting for a notification.
- Board: the code identity covers every script and the page assets, not only `dev_board.py`, so an update that changes a sibling module restarts the board on the next `/dev-kit:board`. The running server also checks it every 30 s and stops itself when the kit changed on disk.
- `dev_worker.py watch`: when `plugin.json` changes, the listener prints `the kit was updated; run /dev-kit:board` and exits; the board skill then restarts it.

## 1.30.1 — 2026-11-20

The board's lifecycle bar shows only finite stages and sub-stages.

### Changed
- Board: Construction gets two sub-stages like the other phases, **milestones** and **release**, each with a short count (`milestones 9/12` closed, `release 9` waiting in the train). The current milestone, the ids waiting for the release and the queued issues move to the tooltip. Before, the chevron printed `M10 · 9 of 12 closed · next release: M1, M2, … · 4 issues queued`, which grew with the project and got cut off. Stable shows only its name, and the title says the sub-stage (`Construction · milestones`) instead of a milestone id.
- `dev_state.py`: in `status --json` → `lifecycle.phases`, construction lists `steps` (`milestones`, `release`) with `state`, `count` and `note`. Phase, step, status line and next command are unchanged.

## 1.30.0 — 2026-11-20

The project phase becomes a lifecycle that runs as a cycle: conception → planning → construction → stable. Building and QA belong to each milestone, releases ship a train of closed milestones, and a scope change reopens conception without stopping construction. The phase is derived from `.dev/`, never set by hand.

### Changed
- `dev_state.py`: the phase is derived by `lifecycle()` from the artifacts and `stale`, the reviews, milestones and gates, the issue queue and the releases. The phases are `conception` (steps `interview`, `prd`, `architecture`, `ux`, `ui`), `planning` (`plan`), `construction` (the current milestone, `release` or `issues`) and `stable`. `status`, `status --short`, `status --json` (`phase`, `step`, `reopened`, `lifecycle`), the status line, the session banner and `status --next` all use it. Before, there were 11 phases set by the skills: `implement` and `qa` flipped back and forth on every milestone, `usability`, `docs` and `done` assumed a single launch, and a scope change moved the phase back.
- `dev_state.py`: `set phase` and `init --phase` are gone. Skills move the lifecycle only through the trace they already leave: `artifact mark brief` closes the interview, `review design n/a` skips UX/UI for a product without a UI, `review docs pending` marks regenerated docs, and the new `release-record` closes a release.
- `dev_state.py stale`: once a task is done, only the `plan` review stops being checked against `plan.md` (dev_state.py appends tasks to it). The PRD and design reviews are always checked, so a scope change during construction reopens conception.
- Release train: closed milestones that no release has shipped yet wait in `lifecycle.release`. `release` ships them between milestones, never with one half built, once `usability` (UI products) and `docs` + `review docs` have passed after the last milestone of the train. It then records the release with `dev_state.py release-record --version X.Y.Z` (or `--hotfix T-nnn` for a patch). With nothing open, the project is `stable`.
- `autopilot` and `start` route by phase and step instead of the old 11-phase table. `--until` takes the same step names. `issue` class `change` reopens conception and planning while the current milestone keeps going.
- Board: the "Project phase" bar of 11 chevrons is now "Project lifecycle", four chevrons with what happens inside each: the steps of conception and planning (✓ done, ◐ in progress or waiting for its review, ↻ out of date after a change, crossed out when skipped), the current milestone, closed count, release train and queued issues in construction, and a "reopened" tag when a scope change sends the project back. The cycle is spelled out beside the title. On a phone, the current phase keeps its details and the others shrink to ✓ or their number.
- Docs: new conventions §19 (project lifecycle). Concepts, README, GET_STARTED, getting started, the plugin README, recipes, glossary (lifecycle, release train, stable), troubleshooting, the e2e checklist and the flow diagram now describe the cycle. The README image shows the new board.

### Migration
- A `state.json` written by an earlier kit is converted on load. A finished interview becomes `artifact mark brief`, skipped UX/UI become a `design` review `n/a`, and a `done` project becomes a release record of its closed milestones (version unknown). Nothing else changes: the phase is recalculated from then on.

## 1.29.0 — 2026-11-20

The board's Plan view becomes lanes that scroll sideways at full width, and the task board and the insights share one card.

### Changed
- Board: the task board and the insights are one card with a single row of tabs in two groups, Tasks · Plan and Quality · Burndown · Velocity · Backlog (arrow keys move between them). The last tab is remembered. The separate Insights card is gone, which shortens the page. The task filters show only on Tasks.
- Board: the Plan view shows open milestones as fixed-width lanes side by side that scroll sideways. The issue queue stays pinned on the left, and each lane scrolls inside itself past a maximum height. Done tasks fold into "N tasks done" (the fold stays open across live updates), and card titles are clamped to two lines. While planning, the card takes the full width and Requests and Activity move below it, side by side. Sideways and inside-lane scrolling survive live updates.
- Board: the page uses up to 2400 px of width (was 1560 px).

### Fixed
- Board: in the Plan view, a long milestone title widened its column's track, so cards spilled over the next column and columns over the card. Columns now have a `minmax(0, 1fr)` track and the title is cut with an ellipsis.
- Board: on phones, the Plan columns lost their header, because the kanban rule that hid it also matched them.

## 1.28.0 — 2026-11-20

Running agents land on their task card by an exact link, carry the task id in Claude Code, and keep one color per agent in Claude Code and on the board.

### Added
- Board: a running agent is linked to its task or QA gate by the `Scope: T-xxx|Mn` line of its own prompt, read from the subagent's transcript (`linked_by: "id"`). Time, type, batch and task pairing remain only as fallbacks. The hook now also stores the path of the subagent's transcript in `.dev/run/agents.jsonl`; nothing from the transcript is kept or served.
- `DS brief T-xxx` prints `Scope: T-xxx`. Agent calls use the `description` `<scope> <short title>`, so Claude Code shows `implementer(T-012 login form)` (conventions §13; implement and qa say so where they spawn).
- Every agent declares a `color` (implementer green, architect purple, code-reviewer blue, security-auditor red, test-auditor yellow, traceability and docs cyan, data/deps/ops/performance orange, design/UX pink). Claude Code shows it and the board colors the agent's dot and chip with the same name, in light and dark themes. The lint requires it.

### Fixed
- Board: an `agent_spawn` logged without `scope` no longer leaves the agent under "Running outside this milestone". The time rule ignores spawns without a scope and never reports a link without a node. Implementers whose spawns have no scope are paired with the in-progress tasks, with or without hooks. An `agent_end` without scope closes the matching spawn.
- `DS event agent_spawn|agent_end` without `scope` warns. For an implementer with exactly one task in progress, it fills in that task.

## 1.27.0 — 2026-11-20

### Changed
- Board: Milestone gates list newest milestone first.
- Board: active chevrons, in-progress items and running states (QA round, requests, Claude Code working) pulse; disabled by reduced-motion.

## 1.26.0 — 2026-11-20

Claude Code's permission prompts are answered on the board while it runs a board request.

### Added
- `PermissionRequest` hook: while the session runs a request from the board and a board is up, each permission prompt appears in Needs you with the tool and the command or path (cut to 300 characters), and Allow, **Allow for this session** (only the allow rule Claude Code itself suggests, kept until the session ends, written to no settings file) and Deny, with the time left. No answer in 10 minutes is a denial, and so is a request cancelled meanwhile; the denial tells Claude not to retry. Questions (`AskUserQuestion`) never become permissions. Outside a board request, or with no board, nothing changes: Claude Code's own prompt applies. The hook runs inside subagents too.
- `/dev-kit:worker`: what to do when a permission is denied (no retry, no workaround; go on without it or finish the request as failed).
- `docs/board-autonomy-check.md`: a 15-minute script to check, on your Claude Code version, that the monitor wakes an idle session and permissions are answered from the board, producing a zip for the kit's author. `DEV_KIT_HOOK_TRACE=1` makes the hooks log event names, process ids and payload keys (never values) to `.dev/run/hook-trace.jsonl` for it.

## 1.25.0 — 2026-11-20

The session that opened the board listens: a request on the page starts work in Claude Code with nobody at the console.

### Added
- **Listening session.** `/dev-kit:board` makes its Claude Code session the one that listens (`dev_worker.py arm`). A plugin monitor (`monitors/monitors.json`, started the first time `/dev-kit:board` runs) keeps `dev_worker.py watch` in the background: silent while it waits, it prints one line when a request arrives for that session, which Claude Code delivers as a notification, and `/dev-kit:worker` runs the queue. It speaks only for the armed session it runs under, not while the queue is paused, and not for a request the running queue takes by itself; a request nobody took is announced again after 10 minutes. Waiting costs no tokens. The Requests card shows "Claude Code: listening", "working on R-nnn", "open, not listening", "paused" or "not running"; the board no longer stops by itself while a session listens. Where plugin monitors are not available the board says so and `/dev-kit:worker` still runs the queue by hand.
- **Go on by itself** (off by default), a switch on the Requests card: after each request Claude Code starts the project's next step (`implement`, `qa`, `review`, `docs`, `usability`) and stops, saying why, when a question or a request waits for an answer, a task is blocked, a request failed or a continuous one was cancelled, the milestone it was working on closed (one milestone per go), the next step is yours to start (deploy, release, plan), or the last step changed nothing. "Go on" resumes. `dev_worker.py continue-next`.
- **Behind a reverse proxy:** `/dev-kit:board --trusted-host <name>` makes the board answer to that host name in `Host` and `Origin` (over http or https), and to no other name; remembered for the project in `.dev/run/board-config.json`, `--trusted-host none` forgets it.
- The tab says when something needs you: "(2) Needs you · project" in the title and a red dot on the icon (questions, permission requests, blocked tasks, and failed requests you have not seen).
- `/dev-kit:worker` closes a request left running by an interrupted turn before taking the next one.

### Changed
- Requests are on by default on a shared board too (`--host`): the board is a single-user tool and nobody opens a shared one without its access key. `--actions off` makes any board show the project only; `auto` now means on.
- The session banner and the end-of-turn notice about waiting requests stay silent while a session listens.

## 1.24.0 — 2026-11-20

The board asks Claude Code for work: buttons, answers, new issues and a plan drawn by dragging cards, run by `/dev-kit:worker` in your session.

### Added
- Board (local, or shared with `--actions on`): ▶ next to every command the server accepts, "Next step" with the command `status --next` gives under the milestone, a Requests card (Claude Code ready, working on R-nnn, paused or not running; open and recent requests with their result; Cancel; New issue; Pause queue), answers to open questions in Needs you (the options, the recommended one first, or your own text; "Keep the assumption" for questions without options), permission requests with Allow and Deny when a hook raises them, and a toast for every request queued or refused.
- Board Plan tab: the issue queue, every open milestone and the next one to add, as columns that wrap. Drag tasks not started and open issues, or use Move… (up, down, to a milestone) by keyboard or touch; the draft lists the changes, flags a task placed before one it depends on, and has Undo, Discard and Send. The server checks the draft again before queuing it; over the issue buffer it asks before sending again.
- `/dev-kit:worker`: runs the board's requests in this Claude Code session one at a time (answers first, then requests whose answer arrived, then the oldest), in board mode: questions go to the board with answers to pick and the request waits for them while the others run. Text typed on the board is data, never an instruction.
- Hooks: at session start, at a prompt and at the end of a turn, one line when the board has requests waiting (only when the set changed; ids and counts only); the status line shows `▣ N`. `UserPromptSubmit` joins the hooks.
- `dev_board.py start` prints whether requests are on; `/dev-kit:board --actions auto|on|off`.

### Fixed
- Board: "Assumed meanwhile: -" was shown for questions recorded without an assumption.

## 1.23.0 — 2026-11-20

The groundwork for driving Claude Code from the board: a request queue, plan edits that keep `plan.md` and state together, and questions with answers to pick. The page itself does not use them yet.

### Added
- `dev_worker.py`, the board's request queue to Claude Code and the only code that knows its files (`.dev/run/inbox/`, `worker.json`, `worker-mode.json`, `approvals/`). The board queues guided requests only: a kit command from a fixed list (`run`), a new issue, an answer to a question, or a plan draft; every field is validated and free text is cleaned and handed to the executor as data, never as an instruction. The executor (the Claude Code session) claims one request at a time (answers first, then requests parked on a question that got its answer, then the oldest), finishes it as done, failed, cancelled or waiting for an answer; one executor per project; a request whose executor died is marked stale and never runs twice; the queue can be paused; at most 20 open requests.
- Board API: `POST /api/inbox`, `POST /api/inbox/<id>/cancel`, `POST /api/worker/mode` (pause, continuous), `POST /api/approvals/<id>` (allow or deny), all with the per-run token, an allowed Host and Origin, JSON of at most 16 KB. A plan draft is checked against the current state before it is queued, so the reasons come back at once. `/api/state` gains `inbox` (open and recent requests, executor, approvals waiting), `next.command` and the options of each open question. `dev_board.py start --actions auto|on|off`: requests are on by default only on loopback; a board shared with `--host` takes none unless started with `--actions on`. The server still never writes the project's state, plan or questions.
- `dev_state.py move-task`, `new-milestone`, `reorder` and `plan-apply` (a draft from the board, or `--ops` JSON): every change is checked against the state the earlier ones left (tasks not started only, open milestones only, no task before a task it depends on, the issue buffer unless confirmed, expedite and change issues refused, the next milestone number only, one per draft), then `plan.md` and state are written together, or nothing is; `--dry-run` shows the changes.
- `dev_state.py add-question --options "a|b" --recommended a [--request R-nnn]` and `answer-question Q-nnn --answer … [--ref …]`, which moves the question to Resolved.

### Changed
- `next` follows the order of the tasks in `plan.md` inside a milestone (`sync-plan` records it as `seq`) instead of the task number. For plans never reordered the order is the same.

## 1.22.1 — 2026-11-20

### Fixed
- Board: the implementers of `implement --parallel` showed as "not linked" under "Running outside this milestone" while their tasks sat in Build with no agent. Two agents of the same type starting together matched neither the time rule nor the type rule, so neither was linked. Agents of one type are now paired with the open spawns of that type when the counts match (they look the same on the board, so the pairing cannot mislead); implementers the skill did not log are paired with the in-progress tasks when the counts match; and a spawn whose task is already done, dropped or blocked (its `agent_end` was never logged) no longer blocks the link.

## 1.22.0 — 2026-11-20

The board shows what is actually happening, and a card that exceeds its agreed failure limit goes to Blocked.

### Changed
- No more sprints: the board, docs and tips speak of milestones only (the milestone strip, the task board, "tasks done per milestone", "later milestones"); dev-kit is not Scrum. "Live Scrum board" is now "live board".
- Board: **QA & fixes** is one stage with its rounds as a trail (`R1 ✕ 89 → 1/1 fix ✓ → R2 ●`), the auditors of the running round ("9 of 10 auditors done", the running ones with their role and time), and what to do next (`/dev-kit:qa M2` with a copy button) when no round is running. It replaces the separate QA gate and Fixes stages, whose straight line hid the loop.
- Board: the gate badge says what is going on: "QA round 2 running", "Round 1 failed · copy 50, spec 72 below 75" (the reason, not overall / cut-off), "N QA rounds failed · needs your decision", "Gate passed · 91 in round 2".
- Board: the milestone header shows the stage ("Stage 3 of 4 · QA & fixes") instead of a task percentage, with "All tasks done; the milestone closes after the QA gate"; a milestone whose tasks are all done shows "QA" on its tab.
- Board activity merges skill and agent starts and ends from the session log (e.g. "a11y-auditor started (accessibility audit) · QA gate of M8"), so the feed moves while QA runs.
- `qa` logs `skill_start`/`skill_end` with `scope=<M>`.

### Fixed
- A fix task whose finding is still open after the task was done went silently unnoticed (`fix-tasks` skipped it): it is now reopened, and blocked the second time (`rounds_exhausted`), with the reason on the card.
- A QA round past `max_fix_rounds_per_gate` left its new fix tasks in To do, for `next` to pick: `gate --count-run` now blocks them, with the reason.
- A new QA finding that reused the id of an earlier, closed one got no fix task (it was taken for the old one): it gets its own task under a round-qualified anchor; fix tasks record their QA round.
- Board: an auditor started by a hook minutes after the skill logged it showed as "Also running" with no task; agents are now also linked by type (when every open spawn of that type points to the same task or gate) and, for auditors, by the qa run in progress. Agents left open by a skill that ended no longer count as running.
- Board: "Cost US$ 0.00" when costs were never computed now reads "Cost not computed" with the command to copy.

## 1.21.1 — 2026-11-20

### Changed
- Board: the sprint tabs are a chevron strip like the phase and the stages: "+N earlier", the selected sprint and its neighbours, "+N later", each coloured by its state (gate passed ✓, in progress, not started; the selected one highlighted). On a phone the strip keeps one line with short labels.
- README screenshots show the sprint chevrons.

### Fixed
- Board on a 320 px screen: a running task with two agents no longer pushes the page sideways.

## 1.21.0 — 2026-11-20

### Added
- Board: **milestone stages** below the sprint card, in the order the kit runs them: Plan → Build → QA gate ⇄ Fixes (round n of max) → Smoke test (only with a local preview) → Deploy (only with production per milestone) → Closed. The stage where the milestone is now is wider and holds its running tasks with their agents (QA agents under QA gate) or the next task; a stage with blocked tasks links to "Needs you"; work running outside the shown milestone sits on an "Also running" line. `/api/state` gains `lifecycle` (local preview mode, production `when`, max fix rounds) and `milestones[].deploy` (latest production deploy of that milestone).

- **Claude Code interface** (conventions §15). Every skill ends its report with the next command alone on the last line, so Claude Code's greyed-out prompt suggestion offers it (Tab or Right arrow); `dev_state.py status --next` (and `next_command` in `status --json`) computes it. `dev_ui.py` writes dev-kit spinner tips (the `tips.json` entries marked `spinner`, translated) and a status line (`dev_statusline.py`: phase · milestone progress · running task · blocked · open questions · next command) to the project's `.claude/settings.local.json`, touching only what is the kit's and never replacing the user's own status line. Hooks: session title and one-line banner with the next command on a new session, and a desktop notification (OSC 9) at the end of the turn for gates, blocked tasks and the end of autopilot (`dev_state.py notify`). `start` offers tips, status line and notifications once; `/dev-kit:settings` turns each on or off (`autonomy.ui`).

- Board: every command the user is told to run in Claude Code (`/dev-kit:plan`, `/dev-kit:interview --gaps`, `/dev-kit:deploy`, `/dev-kit:costs`, `/dev-kit:board`, `/dev-kit:board stop`) has a copy button next to it, with a "Copied" confirmation announced to screen readers; on a board shared over plain HTTP, where the browser has no Clipboard API, it copies through a temporary selection.

### Changed
- Board: the project phase is no longer a small button in the top bar but a full-width row of chevrons at the top of the page (done ✓, the current one large and highlighted, the rest numbered); on a phone it shows the previous, current and next phase with "Step n of N". The milestone stages use the same chevrons (pointing down when stacked on narrow screens).
- Board sprint tabs show only the selected milestone and its neighbours (M-1 · M · M+1, the current one by default); the others are in "+N earlier" / "+N later" lists, arrow keys walk all of them, and "Back to current" returns. No more horizontal scrolling.
- Board: the "right now" strip is gone; "Needs you" is a full-width, highlighted strip above the stages that appears only when something waits on the user.
- Board layout: two columns, with sprint board and Insights on the left and Activity on the right, filling their height (60 log lines instead of 25).
- Board Insights: Quality is the first tab and the default (remembered choice reset once).
- Board kanban: at most 3 cards per column, each with "Show all N" / "Show less"; To do lists the next task first, then ready, then waiting ones.

## 1.20.0 — 2026-11-20

Nothing to run by hand: every action a user may need goes through a skill; the scripts are the skills' tools.

### Added
- `/dev-kit:settings`: shows and changes the project's settings in plain words (autonomy level and pause points, quality cut-offs, model escalation, review and fix rounds, incremental reuse and spot checks, task checks, issue buffer and cool-down, local preview, production deploy, permissions, tips on/off/always/reset), validated against the floors, with an ADR for decisions. Replaces the `dev_state.py set …` instructions in the docs.
- `qa --full`: audits everything again without reusing earlier clean reviews; the QA report gains a "Reused work" line per dimension (reviewed, reused, spot-checked, and why).
- `/dev-kit:start` housekeeping on resume: stops processes left by a crashed run and frees expired locks (`cleanup`), records the current documents as the reference for stale tracking in projects created before 1.16 (`artifact mark all`), and fixes a task whose recorded commit was rewritten (after asking).
- `dev_state.py status` shows `Stale:` and `Locks:` lines; `/dev-kit:status` relays them.

### Changed
- Troubleshooting, recipes and glossary point to skills instead of script commands (cleanup, tips, dropped tasks, wrong commit, costs re-read, models per agent, QA tooling, reuse, exclusive resources).
- 24 skills (plus `core`).

## 1.19.0 — 2026-11-20

Specifications that prevent late rework: the second field report traced many late findings to facts nobody wrote down early (what one task hands to another, which texts are fixed, how to reach a screen state, what a data source really covers, which resource cannot be shared).

### Added
- Task contracts in `plan.md`: `contract:` (what a task provides), `consumes: T-nnn` (must also be a dependency; `sync-plan` checks) and `shared: yes` (runs alone in parallel batches). `dev_state.py brief` gives a consumer the producer's contract; `xref` reports `contract_missing`.
- `dev_state.py lock acquire|release|status` for exclusive resources (one holder, `--ttl`, `--wait`, expired locks freed by `cleanup`), the architecture's "Exclusive resources and environment limits" table and an interview question.
- `dev_state.py strings --since <sha>`: user-facing strings added since a commit (templates, UI attributes, message calls, i18n catalogs); `copy-reviewer` gets only those.
- `dev_state.py contrast`: WCAG ratios of the colour token pairs in `ui-spec.md` (text 4.5, large text and UI parts 3.0); `ui` and `design-reviewer` use it instead of computing by hand.
- `[locked]` literals in PRD ACs, a message catalog in `ux-flows.md` §7.1 and a screen → route → states map in `ui-spec.md` (also the input of the ledger's `shot:` units).
- Data: interview question on external sources (coverage, freshness, quotas), the architecture's data sources table, a coverage assumption in data ACs, a data spike when a milestone reads a new source, a versioned data invariants file run by `data-reviewer`.
- Performance scenarios file measured cold and warm against the previous round.
- `"out_of_scope": true` for a problem in shared code the scope did not change (a global component): not scored, registered as an issue.
- Changelog fragments (`changelog.d/T-xxx.md`, `docs/setup.d/T-xxx.md`) merged by `docs`; `release` refuses leftover fragments.
- `dev_detect_stack.py --tools` reports the dependency audit tools per ecosystem and what to install; deferred upgrades become issues.

### Changed
- `pause_policy.paid_services` with `preauthorize` accepts `max_monthly: "unlimited"` only as an explicit value; anything else must be a positive amount.
- `start` creates a minimal state before its first event (events were dropped before the interview's `init`); onboarding runs discovery, document review and the test baseline at the same time.
- `test-pyramid.md`: axe checks in component tests and data invariants per data task; `operations.md`: a runbook rule for manual deploy steps.
- `design-reviewer` flags ad-hoc texts outside the catalog and screens without a map; `architect` verifies data source coverage.

## 1.18.0 — 2026-11-20

Incremental work. A second field report (52 h of activity on 1.14) showed the time going into redoing verified work: implementers running the whole integration suite per task (37% of the time), QA rounds of up to 150 minutes, every auditor running `make check` again, every screen captured again by two agents, whole documents re-read for a changed paragraph. Rule of this release: never redo verified work whose inputs did not change, and never let reuse lower the bar.

### Added
- Work ledger (`dev_state.py ledger`, module `dev_ledger.py`, conventions §18): every verified unit (auditor pass over a file, document section, screen capture, dependency audit, implementation attempt) is recorded with the fingerprint of its own files, its context (checklists, specs) and salt (model tier, kit version). `plan`/`record` for audit dimensions and screens (`unit=file+file`), `sections`/`record-sections` for document reviews, `put`/`check`/`get` for single units, `drop` to invalidate.
- Quality rules: conservative invalidation; findings never close from the cache (units with findings are always reviewed again); every unit reviewed at least once; seeded spot checks (`autonomy.incremental.spot_check_pct`, default 10%, at least one) and a full re-run of the dimension when a spot check finds something; shared files invalidate the whole plan; `release` audits with `--no-cache` (also the last gate with `full_on_last_gate`). `autonomy.incremental.enabled false` turns reuse off.
- `qa`: one shared baseline per round (`.dev/qa/<M>/baseline.json`: suite, lint, type-check, data smoke, one QA harness run for visual and a11y) read by every auditor; `Files to review:` per auditor from the ledger; static auditors start at once, environment auditors after the baseline and after long jobs; a failing data smoke stops the environment auditors for that round.
- `dev_score.py consolidate`: `findings.json` and `findings-round-<n>.json` with stable ids across rounds, deferred and legacy apart, and `same_as` links between dimensions (one fix task).
- `dev_score.py select`: which auditors a re-run needs (open findings or changed files in their dimension); the others keep their result with `"carried": true`.
- Document reviews from round 2 get `Sections to review:` (changed sections, sections citing a changed id, sections with findings, spot sample) instead of the whole document; `review all` runs independent targets in parallel.
- `dev_state.py next --batch N`: ready tasks that can run in parallel; `autopilot` runs in parallel by default when the brief allows it.
- `dev_state.py brief T-xxx`: an implementer's base prompt from state and architecture (languages, §8 commands, verification rule, worktree rules, contracts, previous attempt).
- Failed or blocked attempts keep their branch and notes (`ledger put task:T-xxx --result failed`); the next attempt continues from them.
- `dev_cost.py report --time` and `/dev-kit:costs --time`: share, runs, average and maximum minutes per agent and skill, plus what each ledger plan reused (new `ledger` telemetry event).

### Changed
- Implementers run unit, lint, type-check and only the integration tests their task affects; the full suite runs once per merge in the orchestrator.
- Auditors read the baseline instead of running the suite, lint, type-check or captures: test-auditor confirms assertions, flakiness and coverage, running only the AC tests it needs, in the background and within `Time budget:`; security scans only commits after the last scan and skips an unchanged lockfile's audit; spec-tracer reads test results from the baseline; requirements-reviewer judges merit and leaves form to `xref`; copy-reviewer gets the application and report languages.
- Contract: `partial: true` for a partly fixed finding (stays open), duplicates across dimensions reported and linked, rules for `Baseline:` and `Files to review:`; isolation: long commands in the background, time budgets.
- `fix-tasks` creates one task for findings linked by `same_as`; `autopilot` logs `skill_end` for `implement` per milestone.
- `architecture.md` template: unit-only and data-smoke commands, long jobs in §7.

## 1.17.0 — 2026-11-20

Third release from the field report: gates that confirm instead of discover, and less repeated work (test suites run three times, a deploy per fix batch, auditors reporting fixes made while they read, agents without browsers or dependencies in their worktree).

### Added
- `dev_state.py tests record|lookup`: green suites recorded per commit in `.dev/run/test-runs.jsonl` (`--kind unit|integration|e2e|all`, `--paths`); `lookup` reuses a run on the same commit or when nothing it covers changed since (docs and `.dev/` do not count), never a failing run or a dirty tree, and exits 3 otherwise. `implement` records after each commit, `qa` reuses or records its baseline, and `test-auditor` reads it before running anything (`stats.tests_reused`).
- Checks inside the task: the implementer's self-check (AC ↔ test, copy, static WCAG on what it touched, harness screen entry) and `autonomy.task_checks` (`ui` default, `all`, `off`): `copy-reviewer` and `a11y-auditor` (`Mode: static`) on haiku for UI tasks, into `.dev/qa/T-xxx/precheck/`, blocking findings fixed before the commit.
- `dev_detect_stack.py --tools`: Playwright, Chromium (also from `PLAYWRIGHT_BROWSERS_PATH`), axe, Lighthouse, `node_modules`, virtualenv and the QA harness scripts. `qa` and `plan` use it.
- `shared/templates/qa-harness.md` and a "QA harness" chore task that `plan` adds to the first UI milestone when none exists: Playwright with mocks, every screen × state × viewport (`qa:shots`), axe per screen (`qa:a11y`). `visual-reviewer` and `a11y-auditor` run it when present.
- `architecture.md` §8 template: integration-only command, harness commands, integration paths and **QA access** (a local seed user or read token, by env var name, never production credentials).

### Changed
- `qa` freezes the tree while auditors run and gives them `Audited commit:` (recorded as `sha` in each result); fixes start only after all have returned.
- One deploy per approved gate (conventions §12): fix tasks are one batch, then one `qa` round with at most one local preview; `deploy` never runs mid-round, and `dev_state.py deploy` warns when the milestone's gate is not passed.
- `resource-isolation.md`: worktrees link `node_modules`/`.venv` from the main checkout (with the `git check-ignore` check for symlinks) and never install; QA credentials rule; one simple command per Bash call, Read/Grep/Glob for reading, no heredocs or `cd … &&` chains.
- Troubleshooting: an allowlist for read-only commands, worktree dependencies, static-only visual audits, repeated suites.

## 1.16.0 — 2026-11-19

Second release from the field report: document reviews that converge. Long runs had the PRD in 8 rounds, the plan in 9 and the design in 6, because each round re-read everything, documents drifted apart, and a fix a reviewer suggested became the next round's regression.

### Added
- `dev_state.py artifact mark <brief|prd|architecture|ux|ui|plan|all> [--note]` and `dev_state.py stale [--json] [--strict]`: each planning artifact records the version of its sources; `stale` lists artifacts whose sources changed since (directly or through a stale source) and passed reviews whose artifact changed. Header-only edits (date, status) do not count. `status --short` shows a `stale:` line and `status --json` a `stale` object.
- `review` step 1 runs `stale` and refreshes the target and its upstream (or marks them `no impact`) before spawning a reviewer; `autopilot` never advances past a review that passed on an older version.
- `dev_state.py xref [--json] [--strict]`: deterministic cross-document checks (ACs with no task, tasks citing unknown ACs, screens without a spec, ADRs cited but not recorded, unknown deps).
- `shared/prompts/self-check.md`: prd, architecture, ux, ui and plan run `xref` and the reviewer's own checklist, including the metric ↔ data and route ↔ artifact links, before `artifact mark`; `review` runs it after every revision.
- Real delta for document reviews: `review` keeps a snapshot per round and gives the reviewer `Changes since round <n-1>:` (a diff). New findings carry `in_change`; below critical and outside the change they are deferred (`--kind review` only; gates still score them). A finding with `contradicts: F-nnn` is capped at medium and listed in `conflicts` for an ADR.
- `dev_score.py` reports `convergence` (blocking findings, mediums now versus the previous round, trend, `converged`).
- `autonomy.max_review_rounds` (default 3), separate from `max_fix_rounds_per_gate`; conventions §9 recommends accepting a review that converged two rounds in a row (never for security; policy force still refuses open critical/high).

### Changed
- Stage grades count review rounds against `max_review_rounds`.

## 1.15.0 — 2026-11-19

First of three releases from a field report: most of a long run's cost was rework and orchestration context, not writing code. This one makes the cost measurable and the agents' output reliable and small.

### Added
- `dev_score.py check [--fix] FILE…`: validates auditor results against the output contract and normalises the usual drift (`previous[].status` → `state`, severity synonyms such as `Major`/`nit`/`blocker`, state synonyms such as `fixed`/`still open`, missing or repeated ids, `auditor` from the file name, a JSON block wrapped in prose). What it cannot fix exits 1 with the message to send back to the agent.
- Auditors and reviewers write their result to the `Output file:` given in the prompt and answer in at most 5 lines; the orchestrator no longer copies JSON out of long messages. The 15 scored agents gain `Write`, limited by the contract to that file.
- `dev_state.py fix-tasks --from <findings.json> --milestone M [--include F-…]`: one fix task per blocking finding (file, AC, `F-nnn resolved: …`), idempotent; used by `qa`, `usability` and `release`.
- `autopilot --milestones N`: stop after N approved gates and resume in a fresh session.
- conventions §17 "Lean orchestration".

### Changed
- Every Agent call passes `model` and `effort` explicitly from round 1 (conventions §9): hosts that ignore the frontmatter ran every auditor on the orchestrator's model.
- `dev_score.py score` rejects an unknown severity instead of scoring it silently as `low`, and reads normalised results.

### Fixed
- `dev_cost.py`: a `requestId` of `"unknown"` (or `null`, or an id too long for the store) collapsed a session into a couple of records; ids now fall back to the message id and the line uuid, and odd ids are kept as a short hash. Stores written before are re-read on the next `ingest`.
- `dev_cost.py`: model names with gateway or provider decoration (`system.ai.claude-…`, `us.anthropic.claude-…-v1:0`, `anthropic/…`, `@date`, `[1m]`) are normalised; an unlisted model of a known family is priced as the family's first listed model, with a "priced as" warning.
- `docs/skills.md` was stale after 1.14.0.

## 1.14.0 — 2026-11-19

Board redesigned around one question: what is happening and what needs me, without scrolling.

### Changed
- Board layout: a one-line top bar (phase as a compact progress track, full list on click; Stop server moved to the ⋯ menu); a "right now" strip with what needs you (blocked tasks, open questions, open hotfixes), what is running (tasks with their agents, plus agents not tied to a task) and the next task; one compact sprint card (tabs, goal clamped to two lines, progress, gate, project total and cost, each number shown once); the kanban next to a side column with the attention list and the activity feed; burndown, velocity, quality (reviews and gates, the ones not run yet on one line) and backlog (issue queue, buffer, later sprints per milestone) in remembered tabs.
- Kanban: filter by id or title and by task type; cards say what they wait on ("Waiting on T-007") or that they are ready; Done shows the latest 5 with "Show all"; an empty Blocked column shrinks; on phones one column at a time behind a status switch.
- Task details open in a side panel instead of a centred dialog, linkable as `#T-nnn`; dependencies and what a task unblocks are links to their own details; it refreshes with live updates.
- Task ids in questions and in the activity feed are links to the task.
- Theme: light/dark button in the top bar, plus Auto (follow the system) in the ⋯ menu; the choice is remembered per browser.

### Removed
- The Graph view (execution DAG) and its endpoint `GET /api/graph`. `.dev/plan-baseline.json` is still written by `sync-plan`.

### Fixed
- Status colours of the old graph nodes were blocked by the board's CSP (inline `style` attributes); the new page sets no inline style attributes.

## 1.13.0 — 2026-11-19

### Added
- Board: click a kanban card (or a graph node, Enter/Space from the keyboard) to open a details dialog with the task's acceptance criteria (with the PRD text), test notes, planned files, dependencies and what it unblocks, source issue, commit (subject and changed files) and history. Served on demand by the new `GET /api/task?id=T-nnn`; `/api/state` stays light.

## 1.12.0 — 2026-11-19

Gap review of 1.11.0: places the brownfield change and earlier features did not reach.

### Added
- Existing projects: the onboarding asks for the number of the first milestone (`brownfield.first_milestone`, default 1); `plan` numbers milestones from it.
- Maintenance mode runs real milestones: `M<n> — Maintenance` is filled by `/dev-kit:issue`, gated by `qa M<n>` like any milestone, and the next issue opens `M<n+1>`.
- `dev_state.py drop T --reason` for tasks removed by a replan (status `dropped`, never counted by milestones, `next` or `release`).
- `dev_state.py done T --commit <sha> --force` corrects the SHA of a task already done.
- `qa --scope T-xxx` records review `hotfix-T-xxx` (or `task-T-xxx`) without touching the milestone gate; `release --hotfix` checks it and deploys once.
- `deploy --dry-run` is described and simulates without recording.
- Autonomy level presets are applied by `set autonomy.level` (`cautious` raises the cut-offs; leaving `unattended` restores the supervised policies).
- `.dev/.gitignore` for machine-local folders; "clean tree" means clean outside `.dev/`, and stashes never take `.dev/`.
- Board shows the existing-project mode and pre-existing issues; dropped tasks are hidden.
- Agents get `Project root:` and call `dev_state.py --root` (implementers run in worktrees).
- Templates: as-built section and `existing | changed | new` tags (PRD, UX flows, UI spec), `architecture.md` §8 with the commands every skill runs, QA report sections for delta trend, deferred findings, local deploy and pre-existing findings, `legacy` in the finding contract, `link:` in imported ADRs.
- Docs: kit CHANGELOG, existing-project sections in concepts, getting started and the root guides, board and failure recipes, 11 glossary terms, 3 recipes, updated flow diagram, extended e2e checklist.
- Lint: checks script commands quoted in markdown, `help.json` args against `argument-hint`, counts and section ranges in prose, telemetry stages and feedback areas, `conventions.md §N` references, and skills invoking skills marked `disable-model-invocation`.

### Fixed
- Onboarding registered baseline issues before the state existed (and without `--title`); `init` now runs right after the baseline tag, so onboarding is also logged and costed.
- `unattended` overrode `pause_policy.dirty_tree: ask` in existing projects, allowing the user's own work to be stashed.
- Delta mode re-scored legacy findings from the previous round; backlog listed them as deferred.
- Switching from maintenance to feature left the `n/a` reviews in place, so the new PRD and plan skipped review.
- `set autonomy.a.b` stored a literal dotted key; `set autonomy.quality` replaced the whole object; booleans and integers were not validated (and could crash `telemetry report`); `init --autonomy-json` skipped validation.
- `start` tried to invoke `autopilot`, which only the user can start; it now shows the command.
- Feedback areas such as `docs`, `release`, `review` or `issue` were rejected; review runs were never graded; stages recorded only as `n/a` were graded 100.
- `event` before `init` failed; it is now skipped.
- `status --short` (the line every skill receives) now shows the existing-project mode.
- `backlog --json` lacked issue `origin` and `note`; `issues.md` gained an origin column.
- Stack detection treated repos without a root manifest (only `setup.py`, `Makefile`, plain sources, monorepo subfolders) as new projects.
- The agents hook wrote into any `.dev/` folder; `board stop|status` created `.dev/run/` in projects without state.
- `costs --all` counted Claude Code sessions from before an existing project adopted the kit.
- Tips shown twice by `status`, `issue` and `qa`; wrong brief block numbers (platform, push, maintenance quality); `implement` cited the wrong discovery section; `add-task`/`add-question` commands missing required arguments; `production_deploy` missing from the pause-point table; `code-reviewer`, `docs` and release notes found commits by `[T-xxx]` subjects instead of the recorded SHA.
- Nine agents (security, requirements, architect, data, copy, visual, usability, a11y, performance) and four checklists had no existing-project rules.

## 1.11.0 — 2026-11-19
- Brownfield end to end: every stage adjusted for projects not built with dev-kit (onboarding conventions, entry modes feature / maintenance / import, baseline-scoped audits, legacy findings, review `n/a`, `commit_style`, deploy method `external`).

## 1.10.0 — 2026-11-19
- Board can bind to `0.0.0.0` and share the board on the network with an access link.

## 1.9.0 — 2026-11-19
- `start` adopts an existing project: baseline tag, discovery, test baseline, retroactive ADRs.

## 1.8.0 — 2026-11-19
- Board: running agents as live badges on the graph nodes.

## 1.7.x — 2026-11-19
- 1.7.0: milestone execution graph (DAG) with plan baseline, failure loops and parallel groups.
- 1.7.2: chevron-shaped phases and milestone tabs. 1.7.3: kit version in the header. 1.7.4: opens on the Graph view and remembers the choice.

## 1.6.x — 2026-11-19
- 1.6.0: initial public version (23 skills, 17 agents). 1.6.1: SSH tunnel fix for the board. 1.6.2: Agents panel. 1.6.3: compact Agents strip, hidden when idle.
