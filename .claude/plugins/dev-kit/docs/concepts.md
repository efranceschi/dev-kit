# Concepts

How the dev-kit works, one idea per section. The normative rules live in `skills/core/shared/conventions.md` (section numbers in brackets). Quick definitions: [glossary](glossary.md). Task-oriented answers: [recipes](recipes.md).

## State in `.dev/`

Everything the kit knows about your project lives in `.dev/` inside the project, so any session can resume.

```
.dev/
  state.json          milestones, tasks, gates, reviews, issues, releases, settings (only via dev_state.py)
  brief.md  prd.md  architecture.md  plan.md  decisions.md (ADRs)  open-questions.md  issues.md  log.md
  design/             ux-flows.md, ui-spec.md
  qa/  reviews/       reports, scores and findings per milestone and per review
  costs/  feedback/   token usage and prices; session reports
  telemetry.jsonl     session log (no project data)
  discovery.md  qa/baseline.md   existing projects only: what was there before dev-kit
  run/  preview/  tmp/   machine-local (board, processes, local preview); ignored by git
```

The Markdown files can be edited by hand. After a scope change run `/dev-kit:prd` or `/dev-kit:plan replan` so the change propagates. Each task becomes one commit, `[T-003] feat: ...` by default or in your project's own style (`autonomy.commit_style`, with a `Refs: T-003` trailer); history is never rewritten.

## Lifecycle: conception, planning, construction [§19]

A product built by agents is never "finished" in a straight line: after the first round of requirements it keeps receiving bugs, improvements and scope changes until it is stable. The kit models that as a cycle of four phases:

```
  conception ──────► planning ──────► construction ──────► stable
  interview, PRD,    plan + review    M1 → M2 → M3 …       nothing open,
  architecture,      (replan on       each: build → QA      everything
  UX, UI + reviews   every change)    → deploy → closed     released
       ▲                  ▲           + release train          │
       │                  └──── bug or improvement (issue) ────┤
       └──────────────────────── scope change (issue change) ──┘
```

- **Conception** runs once at the start and again for every scope change: `interview` → `prd` → review → `architecture` → `ux` → `ui` → review. For a product without a UI, `ux` and `ui` are skipped (review `design` recorded `n/a`).
- **Planning** turns the specs into milestones and tasks (`plan`, then `review plan`), and replans after a change.
- **Construction** is where the product is built, one milestone after the other. Building and QA are not project phases: they repeat inside every milestone (plan → build → QA & fixes → smoke → deploy → closed). Closed milestones wait in the **release train** until a release ships them: `usability` (apps with a UI), `docs`, `review docs`, then `release`, cut between milestones so no work is half built.
- **Stable** means nothing is open: no milestone in progress, no queued issue, every closed milestone released. The next issue starts the cycle again.

The phase is **derived** from what `.dev/` already holds (artifacts, reviews, gates, issues, releases), never set by hand, so it cannot go backwards by mistake. When a scope change edits the PRD, conception shows as *reopened* (from the PRD on) and planning after it, while the milestone already in construction keeps going; once the changes are reviewed and replanned, the project is back in construction. `/dev-kit:status` shows the phase and step (`conception · prd`, `construction · M3`, `stable`) and the release train; the board draws the four phases with their finite sub-stages; `status --next` names the command that moves the cycle forward. An existing codebase goes through an onboarding first (below). See the [flow diagram](dev-kit-flow.png).

Milestones (M1, M2, …) are the cadence of construction: `M2` starts only after the `M1` gate passes, a milestone whose gate passed takes no new task, and nothing ever inserts or renumbers a milestone. A task removed by a replan is `dropped` (kept for history, never counted).

## Quality scores and gates [§7]

Reviewers return findings in one JSON contract; `dev_score.py` turns them into a 0–100 score per dimension with a fixed formula.

- Penalty per finding: critical 40, high 20, medium 8, low 2 (low confidence counts half). A critical caps the dimension at 40, a high at 69.
- **Low cap:** low findings cost at most 10 points per dimension.
- **Dedupe:** the same finding reported by two audits of one dimension counts once.
- **Delta mode:** from round 2, auditors check whether the previous findings were closed; new low findings are recorded but not scored. Rounds converge instead of discovering a new layer of nits.
- **Document reviews (round 2+):** the reviewer gets the diff since the previous round and judges the changed text; new findings below critical in untouched text wait, and a finding that reverses an earlier recommendation is capped at medium and settled by an ADR. The score shows the **convergence** (blocking findings, mediums now vs before); a review converged twice can stop. Rounds are capped by `max_review_rounds` (default 3).
- **Stale artifacts:** each planning document records what it was built from (`dev_state.py artifact mark`). When the PRD changes, `dev_state.py stale` lists architecture, design and plan as stale, and `review` updates them before any reviewer runs. Writers run a self-check first (`xref` plus the reviewer's checklist), so the review confirms quality instead of discovering it.
- **Output files:** each auditor writes its JSON to a file and answers in a few lines; `dev_score.py check` validates it against the contract.
- A gate or review passes only with no critical/high finding, every dimension at its minimum (security 90, spec 85, tests 80, a11y 80, others 70) and the overall score at the cut-off (85 for milestones, 80 for documents). Presets: `standard` 85, `premium` 92, `prototype` 70.
- Failing gates create `fix` tasks. `dev_state.py` refuses a pass below the cut-off; `--force` needs your decision and an ADR.

## Autonomy and pauses [§6, §10]

The interview defines what the kit decides alone (recorded as `ADR (auto)`) and what it always asks: paid services, deleting data, public exposure, major scope changes, security model, credentials, model escalation; production deploys have their own pause point. Levels `high`, `balanced` and `cautious` are presets of these lists (`cautious` also raises the cut-offs).

The **pause policy** decides what happens at each pause point: `ask`, `preauthorize` within a limit, `auto_recommend` (apply the recommendation), or `park` (record it, block only what depends on it, keep going). The `unattended` level fills the recommended values so autopilot never waits. Some floors cannot be lifted: no forced pass with security below its minimum or a critical/high open, no deletion of production data, no history rewrite, no AC change without you. Every question comes with a recommended option and its reason.

## Models and effort [§9]

Agents have a base model and effort by what they need: `speed` (haiku), `balanced` (sonnet), `quality` (opus). Skills pass the model and effort in every agent call, so the tiers hold even where the host ignores the agent's own settings. When a dimension fails, only it is re-run one step higher on the ladder (effort before model), and only with your consent (`model_policy`: `ask`, `preapproved`, `off`). The agents and their tiers: [agents](agents.md).

## Parallel work and isolation

Work is sequential except: `implement --parallel N` (each implementer in its own git worktree, integrated one at a time by the orchestrator), `qa` (auditors at once, heavy ones limited by CPUs) and the release audit. Every agent that runs commands gets a **slot**: its own port, database and scratch folder; it records and stops its own processes and formats only its own files. `dev_state.py cleanup` kills anything left behind, only inside the project.

**Incremental work [§18]:** a work ledger records every verified unit (an auditor's pass over a file, a document section, a screenshot, a dependency audit, a failed attempt at a task) with the fingerprint of its inputs. A later round reviews only what changed, what had findings and a seeded spot sample; findings never close from the cache, every unit is reviewed at least once, a change to a checklist or a shared file invalidates the whole dimension, and `release` audits everything without the cache. Each QA round builds one shared baseline (suite, lint, type-check, data smoke, screenshots) that every auditor reads, auditors with nothing new are not re-run, and `/dev-kit:costs --time` shows where the time went and how much was reused.

**Specifications that prevent late rework:** tasks declare the contract they provide and consume (`contract:`, `consumes:`; `shared:` serialises them); requirements mark fixed texts `[locked]`; the UX flows carry a message catalog and the UI spec a screen → route → states map; the architecture lists data sources with their coverage, exclusive resources (guarded by `dev_state.py lock`), long jobs, data invariants and performance scenarios; tasks write `changelog.d/` fragments instead of editing CHANGELOG.md; and a problem in shared code a milestone did not touch becomes an issue (`out_of_scope`) instead of failing its gate.

Rework is the costly part of a long run, so the kit avoids repeating work: a green test suite is recorded per commit and reused by the test auditor and the gate until the code changes; tasks that touch UI get a self-check and cheap copy and accessibility checks before their commit (`autonomy.task_checks`); auditors work on a frozen commit; fix rounds are batched into one `qa` re-run and one deploy after the gate passes; parallel implementers link the main checkout's `node_modules` instead of installing. A QA harness task (Playwright with mocks, axe) gives the visual and accessibility auditors real screenshots.

## Issues and classes of service [§15]

Bugs and ideas found at any time go through `/dev-kit:issue`, which classifies them:

| class | for | enters |
|---|---|---|
| `expedite` | critical/high bug in delivered work | now, hotfix lane, one at a time, patch release |
| `current` | bug in the milestone being built | that milestone |
| `standard` | medium bug, valuable improvement | the next milestone's buffer (20%) |
| `intangible` | low bug, polish, tech debt | the cool-down after a gate (if on), else spare buffer |
| `change` | new or changed AC | PRD → review → replan, future milestones |

`/dev-kit:backlog` shows everything pending.

## Existing projects [§16]

A codebase not built with dev-kit is **onboarded** by `start`: tag `dev-kit-baseline` on the current commit, `.dev/discovery.md` (stack, commands, your commit/version/CHANGELOG conventions, existing docs and ADRs, imported as `source: imported`), the test results at the baseline in `.dev/qa/baseline.md`, an **entry mode** and the number of the first milestone (default `M1`). Nothing in the code, docs or history is changed.

| mode | for | path |
|---|---|---|
| `feature` | a new capability | short interview on the change → PRD (as-built + new ACs) → architecture → design if new UI → plan → build |
| `maintenance` | bugs and small improvements | as-built PRD, an empty `M<n> — Maintenance` filled by `/dev-kit:issue`; its gate runs like any milestone, then the next issue opens `M<n+1>` |
| `import` | you already have a PRD/specs/ADRs | they are the source; only the gaps are asked; then as `feature` |

- **Baseline-scoped audits:** reviewers judge `git diff dev-kit-baseline..HEAD`. A problem only in untouched code is a **legacy** finding: it never scores and becomes an issue (a leaked secret is still flagged critical so you rotate it).
- **existing / changed / new:** tags on ACs and screens; `existing` needs no task or full spec.
- **Your conventions win:** layout, test framework, commit style, version source and tag prefix; adding a new tool always asks; an uncommitted change is never stashed without asking.
- **`n/a` reviews:** a review that does not apply is recorded with a note and counts as satisfied (and is not graded).
- **`external` deploys:** when your CI/CD deploys, `deploy` only confirms and records the commit.

## Preview and production deploy [§11, §12]

Optionally, each approved milestone can run locally on `127.0.0.1` (`keep_running` or `smoke`). For production, the interview records method, host, timing (`per_milestone`, `on_release`, `manual`), smoke checks and prerequisites; `/dev-kit:deploy` installs with backup and dry-run (`--dry-run` only simulates), and `status` shows how far production is behind. A hotfix is deployed once, by `release --hotfix`.

## The board

`/dev-kit:board` opens a live dashboard of the project in the browser: the project lifecycle as four chevrons (conception, planning, construction, stable) with their finite sub-stages: interview, PRD, architecture, UX and UI; plan; milestones and release (✓ done, ◐ in progress or waiting for its review, ↻ out of date after a change, "reopened" when a scope change sent the project back). Construction shows only short counts (`milestones 9/12`, `release 9` waiting), with the milestone ids in the tooltip, so the bar does not grow with the project; the milestones as chevrons (previous, current and next; the others in "earlier"/"later" lists), a "Needs you" strip only when something waits on you, the stages of the milestone as chevrons too (plan → build → QA & fixes → smoke test → deploy → closed; smoke and deploy only when enabled), where QA & fixes shows its rounds (R1 ✕ 89 → 1 fix ✓ → R2 running) and the auditors of the running round, with what is running and what comes next on the stage it belongs to; the milestone goal, its stage instead of a task percentage, and the task kanban (filterable, 3 cards per column with "Show all", running agents on the cards and a details panel per task, linkable as `#T-nnn`), insights tabs for quality, burndown, velocity and backlog, and the activity feed beside them; light, dark or following the system. One server per project, stopped from the page's ⋯ menu or with `stop`, and by itself after 2 idle hours.

**Requests to Claude Code.** The page can also ask for work: ▶ next to a command ("Next step" included) queues it, Needs you takes the answer to an open question (its options, the recommended one first), Requests has New issue, Pause queue and Go on by itself, and the Plan tab lets you drag tasks not started and open issues between open milestones, add the next milestone and send the draft. The board never changes the project itself: `dev_worker.py` keeps the queue and `/dev-kit:worker`, run in a Claude Code session, executes the requests one at a time; questions that would stop it come back to the board (board mode, conventions §10).

**The session that listens.** The Claude Code session where you ran `/dev-kit:board` becomes the one that listens: the plugin's monitor (`dev_worker.py watch`, a silent background process that costs nothing while it waits) tells that session when a request arrives, and it starts working with nobody at the console. Keep the session open (in tmux, for instance) and drive the project from the browser; the Requests card shows "Claude Code: listening", "working on R-nnn", "paused" or "not running". Its permission prompts go to the board too: Needs you shows the tool and the command or path, with Allow, Allow for this session (the rule Claude Code suggests, until the session ends) and Deny; with no answer in 10 minutes it is denied. The tab's title and icon say when something needs you ("(2) Needs you"). In a session that is not listening, `/dev-kit:worker` runs the queue when asked, and the session banner and the status line (`▣ N`) say that requests wait.

**Going on by itself.** With "Go on by itself" on (off by default), after each request Claude Code starts the project's next step (`implement`, `qa`, `review`, `docs`, `usability`) until something needs you: an open question, a blocked task, a failed request, a milestone that closed (one milestone per go), a step that is yours to start (deploy, release, plan), or a step that changed nothing. The card says why it stopped; "Go on" resumes.

**Reaching the board.** It is a single-user tool: whoever can open it can queue work. By default it listens on `127.0.0.1` only; from another machine use an SSH tunnel. `--host 0.0.0.0` shares it on your network through a private access link (plain HTTP: trusted networks only). Behind your own reverse proxy, with its TLS and login, `--trusted-host <name>` makes the board answer to that host name (and to no other name); it is remembered for the project. `--actions off` makes any of them show the project only.

## Session log, feedback, costs and tips [§13, §14, §15]

- `.dev/telemetry.jsonl` records skills, agents, rounds, scores, pauses and errors at a high level. No project data enters it: keys and values are allowlisted in code.
- `/dev-kit:feedback` grades each stage with its reasons and writes a timestamped report you can send to the kit's author.
- `/dev-kit:costs` shows tokens and estimated US$ per stage from Claude Code's local transcripts (API-equivalent, not a charge).
- Short tips (`💡`) explain each mechanism the first times it matters (each at most twice; `autonomy.tips off` silences them).

## Claude Code interface [§15]

The kit also uses Claude Code's own interface, all of it display only:

- **Next command, one key away.** Every skill ends with the next command alone on the last line, so Claude Code's greyed-out prompt suggestion usually offers it: Tab or Right arrow, then Enter. Claude Code predicts that suggestion itself; no plugin can set it, and it does not appear in plan mode, right after an error or with prompt suggestions turned off.
- **Tips while you wait.** Short dev-kit tips, in your language, rotate under the spinner while Claude works.
- **Status line.** Below the prompt: lifecycle phase (with the step in conception and planning) · milestone progress · running task · blocked tasks · open questions · next command.
- **Session title and notifications.** A new session is named after the project and milestone and opens with one line naming the next command; gates, blocked tasks and the end of autopilot can raise a desktop notification.

`/dev-kit:start` offers the tips, the status line and the notifications once; `/dev-kit:settings` turns each of them on or off. Tips and the status line are written to `.claude/settings.local.json`, your personal settings for the project, which stay out of git. Spinner, suggestions and status line are terminal features: hosts that embed Claude Code (web apps, the SDK) may not show them.

## Language

The kit's files are in English. At run time it talks to you and writes your project's artifacts in your language (`state.json.language`). Code, identifiers, file names, ids and commit subjects stay in English.
