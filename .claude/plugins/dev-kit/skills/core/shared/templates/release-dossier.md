# Release {{release}} — {{release_title}} · approval dossier ({{date}})

> Purpose: everything a person needs to approve or reject this release candidate in a few minutes. Written by `release` before `dev_state.py release-submit`; approval is the one human gate of construction (conventions.md §19). Facts only, from `.dev/` and the audit; no secret, token or personal data.

## Summary
2–4 sentences in user language: the value journey this release delivers and who can now do what.

## Delivered against the PRD
| AC | Story | Status | Evidence |
|---|---|---|---|
| AC-n | … | complete / partial / existing-verified | test, screen or report path |

Must-have ACs not complete: none (otherwise the release is not submitted).

## Milestones
| Milestone | Gate | Score | Rounds | Exit check | Report |
|---|---|---|---|---|---|
| M1 | passed | 91 | 1 | e2e: signup.spec · pass | .dev/qa/M1/report.md |

The exit check of each milestone with its result comes from `.dev/qa/<M>/scores.json` → `exit`; the hard floor (tests, lint, type-check, dependencies, secrets, a11y) and the CI run come from `dev_state.py status --json` → `milestones.<M>.hard_floor` and `.ci`.

## Confirmations
PRD and plan versions the user confirmed before building (`status --json` → `checkpoints`): who, when, the version, and any changes asked on the way.

## Try it
Preview / staging link or local run command (from the local preview of conventions.md §11 when there is one), and the screenshots or videos of the main flows (`.dev/qa/ux/` or the release audit), each with the flow it shows.

## Quality and security
Release audit overall score vs cut-off and every dimension (`.dev/qa/release/scores.json`), security findings left (none blocking), dependency and licence notes, test suite result, smoke results.

## Facts verified in this release
The facts `dev_state.py fact list --json` recorded since the last release (K-id, the fact, its evidence), and the ones struck through as contradicted. "None" when there are none.

## Risks and known limitations
Open questions, medium/low findings deferred, decisions taken autonomously in this release (ADR ids) the reviewer should look at, and what the production deploy will change (migrations, new env vars by name).

## Decision
Approve: production deploy, production smoke checks, then the release is recorded.
Reject: write what must change, one item per line; each item becomes a fix task of the fixes milestone `{{release}} · Fixes <n>` (`M<k>.<n>`, after the release's last milestone).
