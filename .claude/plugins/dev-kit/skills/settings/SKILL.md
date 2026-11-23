---
name: settings
description: Shows and changes the settings of a dev-kit project in plain language - autonomy level and pause points, quality cut-offs, model escalation, review and fix rounds, incremental reuse and spot checks, checks inside each task, issue buffer and cool-down, local preview and production deploy, tips (off, on, always, or shown again), and the Claude Code interface (spinner tips, status line, session title, desktop notifications) - validating every change against the floors and recording it. Use when the user wants to change how autonomous or strict the kit is, turn something on or off, see the current configuration, or asks "where do I configure X".
argument-hint: "[show | <what to change, in words> | tips off|on|always|reset | status line | notifications]"
allowed-tools: Read, Bash, Grep, Glob, AskUserQuestion
---

# settings

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (default: `show`)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `UI` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_ui.py" --root "${CLAUDE_PROJECT_DIR}"`.

The user never runs a script: this skill translates what they ask into the right setting, explains the effect, applies it and confirms. Log `DS event skill_start --set skill=settings --set args_kind=<show|change>` and `skill_end` (`conventions.md` §13).

## What can be changed
| the user says | setting (`DS set …`) | notes |
|---|---|---|
| "more / less autonomous", "run overnight" | `autonomy.level` (`high`, `balanced`, `cautious`, `unattended`) | a level applies its preset; show the pause points it fills (`conventions.md` §10) |
| "never ask me about X", "always ask before deploying" | `autonomy.pause_policy.<point>` as `{"action": …, "limit": …}` | actions allowed per point in §10; `preauthorize` needs its limit (spend cap or `"unlimited"` only when the user says so, environments, targets) |
| "stricter / looser gates", "premium quality" | `autonomy.quality` (`min_overall`, `review_min_overall`, `min_dimension`, `dimension_min.<dim>`) | presets `standard`, `premium`, `prototype` (`interview` block 8) |
| "use a stronger model when it fails", "never escalate" | `autonomy.model_policy.mode` (`ask`, `preapproved`, `off`), `tiers` | §9 ladder |
| "prioritise speed / cost / quality", "spend less on models" | `autonomy.model_policy.router.balance` (`balanced`, `speed`, `cost`, `quality`, or `{"cost": 1, "time": 1, "quality": 2}`) | §9 "Router": the weights of the expected cost; floors never move |
| "do not adapt the models by itself", "only suggest" | `autonomy.model_policy.router.mode` (`apply`, `suggest`, `off`); forget what it learned: `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_router.py" --root "${CLAUDE_PROJECT_DIR}" reset` | `dev_router.py explain` shows what it learned and the savings |
| "a budget per milestone" | `autonomy.model_policy.router.budget_usd_per_milestone` (US$, or `null`) | at 80% it favours cheaper arms, once spent the cheapest allowed one |
| "one model for every task", "as before 1.32" | `autonomy.model_policy.risk_tiers` (`apply`, `suggest`, `off`) with `router.mode off` | `off` + `off` = the per-agent models of 1.31 |
| "this signal is underrated (e.g. schema)" | `autonomy.model_policy.risk_weights` `{"schema": 3}` | §9 "Tier per task"; auth, external_send and schema stay ≥ 1 |
| "more fix rounds", "stop reviews sooner" | `autonomy.max_fix_rounds_per_gate`, `autonomy.max_review_rounds` | 1–10 |
| "do not reuse earlier audits", "check more of the reused work" | `autonomy.incremental.enabled`, `.spot_check_pct`, `.full_on_last_gate` | §18; reuse never closes findings, and release always audits everything |
| "check each task more / less" | `autonomy.task_checks` (`ui`, `all`, `off`) | `off` keeps the implementer's self-check |
| "room for bugs in each milestone", "cool-down" | `autonomy.issue_buffer_pct` (0–50), `autonomy.cooldown` `{"enabled", "max_tasks"}` | §15 |
| "milestones of 8 to 15 tasks", "bigger milestones" | `autonomy.milestone_size` `{"min": 5, "max": 12}`: planned tasks + buffer slots + cool-down; outside it `sync-plan` warns unless the milestone has `size_reason:` | §4 |
| "don't build ahead", "wait for my approval before the next release", "no overlap between milestones" | `autonomy.pipeline` `{"releases_ahead": 1, "milestone_overlap": true}`: how many releases may be built ahead of one waiting for approval (0 = none), and whether independent tasks of the next milestone run while the current one is in QA; both on their own branches | §19 |
| "no CI", "use GitLab", "don't wait for CI", "CI is optional" | `autonomy.ci` `{"provider": "auto", "required": true, "timeout_min": 30}` (provider auto, github, gitlab or none): with a provider and `required`, the gate needs a green CI run on the round's commit | §7 |
| "turn off the hard floor", "allow more deferred findings" | `autonomy.quality.hard_floor` `{"enabled": true}` (tests, lint, type-check, dependencies, secrets and a11y must pass whatever the score) and `autonomy.quality.deferred_cap` `{"total": 20, "medium": 10}` (0 turns a cap off) | §7 |
| "too many issues waiting", "issues that wait too long", "always leave room for one issue" | `autonomy.queue` `{"limit": 15, "limit_pct_remaining": 50, "aging_milestones": 3, "buffer_floor": 1}`: above the limit (count, or % of the remaining tasks) Needs you offers a milestone of the queue; an issue unscheduled after that many closed milestones asks for a decision; every milestone keeps at least that many issue slots | §15 |
| "keep the app running after each milestone" | `autonomy.local_deploy` `{"mode": "off|keep_running|smoke", "port", "notify"}` | §11; ports bound to 127.0.0.1 |
| "deploy to production after each milestone / at release" | `autonomy.production.when` (`per_milestone`, `on_release`, `manual`, `none`) and the rest of `production` | §12; prerequisites by name only, never values |
| "may push", "may install packages", "may start servers" | `autonomy.may_push`, `may_install_deps`, `may_run_servers` | `true` / `false` |
| "fewer tips", "show the tips again" | `autonomy.tips` (`on`, `off`, `always`); show again: `DS tips --reset` | each tip shows at most twice with `on` |
| "tips while I wait", "status line", "notify me", "session title" | `autonomy.ui` through `UI apply` / `UI remove` with `--tips`, `--statusline`, `--notify`, `--title` (not `DS set`) | `conventions.md` §15; tips and status line go to `.claude/settings.local.json`, tips from the next session; a status line of the user's own is kept |

## Procedure
1. **show** (or no argument): read `DS status --json` → `autonomy` and present it in the user's language, grouped as in the table, one line each with its effect in plain words (e.g. "gates pass at 85, security at 90"); list the floors that no setting can lift (`conventions.md` §10). Add the Claude Code interface from `UI status` (spinner tips, status line, session title, notifications). Offer the three changes people make most (level, quality bar, tips) without asking.
2. **change**: map the request to one row of the table. If it is ambiguous or has options with different costs, ask once with AskUserQuestion, recommended option first with one line of reason (`conventions.md` §9 recommendation rule). Never change a setting the user did not ask about.
3. Claude Code interface rows: `UI status` shows what is on; `UI apply --tips` needs the tips in the user's language: translate the texts of `UI tips` (commands and file names stay as they are), write them as a JSON array of strings to `.dev/tmp/spinner-tips.json` and pass `--tips-file .dev/tmp/spinner-tips.json`. Relay what `UI` prints (for example, that the project already has its own status line, which is left alone). Every other row: apply it with `DS set <key> <value>` (JSON objects as one quoted argument; nested keys merge, e.g. `DS set autonomy.incremental.spot_check_pct 20`). `dev_state.py` validates and refuses anything outside the floors; relay its message in plain words and offer the closest allowed value.
4. A change that alters the autonomy or the bar (level, pause policy, quality, model policy, production) is a decision: append an ADR to `.dev/decisions.md` (`source: user`, the old and new value, why).
5. Confirm in one or two lines what changed and when it takes effect (the next skill run; a gate already passed is not re-judged). End with one tip from `DS tip settings` on its own line, if any.

## Rules
- Floors are facts, not options: never force security or a gate with critical/high open, never delete production data, never rewrite history, never change an AC without the user.
- Never ask for or store a secret here; production prerequisites are names.
- No state yet: say so and suggest `/dev-kit:start`.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
