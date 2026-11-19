# Implementation plan — {{project_name}}

> Purpose: ordered, dependency-aware list of vertical-slice tasks. Derived from `prd.md`, `architecture.md`, `design/*.md` on {{date}}. Status: active.
> Status of tasks lives in `.dev/state.json`; the `status:` lines below are informative. Parser contract: `shared/conventions.md` §4.

## Milestone overview
| Milestone | Goal | ACs covered | Gate |
|---|---|---|---|
| M1 | Walking skeleton: project setup, CI, one end-to-end slice | AC-1, AC-2 | pending |
| M2 | … | | pending |

Ordering rules used: setup and CI first; then the highest-priority must-have as a thin end-to-end slice; infrastructure only when a feature needs it; fix tasks jump the queue.

## M1 — {{milestone title}}
{{one-paragraph goal and exit criterion}}

### T-001 Project scaffold, tooling and CI
- status: todo
- deps:
- type: chore
- acceptance:
  - AC-0: `test` and `lint` scripts run green in CI on a clean checkout
- test_notes: smoke test that the app boots
- files: package.json, .github/workflows/ci.yml

### T-002 {{task title}}
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-1: …
- test_notes: …
- files: …

## M2 — {{milestone title}}
…
