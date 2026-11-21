---
name: feedback
description: Evaluation of a dev-kit work session for the user or for the dev-kit author - reads the structured session log (.dev/telemetry.jsonl), grades every stage 0-100 with a fixed formula and its reasons, and writes a timestamped report (what worked, what failed, prioritised suggestions for the kit) plus the matching data export, without any project data. Use when the user asks for the session's feedback, how the run went, an evaluation of the dev-kit, or a report to send to the kit's author. Read-only.
argument-hint: "[--all | --since YYYY-MM-DD]"
allowed-tools: Read, Write, Bash, Grep, Glob
---

# feedback

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: the current session, i.e. since the last `session_start`; `--all` for the whole project; `--since YYYY-MM-DD` for a period)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

This skill only reads the log and writes two files under `.dev/feedback/`. It does not change state, code or the log's past events, and it does not ask the user for feedback.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 (log, grading formula). Log `DS event skill_start --set skill=feedback --set args_kind=period`.
2. Data: `DS telemetry report --json <period args>`; when `.dev/router.json` exists, also `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_router.py" --root "${CLAUDE_PROJECT_DIR}" explain --json` for the router's mistakes, learned weights and savings (counts and signal names only: they carry no project data), and cite them under the `cost` area. It returns `period`, `summary` (agents, models, tokens, scores, pauses, errors, feedback) and `report` (per-stage `score`, `reasons`, rounds, score sequences, agents, duration, tokens, errors, feedback; `overall`; `general_feedback`). If the period has no events, say that no session was logged for that period (and how to start one: any dev-kit skill logs automatically) and stop.
2b. Costs: `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" report --json <period args>` (by stage) and again with `--by agent --no-ingest`; use them for the cost columns and the "Where the cost went" section (`conventions.md` §14).
3. Pick one timestamp `YYYYMMDD-HHMMSS` (UTC) for both files. Write `.dev/feedback/feedback-report-<stamp>.md` (if it exists, add `-2`, `-3`…) in the user's language, with this structure:
   - **Header:** dev-kit version, period (from → to, mode), stack by category, project kind (new, or existing with its entry mode from `session_start`; stages recorded only as `n/a` are shown as `—`, not graded), volume (sessions, skills run, agent runs, total agent time, tokens when known). No project name.
   - **Grades by stage:** table `Stage | Grade | Cost (US$, est.) | Tokens | Summary`, one row per stage, `—` for stages that did not run, then the overall grade. The grade is the script's number, never adjusted by hand; the summary is one line drawn from its `reasons` and data.
   - **Comments by stage:** for each stage that ran, "What worked" and "What went wrong", in short bullets based only on the data (rounds, score sequence such as `40 → 47`, forced passes and by whom, errors by code, agents without JSON, durations, tokens) and on the recorded feedback notes of that stage. Quote feedback notes as they are. Do not invent events, do not speculate about causes the log does not show.
   - **Where the cost went:** the 3 most expensive stages and the 3 most expensive agents, with share of the total and the main driver (output on a large model, cache reads of long runs, many rounds); say it is an API-equivalent estimate.
   - **Prioritised suggestions for the kit:** at most 7, ordered by impact: first the `improve` and `failed` notes that repeat across agents or stages, then the lowest-graded stages with the reason that cost the most points. Each one says what to change in the dev-kit (skill, agent prompt, checklist, script, formula), not in the project.
   - **How the grades are computed:** one line pointing to `conventions.md` §13.
4. **Privacy check before saving:** the report may only use what the export allows: stage and agent names, models, numbers, ids, codes and the recorded notes. For every sentence you wrote yourself, make sure it has no project name, product terms, entity names, file paths, URLs or people. If in doubt, rewrite it generically ("the PRD review" instead of the feature it discussed).
5. Write the matching data file: `DS telemetry export --stamp <stamp> <period args>` (→ `.dev/feedback/telemetry-export-<stamp>.json`, never overwriting).
6. Log `skill_end` with `status` ok and `duration_s`.
6b. End with one tip from `DS tip feedback` on its own line (skip if empty).
7. Show the user, in their language: the grades table, the top 3 suggestions, the two file paths, and a reminder to review both files before sending them to the dev-kit author (nothing is sent automatically).

## Rules
- Read-only apart from the two files in `.dev/feedback/` and the two log events of this skill.
- Never change a grade, and never add data that is not in the log.
- Never include project content; the export already excludes it, and the report must not reintroduce it.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
