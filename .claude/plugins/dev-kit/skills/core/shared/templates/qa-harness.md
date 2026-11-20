# QA harness — {{project_name}}

What the "QA harness" chore task builds (`plan` adds it to the first UI milestone when `dev_detect_stack.py --tools` reports no usable harness). It lets `visual-reviewer`, `a11y-auditor` and `usability-auditor` capture every screen in every state with one command, instead of reading markup and guessing. It is a development dependency, recorded as an ADR (`dev_tooling`; in existing projects an `always_ask` decision).

## Deliverables
| item | content |
|---|---|
| dev dependencies | `@playwright/test`, `@axe-core/playwright` (JS/TS projects); `playwright` and `axe-playwright-python` for Python front ends without Node |
| `qa/harness.config.*` | base URL from `QA_BASE_URL` (default the dev server on `127.0.0.1:<port>`), viewports desktop 1440×900, tablet 834×1112, mobile 390×844, light and dark when the UI has both |
| `qa/screens.*` | one entry per screen id of `.dev/design/ux-flows.md` (`S-01`…): route, the states to capture (loading, empty, error, success, plus any the spec lists) and how each state is produced |
| `qa/mocks/` | API responses per screen and state, served with `page.route(...)`, so every state is reachable without a backend, seed data or a login |
| script `qa:shots` | captures every screen × state × viewport into `.dev/qa/<scope>/shots/<screen>-<state>-<viewport>.png` (scope from `QA_SCOPE`, default `current`); exits non-zero only when a page fails to render |
| script `qa:a11y` | runs axe (WCAG 2.2 AA tags) on every screen × state at the desktop viewport and writes `.dev/qa/<scope>/a11y.json` (violations with rule, impact, target, screen and state) |
| README section | how to run both and how to add a screen |

## Rules
- Mocks first: the harness never needs production credentials, real third-party services or a seeded database. When a screen cannot be mocked (server-rendered behind auth), use the **QA access** recorded in `architecture.md` §8 (a local seed user or read token read from an env var by name).
- Deterministic: freeze time and random seeds, disable animations (`prefers-reduced-motion`), wait for network idle and fonts, so the same commit gives the same screenshots.
- Fast: run on the production build when it starts in under a minute, otherwise on the dev server; parallel workers at most `max(1, nproc // 4)` (`resource-isolation.md`).
- The screen list is the contract: a new screen in `ux-flows.md` adds an entry in the same task that builds it (implementer self-check).
- Output folders under `.dev/qa/` are scratch for audits; do not commit screenshots unless the project asks for visual baselines.

## How the agents use it
`visual-reviewer` runs `qa:shots` with its slot's port and `QA_SCOPE=<scope>` and reviews the images; `a11y-auditor` runs `qa:a11y` and then checks by hand what axe cannot (keyboard, focus order, announcements). Without the harness they fall back to starting the app themselves, and to static reading with `confidence: low` when no browser is available.
