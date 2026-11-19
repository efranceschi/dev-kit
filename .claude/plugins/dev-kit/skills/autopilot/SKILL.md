---
name: autopilot
description: Autonomous end-to-end build driver - starting from the interview brief, runs PRD, architecture, UX, UI, plan, then implement -> QA gate -> fix loops per milestone, usability audit, docs and release, pausing only for always-ask decisions, unresolvable blockers or exceeded fix rounds. Resumes from the current phase. Use when the user wants the application built with minimal interaction ("build it", "continue autonomously", "run until QA").
argument-hint: "[--until prd|architecture|design|plan|qa|usability|docs|release] [--milestone M1]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# autopilot

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Preconditions
`.dev/brief.md` exists and the interview was confirmed (phase ≥ `prd`). If not, invoke `interview` first and come back; never build from an unconfirmed brief.

## Driver loop
Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` and the autonomy policy from `DS status --json`. Start a session log: `DS event session_start --set trigger=autopilot` and `skill_start` (`conventions.md` §13); run `DS cleanup` once to clear processes left by an earlier run. Then repeat until the `--until` target or `done`:

| phase | prerequisite review (must be `pass` in `DS status --json` → `reviews`) | action (Skill tool, by name `<skill>`) | then |
|---|---|---|---|
| prd | - | `prd` | `review prd` until pass → phase architecture |
| architecture | `prd` | `architecture` | → ux (or plan if no UI) |
| ux | - | `ux` | → ui |
| ui | - | `ui` | `review design` until pass → plan |
| plan | `design` (UI products) | `plan` | `review plan` until pass → implement |
| implement | `plan` | at the start of each milestone `DS pull-issues <M>` (issue buffer, §15); then `implement --milestone <current>` (or `--parallel N` if the brief allows and ≥ 3 independent tasks are ready) | when milestone complete → qa |
| qa | - | `qa <M>` (scores the milestone; local preview per §11 when enabled) | gate passed → `DS cooldown <M>` (if on, §15) → `deploy <M>` if `autonomy.production.when` is `per_milestone` (§12), then next milestone (implement) or, if last milestone → usability (`qa` sets the phase); gate pending → implement (fix tasks) and re-run qa; rounds > `max_fix_rounds_per_gate` → pause |
| usability | - | `usability` (score recorded as review `ux`) | review `ux` pass → docs; fail → implement the fix tasks, re-audit |
| docs | `ux` (UI products) | `docs all`, `review docs` until pass, then `release --dry-run`, and the real release only if the brief's definition of done includes one (`release` runs `deploy` when `production.when` is `on_release`) | done (`release` sets it) |

`--until` targets: `prd`, `architecture`, `plan`, `usability`, `docs` stop when that row's "then" column is reached; `design` stops after review `design` passes; `qa` stops after the gate of `--milestone` (default: the current one); `release` runs to the end. `release` is not a phase: it is the last action of the `docs` row.

## Quality control (score and cut-off)
- Every checkpoint above is scored 0–100 by independent agents through `dev_score.py`; the cut-offs come from `autonomy.quality` (set in the interview). The driver never advances past a checkpoint whose review or gate is not `pass`; `dev_state.py` refuses a pass below the cut-off.
- Revision loop for documents: `review` sends the artifact back to its producing skill until it clears the cut-off or `max_fix_rounds_per_gate` is exhausted. Milestone loop: `qa` creates fix tasks, `implement` executes them, `qa` re-scores with fresh auditors in delta mode (`conventions.md` §7), so each round closes the previous findings instead of starting over.
- If the same dimension fails twice with the same root cause, stop looping: write an ADR describing the structural problem and ask the user (replan, change the spec, or accept with `--force`).
- Report the score of every checkpoint in the progress line.

The "current milestone" is the first milestone (by number) with tasks not done or gate pending. Each sub-skill updates `phase` itself (`DS done` of a milestone's last task moves it to `qa`; `qa` moves it to `usability` or `docs` after the last gate); after each returns, re-read `DS status --short` and decide the next row. If a sub-skill stops early (blocked task, question), handle it here before continuing.

## Question handling (governed by `autonomy.pause_policy`, `conventions.md` §10)
Every pause point below first looks up its action; only `ask` opens a question. With `autonomy.level unattended` (or every point set to something other than `ask`) the run never waits for the user.
- `always_ask` category decisions (`paid_services`, `delete_data`, `public_exposure`, `scope_change_major`, `security_model_change`, `credentials`): apply the point's action. For `ask`, collect them, finish every task that does not depend on the answer, then ask once with all pending questions (AskUserQuestion, recommended option first). Record answers as ADRs and continue.
- Blockers (three tasks blocked in a row, or tests/dev server cannot run): point `blocked_env`. `ask` → stop with a precise diagnosis and the command to resume; `park` → record the diagnosis as a question, continue any independent milestone work, then end per `on_park`.
- Fix rounds exhausted at a gate or review, or the same finding reappears twice: point `rounds_exhausted`. `ask` → present the options (keep fixing / accept with `--force` and an ADR / replan / change the spec), recommended option first per §9; `auto_recommend` → apply the recommendation (§10); `park` → leave the gate pending, park, end per `on_park` (later milestones depend on it).
- Dirty working tree with unknown changes: point `dirty_tree`.
- Model or effort escalation: `autonomy.model_policy.mode` (`ask` batches it with the other questions; `preapproved` escalates within the ladder and reports it in the progress line; `off` never escalates).
- Open hotfix (`expedite`, §15): it runs first, whatever the phase; then `qa --scope <task>` and `release --hotfix` (which deploys it once), and back to where the run was.
- Issues of class `change`: follow `pause_policy.scope_change_major`.
- Release audit failure: create the fix tasks, go back to `implement` and re-run `release`, counting rounds like a gate.
- Everything else is decided autonomously and logged (`decisions.md`, `open-questions.md`).

## Progress reporting
After each phase transition, review and milestone, print one line: phase, tasks done/total, gates and review scores (from `DS status --short`), open questions, issues pulled into the milestone, the local preview URL when a milestone was just deployed (`conventions.md` §11), and the estimated cost so far (run `dev_cost.py ingest` then `dev_cost.py report --json --no-ingest` after each milestone; show `total.usd` and tokens, §14). Keep the user's context light: do not dump artifacts; name the files.

## End of run
Run `DS cleanup`. Write the run's feedback on the kit (`DS feedback --trigger autopilot --worked area:note --failed area:note --improve area:note`, at most 3 each, about the dev-kit only, consolidating the agents' `kit_feedback`) and `skill_end`. End the run report with one tip from `DS tip autopilot`. Include the run's estimated cost by stage (`dev_cost.py report`) and suggest `/dev-kit:costs` for the breakdown. Suggest `/dev-kit:feedback` for the session's evaluation by stage (a timestamped report and data export to review and, if the user wants, send to the dev-kit author).

Report in the user's language: what was built (milestones, tasks, commits), gates and review scores with the cut-offs used, decisions taken autonomously that deserve review (ADR ids, highlighting `source: policy` ones and any gate passed with `policy:` force), parked items with their recommendation, the local preview still running (URL, milestone, how to stop it), the production deploy state (`DS status` → `Production:` line: what is deployed and how far behind), open questions (suggest `interview --gaps`), and the single next command if the run stopped early. If the run completed `release`, give the version and how to run it.

## Never
- Never run `release` for real with `public_exposure` implications without an explicit yes recorded in the brief, asked now, or `pause_policy.public_exposure` preauthorized for that target.
- Never bypass a gate silently; `--skip-gate` always leaves an ADR.
- Never rewrite git history.

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): a review recorded as `n/a` satisfies the prerequisite column. Skip the `ux` and `ui` rows when no `new` AC touches the UI (record `DS review design n/a --note "no new UI"`, and at the usability row `DS review ux n/a --note "no new UI"`), going from `architecture` to `plan`. In `maintenance` mode start at `implement` and run the tasks of the open maintenance milestone (`M<n> — Maintenance`); when they are done run `qa M<n>` as for any milestone, then stop and point to `/dev-kit:issue` for the next batch (do not go to usability, docs or release unless the user asks).
