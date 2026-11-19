# Concepts

How the dev-kit works, one idea per section. The normative rules live in `skills/core/shared/conventions.md` (section numbers in brackets). Quick definitions: [glossary](glossary.md). Task-oriented answers: [recipes](recipes.md).

## State in `.dev/`

Everything the kit knows about your project lives in `.dev/` inside the project, so any session can resume.

```
.dev/
  state.json          phases, milestones, tasks, gates, issues, settings (only via dev_state.py)
  brief.md  prd.md  architecture.md  plan.md  decisions.md (ADRs)  open-questions.md  issues.md  log.md
  design/             ux-flows.md, ui-spec.md
  qa/  reviews/       reports, scores and findings per milestone and per review
  costs/  feedback/   token usage and prices; session reports
  telemetry.jsonl     session log (no project data)
```

The Markdown files can be edited by hand. After a scope change run `/dev-kit:prd` or `/dev-kit:plan replan` so the change propagates. Each task becomes one commit `[T-003] feat: ...`; history is never rewritten.

## Flow and milestones

`start → interview → prd → review → architecture → ux → ui → review → plan → review`, then per milestone `implement ⇄ test → qa`, then `usability → docs → review → release`. See the [flow diagram](dev-kit-flow.png).

Milestones (M1, M2, …) are the project's cadence: `M2` starts only after the `M1` gate passes, and nothing ever inserts or renumbers a milestone.

## Quality scores and gates [§7]

Reviewers return findings in one JSON contract; `dev_score.py` turns them into a 0–100 score per dimension with a fixed formula.

- Penalty per finding: critical 40, high 20, medium 8, low 2 (low confidence counts half). A critical caps the dimension at 40, a high at 69.
- **Low cap:** low findings cost at most 10 points per dimension.
- **Dedupe:** the same finding reported by two audits of one dimension counts once.
- **Delta mode:** from round 2, auditors check whether the previous findings were closed; new low findings are recorded but not scored. Rounds converge instead of discovering a new layer of nits.
- A gate or review passes only with no critical/high finding, every dimension at its minimum (security 90, spec 85, tests 80, a11y 80, others 70) and the overall score at the cut-off (85 for milestones, 80 for documents). Presets: `standard` 85, `premium` 92, `prototype` 70.
- Failing gates create `fix` tasks. `dev_state.py` refuses a pass below the cut-off; `--force` needs your decision and an ADR.

## Autonomy and pauses [§6, §10]

The interview defines what the kit decides alone (recorded as `ADR (auto)`) and what it always asks: paid services, deleting data, public exposure, major scope changes, security model, credentials.

The **pause policy** decides what happens at each pause point: `ask`, `preauthorize` within a limit, `auto_recommend` (apply the recommendation), or `park` (record it, block only what depends on it, keep going). The `unattended` level fills the recommended values so autopilot never waits. Some floors cannot be lifted: no forced pass with security below its minimum or a critical/high open, no deletion of production data, no history rewrite, no AC change without you. Every question comes with a recommended option and its reason.

## Models and effort [§9]

Agents have a base model and effort by what they need: `speed` (haiku), `balanced` (sonnet), `quality` (opus). When a dimension fails, only it is re-run one step higher on the ladder (effort before model), and only with your consent (`model_policy`: `ask`, `preapproved`, `off`). The agents and their tiers: [agents](agents.md).

## Parallel work and isolation

Work is sequential except: `implement --parallel N` (each implementer in its own git worktree, integrated one at a time by the orchestrator), `qa` (auditors at once, heavy ones limited by CPUs) and the release audit. Every agent that runs commands gets a **slot**: its own port, database and scratch folder; it records and stops its own processes and formats only its own files. `dev_state.py cleanup` kills anything left behind, only inside the project.

## Issues and classes of service [§15]

Bugs and ideas found at any time go through `/dev-kit:issue`, which classifies them:

| class | for | enters |
|---|---|---|
| `expedite` | critical/high bug in delivered work | now, hotfix lane, one at a time, patch release |
| `current` | bug in the milestone being built | that milestone |
| `standard` | medium bug, valuable improvement | the next milestone's buffer (20%) |
| `intangible` | low bug, polish, tech debt | the cool-down after a gate (if on) |
| `change` | new or changed AC | PRD → review → replan, future milestones |

`/dev-kit:backlog` shows everything pending.

## Preview and production deploy [§11, §12]

Optionally, each approved milestone can run locally on `127.0.0.1` (`keep_running` or `smoke`). For production, the interview records method, host, timing (`per_milestone`, `on_release`, `manual`), smoke checks and prerequisites; `/dev-kit:deploy` installs with backup and dry-run, and `status` shows how far production is behind.

## Session log, feedback, costs and tips [§13, §14, §15]

- `.dev/telemetry.jsonl` records skills, agents, rounds, scores, pauses and errors at a high level. No project data enters it: keys and values are allowlisted in code.
- `/dev-kit:feedback` grades each stage with its reasons and writes a timestamped report you can send to the kit's author.
- `/dev-kit:costs` shows tokens and estimated US$ per stage from Claude Code's local transcripts (API-equivalent, not a charge).
- Short tips (`💡`) explain each mechanism the first times it matters (each at most twice; `autonomy.tips off` silences them).

## Language

The kit's files are in English. At run time it talks to you and writes your project's artifacts in your language (`state.json.language`). Code, identifiers, file names, ids and commit subjects stay in English.
