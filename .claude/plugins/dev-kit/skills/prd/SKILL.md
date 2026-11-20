---
name: prd
description: Writes the product requirements document (.dev/prd.md) from the interview brief - problem, personas, MoSCoW scope, user stories with numbered testable acceptance criteria (AC-n), NFRs, risks and recorded assumptions. Use after interview, or to revise the PRD when scope changes.
argument-hint: "[focus or change request]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# prd

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Preconditions
`.dev/brief.md` must exist. If not, run `interview` first (invoke it; do not improvise a brief).

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md`, `.dev/brief.md`, `.dev/decisions.md`, and the template `${CLAUDE_SKILL_DIR}/../core/shared/templates/prd.md`.
2. Derive the PRD strictly from the brief. When state has `brownfield` (existing project, `core/shared/onboarding.md`), also read `.dev/discovery.md`: open the PRD with a short "As-built" section and tag each AC `existing` (already works; verified only), `changed` (exists but its behaviour changes; gets a task) or `new` (to build). Every must-have feature becomes one or more user stories; every story gets acceptance criteria that are **testable and specific** (concrete messages, limits, redirects, permissions, formats). Number ACs globally and never renumber existing ones when revising. Mark texts the requirement fixes as `[locked] "…"` (copy and visual reviews never reword them). An AC over data names its source and a coverage assumption ("covers all regions"), which the plan's data spike confirms.
3. NFRs come from brief blocks 2, 4, 7, 8: locale/i18n, privacy/retention, accessibility level, performance, security, observability. Make each measurable.
4. Gaps: apply the autonomy rule. For each gap, write the assumption into §8 with an `ADR-nnn (auto)` appended to `.dev/decisions.md`; add a `Q-nnn` via `dev_state.py add-question` when the user might disagree. For `always_ask` categories (e.g. a must-have that implies a paid service) apply the `pause_policy` action (`conventions.md` §10); only those with `ask` go into one batched AskUserQuestion at the end.
5. Write `.dev/prd.md` in the user's language. Keep it under ~400 lines; split epics into `.dev/prd/<epic>.md` if larger and link them.
6. Self-check before finishing: every must-have has ≥ 1 story; every story has ≥ 1 AC; no AC uses vague words (fast, easy, properly) without a number or observable outcome; non-goals listed. Run the self-check (`${CLAUDE_SKILL_DIR}/../core/shared/prompts/self-check.md`, which includes `dev_state.py xref`) and fix what it finds, then `dev_state.py artifact mark prd`. When revising an existing PRD, `dev_state.py stale` then shows which later artifacts must follow.
7. Summarise: counts of stories/ACs, assumptions made, questions raised. Next: `review prd` (independent score against the cut-off), then `architecture`.

## Revising (when a PRD already exists)
Apply the change request; mark removed ACs as `(superseded by ADR-nnn)` rather than deleting; append new ACs with new numbers; note in `.dev/log.md` via a `dev_state.py add-question` only if the change needs confirmation. Tell the user that `plan` must be re-run to sync tasks.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:review prd`. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): in `import` mode the project's PRD, specs or user stories listed in `.dev/discovery.md` §12 are the primary source; keep their wording and identifiers (map them to `AC-n` and cite the original), tag each AC `existing`, `changed` or `new`, and record contradictions with the code as `Q-nnn`. In `maintenance` mode write only the as-built section with `existing` ACs for the main journeys, then `dev_state.py review prd n/a --note "maintenance mode: as-built PRD"`.
