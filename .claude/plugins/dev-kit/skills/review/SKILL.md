---
name: review
description: Independent quality review with a score and cut-off for non-code artifacts - the PRD, the UX/UI design, the implementation plan and the documentation. Spawns requirements-reviewer, design-reviewer or docs-reviewer, computes a 0-100 score with dev_score.py, sends the artifact back for revision until it clears the cut-off, and records the result in state. Use before moving from planning to implementation, after changing a spec, or to audit docs.
argument-hint: "[prd | design | plan | docs | all]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# review

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: the review that matches the current phase; `all` runs prd, design, plan in order)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `SC` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_score.py"`.

## Which reviewer for which target
| target | artifact | reviewer (Agent tool) | producing skill used for revisions |
|---|---|---|---|
| `prd` | `.dev/prd.md` vs `brief.md` | `requirements-reviewer` mode `prd` | `prd` |
| `design` | `.dev/design/ux-flows.md`, `ui-spec.md` | `design-reviewer` | `ux` / `ui` |
| `plan` | `.dev/plan.md` vs PRD, architecture, design | `requirements-reviewer` mode `plan` | `plan replan` |
| `docs` | README, docs/, CHANGELOG, CLAUDE.md | `docs-reviewer` | `docs` |

## Procedure (per target)
Log `skill_start`/`skill_end`, `agent_spawn`/`agent_end` and `pause` events as `conventions.md` §13 says.
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` (§7 scoring) and check the artifact exists; if not, run its producing skill first.
2. Spawn the reviewer agent with the target, the language for prose and, for `plan`/`prd`, the mode. Do not pass your opinion of the artifact. Round 1 uses the agent's frontmatter model/effort; from round 2 use the next ladder row (`conventions.md` §9) after the consent required by `autonomy.model_policy.mode`.
3. Save its JSON block verbatim to `.dev/reviews/<target>/raw/<auditor>.json` (create folders; one file per auditor, round-numbered folder `round-<n>/` when `rounds > 0`).
4. Score: `SC score --scope <target> --kind review --root . --round <n> --out .dev/reviews/<target>/scores.json <raw files>`; exit 0 means pass. Save the findings (with `auditor`) as `.dev/reviews/<target>/findings-round-<n>.json`. From round 2 the reviewer receives the previous findings to mark `closed`/`open` and you add `--previous .dev/reviews/<target>/findings-round-<n-1>.json` (`conventions.md` §7 delta mode): the revision is judged on what it fixed, and new nits on a long document no longer reset the score.
5. Write `.dev/reviews/<target>/report.md` (template `${CLAUDE_SKILL_DIR}/../core/shared/templates/qa-report.md`, user's language): scores, blocking findings, what to change, trend versus the previous round.
6. **Pass**: `DS review <target> pass --score <overall> --count-run`. Report and stop.
7. **Fail**: `DS review <target> fail --score <overall> --count-run`, then revise the artifact: invoke the producing skill (table above) with the findings as the change request (it must apply every blocking finding and the medium findings that are cheap), or edit the artifact directly for small fixes. Prefer fixing the artifact over arguing with the reviewer; when a finding is wrong, write an ADR (`source: auto`) explaining why it is not applied and mark it `accepted risk` in the report. Then repeat from step 2 with a fresh reviewer.
8. **Rounds limit**: after `autonomy.max_fix_rounds_per_gate` failed rounds (default 3), apply `pause_policy.rounds_exhausted` (`conventions.md` §10; a policy acceptance uses `--force --note "policy:rounds_exhausted"`). With `ask`, stop and ask the user with the recommended option first (`conventions.md` §9): keep revising, lower the cut-off for this review (ADR + `DS review <target> pass --score <n> --force`), or revisit the brief with `interview --gaps`.
9. When a revision changes scope or an AC, tell the user which later artifacts are now stale (e.g. plan after PRD) and re-run those reviews.

## Rules
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
- The reviewer never edits; only you or the producing skill do.
- Never mark a review passed by hand; the score comes from `dev_score.py` and `DS review` enforces the cut-off.
- Keep reports short: lead with the verdict and score, then the blocking items.
