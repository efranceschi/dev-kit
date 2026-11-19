# Autonomy policy

Stored in `.dev/state.json` under `autonomy`. Set by `interview` (block 9); changeable with `dev_state.py set autonomy.level <level>`.

```json
{
  "level": "high",
  "decide_alone": ["library_choice", "file_structure", "naming", "test_strategy", "ui_details", "minor_scope_tradeoffs", "dev_tooling", "data_model_details"],
  "always_ask": ["paid_services", "delete_data", "public_exposure", "scope_change_major", "security_model_change", "credentials", "model_escalation"],
  "max_fix_rounds_per_gate": 3,
  "task_time_budget_min": 30,
  "commit_per_task": true,
  "may_install_deps": true,
  "may_run_servers": true,
  "may_push": false,
  "quality": {
    "min_overall": 85,
    "min_dimension": 70,
    "dimension_min": {"security": 90, "tests": 80, "spec": 85, "a11y": 80},
    "review_min_overall": 80,
    "block_on": ["critical", "high"]
  }
}
```

## Quality cut-offs (`autonomy.quality`)

Agents give findings; `dev_score.py` turns them into 0–100 scores per dimension and an overall score (see `shared/conventions.md` §7). A milestone gate or a pre-implementation review passes only if no blocking finding is open, every dimension meets its minimum and the overall score meets the cut-off.

| level | min_overall | review_min_overall | min_dimension | security | tests | spec | a11y |
|---|---|---|---|---|---|---|---|
| `cautious` | 90 | 85 | 75 | 95 | 85 | 90 | 85 |
| `balanced` | 85 | 80 | 70 | 90 | 80 | 85 | 80 |
| `high` (default) | 85 | 80 | 70 | 90 | 80 | 85 | 80 |

The interview (block 8) can override any of these (e.g. "quality bar: premium → overall 92"). Autonomy level and quality bar are independent: `high` autonomy does not lower the bar. Weights live in `dev_state.py` defaults and can be overridden in `autonomy.quality.weights`.

## Levels (presets)

| level | decide_alone | always_ask | typical use |
|---|---|---|---|
| `high` (default) | everything not in always_ask | paid_services, delete_data, public_exposure, scope_change_major, security_model_change, credentials, model_escalation (unless `model_policy.mode` is `preapproved`) | long autonomous runs after a thorough interview |
| `balanced` | library_choice, file_structure, naming, test_strategy, dev_tooling | high list + ui_details, data_model_details, minor_scope_tradeoffs | user wants to review design-level choices |
| `cautious` | naming, file_structure | everything else | first time using the kit, or regulated domains |
| `unattended` | as `high` | as `high`, but each pause point follows `pause_policy` (recommended values in `conventions.md` §10) and `model_policy` is `preapproved`: the run never waits, parked items are reported at the end | long runs without the user present |

`always_ask` says which decisions the agent cannot take on its own judgment; `pause_policy` says what happens when one comes up (`ask`, `preauthorize` within a recorded limit, `auto_recommend`, `park`). The floors in `conventions.md` §10 are enforced by `dev_state.py` and cannot be lifted by the interview.

## Decision categories

| category | examples |
|---|---|
| `library_choice` | which validation/ORM/HTTP/testing library within the chosen stack |
| `file_structure` | folder layout, module boundaries |
| `naming` | identifiers, routes, table names |
| `test_strategy` | which layers to test for a task, test doubles |
| `ui_details` | spacing, component variants, empty-state copy, icon choice |
| `data_model_details` | nullable fields, indexes, enum values not fixed by the PRD |
| `minor_scope_tradeoffs` | deferring a nice-to-have, simplifying an interaction without removing an AC |
| `dev_tooling` | linter config, formatter, CI steps, scripts |
| `paid_services` | signing up for or enabling anything billable |
| `delete_data` | destructive migrations, dropping tables, deleting user files |
| `public_exposure` | deploying publicly, opening ports, publishing packages, pushing to remote |
| `scope_change_major` | adding/removing/altering an AC, changing a must-have |
| `security_model_change` | auth mechanism, permission model, token lifetime, encryption choices |
| `credentials` | anything requiring a secret the user has not provided |

## Procedure when a gap appears

1. Look it up: `brief.md` → `prd.md` → `architecture.md` → `decisions.md`. If answered, use it.
2. Classify. If in `always_ask`: apply `pause_policy.<category>` (`conventions.md` §10). Only for `ask` (the default): stop, ask with AskUserQuestion (recommended option first), record as `ADR-nnn` with `source: user`. Otherwise record `source: policy`.
3. Else: choose the most probable option given the brief, write `ADR-nnn (auto)` in `decisions.md` (context, decision, alternatives, why), and continue. If the user may plausibly disagree, also run `dev_state.py add-question "<question>" --skill <skill>` so `interview --gaps` can surface it later.
4. In `autopilot`, batch `always_ask` questions when possible: finish everything that does not depend on the answer, then ask once with all pending questions.

## ADR format (`shared/templates/adr.md`)

```markdown
### ADR-007 (auto) — Use Zod for request validation
- date: 2026-10-30 · status: accepted · source: auto | user | interview | policy
- context: brief block 5 says TypeScript + Next.js; no validation lib chosen
- decision: Zod, shared schemas between client and server
- alternatives: Yup (less TS inference), class-validator (decorators, heavier)
- consequences: schemas live in `src/schemas/`; AC-3, AC-4 validation tests target them
```
