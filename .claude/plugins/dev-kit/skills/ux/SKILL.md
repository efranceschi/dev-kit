---
name: ux
description: Designs the user experience before UI - information architecture, journeys per persona, screen inventory, every screen state (loading, empty, error, success), forms and validation behaviour, microcopy guide and usability checkpoints - into .dev/design/ux-flows.md. Use after architecture for products with a user interface, or when a flow must be redesigned.
argument-hint: "[flow, persona or screen to (re)design]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# ux

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Preconditions
`.dev/prd.md` exists. If the brief says the product has no UI (API/CLI only), write a short `ux-flows.md` covering CLI/API ergonomics (command/endpoint naming, error messages, help output) instead of screens, then move on.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md`, `${CLAUDE_SKILL_DIR}/../core/shared/checklists/nielsen-10.md`, the brief (blocks 2, 3, 7), the PRD stories/ACs, and the template `${CLAUDE_SKILL_DIR}/../core/shared/templates/ux-flows.md`.
2. Derive principles for this product from the brief (device context, user technical level, tone).
3. Build the information architecture and navigation model; then one journey per persona × top task, each mapped to story and AC ids, with a Mermaid flow and a step table including error/edge paths.
4. Produce the screen inventory with stable ids `S-01…` (existing projects: column `tag` = `existing | new | changed`); for every screen specify all states and the recovery action for errors; specify forms (fields, validation timing, messages pattern, autosave/undo).
5. Message catalog (`ux-flows.md` §7.1: required, too long, invalid format, duplicate, not allowed, not found, network, saved/deleted, empty list) and microcopy guide in the **application language(s)** from brief block 2 with examples; conversation and headings stay in the user's language.
6. Usability checkpoints: for each heuristic that matters here, how the flows satisfy it; list accessibility implications for `ui` (focus order, announcements, target sizes).
7. Gaps → autonomy rule (`ui_details` and most UX choices are `decide_alone`); log ADRs for notable choices (navigation model, onboarding strategy). Ask only for `always_ask` matters (rare here: e.g. collecting extra personal data).
8. Write `.dev/design/ux-flows.md`. Run the self-check (`${CLAUDE_SKILL_DIR}/../core/shared/prompts/self-check.md`, which includes `dev_state.py xref`) and fix what it finds, then `dev_state.py artifact mark ux`. Summarise journeys and screen count; next: `ui`.

## Rules
- Every AC that involves the interface must be reachable in at least one journey step; check this before finishing.
- Do not specify colours, spacing or components here; that is `ui`.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:ui`. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): start the screen inventory from the existing routes and screens in `.dev/discovery.md` §5–6 and tag each `existing` (one line: id, route, file) or `new`/`changed`; journeys, states and forms are specified only for `new`/`changed` screens and for existing screens a `new` AC passes through. Reuse the app's navigation model and microcopy tone; do not redesign. If no `new` AC touches the UI, write nothing, record `dev_state.py review design n/a --note "no new UI"` (the lifecycle skips `ux` and `ui` and goes to planning).
