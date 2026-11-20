# Getting started

Your first project with the dev-kit, step by step. Inside Claude Code, `/dev-kit:help` answers any "how do I…?" at any time.

## 1. Install

```
/plugin marketplace add efranceschi/dev-kit
/plugin install dev-kit@dev-kit
```

To try it without installing: `claude --plugin-dir .claude/plugins/dev-kit`. Open Claude Code in an empty folder (or an existing repository).

## 2. Start and answer the interview

```
/dev-kit:start a personal expense tracker with login and monthly reports
```

`start` runs `git init` if needed and opens the **interview**: about 10 short rounds (product, users, scope, data, stack, integrations, UX/UI, quality, autonomy, delivery). Every question has a recommended option and a "decide for me" choice. It ends with a summary to confirm and writes `.dev/brief.md`.

Answers that matter most later:
- **Quality bar** (`standard`, `premium`, `prototype`): the score each milestone must reach.
- **How much of the run you want to follow** (`supervised` or `unattended`).
- **Issues found during the build:** buffer per milestone and cool-down.
- **Delivery:** local preview per milestone and how production is deployed.

## 3. Review the documents first (recommended)

```
/dev-kit:autopilot --until plan
```

This finishes **conception** (PRD, architecture, UX/UI specs, each reviewed) and **planning** (the plan, reviewed), then stops. Read `.dev/prd.md` and `.dev/plan.md`; mistakes are cheapest here. To change something: `/dev-kit:prd <change>` or `/dev-kit:plan replan`.

## 4. Build

```
/dev-kit:autopilot
```

Now the project is in **construction**. It implements each milestone test-first (one commit per task), runs the quality gate (`qa`), fixes what failed and moves to the next milestone. Building and QA belong to each milestone, so the project phase stays `construction` the whole time; `/dev-kit:status` says which milestone (`construction · M2`). Prefer to drive it yourself? After each document, its review: `/dev-kit:prd` → `/dev-kit:review prd` → `/dev-kit:architecture` → `/dev-kit:ux` → `/dev-kit:ui` → `/dev-kit:review design` → `/dev-kit:plan` → `/dev-kit:review plan`; then `/dev-kit:implement --milestone M1` and `/dev-kit:qa M1`. `release` checks that every review passed.

## Already have a project?

Run `/dev-kit:start <the change you want>` in the repository root (commit pending work first). In a codebase that was not built with dev-kit, `start` first runs an **onboarding**: it tags the current commit `dev-kit-baseline`, writes `.dev/discovery.md` (stack, commands, your commit/version/CHANGELOG conventions, existing docs and ADRs), records the current test results in `.dev/qa/baseline.md`, and asks for an entry mode and the number of the first milestone (default `M1`; continue your own numbering if you have one):

| mode | use it when | what happens |
|---|---|---|
| feature | you want a new capability | short interview about the change, then PRD (as-built + new), plan and build |
| maintenance | you only fix bugs and make small improvements | an as-built PRD and an empty maintenance milestone are written for you; report work with `/dev-kit:issue`, and `/dev-kit:qa` gates each batch |
| import | you already have a PRD, specs or ADRs | they become the source; only the gaps are asked |

Nothing in your code, docs or history is changed by the onboarding. From then on QA scores only what changed since the baseline, and problems that were already there become low-priority issues instead of blocking the gate. Commits follow your project's style. If a stage was skipped, `/dev-kit:start` routes to it; a stage that does not apply (e.g. design when there is no new UI) is recorded as `n/a`.

## 5. Follow along

| You want | Run |
|---|---|
| where the project stands (lifecycle phase and step, release train) | `/dev-kit:status` |
| a live board in the browser (or on your phone) | `/dev-kit:board` (`--host 0.0.0.0` to share it) |
| what is pending and what to do next | `/dev-kit:backlog` |
| report a bug or an idea | `/dev-kit:issue "what happens"` |
| how much it cost | `/dev-kit:costs` |
| an evaluation of the session | `/dev-kit:feedback` |
| help with anything | `/dev-kit:help <question>` |

## 6. Release, and keep the product evolving

Each closed milestone joins the **release train**. A release ships the train between milestones: the usability audit (apps with a UI), the project docs and their review, then `/dev-kit:release` (`--dry-run` first), which tags the version and records it. `autopilot` runs this for you at the end of the planned milestones when your brief asks for releases. If production deploys are configured, `/dev-kit:deploy` installs each approved milestone or the release.

With no milestone open, no issue queued and everything released, the project is **stable**. That is a resting point, not an end:

- a bug or improvement (`/dev-kit:issue`) goes straight to construction, as a task in the current or next milestone;
- a scope change reopens **conception** (the PRD and the specs it affects) and **planning** (replan into future milestones), while the milestone being built keeps going;
- either way the project goes back to construction, and to stable after the next release.

The phase is worked out from `.dev/` (artifacts, reviews, gates, issues, releases), never typed in, so it always matches the work: see [concepts](concepts.md#lifecycle-conception-planning-construction-19).

Next: [recipes](recipes.md) for common tasks, [concepts](concepts.md) for how it works, [skills](skills.md) for every command.
