# Changelog

All notable changes to the dev-kit plugin. Versions follow `.claude-plugin/plugin.json`. Entries before 1.12.0 were reconstructed from the git history.

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
