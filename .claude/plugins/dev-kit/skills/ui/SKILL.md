---
name: ui
description: Defines the visual system and per-screen UI specifications (.dev/design/ui-spec.md) - design tokens, typography, spacing, component inventory with states and accessibility notes, layout patterns, responsive rules, dark mode, and a spec for every screen in ux-flows.md - so implementation stays consistent without per-task design review. Use after ux, or to (re)specify a screen or component.
argument-hint: "[screen id, component or 'tokens']"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion, WebFetch
---

# ui

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Preconditions
`.dev/design/ux-flows.md` exists (run `ux` otherwise). Skip entirely for products without a UI (set phase `plan`).

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md`, `${CLAUDE_SKILL_DIR}/../core/shared/checklists/wcag-2.2-aa.md`, the brief block 7 (references, brand assets, component library, dark mode, a11y level), `.dev/architecture.md` (frontend stack), `.dev/design/ux-flows.md`, and the template `${CLAUDE_SKILL_DIR}/../core/shared/templates/ui-spec.md`.
2. Design system basis: use the library named in the brief/architecture; if none, choose one that fits the stack and record an ADR (`library_choice`). If visual references are URLs, fetch them to extract palette/typography cues.
3. Tokens: define colours with verified contrast (compute ratios; text ≥ 4.5:1, UI ≥ 3:1), type scale, spacing scale, radii, shadows, breakpoints, motion with reduced-motion fallback, dark-mode overrides if required. If the brief supplies brand colours, derive accessible variants rather than replacing them.
4. Component inventory: every component the screens need, with variants, states (default/hover/focus-visible/disabled/loading/error) and a11y notes (roles, names, keyboard, focus trap, live regions, target size ≥ 24 px, prefer 44 px on touch).
5. Layout patterns and responsive behaviour per breakpoint.
6. One spec per screen id from `ux-flows.md`: purpose, ASCII/Mermaid wireframe, components used, copy in the application language, all states, responsive notes, accessibility (heading order, focus order, announcements).
7. Accessibility baseline section and implementation notes (where tokens live, naming of components, visual regression if planned).
8. Gaps → autonomy rule (`ui_details` is normally `decide_alone`); ADR for the library and identity choices. Write `.dev/design/ui-spec.md`. Run the self-check (`${CLAUDE_SKILL_DIR}/../core/shared/prompts/self-check.md`, which includes `dev_state.py xref`) and fix what it finds, then `dev_state.py artifact mark ui`. Then `dev_state.py set phase plan`; summarise; next: `review design` (independent score against the cut-off), then `plan`.

## Rules
- Every screen in `ux-flows.md` §4 has a spec; every component referenced by a spec is in the inventory.
- Visual choices follow the brief's tone and density; when the brief delegated identity, pick a restrained, consistent system over novelty.

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): step 2 uses the UI library already in the code; step 3 extracts the existing tokens (theme files, CSS variables, Tailwind config) and documents them with computed contrast instead of defining new ones, adding tokens only when a `new` screen needs them; step 4 lists existing components with their file paths and specifies only new or changed ones; step 6 specs only `new`/`changed` screens (`existing` ones keep the one-line reference from `ux-flows.md`). Contrast or accessibility problems in inherited tokens become `intangible` issues (`dev_state.py add-issue`), not redesigns.
