---
name: release
description: Release checklist and execution - verifies all milestone gates and the usability audit passed, runs the full suite, security secrets check and build, bumps the version, finalises CHANGELOG and release notes, tags the release, and marks the project phase done. Use when the user wants to ship or cut a version.
argument-hint: "[version e.g. 1.0.0 | --dry-run | --hotfix]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# release

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `SC` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_score.py"`.

## Checklist (stop at the first failure and say what is missing)
Log `skill_start`/`skill_end` and agent events (`conventions.md` §13); give each auditor a `Slot: N` and the isolation line, and run `DS cleanup` after them.
1. All tasks `done` (or `dropped` by a replan); every milestone gate `passed` (with its score) or `skipped`/forced with an ADR; reviews `prd`, `design` (UI products), `plan`, `ux` (UI products) and `docs` are `pass` in `DS status --json` → `reviews` (run `review`/`usability` for any missing). Working tree clean outside `.dev/` (`git status --short -- . ':(exclude).dev'`).
2. Run the full test suite, lint and type-check; run the build command from `architecture.md`.
3. Secrets hygiene: run the detection commands in `${CLAUDE_SKILL_DIR}/../core/shared/checklists/security-secrets.md`; `.env.example` complete.
4. Release audit with score: spawn in parallel `spec-tracer`, `security-auditor`, `ops-reviewer`, `deps-auditor`, `data-reviewer` (if there is a database), `performance-auditor` and `docs-reviewer`, all with scope `release` (existing projects: also `Baseline: <brownfield.baseline_ref>`, so they audit only `git diff <baseline_ref>..HEAD` and mark untouched legacy problems `"legacy": true`). This audit is the full sweep of `conventions.md` §18: no ledger reuse (every `ledger plan` with `--no-cache`, no `Files to review:` list, no carried result; the shared baseline is built fresh on the release commit). Pass `model` and `effort` in every Agent call (`conventions.md` §9) and give each `Output file: .dev/qa/release/raw/<agent>.json`; run `SC check --fix` on those files (missing or invalid → as in `qa` §3.1), then score with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_score.py" score --scope release --kind gate --root . --out .dev/qa/release/scores.json .dev/qa/release/raw/*.json`. Require exit 0 (no blocking findings, every dimension and the overall score at or above the cut-offs); every must-have AC must be `complete`. Legacy findings (`scores.json` → `legacy`) become issues as in `qa` §4, never fix tasks. On failure consolidate the findings into `.dev/qa/release/findings.json` and create the fix tasks with `DS fix-tasks --from .dev/qa/release/findings.json --milestone <last milestone> --source qa/release/report.md`; under `autopilot` return to `implement` and re-run `release` (rounds as in `qa`); otherwise stop and tell the user to run `implement` then `release` again.
5. Docs: README, CHANGELOG present and no fragment left in `changelog.d/` or `docs/setup.d/` (run `docs` first if not; it merges them); open questions reviewed — list the still-open ones in the release notes as known limitations.
6. Version: from the argument or next semver per brief (breaking → major, features → minor, fixes → patch). Update version files (package.json / pyproject / Cargo.toml …), CHANGELOG heading with date, and write `.dev/release-notes-<version>.md` from `${CLAUDE_SKILL_DIR}/../core/shared/templates/release-notes.md`.
7. Commit `chore(release): v<version>` and tag `v<version>` (annotated). Push and publish only if `autonomy.may_push` is true and the brief's block 9 asked for it; deploying anywhere public is `public_exposure` → ask first unless already authorised in the brief or `pause_policy.public_exposure` preauthorizes that target; `park` → stop after tagging and list the deploy as pending.
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
8. If `autonomy.production.when` is `on_release`, run `deploy` for the tagged commit (it asks or parks per `pause_policy.production_deploy`). If a local preview is running (`conventions.md` §11), replace it with the released version when `local_deploy.mode` is `keep_running`, otherwise stop it. `DS set phase done`. Report: version, tag, release score vs cut-off, scores of every gate and review, verification summary, known limitations, and how to run/deploy.

`--hotfix`: patch release for a closed hotfix (`conventions.md` §15): skip step 1's all-milestones check; require the hotfix task `done`, its scoped QA passed (review `hotfix-<task>` is `pass` in `DS status --json` → `reviews`; `qa --scope <task>` records it) and the suite green; bump only the patch number; CHANGELOG entry under "Fixed" with the issue id; tag; then step 8 deploys it once (per `pause_policy.production_deploy`) when there is production. Nobody deploys the hotfix before this step.

`--dry-run`: perform steps 1–5 and report what would happen in 6–8 without changing anything.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: `/dev-kit:deploy` when production waits for it, otherwise `/dev-kit:backlog`. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16):
- Step 1: a review recorded as `n/a` counts as passed; `existing` ACs count as complete when `spec-tracer` reports them `existing-verified`. In `maintenance` mode require only that the tasks of the maintenance milestones are done and their gates passed.
- Step 6: the current version comes from the manifest named in `.dev/discovery.md` §11 and the latest tag; bump from there (never restart at 0.1.0). If manifest and tag disagree, ask which one is right. Keep the project's CHANGELOG format.
- Step 7: commit with `autonomy.commit_style` (e.g. `chore(release): 2.4.0`) and tag with the project's prefix (`v2.4.0`, `2.4.0`, `release-2.4.0`).
- Step 8: with `production.method` `external`, the project's pipeline deploys the tag; `deploy` only records it.
