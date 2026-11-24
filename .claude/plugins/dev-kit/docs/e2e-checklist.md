# dev-kit end-to-end checklist (manual)

Install the plugin (`/plugin marketplace add efranceschi/dev-kit`, then `/plugin install dev-kit@dev-kit`) or run `claude --plugin-dir .claude/plugins/dev-kit` in a scratch project, then start Claude Code there.

Tick each item; note the Claude Code version used.

## 0. Static
- [ ] `python3 -I .claude/plugins/dev-kit/skills/core/tests/lint_suite.py` → 0 errors.
- [ ] `python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests` → all pass.
- [ ] `/help` or the skill list shows all 23 `dev-kit:*` skills (core is not one); agents list shows 17 dev-kit agents.

## 0b. Installation
- [ ] The skills appear as `/dev-kit:start`, `/dev-kit:qa`, ... and `core` is not offered as a command.
- [ ] Remove `core` and run `/dev-kit:start`: it reports the missing support skill instead of failing silently.
- [ ] In a new project run `/dev-kit:start "idea"`: `.dev/` is created in that project and nothing is created next to the skills.
- [ ] Spawned agents read checklists via the `Kit root:` path they receive (check the agent prompt in the transcript).

## 1. New project, Portuguese
- [ ] `mkdir scratch && cd scratch && git init`; start Claude; `/dev-kit:start "API de tarefas com login e painel web"` in Portuguese.
- [ ] It explains the flow in ≤ 3 lines and invokes `interview` without asking questions itself.
- [ ] Interview runs block by block (≤ 4 questions per round, recommended option first, "decida por mim" available); skips blocks answered by the opening message.
- [ ] `.dev/brief.md` written in pt-BR, one section per block; `.dev/state.json` has `language: pt-BR`, `autonomy.level`, `artifacts.brief`, and `status --short` says `phase: conception · prd`; `.dev/decisions.md` has initial ADRs.
- [ ] Closing summary + single confirmation question.

## 2. Autonomous conception and planning
- [ ] `/dev-kit:autopilot --until plan` produces `prd.md` (ACs numbered, testable), `architecture.md` (stack table, data model, contracts), `design/ux-flows.md`, `design/ui-spec.md`, `plan.md` with ≥ 2 milestones; `state.json` has tasks; **no question asked** outside `always_ask` categories; assumptions logged as `ADR-nnn (auto)` and `Q-nnn` rows.
- [ ] `/dev-kit:status` shows `Phase: construction · M1`, the milestones and next task `T-001`; the board opens on the Construction tab, its lifecycle tabs have conception and planning ✓ and construction marked "now".

## 3. Implementation and gate
- [ ] `/dev-kit:implement --tasks 2` → two commits `[T-001] …`, `[T-002] …`; `state.json` tasks done with SHAs; tests green.
- [ ] Kill the session; restart Claude in the folder → `/dev-kit:start` shows the 3-line `[dev-kit]` status and resumes without re-interviewing.
- [ ] Finish M1 (`implement --milestone M1`); `dev_state.py next` exits 3 with "gate of M1 is pending".
- [ ] `/dev-kit:qa M1` spawns the applicable auditors in parallel (see 3b); writes `qa/M1/report.md`, `findings.json` + `scores.json`; blocking findings become `fix` tasks placed first in `next`; gate `pending` or `passed` accordingly.
- [ ] If pending: `implement` picks the fix tasks first; `qa M1` again → `passed`.
- [ ] Through the whole milestone (implement, QA, fixes, gate) the phase stays `construction`; after the gate the step is `M2` and `status` shows `Next release: M1 closed since the last release`.
- [ ] Scope change during M2: `/dev-kit:issue "<new behaviour>"` (class change) → after `prd`, `status --short` says `phase: conception · … (reopened)`, the board shows conception and planning "reopened" and construction still active; after `review prd`, the refreshed design and `plan replan` + `review plan` the phase is back to `construction · M2`.

## 3b. Quality score and cut-off
- [ ] In the interview, block 8 offers `standard | premium | prototype`; `state.json` has `autonomy.quality` with the chosen numbers.
- [ ] `review prd`, `design` and `plan` each spawn the right reviewer, write `.dev/reviews/<target>/scores.json`, and `dev_state.py status` shows `reviews: prd:pass(NN) ...`. A failing review sends the artifact back to its producing skill and re-scores with a fresh reviewer.
- [ ] `autopilot` does not start `architecture` before review `prd` passes, `plan` before `design`, `implement` before `plan`.
- [ ] `qa M1` on a UI milestone runs the 11 auditors that apply (core 4, operations, data, dependencies, performance, a11y, visual, copy) and skips the rest with a reason; `.dev/qa/M1/scores.json` lists all dimensions.
- [ ] `python3 -I .claude/plugins/dev-kit/skills/core/scripts/dev_state.py gate M1 passed --score 80` is refused (below 85); with the real score it succeeds and `status --short` shows `M1:passed(NN)`.
- [ ] A seeded flaw (e.g. an unauthenticated route) produces a `critical` security finding, a security score ≤ 40, gate `pending`, and a fix task that is picked first by `next`.

## 4. Brownfield onboarding
- [ ] In a git repo with `pyproject.toml` (fastapi + pytest), tests and a README, no `.dev/`, run `/dev-kit:start "add X"`: it creates tag `dev-kit-baseline`, `.dev/discovery.md`, `.dev/qa/baseline.md`, ADRs with `source: discovered`, `brownfield` in `state.json`, and only then runs `interview --express` with block 5 pre-filled as inferred.
- [ ] A failing test in the repo becomes an `intangible` issue, not a finding; existing README/docs/source are unchanged after onboarding.
- [ ] `prd` tags ACs `existing`/`new`; `plan` has no walking-skeleton M1 and no tasks for `existing` ACs; `architecture` keeps the stack.
- [ ] `qa M1` scores only `git diff dev-kit-baseline..HEAD`; a legacy flaw in untouched code is reported `"legacy": true`, becomes an `intangible` issue and does not block the gate.
- [ ] Repo with Conventional Commits, `docs/adr/0001-*.md`, tag `v2.3.0` and a deploy workflow: `discovery.md` §11 proposes `commit_style` `{type}: {summary}`, the ADR appears as `source: imported`, `production.method` is `external`; a task commit is `feat: …` with trailer `Refs: T-001`; `release --dry-run` proposes `v2.4.0`.
- [ ] Mode **maintenance** with first milestone `7`: after onboarding the phase is `stable` (no task yet; `construction · M7` once the first issue adds a task), `plan.md` has an empty `## M7 — Maintenance`, reviews `prd`/`design`/`plan` are `n/a`; `/dev-kit:issue` with a medium bug schedules a task in M7 (no queue); `status --short` says `existing project: maintenance`; when the task is done `implement` points to `qa M7`; after the gate passes, the next issue opens `M8 — Maintenance` (`add-task` into M7 is refused).
- [ ] Onboarding order: `.dev/state.json` exists before discovery; a failing test at the baseline becomes issue `origin: baseline` (visible in `backlog --json`); `session_start` and the onboarding's `skill_start` are in `telemetry.jsonl`.
- [ ] With `autonomy.level unattended` in the existing project, `pause_policy.dirty_tree` is still `ask`; an uncommitted file of the user is never stashed.
- [ ] Switching maintenance → feature (`/dev-kit:start "add X"`) reopens reviews `prd`/`design`/`plan` as `pending`.
- [ ] A repo with only `setup.py` (or only PHP files, or `apps/web/package.json`) is detected as existing (`"greenfield": false`) and onboarded.
- [ ] Mode **import** with a `docs/prd.md`: the interview asks only blocks the document does not cover and `prd` cites the original ids.
- [ ] Delete `.dev/prd.md` and run `/dev-kit:start`: it routes to `prd` and says the stage was skipped; `status --short` says `phase: conception · prd`; `dev_state.py set phase plan` is refused (the phase is derived).

## 5. Gaps, usability, docs, release
- [ ] `/dev-kit:interview --gaps` lists exactly the open `Q-nnn` rows; answering one that contradicts an assumption creates a superseding ADR and (when needed) a fix task.
- [ ] `/dev-kit:usability --url http://localhost:3000` (if the app runs) runs 4 auditors in parallel, captures screenshots, writes `qa/ux/report.md` with Nielsen/WCAG references and records review `ux` with a score.
- [ ] `/dev-kit:docs all` writes README, CHANGELOG, user guide, CLAUDE.md section; `review docs` executes the README commands in a temp clone and scores the result.
- [ ] `/dev-kit:release --dry-run` reports the checklist including the release audit score; the checklist refuses while a milestone is half built; the real run tags `v0.1.0` and records it (`dev_state.py release-record`): the next release is empty and, with no issue queued, `status` says `Phase: stable`; nothing is pushed unless `may_push` is true. A new issue afterwards brings the phase back to `construction`.
- [ ] With `## R1`/`## R2` headings in `plan.md`: no task of R2 starts while R1 is not released; when R1's milestones are closed, `/dev-kit:release` writes `.dev/releases/R1/review.md`, submits it and stops; the board shows R1 in Needs you and on the Construction release strip with Approve and Reject; a rejection with two lines adds `M<k>.1 — R1 · Fixes 1` (after R1's last milestone `M<k>`) with two fix tasks before R2; an approval lets `release` tag, deploy, smoke and record R1, and R2 starts.

## 6. Autonomy policy
- [ ] With `autonomy.level = cautious`, `implement` asks before a library choice; with `high` it logs an ADR instead.
- [ ] A `paid_services` decision triggers a question at every supervised level; under `unattended` it is parked (`pause_policy.paid_services` = `park`), never decided alone.
- [ ] `dev_state.py set autonomy.level cautious` raises the cut-offs to 90/85/75 and moves `library_choice` to `always_ask`; back to `high` restores the lists.

## 7. Board, costs, feedback, deploy, issues
- [ ] `/dev-kit:board` opens once (a second call reuses it); `--host 0.0.0.0` prints an access link and the page answers "Access link required" without it; `stop` ends it. In a folder with an unrelated `.dev/` and no state, the hook and `board status` create nothing.
- [ ] `/dev-kit:costs` shows a table by stage; in an existing project `--all` starts at the adoption.
- [ ] `/dev-kit:feedback` writes `feedback-report-<stamp>.md` and `telemetry-export-<stamp>.json`; stages recorded only as `n/a` show `—`.
- [ ] `/dev-kit:deploy --dry-run` changes and records nothing; a real deploy records `Production:` in `status`; with `method external` it runs no install command.
- [ ] Hotfix: `/dev-kit:issue` with a critical bug → `implement` → `qa --scope T-xxx` records review `hotfix-T-xxx` and leaves the milestone gate as it was → `release --hotfix` tags a patch and deploys once.
- [ ] Buffer and cool-down: queued standard issues enter the next milestone through `pull-issues`; with cool-down on, small ones enter right after a gate.
- [ ] `plan replan` dropping a task uses `dev_state.py drop`; the milestone can still complete and `release` does not wait for it.

## 8. Rework and cost (1.15–1.17)
- [ ] An auditor writes its result to the `Output file:` and answers in ≤ 5 lines; a result with `status`, `Major` or a repeated id is fixed by `dev_score.py check --fix`; an unknown severity makes `check` exit 1.
- [ ] `agent_spawn` events show the tier's model for every agent (copy-reviewer on haiku even when the session runs on opus).
- [ ] `/dev-kit:costs` after a session counts every request (no single `unknown` record) and prices gateway model names.
- [ ] Changing the PRD after the plan review: `dev_state.py stale` lists architecture and plan, `status --short` shows them, and `review plan` refreshes them before spawning the reviewer.
- [ ] Round 2 of a document review: the reviewer gets `Changes since round 1:`; findings outside the change are deferred; `convergence` is printed; a `contradicts` finding is capped at medium.
- [ ] `implement` records the green suite per commit; the gate's test auditor reports `tests_reused: true` when nothing changed.
- [ ] A UI task runs the self-check and the haiku copy and static a11y checks into `.dev/qa/T-xxx/precheck/`.
- [ ] A gate with fixes: all fix tasks run, then one `qa` round, one local preview, and production only after the gate passes.
- [ ] `--parallel` implementers link `node_modules` instead of installing; `plan` adds the QA harness task when `dev_detect_stack.py --tools` finds none.
- [ ] (1.18) Gate round 2 after one fix: `ledger plan` lists the fixed file, files with findings and one spot check; `SC select` carries the untouched dimensions; `consolidate` keeps the open ids; `release` audits with `--no-cache`.
- [ ] (1.18) `/dev-kit:costs --time` shows time per agent and skill and the ledger reuse table.
- [ ] (1.19) A consumer task's `dev_state.py brief` shows the producer's contract; `xref` flags `consumes` without `contract`; two parallel tasks cannot hold the same `lock`; `docs` merges `changelog.d/`.

## 9. Requests from the board (1.23–1.26)
These need a real Claude Code with the plugin's hooks and monitors. The step-by-step script that records what this Claude Code version does, to send back to the kit's author, is [board-autonomy-check](board-autonomy-check.md).
- [ ] `/dev-kit:board` prints `requests: on` and `listening`; the Requests card says "Claude Code: listening". ▶ next to "Next step" starts `/dev-kit:implement` in that session with nobody typing; the board shows the request running, then `done` with its note.
- [ ] In a session that did not run `/dev-kit:board`, a queued request shows on the session banner (at the next prompt or at the end of the turn) as `1 request waiting · run /dev-kit:worker` and on the status line as `▣ 1`.
- [ ] "Go on by itself": after a request the next step starts alone; it stops with the reason on an open question, a blocked task, a failed request and when the milestone closes; "Go on" resumes.
- [ ] A permission prompt during a board request appears in Needs you with Allow, Allow for this session (when Claude Code suggests a rule) and Deny; the answer reaches Claude Code; with no answer it is denied after 10 minutes; outside a board request the terminal prompt works as before.
- [ ] The tab title shows "(n) Needs you" and the icon gets its dot while a question or a permission waits.
- [ ] `/dev-kit:board --trusted-host <name>` behind a reverse proxy: the page loads and its buttons work through the proxy's https address; another host name is refused.
- [ ] `/dev-kit:worker` takes the request, runs the skill and closes it; the board shows `done` with the note. A second Claude Code session in the same project running `/dev-kit:worker` is refused while the first is alive.
- [ ] A question raised while a request runs appears in Needs you with its options; the request shows "needs your answer"; answering on the board queues the answer, the worker records it and resumes the request.
- [ ] "Replan the milestones" screen (Planning): drag a task and an open issue into a new milestone, Send; the worker runs `plan-apply` and `plan.md`, state and `issues.md` agree; a draft that breaks a dependency cannot be sent.
- [ ] "Replan the milestones" screen (Planning) with planned releases (R1 and R2 in `plan.md`): switch to Releases, drag a pending milestone from R2 to R1 (leave R2 with at least 2), create R3, Send; the worker runs `plan-apply` and the `## R` sections of `plan.md`, Roadmap and Construction chevrons agree; a release left with 1 milestone, or a closed or released one, is refused with the reason.
- [ ] Releases tab (planned releases in `plan.md`): a card per release with tasks, milestones, QA gates, cost, time and pace; picking a card opens its page (also `#release:R2`) with stages, milestones, fixes, what holds it back, QA scores, gate history and documents; a release waiting for approval shows its count on the tab and Approve and Reject on its page; after a rejection the history lists the fixes milestone.
- [ ] Cancel a running request: the worker stops at the next safe point and the task is blocked with the reason; Pause queue: nothing new is taken.
- [ ] Where plugin monitors do not start (an older Claude Code, `claude -p`): `/dev-kit:board` says "not listening", the card says "open, not listening", and `/dev-kit:worker` runs the queue when asked.
