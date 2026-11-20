# dev-kit

A Claude Code plugin where specialised agents build a complete application and keep it evolving, from the requirements interview through milestones and releases until the product is stable. You answer one interview; the kit then specifies, plans, implements, tests, audits and releases almost on its own, and stops only when it needs a decision from you.

- **25 skills**, invoked as `/dev-kit:<name>`.
- **17 agents** the skills call: one implementer, one architecture consultant and 15 read-only reviewers.
- **Resumable state** in `.dev/` inside your project.
- **Lost?** `/dev-kit:help` tells you what to do next; `/dev-kit:help <question>` answers "how do I…?".

## Install

```
/plugin marketplace add efranceschi/dev-kit
/plugin install dev-kit@dev-kit
```

To try it without installing: `claude --plugin-dir .claude/plugins/dev-kit`. The `skills/core/` folder holds the kit's scripts, templates and checklists; keep it installed next to the other skills.

## First five minutes

```
/dev-kit:start a personal expense tracker with login and monthly reports
/dev-kit:autopilot --until plan      # writes and reviews PRD, architecture, design and plan; read them
/dev-kit:autopilot                   # builds milestone by milestone, with quality gates
```

Step by step: [getting started](docs/getting-started.md).

## What do you want to do?

| I want to… | Run |
|---|---|
| start a project, or resume one | `/dev-kit:start` |
| adopt the kit in an existing project | `/dev-kit:start <the change you want>` (runs the onboarding first) |
| know what to do next | `/dev-kit:help` |
| let the kit build it | `/dev-kit:autopilot` |
| build it step by step | `/dev-kit:prd` → `review prd` → `architecture` → `ux` → `ui` → `review design` → `plan` → `review plan` → `implement` → `qa` |
| see where things stand | `/dev-kit:status` |
| watch it live in the browser | `/dev-kit:board` (`/dev-kit:board stop` to stop) |
| drive it from the board | buttons on `/dev-kit:board`, then `/dev-kit:worker` runs the requests |
| report a bug or ask for an improvement | `/dev-kit:issue "what happens"` |
| see everything pending | `/dev-kit:backlog` |
| put it in production | `/dev-kit:deploy` |
| ship the closed milestones (the release train) | `/dev-kit:release` |
| know how much it cost | `/dev-kit:costs` |
| review the session or send feedback to the author | `/dev-kit:feedback` |
| run it overnight | [recipe](docs/recipes.md#let-it-run-overnight) |

All 25 skills by category, with arguments and examples: [skills](docs/skills.md).

## How it works, in short

```
conception    interview → prd → review → architecture → ux → ui → review
planning      plan → review                                  (and every replan)
construction  per milestone: pull issues → implement ⇄ test → qa gate → (fixes → qa)* → deploy
              release train: usability → docs → review → release   (closed milestones, between milestones)
stable        nothing open, everything released
                 ↺ bug or improvement → construction · scope change → conception and planning
```

- **The lifecycle is a cycle**, derived from `.dev/` and never set by hand: a scope change reopens conception and planning while the milestone in construction keeps going; `/dev-kit:status` shows the phase and step (`construction · M3`).
- **Milestones** M1, M2… are the cadence of construction; each ends with a scored quality gate (0–100 per dimension, cut-off set in the interview). Building and QA belong to the milestone, not to the project phase.
- **Autonomy** is yours to set: supervised (asks at each decision point, always with a recommendation) or unattended (parks what needs you and keeps going).
- **Bugs and ideas** found at any time enter by class of service without renumbering milestones.
- Every question comes with a recommended option; short tips (`💡`) explain each mechanism the first times it matters.

Full picture: [concepts](docs/concepts.md) and the [flow diagram](docs/dev-kit-flow.png).

## Documentation

| Page | For |
|---|---|
| [getting-started](docs/getting-started.md) | your first project |
| [recipes](docs/recipes.md) | "how do I…?" (bug, overnight run, costs, deploy, resume…) |
| [skills](docs/skills.md) | every skill: when, arguments, examples, outputs |
| [agents](docs/agents.md) | every agent: role, model tier, who calls it |
| [concepts](docs/concepts.md) | lifecycle, state, gates and scores, autonomy, isolation, issues, deploy, costs, logs |
| [glossary](docs/glossary.md) | lifecycle, release train, AC, ADR, gate, delta, buffer, cool-down, hotfix, slot, park… |
| [troubleshooting](docs/troubleshooting.md) | when something goes wrong |
| [maintainers](docs/maintainers.md) | layout, scripts, tests, how docs are generated |

## Language

The kit's files are in English. At run time it talks to you and writes your project's artifacts in your language; code, identifiers, ids and commit subjects stay in English.
