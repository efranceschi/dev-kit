---
name: interview
description: Exhaustive requirements interview that captures everything needed to build the application autonomously - product, users, scope, data, stack, integrations, UX/UI, quality bar, autonomy policy and delivery - into .dev/brief.md, initial ADRs and state. Use at the start of a new project, or with --gaps to resolve open questions accumulated during autonomous work.
argument-hint: "[initial idea | --gaps | --express]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# interview

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log (from the moment `.dev/state.json` exists; Setup step 3 creates it): record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS

State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`
Stack: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_detect_stack.py" "${CLAUDE_PROJECT_DIR}"`

## Setup
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md`, `${CLAUDE_SKILL_DIR}/../core/shared/interview/questionnaire.md` and `${CLAUDE_SKILL_DIR}/../core/shared/interview/autonomy-policy.md`.
2. Language: infer from the user's messages; if `.dev/state.json` has `language`, use it. If undeterminable, the very first question asks it.
3. If `.dev/state.json` does not exist: `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" init --language <tag> --phase interview --project "<name or folder>"`.
4. Existing codebase (detection says `"greenfield": false`) but no `brownfield` in state: stop and invoke `start` instead, which runs the onboarding (baseline tag, discovery, test baseline) first; without it none of the existing-project rules apply. With `brownfield` in state, see the last section.

## Mode: full interview (default)
Follow `questionnaire.md` exactly:
- Pre-fill from the initial idea and the repo; mark items known / inferable / unknown.
- One AskUserQuestion per block (max 4 questions; recommended option first; always an option meaning "decide for me"). Skip blocks fully known. One follow-up round per block at most.
- After each block, append its section to `.dev/brief.md` (start from `${CLAUDE_SKILL_DIR}/../core/shared/templates/brief.md`). If `brief.md` already has some sections, resume at the first missing block.
- Block 9 must end with a concrete autonomy JSON (level + any `always_ask` overrides + flags such as `may_push`) that also contains `quality` from block 8: `standard` → `{"min_overall":85,"min_dimension":70}`; `premium` → `{"min_overall":92,"review_min_overall":88,"min_dimension":80,"dimension_min":{"security":95,"tests":85,"spec":90,"a11y":85}}`; `prototype` → `{"min_overall":70,"review_min_overall":65,"min_dimension":50,"dimension_min":{"security":70,"tests":60,"spec":70,"a11y":60}}`; custom numbers if the user gives them. Explain the scoring in one sentence before asking. Also store the autonomy chosen in block 9: `"level": "unattended"` for unattended runs (the script fills the recommended pause policy), plus any `"pause_policy": {"<point>": {"action": ..., "limit": ...}}` changes, `"on_park"` and `"notify_on_park"`; `dev_state.py` rejects actions outside the floors. Add `"issue_buffer_pct"`, `"cooldown": {"enabled": ..., "max_tasks": ...}` and `"tips"` from block 9. Add block 10's production answers as `"production": {"when": ..., "method": ..., "host": ..., "targets": [...], "smoke": [...], "prerequisites": [...]}` (prerequisites by name only, never values) and its consent as `pause_policy.production_deploy`. Add block 10's local deploy as `"local_deploy": {"mode": "off|keep_running|smoke", "port": <int or null>, "notify": <bool>}`; ask it only when the platform allows (`conventions.md` §11), otherwise store `off`. Also ask (block 9) for consent on the model/effort ladder of `conventions.md` §9 and store `"model_policy": {"mode": "ask|preapproved|off", "tiers": {}}` in the same JSON. The `cautious` autonomy level raises the cut-offs to its preset (overall 90, reviews 85, every dimension 75, security 95, tests 85, spec 90, a11y 85; table in `autonomy-policy.md`) unless the user chose higher numbers; `dev_state.py` applies the preset when `level` is set and never lowers a bar.

## Mode: `--express`
New project: single round with the four most consequential questions (platform/stack, must-have scope, auth/data sensitivity, autonomy level). Everything else is marked `delegated`; later skills decide and log ADRs. Say explicitly that more questions may surface in `open-questions.md`.
Existing project (`brownfield` in state): express means "only what discovery cannot answer". Blocks answered by `discovery.md` (or by the imported documents in `import` mode) are written as `(inferred, confirmed)` after one confirmation question; only the remaining blocks are asked, block by block as in the full mode. Nothing is `delegated` that discovery already answered.

## Mode: `--gaps`
Read `.dev/open-questions.md` (Open table). Group questions by theme, ask them in rounds of up to 4 with the assumption that was used as the recommended option. For each answer: move the row to Resolved with the date and answer; if the answer differs from the assumption, write an ADR in `.dev/decisions.md` superseding the `auto` one and, when it affects work already done, create a fix task via `dev_state.py add-task --milestone <current milestone> --type fix --title "<what changes>" --acceptance "<observable condition>" --source open-questions.md#Q-nnn`. Do not re-run the full interview.

## Close (full and express)
1. Show a compact summary: one line per block. Ask for one confirmation (AskUserQuestion: "Confirm and start building" / "Change something").
2. Write `.dev/decisions.md` from `${CLAUDE_SKILL_DIR}/../core/shared/templates/adr.md` with the initial ADRs (stack if chosen, auth model, hosting, autonomy level, git policy) — `source: interview`.
3. Persist: `dev_state.py init --language <tag> --stack-json '<json>' --autonomy-json '<json>' --phase prd` (init is idempotent and only updates the given fields). Record unknowns the user chose to leave open with `dev_state.py add-question "<q>" --skill interview --assumption "<a>" --impact "<i>"`.
4. **Announce the next step on screen.** This is the last thing the user reads, so make it unmissable and in the user's language. State that all requirements were collected and the project is ready to be built, then show:
   - What was saved: `.dev/brief.md`, `.dev/decisions.md`, the autonomy level chosen, the quality cut-offs that gates will enforce (overall and security minimums), and how many open questions remain (if any).
   - The recommended next command in a fenced code block: `/dev-kit:autopilot` (builds everything autonomously from PRD to release, pausing only on always-ask decisions). Mention the useful variants in one line each: `--until plan` (generate only the documents so you can review them first) and `--milestone M1` (build only the first milestone).
   - The step-by-step alternative: `/dev-kit:prd`.
   - Where to check progress at any time: `/dev-kit:status`; for any doubt about what to do or how a skill works: `/dev-kit:help`.
   Then stop. Do not start `autopilot` or `prd` yourself; the user decides when to begin. Exception: an existing project in `maintenance` mode invoked by `start`'s onboarding — return control to the onboarding (step 9 of `onboarding.md` writes the as-built PRD, the empty maintenance milestone and the `n/a` reviews) and announce instead that work enters through `/dev-kit:issue`. In `--gaps` mode, the announcement instead says which questions were resolved, which ADRs or fix tasks changed, and that the user can resume with `/dev-kit:autopilot`.

## Rules
- Never ask something already answered in the initial message, the repo or the brief.
- Keep questions concrete with examples; avoid jargon for non-technical users (block 1 tells you their level).
- Never record secret values; record variable names only.

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16) the mode in `brownfield.mode` limits the interview: `feature` → express round on the change, blocks 5–8 and 10 confirmed from `discovery.md`; `import` → read the documents listed in `discovery.md` §12 first and ask only the blocks they leave open (cite the source of each pre-filled answer in `brief.md`); `maintenance` → only blocks 8–10 (quality, autonomy, deploy consent). In every mode, confirm `autonomy.commit_style`, the version and tag scheme and `production` proposed by discovery (`discovery.md` §10–11) instead of asking them from scratch; `pause_policy.dirty_tree` stays at `ask` (the script enforces it). Block 9's `dev_tooling` is `always_ask` in existing projects (`conventions.md` §16); the script moves it when the level is set.
