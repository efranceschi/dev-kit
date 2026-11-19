# PRD — {{project_name}}

> Purpose: what we are building and how we will know it works. Derived from `brief.md` on {{date}}. Status: draft | approved.

## 1. Problem and goals
- Problem statement (from brief block 1).
- Goals for v1 and success metrics.
- Non-goals (explicitly out of scope).

## 2. Users
| Persona | Goal | Technical level | Key scenario |
|---|---|---|---|

Roles and permissions summary.

## 3. Scope (MoSCoW)
| Priority | Feature | Notes |
|---|---|---|
| Must | | |
| Should | | |
| Could | | |
| Won't | | |

## 4. User stories and acceptance criteria
Group by epic. Every story has at least one AC; ACs are globally numbered and testable (Given/When/Then or a measurable statement).

### Epic: {{epic}}
**US-1 — As a {{persona}}, I want {{goal}} so that {{benefit}}.**
- AC-1: Given … when … then …
- AC-2: …

## 5. Non-functional requirements
| Area | Requirement | Source |
|---|---|---|
| Performance | | brief block 8 |
| Security & privacy | | brief blocks 4, 8 |
| Accessibility | | brief block 7 |
| i18n / locales | | brief block 2 |
| Reliability / observability | | brief block 8 |

## 6. Constraints and dependencies
Stack constraints, external services, credentials needed (names only), deadlines.

## 7. Risks and mitigations
| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|

## 8. Assumptions made (auto decisions)
List each assumption with its ADR id; anything the user should double-check also appears in `open-questions.md`.

## 9. Traceability
AC → milestone/task mapping is maintained in `plan.md`; `spec-tracer` verifies AC → test → code.
