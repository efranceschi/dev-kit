---
name: architecture
description: Decides and documents the technical architecture (.dev/architecture.md) - stack (detected or chosen), repository layout, data model, API contracts, cross-cutting concerns, environments and test strategy - and records ADRs in .dev/decisions.md. Use after prd, or when a structural decision must be revisited.
argument-hint: "[constraints or 'review']"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, WebSearch, WebFetch, Skill
---

# architecture

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status` and a brief `feedback` on the dev-kit itself; the script measures the duration and the plugin hooks log every agent) and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says (allowed keys: `${CLAUDE_SKILL_DIR}/../core/shared/telemetry-schema.json`), with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`
Detected stack: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_detect_stack.py" "${CLAUDE_PROJECT_DIR}"`

## Preconditions
`.dev/prd.md` and `.dev/brief.md` exist. Otherwise invoke the missing step first.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md`, `${CLAUDE_SKILL_DIR}/../core/shared/interview/autonomy-policy.md`, the brief (blocks 4–6, 8, 10), the PRD (NFRs, data entities implied by stories) and `.dev/decisions.md`.
2. Stack decision:
   - Brownfield (detection found manifests): keep the existing stack; only add what the PRD needs. When state has `brownfield`, reuse the `source: discovered` ADRs and `.dev/discovery.md` instead of re-deciding or duplicating them. Record `stack` in state with `dev_state.py init --stack-json '<detected json>'`.
   - Greenfield with stack chosen in the brief: use it.
   - Greenfield with "decide for me": spawn the `architect` agent (pass `model: opus`, `effort: high`, `conventions.md` §9) with the brief, PRD and detection output, asking for a recommendation. Adopt it unless it requires an `always_ask` decision (paid service, public exposure, security model), in which case apply that point's `pause_policy` action (`conventions.md` §10); for `ask`, ask the user once with the recommended option first.
3. Write `.dev/architecture.md` from `${CLAUDE_SKILL_DIR}/../core/shared/templates/architecture.md`: stack table with versions, context diagram, repository layout, data model (every entity from the PRD, with retention/privacy rules from the brief), contracts (every operation needed by the ACs, mapped to AC ids), cross-cutting concerns, environments (when `autonomy.local_deploy.mode` is not `off`, a "local preview" command that builds and starts the production build on `127.0.0.1:<port>`, or installs the CLI/desktop build locally; see `conventions.md` §11), CI steps (when `autonomy.production.when` is not `none`: the production install, migrate and rollback commands, backup location, smoke checks and the list of operational prerequisites with how each is provided; see `conventions.md` §12), the type-check command that covers every project reference, test strategy summary, open points delegated to implementation.
3a. Fill the data sources table (coverage, freshness, quotas; facts to verify, from brief block 4), the exclusive resources table (lock names), the long jobs, the data invariants file and the performance scenarios file when the product has them.
3b. Release flags (`conventions.md` §21): when the brief asks to ship approved milestones dark, or `autonomy.release_flags.enabled` is true, choose the flag mechanism (an environment variable read at start, a config file, or a flag service already in the stack), record it in `architecture.md` §7 (how a flag is read in code, how it is switched on and off in production, and how long a switch takes to apply) with an ADR, and store it: `dev_state.py set autonomy.release_flags '{"enabled": true, "provider": "<mechanism, one line>"}'`. Without flags, write "release flags: off".
4. Append ADRs to `.dev/decisions.md` for every non-obvious choice (`source: auto` or `user`). Add `Q-nnn` questions for choices the user may want to revisit.
5. Persist stack: `dev_state.py init --stack-json '{"lang":..., "framework":..., "pkg":..., "test":..., "lint":..., "db":..., "detected_from":[...]}'` and `dev_state.py artifact mark architecture`. If the brief says the product has no UI (API/CLI only), record it with `dev_state.py review design n/a --note "no UI: <API|CLI|...>"`: the lifecycle then marks `ux` and `ui` as skipped and goes to planning (`conventions.md` §19).
5a. **Architecture diagram**: invoke the skill `dev-kit:diagram` (Skill tool; `update` when `docs/diagrams/architecture.svg` already exists) and follow it fully. Before any code exists it draws the architecture as planned, so the board's Architecture tab shows the shape of the system from conception on, and the person reviewing the architecture sees it as a picture. It edits `.dev/architecture.md` §2 (the link), which is why it runs before the mark below. Skip it only when the architecture did not change (`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_diagram.py" --root "${CLAUDE_PROJECT_DIR}" check` exits 0).
6. Run the self-check (`${CLAUDE_SKILL_DIR}/../core/shared/prompts/self-check.md`, which includes `dev_state.py xref`) and fix what it finds, then `dev_state.py artifact mark architecture`.
7. Summarise the decisions in ≤ 10 lines and name the next step.

## `review` mode
Spawn `architect` with "challenge" instructions on the current `architecture.md`; apply accepted changes as superseding ADRs; do not rewrite from scratch. When `.dev/architecture.md` changed, redraw the diagram (step 5a, with `update`) before `artifact mark architecture`.

## Rules
- No dependency may appear later in code without an ADR or a line in the stack table; `code-reviewer` enforces this.
- Prefer the simplest architecture satisfying the NFRs; justify every extra component with the AC or NFR it serves.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:ux` (or `/dev-kit:plan` without a UI). Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): `architecture.md` describes the system as it is (from `.dev/discovery.md`) plus what the `new` ACs add; mark each section `as-built` or `planned`. When the project already has an architecture document (`discovery.md` §12), summarise it and link to it instead of rewriting it. §8 uses the project's real build, test and lint commands.
