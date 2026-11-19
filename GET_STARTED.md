# Get started with dev-kit

The minimum you need to build your first project. Install the plugin first (see the [README](README.md#install)).

## 1. Open a folder in Claude Code

```
mkdir my-app && cd my-app
claude
```

dev-kit works on the folder where you run it. It will run `git init` for you if needed, because it makes one commit per task.

**Already have code?** Open Claude Code in that repository and run `/dev-kit:start <the change you want>`. The kit first adopts the project without touching your code: it tags a baseline, writes `.dev/discovery.md` and asks whether you want a new feature, maintenance only (bugs and small improvements through `/dev-kit:issue`) or to import your existing PRD/specs. Then continue from step 3.

## 2. Start

```
/dev-kit:start a personal expense tracker with login and monthly reports
```

Describe your idea in one sentence, or run `/dev-kit:start` with no text. The kit starts an interview about the product, users, scope, data, stack, design, quality bar and how much autonomy you want it to have. Answer in your own language; every question comes with a recommended option. The answers are saved in `.dev/brief.md`.

## 3. Plan, then read the plan

```
/dev-kit:autopilot --until plan
```

This writes and reviews the PRD, architecture, UX/UI design and implementation plan, all in `.dev/`. Read `.dev/prd.md` and `.dev/plan.md` and correct anything you disagree with before any code exists.

## 4. Build

```
/dev-kit:autopilot
```

The kit implements the plan milestone by milestone, with tests, and runs a quality gate at the end of each one. It pauses only for decisions that need you.

## Day-to-day commands

| I want to... | Run |
|---|---|
| resume the project after a break | `/dev-kit:start` |
| know what to do next, or ask a "how do I...?" question | `/dev-kit:help` |
| see progress and blockers | `/dev-kit:status` |
| watch it live in the browser | `/dev-kit:board` |
| report a bug or ask for a change | `/dev-kit:issue "what happens"` |
| see everything still pending | `/dev-kit:backlog` |
| put an approved milestone in production | `/dev-kit:deploy` |
| ship a version | `/dev-kit:release` |
| see how much it cost | `/dev-kit:costs` |
| get an evaluation of the session | `/dev-kit:feedback` |

## Good to know

- **Everything is a file.** Specs, plan, state and logs live in `.dev/`; never edit `.dev/state.json` by hand.
- **You can go step by step** instead of autopilot: `prd`, `review prd`, `architecture`, `ux`, `ui`, `review design`, `plan`, `review plan`, `implement`, `qa`, in that order (each review scores the document; `release` requires them).
- **Stuck or lost?** Run `/dev-kit:help`, or see [troubleshooting](.claude/plugins/dev-kit/docs/troubleshooting.md).

Next: the longer [getting-started guide](.claude/plugins/dev-kit/docs/getting-started.md) and the [recipes](.claude/plugins/dev-kit/docs/recipes.md).
