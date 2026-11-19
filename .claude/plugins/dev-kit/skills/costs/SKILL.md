---
name: costs
description: Cost summary of dev-kit work shown in the chat - token usage (input, output, cache write and read) and estimated cost in US$ (API-equivalent) per stage, agent, model or session, read from Claude Code's local transcripts and attributed to stages by the session log; optional CSV with every token count so the user can price it with their own rates. Use when the user asks how much was spent, the project's or session's cost, tokens per stage, or which agent or stage costs the most. Read-only.
argument-hint: "[--all | --since YYYY-MM-DD] [--by stage|agent|model|session] [--csv]"
allowed-tools: Read, Bash, Grep, Glob
---

# costs

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: current session, grouped by stage)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DC` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}"` and `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §14. Log `DS event skill_start --set skill=costs --set args_kind=period`.
2. `DC report --json <period args> --by <grouping>` (it ingests the transcripts first). The JSON has `period`, `source` (`transcripts` or `skills (partial)`), `rows` (key, requests, input, output, cache_write_5m, cache_write_1h, cache_read, tokens, usd, usd_complete, share), `total`, `prices_as_of` and `warnings`. If `total.requests` is 0, explain why (no transcripts for this project on this machine, or nothing ran in the period; suggest `--all`) and stop.
3. With `--csv`, also run `DC export <period args>` and keep the path it prints.
4. Show in the chat, in the user's language, short:
   - **Header:** period, estimated total in US$ (say it is the API-equivalent estimate, not a charge), total tokens and number of requests.
   - **Table** by the grouping: `Stage | US$ | % | Input | Output | Cache write | Cache read`, sorted by cost; tokens in k/M; `n/d` where `usd_complete` is false. Stage names: `orchestration` is the main session outside any skill.
   - **Where the cost went:** the 3 most expensive rows, one line each with the main driver (e.g. output tokens on a large model, cache reads of long sessions). If grouped by stage, also run `DC report --json --by agent --no-ingest <period args>` and name the most expensive agent.
   - **Warnings** from `warnings`, if any (models without price, partial data, old price table).
   - **Data:** `.dev/costs/usage.jsonl` (one line per request, tokens only), `.dev/costs/prices.json` (editable price table, `as_of` date), and the CSV path when generated.
5. Log `skill_end` with `status` ok and `duration_s`. End with one tip from `DS tip costs` on its own line (skip if empty).

## Rules
- Read-only: the only files written are `.dev/costs/` (by `dev_cost.py`) and the CSV on request.
- Never edit the price table on your own and never present the estimate as a real charge.
- Never show transcript content; only the numbers in the report.
