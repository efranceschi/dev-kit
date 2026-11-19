---
name: help
description: Help for the dev-kit inside Claude Code - with no argument, what to do next in this project and the map of skills by goal; with a skill name, how to use it with examples; with a question ("how do I report a bug?", "how much did I spend?", "what is a gate?"), the recipe, concept or command that answers it; with "agents", the agents and who calls them. Use when the user is lost, asks which skill to use, how something works, or what to do next. Read-only.
argument-hint: "[skill | question | agents | concept]"
allowed-tools: Read, Bash, Grep, Glob
---

# help

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DD` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_docs.py"` and `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

Read-only. The sources are in English (`${CLAUDE_SKILL_DIR}/../core/shared/help.json` and the generated docs); answer in the user's language, translating at display time. Keep commands, ids and file names as they are.

## Procedure
1. If `.dev/state.json` exists, log `DS event skill_start --set skill=help --set args_kind=query`.
2. Get the answer: `DD help <arguments> --json`. Its `kind` says what it is:
   - `map` (no argument): this is the orientation answer.
     - No `.dev/` in the project: say this is not a dev-kit project yet and show how to start (`/dev-kit:start <idea>` for a new project; in a folder that already has code, `/dev-kit:start "<what you want to change>"` adopts it without touching the existing code: baseline tag, discovery, and a choice of feature, maintenance or import mode), plus the map.
     - Otherwise read `DS status --json` and `DS backlog --json` and lead with **"Now"**: the phase and the 1–3 most useful commands at this moment, in this order of priority: open hotfix → `/dev-kit:implement <task>`; parked or open questions → `/dev-kit:interview --gaps`; milestone in progress → `/dev-kit:autopilot` or `/dev-kit:implement`; tasks done and gate pending → `/dev-kit:qa <M>`; existing project in maintenance mode with no task → `/dev-kit:issue "<bug or improvement>"`; build finished → `/dev-kit:docs`, `/dev-kit:release`. Then the compact map "What do you want to do?" by category (one line per skill).
   - `skill`: show the card: what it does, when to use it, usage line, arguments, 2–3 examples, what it produces, related skills.
   - `recipe`: the numbered steps with the commands; add the glossary definition if a `term` came with it.
   - `term`: the definition, plus the recipe or skill where it matters if obvious from the catalog.
   - `agents`: a short table: agent, role, tier, called by (from the returned markdown).
   - `suggest` (no match): the closest skills and the docs pages to read (`docs/recipes.md`, `docs/skills.md`, `docs/concepts.md`, `docs/glossary.md`, `docs/troubleshooting.md`); offer to rephrase.
3. Keep it short: the user wants to know what to type. Never invent a skill, argument or behaviour that is not in the catalog or the docs; if unsure, point to the doc page.
4. End with one tip from `DS tip help` on its own line (only if `.dev/` exists and the tip is not empty), translated into the user's language. If `.dev/` exists, log `skill_end`.
