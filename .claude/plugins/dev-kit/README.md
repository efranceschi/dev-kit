# dev-kit

A Claude Code plugin where specialised agents build a complete application and keep it evolving, from the requirements interview through milestones and releases until the product is stable. You answer one interview; the kit then specifies, plans, implements, tests, audits and releases almost on its own, and stops only when it needs a decision from you.

- **27 skills**, invoked as `/dev-kit:<name>`.
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

Step by step: [getting started](docs/getting-started.md). What each stage expects from you: [stage by stage](docs/stages.md).

## What do you want to do?

| I want to… | Run |
|---|---|
| start a project, or resume one | `/dev-kit:start` |
| adopt the kit in an existing project | `/dev-kit:start <the change you want>` (runs the onboarding first) |
| know what to do next | `/dev-kit:help` |
| let the kit build it | `/dev-kit:autopilot` |
| build it step by step | `/dev-kit:prd` → `review prd` → `architecture` → `ux` → `ui` → `review design` → `plan` → `review plan` → `implement` → `qa` |
| see where things stand | `/dev-kit:status` |
| watch it live in the browser (read-only) | `/dev-kit:board` (`/dev-kit:board stop` to stop) |
| follow every project on this machine in one page (from any session) | `/dev-kit:spog` (`/dev-kit:spog stop` to stop) |
| report a bug or ask for an improvement | `/dev-kit:issue "what happens"` |
| see everything pending | `/dev-kit:backlog` |
| put it in production | `/dev-kit:deploy` |
| submit a finished release for your approval | `/dev-kit:release` |
| change autonomy, release flags, health check | `/dev-kit:settings` |
| know how much it cost | `/dev-kit:costs` |
| review the session or send feedback to the author | `/dev-kit:feedback` |
| draw the diagrams of what is being built: architecture, data model, deployment (shown on the board's Architecture tab) | `/dev-kit:diagram` |
| find out why a run looks stuck, or make a dump for a dev-kit patch | `/dev-kit:debug` |
| run it overnight | [recipe](docs/recipes.md#let-it-run-overnight) |

All 27 skills by category, with arguments and examples: [skills](docs/skills.md).

## How it works, in short

<p align="center">
  <img src="docs/how-it-works.svg" alt="How dev-kit works. Conception: interview, PRD, review, architecture, UX, UI, review. Planning: plan with milestones grouped into releases R1, R2…, review, and every replan. Construction, per milestone on its own: pull issues, implement and test, QA gate, fix rounds, smoke, deploy when per milestone; per planned release when its milestones are closed: usability, docs, review, release audit, release review, your approval, production and smoke, released, and a rejection becomes a fixes milestone in the same release, with no milestone of the next release starting before. Stable: nothing open, everything released; a bug or improvement returns to construction, a scope change to conception." width="900">
</p>

- **The lifecycle is a cycle**, derived from `.dev/` and never set by hand: a scope change reopens conception and planning while the milestone in construction keeps going; `/dev-kit:status` shows the phase and step (`construction · M3`).
- **Milestones** M1, M2… are the cadence of construction; each ends with a quality gate: a hard floor (build, tests, secrets), its `exit_check` and a score of 0–100 per dimension against the cut-off set in the interview. Building and QA belong to the milestone, not to the project phase.
- **Releases** R1, R2… group milestones; each is audited, gets a release review and waits for your approval before production. With release flags, milestones can reach production earlier behind the release's flag.
- **You confirm** the PRD and the plan at checkpoints, and approve each release; everything else runs on its own.
- **Autonomy** is yours to set: in four steps: supervised (asks at each decision point, always with a recommendation), assisted (decides the operational points, asks only what is yours), milestone (asks your questions together at the end of each milestone) or unattended (parks what needs you and keeps going).
- **Bugs and ideas** found at any time enter by class of service without renumbering milestones.
- Every question comes with a recommended option; short tips (`💡`) explain each mechanism the first times it matters.

Full picture: [concepts](docs/concepts.md) and the [flow diagram](docs/dev-kit-flow.svg) (a vector image: zoom in as much as you like).

## Documentation

| Page | For |
|---|---|
| [getting-started](docs/getting-started.md) | your first project |
| [stages](docs/stages.md) | each stage of the flow: what to run, what the board shows, what needs you, how to get unstuck; coming from 2.x |
| [recipes](docs/recipes.md) | "how do I…?" (bug, overnight run, costs, deploy, resume…) |
| [skills](docs/skills.md) | every skill: when, arguments, examples, outputs |
| [agents](docs/agents.md) | every agent: role, model tier, who calls it |
| [concepts](docs/concepts.md) | lifecycle, state, gates and scores, autonomy, isolation, issues, deploy, costs, logs |
| [glossary](docs/glossary.md) | lifecycle, next release, AC, ADR, gate, delta, buffer, cool-down, hotfix, slot, park… |
| [troubleshooting](docs/troubleshooting.md) | when something goes wrong |
| [maintainers](docs/maintainers.md) | layout, scripts, tests, how docs are generated |

## Language

The kit's files are in English. At run time it talks to you and writes your project's artifacts in your language; code, identifiers, ids and commit subjects stay in English.
