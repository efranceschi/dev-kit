---
name: deploy
description: Production deploy of an approved milestone or release - preflight (gate passed, clean tree, operational prerequisites present), backup, dry-run, install, migrations and smoke checks using the method recorded in the interview and architecture.md, then records what is deployed so status shows how far production is behind the checkout. Use after a milestone gate passes when the brief deploys per milestone, at release, or when the user asks to deploy or to check whether production is up to date.
argument-hint: "[M3 | --check | --dry-run | --health | --rollback R2]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# deploy

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: the latest milestone whose gate passed)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §10 and §12, `autonomy.production` from `DS status --json`, and `.dev/architecture.md` §7 (install, migrate, rollback commands, smoke checks, prerequisites). Log `DS event skill_start --set skill=deploy --set args_kind=milestone` (`conventions.md` §13). If `production.when` is `none` or there is no install command, say so and stop: there is nothing to deploy.
2. `--dry-run`: run steps 1 and 4 and the method's own dry-run from step 5 (no backup), report what would be installed and migrated, and stop; nothing is recorded and no consent is needed.
2a. `--health`: run `DS prod-check` (the check in `autonomy.production.health`; none set → propose one from `production.smoke` and `architecture.md` §7, a command or an `https://` URL, confirm it with the user and store it with `DS set autonomy.production.health '{"command": "...", "interval_min": 15}'`). Report the result; a failure has opened or updated an `expedite` issue (`conventions.md` §12): offer its hotfix (`/dev-kit:issue I-nnn`). The board runs the check while it is open; for the rest of the time, offer (recommended, never without a yes) a scheduled task that runs `python3 -I <kit>/scripts/dev_state.py --root <project> prod-check --due` every `interval_min` (a cron line, or a Claude Code scheduled task when the session has one). Stop.
2b. `--rollback R<n>` (release flags on, `conventions.md` §12): turn `release_R<n>` off in production with the mechanism of `architecture.md` §7 (consent as in step 4), run the smoke checks, record `DS flag set release_R<n> off --rollback --note "<why>"`, and open an issue for the cause (`/dev-kit:issue`). No redeploy. Stop.
3. `--check`: run `DS status --head-migration <current migration head>` (read the head from the migrations folder or the migration tool), report the `Production:` line (deployed commit, milestone, migrations and milestones behind) and stop.
4. **Consent:** apply `pause_policy.production_deploy`: `ask` → AskUserQuestion with the recommended option first (deploy now / later), saying what changes (milestones, migrations); `preauthorize` → only for a target listed in `limit.targets`, otherwise treat as `park`; `park` → record the pending deploy with `DS add-question`, log `pause`, stop.
5. **Preflight:** the milestone gate is `passed`, or the commit is a release tag (including a `release --hotfix` tag, whose scoped QA is review `hotfix-<task>` `pass`); the working tree is clean outside `.dev/`; every item in `production.prerequisites` is present (env var names set on the target, files present, keys provided). A missing prerequisite → apply `pause_policy.credentials` (park or ask) and stop; never deploy with a missing one.
6. **Backup**, when the method supports it (database dump, copy of the current release), into the location from `architecture.md` §7. **Dry-run**, when the install script supports it; stop on any error.
7. **Install and migrate** from the commit being deployed (`git rev-parse HEAD`, or the milestone's last commit), with the commands from `architecture.md` §7. Remote hosts are reached only as recorded in the brief; never invent credentials.
8. **Smoke checks:** every item in `production.smoke` (e.g. `/health`, the main routes or a CLI command) must succeed.
9. **Record:** `DS deploy production --sha <sha> --milestone <M> --migration <head> --status ok` (with `production.when` `per_milestone_flagged`, the milestone's code goes out with its release's flag off: check the flag is off in production before the smoke checks; the record shows it). On failure: run the rollback command if the failure left the service down, record `--status failed` (or `rolled_back`), log `error`, create a fix task (`DS add-task --type fix --milestone <M> --title "Deploy failed: <step>" --acceptance "deploy of <M> passes smoke checks"`), and stop.
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
10. Log `skill_end` with `status` and a short `feedback` on the kit. Report: what was deployed (milestone, commit, migrations), smoke results, the `Production:` line, and how to roll back.

## Rules
- One production deploy per approved gate: never deploy during a fix round to "check" a fix (that is what the local preview and the smoke check of `qa` are for); the only repeat deploy of a milestone is the fix of a failed deploy. `DS deploy` warns when the gate is not passed.
- Never deploy a milestone whose gate is not passed (a hotfix goes out only through `release --hotfix`), from a dirty tree, or with production credentials pasted into the conversation.
- Never skip the backup when the method supports one.
- Production data is never deleted by this skill (`conventions.md` §10 floors).

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): if `autonomy.production` is empty, propose it from `.dev/discovery.md` §10 and confirm with the user before the first deploy. With `production.method` `external` (the project's CI/CD deploys), steps 6–8 are replaced by: tell the user which commit or tag the pipeline must deploy (or read the pipeline status with `gh run list` when available), wait for their confirmation of success, then record it in step 9. Never run install or migration commands that the project's pipeline owns.
