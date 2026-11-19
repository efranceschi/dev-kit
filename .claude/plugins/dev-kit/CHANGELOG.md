# Changelog

All notable changes to the dev-kit plugin. Versions follow `.claude-plugin/plugin.json`. Entries before 1.12.0 were reconstructed from the git history.

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
