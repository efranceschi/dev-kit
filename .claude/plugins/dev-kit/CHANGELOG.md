# Changelog

All notable changes to the dev-kit plugin. Versions follow `.claude-plugin/plugin.json`. Entries before 1.12.0 were reconstructed from the git history.

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
