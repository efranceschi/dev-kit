# QA report — {{scope}} ({{date}})

> Purpose: consolidated result of the quality gate. Auditors: {{auditors}}. Verdict: **{{pass|fail}}**. Gate status after this run: {{passed|pending}}.

## Quality score
| Dimension | Score | Minimum | Auditor | Blocking findings |
|---|---|---|---|---|

Overall: **{{overall}}** / cut-off {{cutoff}} → {{PASS|FAIL}}. Reasons if failed: {{reasons from scores.json}}. Previous run: {{score or n/a}} (trend {{up|down|same}}).

Round {{n}} (delta mode from round 2): closed {{n}} · still open {{n}} · new {{n}} · deferred lows {{n}}.

## Summary
| Auditor | Verdict | critical | high | medium | low |
|---|---|---|---|---|---|
| code-reviewer | | | | | |
| security-auditor | | | | | |
| test-auditor | | | | | |
| spec-tracer | | | | | |

Tests: {{passed}}/{{total}} passing · Coverage: {{coverage or n/a}} · Lint: {{clean|n issues}} · Test baseline (existing projects): {{failures already failing at the baseline, from qa/baseline.md}}

Auditors skipped: {{auditor — reason}}.

## Blocking findings (critical / high)
| id | severity | title | file:line | AC | fix task |
|---|---|---|---|---|---|

## Non-blocking findings (medium / low)
| id | severity | title | file:line | action |
|---|---|---|---|---|

## Contested
Critical/high findings another role or model disputed with evidence (`findings.json` → `disputed`): not scored, no fix task, counted toward the deferred debt cap. A disputed critical security finding stays under Blocking and waits for the user's answer.
| id | severity | title | file:line | auditor's evidence | challenger and evidence |
|---|---|---|---|---|---|

## Deferred findings
New lows of this round and mediums not turned into tasks; promote with `/dev-kit:issue --from <F-id> {{scope}}`.

## Pre-existing (not scored) — existing projects only
| id | severity | title | file:line | issue |
|---|---|---|---|---|

## Local deploy
Mode {{off|smoke|keep_running}} · {{URL, install path or command}} · result {{ok|failed}} · how to stop it.

## Acceptance traceability (from spec-tracer)
| AC | tasks | tests | status (complete · partial · untested · missing · existing-verified) |
|---|---|---|---|

## Decisions taken during this gate
ADRs created (auto) while triaging, e.g. deferring a medium finding.

## Next steps
Fix tasks created: … · Re-run gate with `/dev-kit:qa {{milestone}}` after fixes.

Raw findings: `findings.json` in this folder.
