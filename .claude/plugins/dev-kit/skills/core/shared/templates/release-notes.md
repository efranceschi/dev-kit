# Release {{version}} — {{project_name}} ({{date}})

> Purpose: what ships, how it was verified, how to run it. Derived from `plan.md`, git log since {{previous_tag}}, QA reports.

## Highlights
3–6 bullets in user language, grouped by epic.

## Changes
### Features
- [T-00x] … (AC-n)
### Fixes
- [T-00y] …
### Chores / docs
- …

## Quality
| Gate | Status | Report |
|---|---|---|
| M1 | passed | .dev/qa/M1/report.md |
| Usability | passed | .dev/qa/ux/report.md |

Tests: {{passed}}/{{total}} · Known issues: see `open-questions.md` and medium/low findings.

## Upgrade / run
Prerequisites, env vars (names only), migrations to run, commands to start.

## Decisions worth knowing
Links to ADRs taken autonomously during this release that the user should review.
