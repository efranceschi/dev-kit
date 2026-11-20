# UI spec — {{project_name}}

> Purpose: visual system and per-screen specifications so implementation is consistent without design review per task. Derived from `design/ux-flows.md` and `brief.md` block 7 on {{date}}. Status: draft | approved.

## 1. Design system basis
Component library / CSS approach chosen (ADR ref). Brand assets available or identity created here. Existing projects: the library already in the code, and the tokens below are **extracted** from it (theme files, CSS variables, Tailwind config) with their source file; add a token only when a `new` screen needs it.

## 2. Tokens
| Token | Value | Usage |
|---|---|---|
| color.primary | | buttons, links |
| color.surface / background / border | | |
| color.success / warning / danger / info | | |
| text colours (contrast ≥ 4.5:1 on their surfaces) | | |
| font.family / sizes (scale) / weights / line-heights | | |
| space scale (4-based) | | |
| radius, shadow, z-index scale | | |
| breakpoints | | mobile / tablet / desktop |
| motion (durations, easing, reduced-motion behaviour) | | |

Dark mode: token overrides or "not in v1" (brief).

## 3. Component inventory
| Component | Variants | States | A11y notes | Used in screens |
|---|---|---|---|---|
| Button | primary, secondary, ghost, destructive | default, hover, focus-visible, disabled, loading | role, label, min 44×44 target | all |
| Input / Select / Checkbox / Radio / Switch | | error, disabled | label association, error announced | |
| Modal / Drawer / Toast / Tooltip | | | focus trap, escape, aria-live | |
| Table / List / Card / Empty state / Skeleton | | | | |
| Navigation (header, sidebar, tabs) | | | landmark roles, current page | |

## 4. Layout patterns
Page shells (app shell, auth pages, settings), grid, max widths, responsive behaviour per breakpoint.

## 5. Screen specs
One per screen in `ux-flows.md` §4 (existing projects: only screens tagged `new` or `changed`; `existing` ones are not specified here).

### S-01 — {{screen name}}
- Purpose & primary action; stories/ACs served.
- Layout (wireframe in ASCII or Mermaid; regions and their components).
- Content and copy (application language).
- States: loading / empty / error / success (reference §5 of ux-flows).
- Responsive notes.
- Accessibility: heading order, focus order, keyboard interactions, announcements.

### Screen map (for QA and the harness)
| screen | route | states reachable by URL or mock | route files |
|---|---|---|---|
| S-01 | /orders | `?state=empty`, `?state=error`, mock `orders-empty` | src/pages/orders.tsx, src/ui/OrderList.tsx |

The route files feed the work ledger (`shot:` units, conventions §18): a screen is captured again only when they change.

## 6. Accessibility baseline
Target level (brief, default WCAG 2.2 AA); checklist `shared/checklists/wcag-2.2-aa.md`; global rules (focus visible, skip link, reduced motion, text resizing to 200%).

## 7. Implementation notes
Where tokens live in code, naming of components, Storybook/visual test setup if any.
