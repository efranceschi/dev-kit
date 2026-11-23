# Implementation plan — {{project_name}}

> Purpose: ordered, dependency-aware list of vertical-slice tasks. Derived from `prd.md`, `architecture.md`, `design/*.md` on {{date}}. Status: active.
> Status of tasks lives in `.dev/state.json`; the `status:` lines below are informative. Parser contract: `shared/conventions.md` §4.

## Milestone overview
| Release | Milestone | Goal | ACs covered | Gate |
|---|---|---|---|---|
| R1 | M1 | Walking skeleton: project setup, CI, one end-to-end slice | AC-1, AC-2 | pending |
| R1 | M2 | … | | pending |

Ordering rules used: setup and CI first; then the highest-priority must-have as a thin end-to-end slice; infrastructure only when a feature needs it; fix tasks jump the queue.

Existing projects: no walking skeleton (scaffold, tooling and CI exist; skip T-001 below); milestones start at `M<brownfield.first_milestone>`; `existing` ACs get no tasks. In maintenance mode the whole plan is `# Plan`, `## R1 — Maintenance` and an empty `## M<n> — Maintenance` below it, filled by `/dev-kit:issue`.

## R1 — {{release title: the value journey it delivers}}
{{why the release ends here: complete journey, risk isolated (payments, auth, sensitive migration), 2–5 milestones}}

## M1 — {{milestone title}}
{{one-paragraph goal}}
- exit_check: e2e: {{test that walks the goal}}; cmd: {{command}}; acs: {{AC-n, AC-m}}

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
- contract: (optional) what other tasks consume from this one: table and columns, routes and fields, event names
- consumes: (optional) T-001 (tasks whose contract this one uses; they must also be in deps)
- dep_reasons: (optional) T-001=why it is needed; T-002=why (only for a dependency with no consumes and no common file: a generated artifact, data file or schema it reads)
- shared: (optional) yes when the task edits a file other tasks touch (registry, schema, shared config): it runs alone
- risk: medium            # low | medium | high (conventions.md §9 "Tier per task")
- complexity: medium      # low | medium | high
- uncertainty: low        # low | medium | high (new API, preview, spike)
- risk_reasons: integrates T-001; first write to the orders table
- opportunity: none       # or: downgrade-ok, parallel-safe, batchable, reuse:<module>
- tier: (optional override) speed | balanced | balanced+ | quality, only with tier_reason: why the rule is not enough

Task notes for accumulating files: a task writes its CHANGELOG entry to `changelog.d/T-xxx.md` (and setup notes to `docs/setup.d/T-xxx.md`) instead of editing `CHANGELOG.md` or `README.md`; `docs` and `release` merge the fragments. A milestone that reads a new external data source starts with a spike task that confirms the source's coverage assumption (see the PRD data ACs).

## M2 — {{milestone title}}
…
