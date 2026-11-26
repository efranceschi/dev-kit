# Autonomy policy

Stored in `.dev/state.json` under `autonomy`. Set by `interview` (block 9); changeable with `dev_state.py set autonomy.level <level>`.

```json
{
  "level": "high",
  "decide_alone": ["library_choice", "file_structure", "naming", "test_strategy", "ui_details", "minor_scope_tradeoffs", "dev_tooling", "data_model_details"],
  "always_ask": ["paid_services", "delete_data", "public_exposure", "scope_change_major", "security_model_change", "credentials", "model_escalation"],
  "max_fix_rounds_per_gate": 3,
  "max_review_rounds": 3,
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
    "low_cap": 10
  },
  "model_policy": {"mode": "ask", "tiers": {}},
  "pause_policy": {},
  "presence": {"step": "supervised", "overrides": {}},
  "on_park": "stop_when_idle",
  "issue_buffer_pct": 20,
  "cooldown": {"enabled": false, "max_tasks": 5},
  "local_deploy": {"mode": "off", "port": null, "notify": false},
  "production": {"when": "none", "method": null, "host": null, "targets": [], "smoke": [], "prerequisites": []},
  "tips": "on",
  "task_checks": "ui",
  "verify": {"full_suite": "per_batch", "batch_size": 4}
}
```

`commit_style` is added when the project has its own (existing projects, `conventions.md` §5). Nested fields can be changed one at a time, e.g. `dev_state.py set autonomy.quality.min_overall 90` (the object is merged and validated).

## Quality cut-offs (`autonomy.quality`)

Agents give findings; `dev_score.py` turns them into 0–100 scores per dimension and an overall score (see `shared/conventions.md` §7). A milestone gate or a pre-implementation review passes only if no blocking finding is open, every dimension meets its minimum and the overall score meets the cut-off.

| level | min_overall | review_min_overall | min_dimension | security | tests | spec | a11y |
|---|---|---|---|---|---|---|---|
| `cautious` | 90 | 85 | 75 | 95 | 85 | 90 | 85 |
| `balanced` | 85 | 80 | 70 | 90 | 80 | 85 | 80 |
| `high` (default) | 85 | 80 | 70 | 90 | 80 | 85 | 80 |

`dev_state.py set autonomy.level <level>` applies the row (it only raises numbers, never lowers what the user chose). The interview (block 8) can override any of these (e.g. "quality bar: premium → overall 92"). Autonomy level and quality bar are independent: `high` autonomy does not lower the bar. Weights live in `dev_state.py` defaults and can be overridden in `autonomy.quality.weights`.

## Levels (presets)

| level | decide_alone | always_ask | typical use |
|---|---|---|---|
| `high` (default) | everything not in always_ask | paid_services, delete_data, public_exposure, scope_change_major, security_model_change, credentials, model_escalation (unless `model_policy.mode` is `preapproved`) | long autonomous runs after a thorough interview |
| `balanced` | library_choice, file_structure, naming, test_strategy, dev_tooling | high list + ui_details, data_model_details, minor_scope_tradeoffs | user wants to review design-level choices |
| `cautious` | naming, file_structure | everything else | first time using the kit, or regulated domains |

Setting a level replaces `decide_alone` and `always_ask` with its preset; it leaves the presence step and its exceptions as they are. In an existing project `dev_tooling` is always in `always_ask` and `pause_policy.dirty_tree` stays `ask` (`conventions.md` §16).

`unattended` is no longer a level: since 3.17 `set autonomy.level unattended` means level `high` plus the presence step `unattended`, and a state that had it is migrated so.

## Presence steps (`autonomy.presence`)

How much of a run the user follows, independent of the level (`conventions.md` §10 has the full matrix):

| step | operational points (dirty tree, rounds used up, CI timeout, blocked environment, model escalation) | product and external points (scope, security model, paid services, credentials, deleting data, exposure, production) | typical use |
|---|---|---|---|
| `supervised` | ask | ask | following a first project closely |
| `assisted` (recommended) | decided alone, with an ADR | ask | most projects: you are asked only what is yours to decide |
| `milestone` | decided alone | parked, asked together at the end of each milestone | a few check-ins a day |
| `unattended` | decided alone | parked (security model: recommendation applied; data: deleted in dev and test only) | runs nobody watches |

`{"step": "assisted", "overrides": {"security_model_change": {"action": "ask"}}}`: the exceptions win over the step. The release approval, the PRD and plan confirmations and the floors stay with the user at every step.
