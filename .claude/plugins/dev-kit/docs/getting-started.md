# Getting started

Your first project with the dev-kit, step by step. Inside Claude Code, `/dev-kit:help` answers any "how do I…?" at any time.

## 1. Install

```
/plugin install dev-kit@minhas-skills
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

This writes and reviews the PRD, architecture, UX/UI specs and the plan, then stops. Read `.dev/prd.md` and `.dev/plan.md`; mistakes are cheapest here. To change something: `/dev-kit:prd <change>` or `/dev-kit:plan replan`.

## 4. Build

```
/dev-kit:autopilot
```

It implements each milestone test-first (one commit per task), runs the quality gate (`qa`), fixes what failed and moves to the next milestone. Prefer to drive it yourself? `/dev-kit:implement --milestone M1`, then `/dev-kit:qa M1`.

## 5. Follow along

| You want | Run |
|---|---|
| where the project stands | `/dev-kit:status` |
| what is pending and what to do next | `/dev-kit:backlog` |
| report a bug or an idea | `/dev-kit:issue "what happens"` |
| how much it cost | `/dev-kit:costs` |
| an evaluation of the session | `/dev-kit:feedback` |
| help with anything | `/dev-kit:help <question>` |

## 6. Finish

`autopilot` continues with the usability audit, project docs and the release (`--dry-run` first). If production deploys are configured, `/dev-kit:deploy` installs each approved milestone or the release.

Next: [recipes](recipes.md) for common tasks, [concepts](concepts.md) for how it works, [skills](skills.md) for every command.
