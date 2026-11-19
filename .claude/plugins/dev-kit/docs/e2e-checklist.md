# dev-kit end-to-end checklist (manual)

Install the plugin (`/plugin install dev-kit@dev-kit`) or run `claude --plugin-dir .claude/plugins/dev-kit` in a scratch project, then start Claude Code there.

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
- [ ] `.dev/brief.md` written in pt-BR, one section per block; `.dev/state.json` has `language: pt-BR`, `autonomy.level`, `phase: prd`; `.dev/decisions.md` has initial ADRs.
- [ ] Closing summary + single confirmation question.

## 2. Autonomous design phases
- [ ] `/dev-kit:autopilot --until plan` produces `prd.md` (ACs numbered, testable), `architecture.md` (stack table, data model, contracts), `design/ux-flows.md`, `design/ui-spec.md`, `plan.md` with ≥ 2 milestones; `state.json` has tasks; **no question asked** outside `always_ask` categories; assumptions logged as `ADR-nnn (auto)` and `Q-nnn` rows.
- [ ] `/dev-kit:status` shows milestones, next task `T-001`.

## 3. Implementation and gate
- [ ] `/dev-kit:implement --tasks 2` → two commits `[T-001] …`, `[T-002] …`; `state.json` tasks done with SHAs; tests green.
- [ ] Kill the session; restart Claude in the folder → `/dev-kit:start` shows the 3-line `[dev-kit]` status and resumes without re-interviewing.
- [ ] Finish M1 (`implement --milestone M1`); `dev_state.py next` exits 3 with "gate of M1 is pending".
- [ ] `/dev-kit:qa M1` spawns the applicable auditors in parallel (see 3b); writes `qa/M1/report.md`, `findings.json` + `scores.json`; blocking findings become `fix` tasks placed first in `next`; gate `pending` or `passed` accordingly.
- [ ] If pending: `implement` picks the fix tasks first; `qa M1` again → `passed`.

## 3b. Quality score and cut-off
- [ ] In the interview, block 8 offers `standard | premium | prototype`; `state.json` has `autonomy.quality` with the chosen numbers.
- [ ] `review prd`, `design` and `plan` each spawn the right reviewer, write `.dev/reviews/<target>/scores.json`, and `dev_state.py status` shows `reviews: prd:pass(NN) ...`. A failing review sends the artifact back to its producing skill and re-scores with a fresh reviewer.
- [ ] `autopilot` does not start `architecture` before review `prd` passes, `plan` before `design`, `implement` before `plan`.
- [ ] `qa M1` on a UI milestone runs the 11 auditors that apply (core 4, operations, data, dependencies, performance, a11y, visual, copy) and skips the rest with a reason; `.dev/qa/M1/scores.json` lists all dimensions.
- [ ] `python3 -I .claude/plugins/dev-kit/skills/core/scripts/dev_state.py gate M1 passed --score 80` is refused (below 85); with the real score it succeeds and `status` shows `M1:passed(NN)`.
- [ ] A seeded flaw (e.g. an unauthenticated route) produces a `critical` security finding, a security score ≤ 40, gate `pending`, and a fix task that is picked first by `next`.

## 4. Brownfield onboarding
- [ ] In a git repo with `pyproject.toml` (fastapi + pytest), tests and a README, no `.dev/`, run `/dev-kit:start "add X"`: it creates tag `dev-kit-baseline`, `.dev/discovery.md`, `.dev/qa/baseline.md`, ADRs with `source: discovered`, `brownfield` in `state.json`, and only then runs `interview --express` with block 5 pre-filled as inferred.
- [ ] A failing test in the repo becomes an `intangible` issue, not a finding; existing README/docs/source are unchanged after onboarding.
- [ ] `prd` tags ACs `existing`/`new`; `plan` has no walking-skeleton M1 and no tasks for `existing` ACs; `architecture` keeps the stack.
- [ ] `qa M1` scores only `git diff dev-kit-baseline..HEAD`; a legacy flaw in untouched code becomes an `intangible` issue and does not block the gate.

## 5. Gaps, usability, docs, release
- [ ] `/dev-kit:interview --gaps` lists exactly the open `Q-nnn` rows; answering one that contradicts an assumption creates a superseding ADR and (when needed) a fix task.
- [ ] `/dev-kit:usability --url http://localhost:3000` (if the app runs) runs 4 auditors in parallel, captures screenshots, writes `qa/ux/report.md` with Nielsen/WCAG references and records review `ux` with a score.
- [ ] `/dev-kit:docs all` writes README, CHANGELOG, user guide, CLAUDE.md section; `review docs` executes the README commands in a temp clone and scores the result.
- [ ] `/dev-kit:release --dry-run` reports the checklist including the release audit score; real run tags `v0.1.0` and sets phase `done`; nothing is pushed unless `may_push` is true.

## 6. Autonomy policy
- [ ] With `autonomy.level = cautious`, `implement` asks before a library choice; with `high` it logs an ADR instead.
- [ ] A `paid_services` decision always triggers a question regardless of level.
