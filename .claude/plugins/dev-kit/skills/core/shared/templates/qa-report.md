# QA report — {{scope}} ({{date}})

> Purpose: consolidated result of the quality gate. Auditors: {{auditors}}. Verdict: **{{pass|fail}}**. Gate status after this run: {{passed|pending}}.

## Quality score
| Dimension | Score | Minimum | Auditor | Blocking findings |
|---|---|---|---|---|

Overall: **{{overall}}** / cut-off {{cutoff}} → {{PASS|FAIL}}. Reasons if failed: {{reasons from scores.json}}. Previous run: {{score or n/a}} (trend {{up|down|same}}).

## Summary
| Auditor | Verdict | critical | high | medium | low |
|---|---|---|---|---|---|
| code-reviewer | | | | | |
| security-auditor | | | | | |
| test-auditor | | | | | |
| spec-tracer | | | | | |

Tests: {{passed}}/{{total}} passing · Coverage: {{coverage or n/a}} · Lint: {{clean|n issues}}

## Blocking findings (critical / high)
| id | severity | title | file:line | AC | fix task |
|---|---|---|---|---|---|

## Non-blocking findings (medium / low)
| id | severity | title | file:line | action |
|---|---|---|---|---|

## Acceptance traceability (from spec-tracer)
| AC | tasks | tests | status |
|---|---|---|---|

## Decisions taken during this gate
ADRs created (auto) while triaging, e.g. deferring a medium finding.

## Next steps
Fix tasks created: … · Re-run gate with `/dev-kit:qa {{milestone}}` after fixes.

Raw findings: `findings.json` in this folder.
