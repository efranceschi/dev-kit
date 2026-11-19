# Design review checklist (design-reviewer)

Review `.dev/design/ux-flows.md` and `.dev/design/ui-spec.md` **before any UI code exists**, against `prd.md`, `brief.md` block 7 and `architecture.md`. Findings use `category: design` (or `accessibility` / `consistency` where more specific).

## UX flows
- **AC reachability**: every interface-related AC is reachable in at least one journey step. Unreachable AC → `critical`.
- **Journeys**: one per persona × top task; happy path and the main error path are both described; no dead ends; back/cancel exists where users can lose work. Missing journey for a must-have → `high`.
- **States**: every screen defines loading, empty, error (network, validation, permission) and success; each error names its recovery action. Missing states on a main screen → `high`.
- **Forms**: field list, validation timing, error pattern, defaults, autocomplete, destructive-action confirmation or undo.
- **Navigation**: findable from anywhere in ≤ 3 steps for primary tasks; consistent model; current location visible.
- **Cognitive load**: one primary action per screen; progressive disclosure for advanced options; onboarding for first use.
- **Nielsen**: walk `shared/checklists/nielsen-10.md` over the journeys; record violations that can be fixed in the spec.

## UI spec
- **Token completeness**: colour roles (primary, surface, border, success/warning/danger/info, text), type scale, spacing, radius, shadow, breakpoints, motion, dark mode if required. Missing role used by a screen → `medium`.
- **Contrast**: compute ratios for every text/background and UI-component/background pair in the tokens and states (hover, disabled, focus). Text < 4.5:1 (large < 3:1) or UI < 3:1 → `high`. Show the numbers.
- **Component inventory**: every component used by a screen spec exists in the inventory with variants and states (default, hover, focus-visible, disabled, loading, error). Reference to unknown component → `medium`.
- **Screen specs**: every screen id in `ux-flows.md` has a spec with layout, content, states, responsive notes and accessibility notes. Missing screen → `high`.
- **Responsive**: behaviour defined for each breakpoint in scope; touch targets ≥ 44 px on touch platforms, ≥ 24 px minimum anywhere.
- **Accessibility by design**: heading order, focus order, keyboard interactions for custom widgets, announcements for dynamic content, reduced-motion behaviour, text resizing to 200%.
- **Consistency**: same pattern for same task across screens (same button placement, same empty-state structure); no screen invents a component outside the inventory.
- **Brand fit**: choices match the tone, density and references in the brief.
- **Implementability**: the chosen UI library supports the specified components and tokens without hacks.

Rate each finding by how central the flow is. Say what to change in the spec, one sentence.
