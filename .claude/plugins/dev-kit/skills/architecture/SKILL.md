---
name: architecture
description: Decides and documents the technical architecture (.dev/architecture.md) - stack (detected or chosen), repository layout, data model, API contracts, cross-cutting concerns, environments and test strategy - and records ADRs in .dev/decisions.md. Use after prd, or when a structural decision must be revisited.
argument-hint: "[constraints or 'review']"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, WebSearch, WebFetch
---

# architecture

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

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
   - Greenfield with "decide for me": spawn the `architect` agent with the brief, PRD and detection output, asking for a recommendation. Adopt it unless it requires an `always_ask` decision (paid service, public exposure, security model), in which case apply that point's `pause_policy` action (`conventions.md` §10); for `ask`, ask the user once with the recommended option first.
3. Write `.dev/architecture.md` from `${CLAUDE_SKILL_DIR}/../core/shared/templates/architecture.md`: stack table with versions, context diagram, repository layout, data model (every entity from the PRD, with retention/privacy rules from the brief), contracts (every operation needed by the ACs, mapped to AC ids), cross-cutting concerns, environments (when `autonomy.local_deploy.mode` is not `off`, a "local preview" command that builds and starts the production build on `127.0.0.1:<port>`, or installs the CLI/desktop build locally; see `conventions.md` §11), CI steps (when `autonomy.production.when` is not `none`: the production install, migrate and rollback commands, backup location, smoke checks and the list of operational prerequisites with how each is provided; see `conventions.md` §12), the type-check command that covers every project reference, test strategy summary, open points delegated to implementation.
4. Append ADRs to `.dev/decisions.md` for every non-obvious choice (`source: auto` or `user`). Add `Q-nnn` questions for choices the user may want to revisit.
5. Persist stack: `dev_state.py init --stack-json '{"lang":..., "framework":..., "pkg":..., "test":..., "lint":..., "db":..., "detected_from":[...]}'` and `dev_state.py set phase ux` (if the brief says the product has no UI — API/CLI only — set phase `plan` and note that `ux`/`ui` are skipped).
6. Summarise the decisions in ≤ 10 lines and name the next step.

## `review` mode
Spawn `architect` with "challenge" instructions on the current `architecture.md`; apply accepted changes as superseding ADRs; do not rewrite from scratch.

## Rules
- No dependency may appear later in code without an ADR or a line in the stack table; `code-reviewer` enforces this.
- Prefer the simplest architecture satisfying the NFRs; justify every extra component with the AC or NFR it serves.
