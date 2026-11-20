---
name: autopilot
description: Autonomous end-to-end build driver - starting from the interview brief, runs conception (PRD, architecture, UX, UI) and planning, then the construction cycle (implement -> QA gate -> fix loops per milestone) and the release train (usability audit, docs, release) until the project is stable, pausing only for always-ask decisions, unresolvable blockers or exceeded fix rounds. Resumes from the current lifecycle step. Use when the user wants the application built with minimal interaction ("build it", "continue autonomously", "run until QA").
argument-hint: "[--until prd|architecture|design|plan|qa|usability|docs|release] [--milestone M1] [--milestones N]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# autopilot

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Preconditions
`.dev/brief.md` exists and the interview was confirmed (the lifecycle step is past `interview`, i.e. `artifact mark brief` was recorded). If not, invoke `interview` first and come back; never build from an unconfirmed brief.

## Driver loop
Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` and the autonomy policy from `DS status --json`. Start a session log: `DS event session_start --set trigger=autopilot` and `skill_start` (`conventions.md` §13); run `DS cleanup` once to clear processes left by an earlier run. Then repeat until the `--until` target, or until the lifecycle is `stable`:

The project lifecycle is derived by `dev_state.py` (`conventions.md` §19): read `phase` and `step` from `DS status --json` (`lifecycle.phases` has the state of every step). In conception and planning, run the step's skill when the step is `todo`, `doing` or `stale`, and its review when it is `review`. Construction runs the milestone cycle and the release train.

| phase · step | prerequisite (must be `pass` or `n/a` in `DS status --json` → `reviews`) | action (Skill tool, by name `<skill>`) | then |
|---|---|---|---|
| conception · prd | - | `prd` | `review prd` until pass |
| conception · architecture | `prd` | `architecture` (it records review `design` `n/a` for a product without a UI) | ux, or planning when there is no UI |
| conception · ux | - | `ux` | ui |
| conception · ui | - | `ui` | `review design` until pass |
| planning · plan | `design` (UI products) | `plan` (`plan replan` when `plan.md` already has tasks) | `review plan` until pass |
| construction · M<n> | `plan` | at the start of each milestone `DS pull-issues <M>` (issue buffer, §15); then `implement --milestone <current> --parallel N` whenever the brief allows parallel work and `DS next --batch N` returns more than one task (N from the brief, default 3), else `implement --milestone <current>`; log a `skill_end` for `implement` at the end of each milestone so the time of every milestone is recorded (`conventions.md` §13) | milestone complete → `qa <M>` |
| construction · M<n>, tasks done, gate pending | - | `qa <M>` (scores the milestone; local preview per §11 when enabled) | gate passed → `DS cooldown <M>` (if on, §15) → `deploy <M>` if `autonomy.production.when` is `per_milestone` (§12), then the next milestone; gate pending → implement (fix tasks) and re-run qa; rounds > `max_fix_rounds_per_gate` → pause |
| construction · release | - | the release train (`lifecycle.release`): `usability` when it says `todo` (score recorded as review `ux`; fail → implement the fix tasks, re-audit), then `docs all` and `review docs` until pass, then `release --dry-run`, and the real release only if the brief's definition of done includes one (`release` runs `deploy` when `production.when` is `on_release`, and records the release) | stable (or the next milestone when one was planned meanwhile) |
| construction · issues | - | none: queued issues wait to be scheduled (`backlog`); stop and show them | - |
| stable | - | none: nothing is open | end of run |

When conception is reopened by a scope change (`reopened` in `DS status --json`) the driver finishes the changed steps and the replan first, then goes back to the milestone in construction, which kept its state.

`--until` targets: `prd`, `architecture`, `plan` stop once that step is done; `design` stops after review `design` passes; `qa` stops after the gate of `--milestone` (default: the current one); `usability` and `docs` stop after that part of the release train; `release` runs until the release is recorded. `--milestones N` stops after N milestone gates pass in this run (with `deploy` done when it applies), with the progress line and the command to resume (`/dev-kit:autopilot`) in a new session or after `/clear`: the state in `.dev/` is all a resume needs, and a fresh context is much cheaper per turn than a long one (`conventions.md` §17).

## Quality control (score and cut-off)
- Every checkpoint above is scored 0–100 by independent agents through `dev_score.py`; the cut-offs come from `autonomy.quality` (set in the interview). The driver never advances past a checkpoint whose review or gate is not `pass`; `dev_state.py` refuses a pass below the cut-off.
- Revision loop for documents: `review` sends the artifact back to its producing skill until it clears the cut-off or `max_fix_rounds_per_gate` is exhausted. Milestone loop: `qa` creates fix tasks, `implement` executes them, `qa` re-scores with fresh auditors in delta mode (`conventions.md` §7), so each round closes the previous findings instead of starting over.
- If the same dimension fails twice with the same root cause, stop looping: write an ADR describing the structural problem and ask the user (replan, change the spec, or accept with `--force`).
- Report the score of every checkpoint in the progress line.

Before every review in the table, run `DS stale`: an artifact that is stale is refreshed with its producing skill before its review runs (`review` step 1 does it; never advance past a review that passed on an older version of its artifact, `stale` → `reviews`).

The "current milestone" is the first milestone (by number) with tasks not done or gate pending. No sub-skill sets the phase: it is derived from what they leave in `.dev/` (artifacts, reviews, gates, releases); after each returns, re-read `DS status --short` and decide the next row. If a sub-skill stops early (blocked task, question), handle it here before continuing.

## Question handling (governed by `autonomy.pause_policy`, `conventions.md` §10)
Every pause point below first looks up its action; only `ask` opens a question. With `autonomy.level unattended` (or every point set to something other than `ask`) the run never waits for the user.
- `always_ask` category decisions (`paid_services`, `delete_data`, `public_exposure`, `scope_change_major`, `security_model_change`, `credentials`): apply the point's action. For `ask`, collect them, finish every task that does not depend on the answer, then ask once with all pending questions (AskUserQuestion, recommended option first). Record answers as ADRs and continue.
- Blockers (three tasks blocked in a row, or tests/dev server cannot run): point `blocked_env`. `ask` → stop with a precise diagnosis and the command to resume; `park` → record the diagnosis as a question, continue any independent milestone work, then end per `on_park`.
- Fix rounds exhausted at a gate or review, or the same finding reappears twice: point `rounds_exhausted`. `ask` → present the options (keep fixing / accept with `--force` and an ADR / replan / change the spec), recommended option first per §9; `auto_recommend` → apply the recommendation (§10); `park` → leave the gate pending, park, end per `on_park` (later milestones depend on it).
- Dirty working tree with unknown changes: point `dirty_tree`.
- Model or effort escalation: `autonomy.model_policy.mode` (`ask` batches it with the other questions; `preapproved` escalates within the ladder and reports it in the progress line; `off` never escalates).
- Open hotfix (`expedite`, §15): it runs first, whatever the phase or step; then `qa --scope <task>` and `release --hotfix` (which deploys it once), and back to where the run was.
- Issues of class `change`: follow `pause_policy.scope_change_major`.
- Release audit failure: create the fix tasks, go back to `implement` and re-run `release`, counting rounds like a gate.
- Everything else is decided autonomously and logged (`decisions.md`, `open-questions.md`).

## Progress reporting
After each step, review and milestone, print one line: phase and step, tasks done/total, gates and review scores (from `DS status --short`), open questions, issues pulled into the milestone, the local preview URL when a milestone was just deployed (`conventions.md` §11), and the estimated cost so far (run `dev_cost.py ingest` then `dev_cost.py report --json --no-ingest` after each milestone; show `total.usd` and tokens, §14). Keep the user's context light: do not dump artifacts; name the files, and follow `conventions.md` §17 (agents write their results to files; read `status --short`, scores and consolidated findings, never raw results).

## End of run
Run `DS cleanup`. Queue the end-of-run notification in the user's language, one short line with no project text beyond ids and scores (`DS notify "dev-kit: autopilot stopped at M2, 3 questions parked"`; it shows only when `autonomy.ui.notify` is on, `conventions.md` §15). Write the run's feedback on the kit (`DS feedback --trigger autopilot --worked area:note --failed area:note --improve area:note`, at most 3 each, about the dev-kit only, consolidating the agents' `kit_feedback`) and `skill_end`. End the run report with one tip from `DS tip autopilot`. Include the run's estimated cost by stage (`dev_cost.py report`) and suggest `/dev-kit:costs` for the breakdown. Suggest `/dev-kit:feedback` for the session's evaluation by stage (a timestamped report and data export to review and, if the user wants, send to the dev-kit author).

Report in the user's language: what was built (milestones, tasks, commits), gates and review scores with the cut-offs used, decisions taken autonomously that deserve review (ADR ids, highlighting `source: policy` ones and any gate passed with `policy:` force), parked items with their recommendation, the local preview still running (URL, milestone, how to stop it), the production deploy state (`DS status` → `Production:` line: what is deployed and how far behind), open questions (suggest `interview --gaps`), and the single next command if the run stopped early. If the run completed `release`, give the version and how to run it.

## Never
- Never run `release` for real with `public_exposure` implications without an explicit yes recorded in the brief, asked now, or `pause_policy.public_exposure` preauthorized for that target.
- Never bypass a gate silently; `--skip-gate` always leaves an ADR.
- Never rewrite git history.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:autopilot` to resume, or `/dev-kit:interview --gaps` when it parked questions. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): a review recorded as `n/a` satisfies the prerequisite column. Skip the `ux` and `ui` rows when no `new` AC touches the UI (record `DS review design n/a --note "no new UI"`, and in the release train `DS review ux n/a --note "no new UI"`), going from `architecture` to `plan`. In `maintenance` mode the lifecycle is already in construction (or `stable` with no task): run the tasks of the open maintenance milestone (`M<n> — Maintenance`); when they are done run `qa M<n>` as for any milestone, then stop and point to `/dev-kit:issue` for the next batch (do not run the release train unless the user asks).
