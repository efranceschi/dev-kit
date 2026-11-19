# dev-kit conventions

Every dev-kit skill and agent follows these rules. Read this file once per session when a dev-kit skill runs.

## 0. Kit root (`<KIT>`)

Paths written as `<KIT>/shared/...` and `<KIT>/scripts/...` are relative to the **kit root**: the folder that contains `shared/` and `scripts/`. The skill that loaded you prints it as `Kit root: ...` and passes it in the prompt of every agent it spawns; use that absolute path literally. Never assume it is inside the project being built. Run every command from the project root; do not `cd` elsewhere, and use `dev_state.py --root <project root>` if you must.

## 1. Language

- Detect the user's language from their messages in this conversation. If `.dev/state.json` exists, `language` there wins (BCP-47, e.g. `pt-BR`, `en`, `es`).
- Use that language for **everything user-facing**: conversation, questions, and every artifact written under `.dev/` (PRD, plan, reports, ADRs, commit bodies). Code, identifiers, file names, task IDs and commit subjects stay in English.
- If the language cannot be determined (no messages, no state), ask once with AskUserQuestion and record it with `dev_state.py set language <tag>`.
- **Kit files are English only** (skills, agents, shared files, catalogs such as `help.json` and `tips.json`, docs). Translate at display time: when a skill shows a tip, a help card or a report to the user, it writes it in the user's language. The lint rejects non-English text in the kit.
- The language of the *application being built* (its UI copy) is a separate question answered in the interview (block 2) and lives in `brief.md`.

## 2. Layout of `.dev/` in the target project

```
.dev/
  state.json          machine-readable status, single source of truth (managed only via dev_state.py)
  brief.md            interview output: all requirements and decisions the user gave
  open-questions.md   non-blocking doubts accumulated by skills; consumed by `interview --gaps`
  prd.md              product requirements with acceptance criteria AC-n
  architecture.md     stack, structure, data model, contracts
  decisions.md        ADR log (ADR-001 ...), including `auto` decisions
  plan.md             milestones M1.. and tasks T-001.. (parser contract below)
  design/ux-flows.md  flows, journeys, states, microcopy
  design/ui-spec.md   tokens, components, per-screen specs
  qa/test-plan.md     test strategy
  qa/<M>/report.md    QA gate report per milestone (+ findings.json)
  qa/ux/report.md     usability/accessibility audit
  log.md              append-only journal (written by dev_state.py)
```

Never edit `state.json` by hand. Always go through `python3 -I "<KIT>/scripts/dev_state.py" <subcommand>`.

## 3. Identifiers

- Milestones: `M1`, `M2`, ... Tasks: `T-001`, `T-002`, ... (zero-padded to 3, sequential across the whole project, never reused).
- Acceptance criteria in `prd.md`: `AC-1`, `AC-2`, ... Each user story lists its ACs; tasks reference ACs; tests mention the AC id in their name or a comment so `spec-tracer` can trace them.
- ADRs: `ADR-001`, ... Findings from auditors: `F-001`, ... (per report). Open questions: `Q-001`, ...

## 4. Task format in `plan.md` (parser contract)

```markdown
## M1 — Milestone title
Short goal of the milestone (one paragraph).

### T-003 Task title
- status: todo
- deps: T-001, T-002
- type: feature
- acceptance:
  - AC-4: invalid email shows inline error
  - AC-5: successful login redirects to dashboard
- test_notes: unit tests for validator; e2e happy path
- files: src/auth/LoginForm.tsx, src/auth/validate.ts
```

Rules: `type` ∈ `feature | fix | chore | test | docs`. `status` in plan.md is informative only; `state.json` wins on conflict. `deps` may be empty (`- deps:`). Tasks should be vertical slices completable in one sitting (roughly 30–90 minutes of work) with tests included.

## 5. Commits

- One commit per completed task, subject: `[T-003] <type>: <imperative summary>` (type = feat | fix | chore | test | docs | refactor). Body (in the user's language): what changed, which ACs it satisfies, how it was verified.
- Only commit when the working tree contains just that task's changes. Never amend or rewrite history. Never push unless the brief says so.
- Record the SHA: `dev_state.py done T-003 --commit <sha>`.
- If the brief says `commit_per_task: false`, skip committing but still call `done`.

## 6. Autonomy rule (summary; full text in `shared/interview/autonomy-policy.md`)

When a skill hits a gap not covered by `brief.md`, `prd.md`, `architecture.md` or `decisions.md`:
1. Classify the decision into a category (see policy file).
2. If the category is in `autonomy.always_ask` → stop and ask the user (AskUserQuestion), then record the answer as an ADR.
3. Otherwise → pick the most probable option, record it as `ADR-nnn (auto)` in `decisions.md`, optionally add a `Q-nnn` to `open-questions.md` via `dev_state.py add-question`, and continue.
4. Never silently change scope defined in the PRD; scope changes are `scope_change_major` or `minor_scope_tradeoffs` by size (minor = does not remove or alter an AC).

## 7. Severity scale (QA findings)

| severity | meaning | effect on gate |
|---|---|---|
| critical | data loss, security breach, crash on main path, AC not met | blocks |
| high | wrong behaviour on common path, missing validation, test gap on an AC | blocks |
| medium | maintainability, minor UX, weak test | does not block, becomes `fix` task if cheap |
| low | style, nit | recorded only |

A gate or review is `passed` only when there are no open `critical` or `high` findings **and** the quality score meets the cut-offs below.

### Quality score (0–100) and cut-off
Computed by `python3 -I "<KIT>/scripts/dev_score.py" score ...` from the auditors' JSON; never estimated by hand.

- Dimension score = 100 − penalties (critical 40, high 20, medium 8, low 2; `confidence: low` counts half). Any critical caps the dimension at 40; any high caps it at 69.
- **Low cap:** the low penalties of a dimension add up to at most `autonomy.quality.low_cap` (default 10), so a large artifact or a product with many screens is not failed by nits alone.
- **Dedupe:** when several audits feed one dimension (e.g. usability split by persona), the same finding (same file and line, or same title and file) counts once, at its highest severity.
- **Delta mode (round ≥ 2):** save the consolidated findings of each round (`.dev/qa/<M>/findings.json`, `.dev/reviews/<target>/findings.json`, `.dev/qa/ux/findings.json`; each finding keeps its `auditor`). In the next round give every re-run auditor the previous findings of its dimension and score with `dev_score.py score ... --previous <previous findings.json> --round <n>`. Previous findings stay scored until an auditor marks them `closed`; new critical/high/medium findings score; new low findings are recorded as deferred (listed in the report, not scored). This is what makes rounds converge: each round closes work instead of discovering a new layer of nits.
- Dimensions by auditor: code (code-reviewer), security (security-auditor), tests (test-auditor), spec (spec-tracer), ux (usability-auditor), a11y (a11y-auditor), visual (visual-reviewer), copy (copy-reviewer), performance (performance-auditor), data (data-reviewer), operations (ops-reviewer), dependencies (deps-auditor), docs (docs-reviewer), design (design-reviewer), requirements (requirements-reviewer, prd and plan).
- Overall = weighted average of the dimensions that ran. Defaults: overall ≥ 85 for milestone gates, ≥ 80 for pre-implementation reviews, every dimension ≥ 70, with higher minimums for security (90), spec (85), tests (80), a11y (80).
- Cut-offs live in `state.json` under `autonomy.quality` (set in the interview, block 8) and are enforced by `dev_state.py gate <M> passed --score N` and `dev_state.py review <name> pass --score N`, which refuse scores below the cut-off. `--force` exists only for a user decision and must be accompanied by an ADR.
- Scores are stored with the gate/review and shown in `dev_state.py status`.

## 8. Writing style for artifacts

- Lead with the decision or the result. Short sections, tables for inventories, Mermaid for diagrams.
- Every artifact starts with a 3–5 line header: purpose, inputs it was derived from, date, status (`draft | approved | superseded`).
- Keep artifacts the user will read under ~400 lines; split otherwise.

## 9. Model and effort per agent (escalation ladder)

Each agent declares its base `model` and `effort` in its frontmatter (round 1). Agents are grouped by what they really need:

| tier | agents | why | round 1 |
|---|---|---|---|
| `speed` | copy-reviewer, deps-auditor, docs-reviewer | checkable output (tools, executed commands, style guide), low cost of a miss, `release` re-audits | haiku / medium |
| `balanced` | code-reviewer, test-auditor, performance-auditor, a11y-auditor, usability-auditor, visual-reviewer, design-reviewer, ops-reviewer, data-reviewer, implementer | judgment backed by tools (axe, test suite, build, tests) | sonnet / medium |
| `quality` | security-auditor, spec-tracer, architect, requirements-reviewer | a miss is costly or propagates downstream; few calls | opus / high |

`autonomy.model_policy.tiers` may override the tier of an agent; if absent in `state.json`, use `{"mode": "ask", "tiers": {}}`.

Escalation applies **only to the dimensions that failed** (re-run the failures, not every auditor), and only when the passed dimensions' files did not change since their run:

| tier | round 1 | round 2 | round 3 |
|---|---|---|---|
| `speed` | haiku / medium | sonnet / medium | sonnet / high |
| `balanced` | sonnet / medium | sonnet / high | opus / high |
| `quality` | opus / high | opus / xhigh | ask (rule below) |

Pass them in the Agent call (`model` alias and `effort`); they override the frontmatter. Effort is raised before the model, except in the `speed` tier, where the capability gap is real. Raising model or effort is a cost decision that belongs to the user:

- `mode: ask` (default): before every escalation, ask with AskUserQuestion (see "Recommendation rule"); escalate only on yes.
- `mode: preapproved`: escalate without asking, but only within this ladder; anything beyond it asks.
- `mode: off`: never escalate; re-run at the base.
- Under `autopilot`, an escalation in `ask` mode is an `always_ask` item (`model_escalation`): batch it with the other questions.

### Recommendation rule
Every question that asks the user to decide (escalation, rounds exhausted, consent in the interview) puts the recommended option first, labelled "(Recommended)", with one line of reason and the relative cost and time of each option. Derive it from the first row that matches:

| observed | recommend |
|---|---|
| score within 5 points of the cut-off, only medium/low open | raise effort in the same tier |
| critical/high open in a `balanced` or `speed` dimension | raise one model tier for that dimension only |
| the findings are fixable by a tool (lint, test, audit) | do not escalate: fix tasks, re-run at the same tier |
| the same finding came back twice | stop escalating: replan or revisit the spec (`interview --gaps`) |
| rounds exhausted, only medium/low open, gap ≤ 5 | accept with `--force` + ADR (never for security) |
| rounds exhausted, critical/high open or gap > 5 | replan |
| consent in the interview | mode `ask` with the default ladder |

## 10. Pause policy (how autonomous a run is)

Before any AskUserQuestion, a skill reads `autonomy.pause_policy.<point>.action` (`DS status --json`); a missing point means `ask` (supervised, the default). The interview sets it (block 9); `autonomy.level unattended` fills the recommended values below.

| point | when it happens | actions allowed | `unattended` value |
|---|---|---|---|
| `paid_services` | something billable is needed | ask · preauthorize (`limit.max_monthly`, currency) · park | park |
| `delete_data` | destructive migration, dropping data | ask · preauthorize (`limit.environments`, never production) · park | preauthorize dev, test |
| `public_exposure` | push, deploy, publish, open ports | ask · preauthorize (`limit.targets`) · park | park |
| `scope_change_major` | an AC or must-have would change | ask · park | park |
| `security_model_change` | auth, permissions, token lifetime, crypto | ask · auto_recommend · park | auto_recommend |
| `credentials` | a secret the user has not provided | ask · park | park |
| `rounds_exhausted` | fix rounds exhausted, or the same finding came back twice | ask · auto_recommend · park | auto_recommend |
| `dirty_tree` | uncommitted changes nobody owns | ask · auto_recommend (`git stash push -m "dev-kit auto <date>"`) | auto_recommend |
| `blocked_env` | three tasks blocked in a row, tests or server cannot run | ask · park | park |
| model escalation | §9 | governed by `autonomy.model_policy.mode` | preapproved |

What each action does:
- `ask`: AskUserQuestion with the recommended option first (§9 "Recommendation rule").
- `preauthorize`: decide alone **within the recorded limit**; anything beyond it is treated as `park`. Record `ADR-nnn` with `source: policy`.
- `auto_recommend`: apply the option the §9 recommendation rule selects, record `ADR-nnn` with `source: policy` and the reason, and continue. For `rounds_exhausted`, "accept" means `DS gate <M> passed --score <n> --force --note "policy:rounds_exhausted"` (or `DS review ... --force --note "policy:..."`); `dev_state.py` refuses it when a critical/high finding is open or security is below its minimum. When the recommendation is "replan" or "revisit the spec", treat it as `park`.
- `park`: never wait. `DS add-question` with the recommended answer as the assumption, `DS block` only the tasks that depend on it (missing credentials: build against a stub or mock and block only the task that needs the real secret), and continue with all independent work. If `notify_on_park` is true and a notification tool is available, send one short message per parked item.
- `autonomy.on_park`: `stop_when_idle` (default) ends the run when nothing else can advance; `stop_first` ends it at the first parked item. Either way the final report lists every parked item with its recommendation and the command to resume (`interview --gaps`, then `autopilot`).

Floors no policy can lift (the interview shows them, it does not ask): never force security or a gate with critical/high open; never delete production data; never rewrite git history; never change an AC without the user (always `park`).

Claude Code's own permission prompts (Bash, Edit) are outside the kit: for an unattended run the user needs a permission mode or allowlist that covers the project (`/fewer-permission-prompts`).

## 11. Local deploy per milestone (`autonomy.local_deploy`)

Optional, chosen in the interview (block 10); default `off`. Modes: `keep_running` (the approved milestone stays running for the user to try while the next one is built; the previous preview is replaced), `smoke` (start, check, stop: proves the milestone runs without holding a port), `off`.

Asked only when it makes sense for the platform (brief block 3):

| platform | ask? | what "local deploy" means |
|---|---|---|
| web app, API, full-stack, bot/service | yes, if `may_run_servers` is true | production build + start on `127.0.0.1:<port>` from the milestone commit |
| desktop | yes | build the executable/installer into `.dev/preview/<M>/` |
| CLI | yes | isolated local install (venv, `npm link`, `cargo install --path`) plus one example command |
| native mobile | only if an emulator/SDK is detected | debug build installed on the emulator |
| library/package, single script, documents only | no: record `off (inferred)` in the brief | — |

Procedure (run by `qa` after the score passes and **before** `DS gate <M> passed`):
1. Stop the running preview, if any (pid in `DS status --json` → `milestones.*.preview`), then `git worktree add --force .dev/preview/current <sha>` (or reset it to `<sha>`); make sure `.dev/preview/` is in `.gitignore`.
2. Run the "local preview" command from `architecture.md` §7 (or the `run` skill) inside the worktree, with the local `.env` (never production credentials), bound to `127.0.0.1` on `local_deploy.port` (or a free port different from the dev port). Binding to `0.0.0.0` or a network is `public_exposure` (§10).
3. Smoke check: the URL answers 2xx, or the CLI/desktop example runs and exits 0. A failure in build, start or check is an `ops` finding with severity `high` (auditor `ops-reviewer`, added to the raw results before scoring is final): the gate does not pass and a fix task is created.
4. `keep_running` → leave it in the background and `DS preview <M> --url <url> --sha <sha> --pid <pid>`; `smoke` → stop it and `DS preview <M> --url <url> --sha <sha>` then `DS preview <M> --stopped`.
5. Tell the user the URL (or install path / command) and how to stop it; if `local_deploy.notify` is true and a notification tool is available, send one short message with the URL.

## 12. Production deploy (`autonomy.production`, skill `deploy`)

Set in the interview (block 10) when the product has a production environment: `method` (install script, systemd, docker compose, PaaS…), `host` (local | remote), `when` (`per_milestone` | `on_release` | `manual` | `none`), `smoke` checks and the operational `prerequisites` (backup credentials, keys, model downloads…). `architecture.md` §7 holds the install, migrate and rollback commands.

- `autopilot` runs `deploy` after each approved gate (and after the local preview of §11) when `when` is `per_milestone`; `release` runs it when `when` is `on_release`.
- Consent: pause point `production_deploy` (§10): `ask` (default), `preauthorize` for the listed `limit.targets`, or `park`.
- A missing prerequisite never makes `deploy` try: it parks or asks per `pause_policy.credentials`.
- Every deploy is recorded with `dev_state.py deploy production --sha <sha> --milestone <M> --migration <rev> --status ok|failed|rolled_back`. `status --head-migration <rev>` shows how far production is behind the checkout (commits, approved milestones, migrations).

## 13. Session log (`.dev/telemetry.jsonl`)

Every skill keeps a structured, high-level log of the session, for the user to follow or review the run, or to send to the dev-kit author for troubleshooting and improvements. It never contains project data: `dev_state.py` accepts only allowlisted keys and values (numbers, booleans, ids such as T-001/M1/F-003, short lowercase tokens) and rejects titles, finding texts, paths, URLs and names.

- The scripts log by themselves: task transitions, gates, reviews, scores (per dimension, with delta), previews, deploys, cleanups and policy changes.
- Each skill logs, with `DS event <type> --set key=value ... [--json '{...}']`:
  - `skill_start` when it begins (`skill`, `args_kind`) and `skill_end` when it ends (`skill`, `status`: ok | failed | parked | stopped, `duration_s`, `feedback`);
  - `agent_spawn` / `agent_end` around every agent (`agent`, `model`, `effort`, `slot`, `round`, `scope`; on end also `status`, `duration_s`, `tokens` when the tool reports usage, `findings` counts, `parsable`, and the agent's `kit_feedback` as `feedback`);
  - `pause` at every pause point (`point`, `action`, `outcome`) and `escalation` for every model/effort change (`agent`, `from`, `to`, `consent`);
  - `error` with an enumerated `code` (`no_json`, `tests_failed`, `env_broken`, `hook_rejected`, `merge_conflict`, `port_in_use`, `timeout`, `other`).
- **Feedback** (`feedback` on `skill_end` and `agent_end`; `DS feedback --worked/--failed/--improve area:note` at the end of a run): what worked, what failed and what could be improved in the dev-kit, at most 3 items per list, each note ≤ 140 characters and about the kit, never about the project. `autopilot` writes a `session_feedback` when the run ends.
- `DS event session_start --set trigger=<skill>` starts a new session id (`start` and `autopilot` call it). `DS telemetry summary` shows the session; `DS telemetry report [--json]` grades each stage; `DS telemetry export [--events] [--stamp S]` writes `.dev/feedback/telemetry-export-<YYYYMMDD-HHMMSS>.json` (never overwriting) for the user to review and send to the author. All three take `--all` or `--since YYYY-MM-DD` (default: the current session). The skill `feedback` turns them into `.dev/feedback/feedback-report-<stamp>.md`.
- **Stage grades** (fixed formula, `dev_telemetry.stage_report`): start at 100; −10 per round beyond the first of each review or gate, plus −10 per round beyond `max_fix_rounds_per_gate`; forced pass −25 by the user, −15 by policy; −10 each time a scope's score drops between rounds; −5 per error (max −30); −5 per agent without parsable JSON; −10 per failed and −5 per parked skill run; feedback of the stage's area −3 per `failed` and +2 per `worked` item (net −15…+6); a review or gate still failing caps the stage at 60; clamp 0–100. Stages that did not run show `—`; the overall grade is the mean of the stages that ran. Every grade lists the reasons that produced it.
- Logging never blocks work: if an event is rejected, fix the fields or drop it; never put project text into a field to make it pass.

## 14. Costs (`dev_cost.py`, skill `costs`)

- **Source:** Claude Code's local transcripts of the project (`~/.claude/projects/<project>/<session>.jsonl` and `<session>/subagents/agent-*.jsonl`, or `$CLAUDE_CONFIG_DIR`). `dev_cost.py ingest` reads only usage numbers, model, agent type and ids, deduplicated by request, into `.dev/costs/usage.jsonl`. It is incremental and safe to run often. Message content is never read into the store. Without transcripts, the totals fall back to the `tokens` the skills logged in `agent_end` (marked partial).
- **Tokens kept per request:** `input`, `output`, `cache_write_5m`, `cache_write_1h`, `cache_read`, plus model and speed, so the user can price them with any rates (`dev_cost.py export` → `.dev/costs/tokens-<YYYYMMDD-HHMMSS>.csv`, never overwriting).
- **Stage:** main-session requests take the stage of the innermost skill window (`skill_start`…`skill_end`, §13) they fall in. Subagents take the stage of the window where they started (the implementer is always `implement`). Everything else is `orchestration`.
- **Price:** `.dev/costs/prices.json` (US$ per million tokens, with `as_of`; created from the built-in defaults, editable). Cache writes cost 1.25× input (5 min) or 2× (1 h); cache reads use the model's own price or 0.1× input; `fast` speed multiplies by the model's factor. A model without a price keeps its tokens and shows `n/d`. The value is an **API-equivalent estimate**; on subscription plans nothing is billed per token.
- **When it runs:** `qa`, `review`, `usability`, `implement`, `deploy`, `release` and `autopilot` run `dev_cost.py ingest` before their `skill_end`. `dev_cost.py report` writes `.dev/costs/summary.json`, which `status` shows as `Cost (est., API-equivalent): …`. The `report` also logs a `cost` event with numbers only.

## 15. Issues, classes of service and cadence (`issue`, `backlog`)

**The cadence is fixed.** Milestones M1, M2, M3… are the project's rhythm. Issues never create, insert or renumber milestones: they wait in a queue and enter existing milestones by class of service (inspired by Kanban classes of service, Scrum's capacity buffer and Shape Up's cool-down).

| class | written criterion | where it enters |
|---|---|---|
| `expedite` | bug, critical or high, in delivered work or production, or blocking the current milestone | **now**, hotfix lane: `add-task --lane hotfix` in the current milestone; runs before everything, even with a pending gate; **WIP 1**; closes with `qa --scope T-xxx`, deploy and a patch version (`release --hotfix`); the milestone gate is untouched |
| `current` | bug in a task of the milestone being built, before its gate | that milestone, now (like QA fix tasks) |
| `standard` | medium bug, improvement with clear value | the **buffer** of the next milestone |
| `intangible` | low bug, polish, tech debt, promoted deferred finding | the **cool-down** (if on), else spare buffer |
| `change` | adds or alters an AC or a must-have | `prd` → `review prd` → (`ux`/`ui` → `review design`) → `plan` replan, into future milestones only |

- **Buffer:** when a milestone starts, `dev_state.py pull-issues Mn` creates tasks for queued issues (standard before intangible, then severity, then age) up to `ceil(autonomy.issue_buffer_pct% × planned tasks of Mn)` (default 20%). What does not fit stays queued.
- **Cool-down** (`autonomy.cooldown = {enabled, max_tasks}`, off by default): after the gate of Mn passes, `dev_state.py cooldown Mn` takes small queued issues (effort S, severity low/medium, at most `max_tasks`) into Mn+1 with lane `cooldown`; they run first in Mn+1 and are audited by its QA. After the last milestone there is no cool-down: the queue waits for the next cycle, planned as the next milestone number.
- **State:** `issues` in `state.json` and `.dev/issues.md` (generated). Tasks created for an issue carry `source: issue:I-nnn`; the issue moves `open → scheduled → in_progress → done` automatically with its tasks (`wontfix` and `duplicate` close it by hand).
- **Overuse:** more than 2 hotfixes in one milestone is reported by `backlog` as a warning.
- **Tips:** `dev_state.py tip <context>` returns one short tip from `shared/tips.json` (each at most twice; `autonomy.tips: on | off | always`; `tips --reset`). Scripts append it to their human output (`💡 …`); skills end their report with at most one tip, never inside a question and never invented.

