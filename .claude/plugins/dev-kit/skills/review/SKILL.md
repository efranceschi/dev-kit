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
Log `skill_start`/`skill_end` (with `--set scope=<target>`, so the run is graded in the target's stage), `agent_spawn`/`agent_end` and `pause` events as `conventions.md` §13 says.
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` (§7 scoring) and check the artifact exists; if not, run its producing skill first. Then run `DS stale`: if the target or anything upstream of it is stale (e.g. `plan` after a PRD change, or `architecture` that the plan reads), bring those artifacts up to date **first**, in the order `stale` lists them, with the producing skill it names; when a change upstream does not affect an artifact, record that with `DS artifact mark <artifact> --note "no impact: <why>"` instead. Never spend a review round on an artifact that is out of date with its sources: its findings would be about the gap, and they come back in every later round.
2. Spawn the reviewer agent with the target, the language for prose and, for `plan`/`prd`, the mode. Do not pass your opinion of the artifact. Always pass `model` and `effort` in the Agent call: round 1 is the agent's tier row 1 (`conventions.md` §9; the host may ignore the frontmatter); from round 2 use the next ladder row after the consent required by `autonomy.model_policy.mode`. Give it `Output file: .dev/reviews/<target>/raw/<auditor>.json` (inside `round-<n>/` when `rounds > 0`; create the folders). Copy the artifact's files as they are now to `.dev/reviews/<target>/snapshots/round-<n>/` (keeping their paths under `.dev/`). **From round 2** run `DS ledger sections --target <target> --context <the reviewer's checklist; for plan also .dev/prd.md,.dev/architecture.md and the design files> --seed <target>-r<n> --json` (`conventions.md` §18) and give the reviewer `Sections to review:` with its list (file, section, lines, why: changed, cites a changed id, had findings, spot check) and the previous findings; as a fallback (no ledger records yet) write `diff -u` between the previous round's snapshot and the current files to `.dev/reviews/<target>/snapshots/round-<n>.diff` and give `Changes since round <n-1>: <that path>`. With either, the reviewer it verifies those, reviews the changed text and what it affects, and marks new findings `in_change` and `contradicts` (`auditor-output-contract.md`, document reviews in delta mode). It does not re-read the whole document.
3. Validate the file the reviewer wrote, then record the sections it judged: `DS ledger record-sections --target <target> --context <same> --findings-from <raw file>` (sections with a finding are recorded as `findings` and are reviewed again next round).
3a. Validate: `SC check --fix <file>`. Missing or still invalid → send the reviewer the `check` output once and check again (a reviewer that answered with the JSON in its message gets it written verbatim to the file by you). Do not read the file into the conversation (`conventions.md` §17).
4. Score: `SC score --scope <target> --kind review --root . --round <n> --out .dev/reviews/<target>/scores.json <raw files>`; exit 0 means pass. Save the findings (with `auditor`) as `.dev/reviews/<target>/findings-round-<n>.json`; legacy findings (existing projects) are left out of it and listed in the report as "Pre-existing (not scored)". From round 2 the reviewer receives the previous findings to mark `closed`/`open` and you add `--previous .dev/reviews/<target>/findings-round-<n-1>.json` (`conventions.md` §7 delta mode): the revision is judged on what it fixed; new lows and new findings outside the changed text (below critical) are deferred, so a long document is not failed again by a fresh layer of nits. The score prints `convergence` (blocking findings, mediums now versus the previous round) and any `conflicts` (a finding that reverses an earlier recommendation): settle each conflict with an ADR choosing one side, and do not apply a reversal just because a reviewer asked for it.
5. Write `.dev/reviews/<target>/report.md` (template `${CLAUDE_SKILL_DIR}/../core/shared/templates/qa-report.md`, user's language): scores, blocking findings, what to change, trend versus the previous round.
6. **Pass**: `DS review <target> pass --score <overall> --count-run`. Report and stop.
7. **Fail**: `DS review <target> fail --score <overall> --count-run`, then revise the artifact: invoke the producing skill (table above) with the findings as the change request (it must apply every blocking finding and the medium findings that are cheap), or edit the artifact directly for small fixes. Prefer fixing the artifact over arguing with the reviewer; when a finding is wrong, write an ADR (`source: auto`) explaining why it is not applied and mark it `accepted risk` in the report. Before the next round, run `${CLAUDE_SKILL_DIR}/../core/shared/prompts/self-check.md` on the revised artifact (it closes the cross-document gaps the reviewer would find next) and `DS artifact mark <artifact>`. Then repeat from step 2 with a fresh reviewer.
8. **Convergence and rounds limit**: a review has at most `autonomy.max_review_rounds` rounds (default 3; gates use `max_fix_rounds_per_gate`). Stop revising early when `convergence.converged` is true for two rounds in a row (no critical/high open, mediums falling or flat): the remaining mediums are not worth another full round. In both cases apply `pause_policy.rounds_exhausted` (`conventions.md` §10; a policy acceptance uses `--force --note "policy:rounds_exhausted"`, which `dev_state.py` refuses while a critical/high is open). The §9 recommendation for a converged review is to accept it and record each remaining medium as a question (`DS add-question`) or as an item for the next revision; with `ask`, ask the user with that option first, then keep revising or revisit the brief with `interview --gaps`.
9. A revision that changes scope or an AC makes later artifacts stale; `DS stale` lists them, and step 1 of their next review brings them up to date before any reviewer runs.

`all`: run the targets that do not depend on each other at the same time (e.g. `prd` and `design` when neither is stale), then `plan`, which reads both.

## Rules
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
- The reviewer never edits; only you or the producing skill do.
- Never mark a review passed by hand; the score comes from `dev_score.py` and `DS review` enforces the cut-off.
- Keep reports short: lead with the verdict and score, then the blocking items.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the next stage, e.g. `/dev-kit:architecture` after `prd` passes. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)
When state has `brownfield` (`conventions.md` §16): a target that does not apply (e.g. `design` when no `new` AC touches the UI; `prd`/`plan` in `maintenance` mode) is recorded as `DS review <target> n/a --note "<reason>"` instead of spawning a reviewer. Tell the reviewer the project is brownfield (`Baseline: <brownfield.baseline_ref>`) so it judges only `new`/`changed` content against the as-built baseline, and so pre-existing problems are marked `"legacy": true`.
