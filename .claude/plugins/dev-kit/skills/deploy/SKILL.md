---
name: deploy
description: Production deploy of an approved milestone or release - preflight (gate passed, clean tree, operational prerequisites present), backup, dry-run, install, migrations and smoke checks using the method recorded in the interview and architecture.md, then records what is deployed so status shows how far production is behind the checkout. Use after a milestone gate passes when the brief deploys per milestone, at release, or when the user asks to deploy or to check whether production is up to date.
argument-hint: "[M3 | --check | --dry-run]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# deploy

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: the latest milestone whose gate passed)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §10 and §12, `autonomy.production` from `DS status --json`, and `.dev/architecture.md` §7 (install, migrate, rollback commands, smoke checks, prerequisites). Log `DS event skill_start --set skill=deploy --set args_kind=milestone` (`conventions.md` §13). If `production.when` is `none` or there is no install command, say so and stop: there is nothing to deploy.
2. `--check`: run `DS status --head-migration <current migration head>` (read the head from the migrations folder or the migration tool), report the `Production:` line (deployed commit, milestone, migrations and milestones behind) and stop.
3. **Consent:** apply `pause_policy.production_deploy`: `ask` → AskUserQuestion with the recommended option first (deploy now / later), saying what changes (milestones, migrations); `preauthorize` → only for a target listed in `limit.targets`, otherwise treat as `park`; `park` → record the pending deploy with `DS add-question`, log `pause`, stop.
4. **Preflight:** the milestone gate is `passed` (or the release is tagged); the working tree is clean; every item in `production.prerequisites` is present (env var names set on the target, files present, keys provided). A missing prerequisite → apply `pause_policy.credentials` (park or ask) and stop; never deploy with a missing one.
5. **Backup**, when the method supports it (database dump, copy of the current release), into the location from `architecture.md` §7. **Dry-run**, when the install script supports it; stop on any error.
6. **Install and migrate** from the commit being deployed (`git rev-parse HEAD`, or the milestone's last commit), with the commands from `architecture.md` §7. Remote hosts are reached only as recorded in the brief; never invent credentials.
7. **Smoke checks:** every item in `production.smoke` (e.g. `/health`, the main routes or a CLI command) must succeed.
8. **Record:** `DS deploy production --sha <sha> --milestone <M> --migration <head> --status ok`. On failure: run the rollback command if the failure left the service down, record `--status failed` (or `rolled_back`), log `error`, create a fix task (`DS add-task --type fix --milestone <M> --title "Deploy failed: <step>" --acceptance "deploy of <M> passes smoke checks"`), and stop.
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
9. Log `skill_end` with `status` and a short `feedback` on the kit. Report: what was deployed (milestone, commit, migrations), smoke results, the `Production:` line, and how to roll back.

## Rules
- Never deploy a milestone whose gate is not passed, from a dirty tree, or with production credentials pasted into the conversation.
- Never skip the backup when the method supports one.
- Production data is never deleted by this skill (`conventions.md` §10 floors).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): if `autonomy.production` is empty, propose it from `.dev/discovery.md` §10 and confirm with the user before the first deploy. With `production.method` `external` (the project's CI/CD deploys), steps 5–7 are replaced by: tell the user which commit or tag the pipeline must deploy (or read the pipeline status with `gh run list` when available), wait for their confirmation of success, then record it in step 8. Never run install or migration commands that the project's pipeline owns.
