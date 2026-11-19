---
name: qa
description: Quality gate for a milestone with a score and cut-off - runs the relevant auditors in parallel (code, security, tests, spec traceability, plus data, dependencies, operations, performance, and on UI milestones accessibility, visual and copy), computes a 0-100 score per dimension and overall with dev_score.py, turns blocking findings into fix tasks, and sets the gate to passed only when the cut-offs are met. Use when a milestone's tasks are done, before the next milestone, or with --only to run a subset.
argument-hint: "[M1 | --only code,security,tests,spec,data,deps,ops,perf,a11y,visual,copy | --scope T-003]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
---

# qa

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `SC` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_score.py"`.

## 1. Prepare
1. Read `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` (§7 severities and scoring) and the template `${CLAUDE_SKILL_DIR}/../core/shared/templates/qa-report.md`. Determine the milestone (argument, or the latest one whose tasks are all done and gate is pending). Ensure the working tree is clean outside `.dev/` (`git status --short -- . ':(exclude).dev'`); otherwise apply `pause_policy.dirty_tree` (`conventions.md` §10): `ask` → ask to commit or stash; `auto_recommend` → stash with a dated message, never `.dev/` (`git stash push -u -m "dev-kit auto <date>" -- . ':(exclude).dev'`), and say so in the report. `--scope T-xxx` (a hotfix or a single task) audits only that task's commit (`git show <sha>` from `DS status --json`) and never touches the milestone gate: see §4.
2. Existing project (state has `brownfield`): scope every auditor to what changed since `brownfield.baseline_ref` (`git diff <baseline_ref>..HEAD`); failures already listed in `.dev/qa/baseline.md` are not F-001, and problems found only in untouched legacy code are marked `"legacy": true` by the auditors (tell them so in the prompt; `conventions.md` §16), never blocking findings or fix tasks. Then run the test suite yourself once for a baseline (command in `architecture.md` §8). A failing suite is finding F-001 (`critical`, auditor `test-auditor`) and the gate cannot pass; still run the agents so fixes are batched.
3. Decide which auditors apply, from the milestone's tasks (`DS status --json`: files, acceptance) and the changed files (`git diff --name-only <before-first-task-commit>..HEAD`):

| auditor | runs when |
|---|---|
| `code-reviewer`, `security-auditor`, `test-auditor`, `spec-tracer` | always |
| `ops-reviewer` | always (light on the first milestone of a new project: config, CI, run-from-clean-checkout) |
| `data-reviewer` | project has a database and the milestone touches schema, migrations, models or queries (or the first milestone of a new project; existing projects: only when the diff touches them) |
| `deps-auditor` | manifests or lockfiles changed in the milestone (or the first milestone of a new project; existing projects: only when the diff touches them) |
| `performance-auditor` | milestone adds or changes endpoints, pages, queries or jobs, or the brief has performance targets |
| `a11y-auditor`, `visual-reviewer`, `copy-reviewer` | milestone touches UI files (components, templates, styles, catalogs) and the product has a UI |

`--only` overrides the selection (aliases: deps, ops, perf). A skipped auditor does not count in the score; say which were skipped and why in the report.

## 2. Run the auditors (parallel, within the host's budget)
Log `DS event skill_start --set skill=qa --set args_kind=milestone` at the start and `skill_end` (with `status`, `duration_s` and your `feedback` on the kit) at the end (`conventions.md` §13).

Give every auditor a distinct `Slot: N` (1, 2, 3…) and the line `Isolation: follow <KIT>/shared/prompts/resource-isolation.md`. **Concurrency:** read `nproc`; the heavy auditors (`test-auditor`, `a11y-auditor`, `visual-reviewer`, `performance-auditor`, and any that starts browsers or e2e) run at most `max(1, nproc // 3)` at a time; the light ones (code, security, spec, data, deps, ops, copy) all at once. Log `agent_spawn` / `agent_end` for each (`conventions.md` §13).

Spawn the selected auditors with the Agent tool, `run_in_background: true`, then wait for all. On the first run each agent uses its frontmatter model/effort. On a re-run, spawn only the auditors whose dimension failed (the others keep their raw JSON when their files did not change) with the model and effort of the next ladder row (`conventions.md` §9), after the consent that `autonomy.model_policy.mode` requires (read it from `DS status --json`). Give each: the scope (`M1` or `--scope`), the language for prose, `Project root: ${CLAUDE_PROJECT_DIR}`, the base URL if the app is already running, and in existing projects `Baseline: <brownfield.baseline_ref>` with the instruction to audit only `git diff <baseline_ref>..HEAD` and to mark problems that exist only in untouched code `"legacy": true`. Tell visual/a11y/performance auditors whether `autonomy.may_run_servers` is true. Do not pre-load them with opinions. **Round ≥ 2 (delta mode):** also give each re-run auditor the previous findings of its dimension from `.dev/qa/<M>/findings-round-<n-1>.json` (id, severity, title, file, line) and ask it to report each as `closed` or `open` in `previous` (`auditor-output-contract.md`). After all auditors return, run `DS cleanup`.

## 3. Score
1. Save each agent's JSON block as `.dev/qa/<M>/raw/<agent-name>.json` (several audits of one type: `<agent-name>-<k>.json`); for that, write the fenced JSON block of the agent's final message to the file verbatim, never reconstruct it from the prose (if an agent returned no parsable JSON, re-run that agent once; if it still fails, record `{"auditor": "<name>", "findings": [{"id":"F-000","severity":"high","title":"auditor produced no parsable result",...}]}` so the gate cannot pass silently).
2. Run `SC score --scope <M> --kind gate --root . --round <n> --out .dev/qa/<M>/scores.json .dev/qa/<M>/raw/*.json`, adding `--previous .dev/qa/<M>/findings-round-<n-1>.json` from round 2 on (`conventions.md` §7 delta mode). Exit 0 = pass, 1 = fail. The command prints the per-dimension table; use it verbatim in the report.
3. Consolidate findings: renumber `F-001…`, merge duplicates across auditors (same file/line/root cause → keep highest severity and list both auditors) into `.dev/qa/<M>/findings.json` and a copy `.dev/qa/<M>/findings-round-<n>.json` (every finding keeps `auditor`; in delta mode the file holds the previous findings still open plus the new scored ones; new lows go to a `deferred` list). Legacy findings never go into these files: they are issues (§4), and `dev_score.py` ignores any that slip into `--previous`. Do not change severities to move the score; if a severity is clearly wrong, re-run that auditor with a note instead.
4. **Local deploy** (only if `autonomy.local_deploy.mode` is not `off` and the score verdict is pass): follow `conventions.md` §11 on the milestone's last commit. On failure add the `ops` finding to `.dev/qa/<M>/raw/local-deploy.json` (`auditor: ops-reviewer`), re-score, and the gate fails.
5. Write `.dev/qa/<M>/report.md` from the template in the user's language: score table, trend versus the previous run (delta: closed · still open · new · deferred lows), blocking findings, deferred findings, decisions, and the local deploy result (URL or path, mode).

## 4. Triage and gate
- Legacy findings (existing projects): for each entry in `scores.json` → `legacy`, `DS add-issue --type <bug, or improvement for docs, licence and style debt> --class <intangible; standard for a critical/high security finding such as a secret in the history> --title "<title>" --severity <severity> --origin qa --note "legacy: qa/<M>/report.md"` unless an open issue already covers it (`DS backlog --json` lists `origin` and `note`); list them in the report under "Pre-existing (not scored)", and tell the user plainly about any critical security one (a leaked secret must be rotated whatever the gate says).
- Each blocking finding (`critical`/`high`) → `DS add-task --milestone <M> --type fix --title "<finding title>" --acceptance "<AC or 'F-00n resolved: <observable condition>'>" --source qa/<M>/report.md#F-00n --files "<file>"`.
- Dimension below its minimum without blocking findings (many mediums): create fix tasks for the cheapest, highest-penalty mediums first until the projected score clears the cut-off (each medium costs 8 points, low 2); remaining mediums/lows are listed as deferred.
- Gate: if the score verdict is pass → `DS gate <M> passed --score <overall> --count-run`; when it was the last milestone, `DS set phase usability` (or `docs` for products without a UI). Otherwise `DS gate <M> pending --score <overall> --count-run --note "<reasons> → fix tasks T-…"`.
- `--scope T-xxx`: no gate. Score with `--scope T-xxx --kind gate` into `.dev/qa/T-xxx/`, then record `DS review hotfix-T-xxx pass|fail --score <overall> --count-run` (a hotfix) or `DS review task-T-xxx …` (any other task); fix tasks go to the task's milestone. `release --hotfix` checks this review.
- Rounds: if `qa_runs` exceeds `autonomy.max_fix_rounds_per_gate`, apply `pause_policy.rounds_exhausted` (`conventions.md` §10; `auto_recommend` accepts with `--force --note "policy:rounds_exhausted"` only where §9 recommends it). With `ask`, stop and ask the user (recommended option first per `conventions.md` §9): keep fixing, accept with `DS gate <M> passed --score <n> --force` plus an ADR (`source: user`), or replan.

## 5. Report to the user
If there are deferred findings, say how many and offer to promote the relevant ones with `/dev-kit:issue --from <F-id> <M>`; end with one tip from `DS tip qa_deferred` (when the gate passed, `DS gate` already printed one: relay it instead of asking for another).
Before `skill_end`, run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_cost.py" --root "${CLAUDE_PROJECT_DIR}" ingest` (token usage per stage, `conventions.md` §14).
Verdict, overall score vs cut-off, the dimension table (one line each), the local preview (URL/command and how to stop it) when there is one, fix tasks created, auditors skipped, and the next command (`implement` for fixes then `qa <M>` again; or next milestone).

## Rules
- Agents are read-only; every state change happens here. Never pass a gate by hand or with failing tests.
- Fix tasks must be concrete (file, condition to verify) so `implement` can execute them without re-reading the report.
- A re-run uses fresh auditor instances that receive the previous findings only to verify them (delta mode), never the previous verdicts; escalating model or effort is allowed only as `conventions.md` §9 says, and never silently.
