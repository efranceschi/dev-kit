---
name: issue
description: Registers a bug, improvement or scope change found at any time - classifies it (type and class of service - expedite hotfix, current milestone, standard queue, intangible cool-down, or change through PRD and replan) against the PRD and plan, confirms with the user, records it as I-nnn and routes it without ever creating or renumbering milestones. Also shows, updates, schedules, promotes deferred QA findings and closes issues. Use when the user reports a bug, asks for an improvement or a change, or says "new issue", "found a problem", "I want X to work differently".
argument-hint: "[\"description\" | I-003 | --from F-012 M3 | --schedule I-003 M8 | --close I-003 wontfix|duplicate]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion, Skill
---

# issue

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Rules that never bend
- Issues never create, insert or renumber milestones. The cadence M1, M2, M3… stays as planned (`conventions.md` §15).
- The class follows the written criteria below, not the urgency of the moment. If the user asks for expedite without meeting the criterion, say so and recommend `standard`.

## Classes of service (`conventions.md` §15)
| class | criterion | where it goes |
|---|---|---|
| `expedite` | bug, `critical` or `high`, in delivered work (or production), or blocking the current milestone | hotfix lane now (one at a time): `add-task --lane hotfix` in the current milestone |
| `current` | bug in a task of the milestone being built, before its gate | task in that milestone now |
| `standard` | `medium` bug, or improvement with clear value | queue → buffer of the next milestone (`pull-issues`) |
| `intangible` | `low` bug, polish, tech debt, promoted deferred finding | queue → cool-down (if on) or spare buffer |
| `change` | adds or alters an acceptance criterion or a must-have (type `change`) | `prd` → `review prd` → (`ux`/`ui` → `review design`) → `plan` replan into a future milestone |

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §15, `.dev/prd.md` (ACs), `.dev/plan.md` and `DS backlog --json`. Log `DS event skill_start --set skill=issue --set args_kind=issue` (`conventions.md` §13).
2. **Modes:**
   - `I-003` → show it (`DS issue I-003`) with its tasks and status, and offer the useful next step.
   - `--close I-003 wontfix|duplicate [I-001]` → `DS issue I-003 --status wontfix` or `--duplicate-of I-001`.
   - `--schedule I-003 M8` → only an **existing** milestone: create the task there (`DS add-task --milestone M8 --issue I-003 ...`); warn if it exceeds the buffer of M8 and ask before going on.
   - `--from F-012 M3` → read the finding from `.dev/qa/M3/findings-round-*.json` (or `.dev/reviews/<target>/…`), and register it as an issue with `--origin qa` (class usually `intangible` or `standard` by severity).
   - Free text → continue below.
3. **Duplicates:** compare with open issues and `todo` tasks (`DS backlog --json`). If one matches, offer to link (`DS issue <id> --note …` or `--duplicate-of`) instead of creating.
4. **Classify:** type (`bug` | `improvement` | `change`), class (table above), severity for bugs, effort (S | M | L), `affects` (milestones and ACs, e.g. `M3,AC-12`), and 1–3 acceptance criteria phrased as observable behaviour. For a bug, check the PRD: if the behaviour contradicts an AC, cite it.
5. **Confirm** with one AskUserQuestion (at most 3 questions: type and class together, severity, and for `standard`/`intangible` whether to schedule it now in a milestone instead of queueing). Recommended option first, with one line of reason, as `conventions.md` §9 says.
6. **Register:** `DS add-issue --type <t> --class <c> --title "<short title>" [--severity] [--effort] [--affects] [--acceptance "..."]...`. Then by class:
   - `expedite` → `DS add-task --milestone <current milestone from DS backlog --json> --type fix --title "..." --issue I-nnn --lane hotfix --acceptance "regression test reproducing I-nnn fails before the fix and passes after"`. Offer (recommended): `/dev-kit:implement T-xxx` → `/dev-kit:qa --scope T-xxx` → `/dev-kit:deploy` (if there is production) → `/dev-kit:release --hotfix`.
   - `current` → `DS add-task --milestone <current> --type fix --issue I-nnn ...` (regression test first). Offer `/dev-kit:implement T-xxx`.
   - `standard` / `intangible` → leave it queued; tell when it will be picked (next milestone's buffer, or cool-down) and its position in the queue (`DS backlog --json` → `queue`, `buffer`).
   - `change` → it is `scope_change_major`: apply `pause_policy.scope_change_major` (`conventions.md` §10). With the user's yes, chain `prd` (with the issue as the change request) → `review prd` → (`ux`/`ui` → `review design` if the UI changes) → `plan` replan, adding tasks only to future milestones with `--issue I-nnn`. Otherwise leave it `open`.
   - UI improvements: the task's acceptance includes updating `.dev/design/ui-spec.md`, so spec and code do not drift.
7. Run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` and log `skill_end` (`conventions.md` §13–14).
8. **Report** in the user's language, short: issue id, type and class (with the reason), what happens next and when, the recommended next command. End with one tip from `DS tip issue_created:<class>` on its own line (skip if empty).
