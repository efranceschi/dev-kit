# Decisions — {{project_name}}

> Purpose: append-only log of architecture and product decisions, including those taken autonomously. Newest at the bottom. Status per entry.

Format for each entry:

```markdown
### ADR-001 — Short title
- date: YYYY-MM-DD · status: accepted | superseded by ADR-00n · source: interview | user | auto | policy | discovered | imported (decided by `pause_policy`, conventions §10)
- category: library_choice | file_structure | naming | test_strategy | ui_details | data_model_details | minor_scope_tradeoffs | dev_tooling | paid_services | delete_data | public_exposure | scope_change_major | security_model_change | credentials | model_escalation
- context: why a decision was needed, which brief/PRD item it relates to
- decision: what was decided
- alternatives: options considered and why rejected (one line each)
- consequences: what this implies for tasks, tests, docs
- link: path of the original document (only for `source: imported`; its content is never copied)
```

`(auto)` in the title marks decisions taken without asking, per the autonomy policy. Users can review them with `interview --gaps` or by reading this file.

---

### ADR-001 — {{first decision}}
- date: {{date}} · status: accepted · source: interview
- category:
- context:
- decision:
- alternatives:
- consequences:
