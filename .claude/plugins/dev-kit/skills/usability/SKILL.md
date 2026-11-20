---
name: usability
description: Whole-product usability, accessibility, visual and copy audit with a score and cut-off - runs the app, captures screenshots, and has usability-auditor, a11y-auditor, visual-reviewer and copy-reviewer evaluate every screen and journey against Nielsen heuristics, WCAG 2.2 AA, the UI spec and the brief's tone; writes .dev/qa/ux/report.md and creates fix tasks. Use after the UI milestones are built and before release, or when the user asks whether the app is usable, accessible and polished.
argument-hint: "[screen ids | flow ids | --url http://localhost:3000]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# usability

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `SC` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_score.py"`.

## Procedure
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §7, `.dev/brief.md` block 7, `.dev/design/ux-flows.md` §3–4 and `.dev/design/ui-spec.md`. Scope: argument, or every screen whose tasks are `done`.
2. With `--url`, use that running app as is (do not start another one, do not stop it at the end). Otherwise run the app if `autonomy.may_run_servers` is true (project dev command from `architecture.md`, or the `run` skill if available); wait until it responds and keep the URL; seed demo data only via documented scripts. If it cannot run, say so; auditors will work from code and mark visual claims `confidence: low`.
3. Spawn in parallel (Agent tool, one message, background): `usability-auditor` (journeys, heuristics, UI consistency), `a11y-auditor` (WCAG 2.2 AA, keyboard, axe), `visual-reviewer` (screenshots versus spec), `copy-reviewer` (strings, tone, locale). For many screens, split the usability auditor by persona/journey set (one raw file per audit; `dev_score.py` dedupes their common findings). Give each a distinct `Slot: N` and the isolation line (`resource-isolation.md`); run at most `max(1, nproc // 3)` browser-based auditors at a time; run `DS cleanup` when they return. Log agent events (`conventions.md` §13). From round 2 give each auditor the previous findings of its dimension (`.dev/qa/ux/findings-round-<n-1>.json`) to mark `closed`/`open`. Give each scope, language, URL, `Project root: ${CLAUDE_PROJECT_DIR}` and the screenshots folder `.dev/qa/ux/screenshots/` (existing projects: also `Baseline: <brownfield.baseline_ref>`, see the last section). Give each `Output file: .dev/qa/ux/raw/<agent>.json` (split audits: `<agent>-<k>.json`). Always pass `model` and `effort` in the Agent call (`conventions.md` §9). First run: the tier's row 1; re-runs: only the failed dimensions, with the next ladder row and the consent of `autonomy.model_policy.mode` (`conventions.md` §9).
4. Run `SC check --fix .dev/qa/ux/raw/*.json` (missing or invalid → as in `qa` §3.1); score with `SC score --scope ux --kind gate --root . --round <n> --out .dev/qa/ux/scores.json .dev/qa/ux/raw/*.json` plus `--previous .dev/qa/ux/findings-round-<n-1>.json` from round 2; save `.dev/qa/ux/findings-round-<n>.json`.
5. Write `.dev/qa/ux/report.md` (template `${CLAUDE_SKILL_DIR}/../core/shared/templates/qa-report.md`, plus a "What works well" section with the strengths the auditors listed) and `.dev/qa/ux/findings.json`.
6. Triage like `qa` (legacy findings → issues, never fix tasks, `qa` §4): blocking findings → `DS fix-tasks --from .dev/qa/ux/findings.json --milestone <last milestone> --source qa/ux/report.md`; cheapest mediums until the projected score clears the cut-off; the rest deferred, with `DS add-question` for product decisions (e.g. simplify a flow).
7. Record the outcome as a review named `ux` (milestone gates belong to `qa`): pass → `DS review ux pass --score <overall> --count-run`; fail → `DS review ux fail --score <overall> --count-run`, then run `implement` for the fix tasks and `usability` again. Respect `max_fix_rounds_per_gate` as in `qa`, and on exhaustion apply `pause_policy.rounds_exhausted` (`conventions.md` §10); with `ask`, ask the user with the recommended option first (keep fixing, or accept with `--force` plus an ADR).
8. Stop any server you started (never one given with `--url`). If the review passed and the phase is `usability`, `DS set phase docs`.
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
9. Offer to promote relevant deferred findings with `/dev-kit:issue --from <F-id> ux`. Report: overall score vs cut-off, dimension table, screens reviewed, three strengths, fix tasks, next command.

## Existing projects (brownfield)

When state has `brownfield` (`conventions.md` §16): the scope is the screens tagged `new` or `changed` in `.dev/design/ux-flows.md` plus the journeys that pass through them, not the whole product; `existing` screens are visited only as steps of those journeys. Tell every auditor so, with `Baseline: <brownfield.baseline_ref>`: a problem that exists only on an `existing` screen (or in untouched code) is reported with `"legacy": true`, does not score and becomes an issue (`DS add-issue --type <bug|improvement> --class intangible --title "<title>" --severity <severity> --origin usability --note "legacy: qa/ux/report.md"`); an `existing` screen has no full spec, so "differs from the spec" is not a finding there. The report adds a "Pre-existing (not scored)" section. If no `new`/`changed` screen exists, record `DS review ux n/a --note "no new UI"` and stop.
