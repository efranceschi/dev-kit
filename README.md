# dev-kit

A [Claude Code](https://claude.com/claude-code) plugin where a team of specialised agents builds a complete application and keeps it evolving: from the requirements interview to releases, and on through every bug, improvement and scope change until the product is stable.

You answer one thorough interview. The kit then writes the PRD, architecture and design, plans the work, implements it milestone by milestone with tests, audits every milestone and ships releases. It stops only when it needs a decision from you, and everything it produces is kept in a `.dev/` folder inside your project, so you can stop and resume at any time.

## How a project moves

<p align="center">
  <img src=".claude/plugins/dev-kit/docs/dev-kit-flow.svg" alt="The dev-kit flow. Conception: interview, PRD, review, your confirmation of the PRD, architecture, UX and UI when there is an interface, design review. Planning: the plan groups milestones into releases, each milestone with an exit check, then the plan review, your confirmation and sync-plan. Milestones, on their own: pull issues, implement, QA, gate (hard floor, exit check, cut-offs); a failed gate creates fix tasks, a passed one goes to smoke and deploy. Releases: usability and docs, release audit, release review, your approval, production with the flag on, released; a rejection becomes a fixes milestone in the same release. Stable: the production health check runs and each issue is classified as expedite, standard or a scope change, which return to construction or conception." width="900">
</p>

The diagram reads top to bottom, one lane per stage. **Conception** (interview, PRD, architecture, UX and UI, each reviewed, and the PRD confirmed by you) and **planning** (milestones grouped into releases, each milestone with an exit check, the plan confirmed by you) happen once at the start, and again, only for what changed, whenever the scope changes. **Milestones** then run on their own: pull the issues, implement, QA, and a gate that either creates fix tasks or sends the milestone to smoke and deploy. When the milestones of a **release** are closed, it gets its usability and docs checks, an audit and a release review, and waits for **your approval** before production (a rejection becomes a fixes milestone in the same release). When nothing is open and everything is released, the project is **stable**: a production health check keeps running, and each new issue is classified and sent back to the milestones (a bug or improvement) or to conception (a scope change). The kit works out the phase from what is in `.dev/`, so it never gets out of step with the work ([concepts](.claude/plugins/dev-kit/docs/concepts.md#lifecycle-conception-planning-construction-19)).

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/dev-kit-board-dark.png">
    <img src=".github/assets/dev-kit-board.png" alt="dev-kit board of a sample project, Larder: the Autopilot switch on and running for 24 minutes, the lanes of the flow as tabs (conception and planning done, the milestones lane current with M4 at 3 of 6 tasks, releases 1 of 3 released, stable), a red Needs you button with one item, the stages of M4 as a flow (pull issues done, implement in progress with two implementer agents, QA, gate, deploy) and the task board in four columns of equal height" width="900">
  </picture>
  <br>
  <sub><code>/dev-kit:board</code> shows the build in <b>real time</b> in your browser and, with its <b>Autopilot</b> switch on, drives it: one screen per lane of the flow, laid out like the diagram: where the project is, what needs you, the stage of the milestone or release with what is running in it, a forecast to finish and the task board; details, metrics and activity one click away. More screenshots in the <a href="GET_STARTED.md">quickstart</a>.</sub>
</p>

## What it does

- **Skills for the whole lifecycle**, invoked as `/dev-kit:<name>`, such as `interview`, `prd`, `architecture`, `ux`, `ui`, `plan`, `implement`, `test`, `qa`, `review`, `usability`, `docs`, `release`, `deploy`, plus `autopilot`, `status`, `board`, `backlog`, `issue`, `costs`, `feedback`, `debug`, `help` and `start`.
- **Specialised agents** that the skills call: an implementer, an architecture consultant and a team of read-only reviewers (code, security, tests, accessibility, data, performance, copy and more).
- **Quality gates**: each milestone ends with a scored review (0-100 per dimension) that must clear a cut-off before the next one starts.
- **Planned releases with one human gate**: the plan groups milestones into releases (R1, R2…: a complete value journey each, 2–5 milestones, a risky delivery ends one). Milestones run on their own; when a release is complete, `/dev-kit:release` audits it, writes a release review and waits for you to approve (production deploy, smoke, release) or reject with what must change (a fixes milestone in the same release).
- **Checkpoints where your judgement matters**: after their reviews pass, you confirm the PRD and the plan on the board (or ask for changes) before the cycle goes on. Each milestone has an `exit_check` (a test, a command or acceptance criteria) that must pass at its gate, besides a hard floor of build, tests and secrets.
- **Deploy without release** (optional): with release flags, each milestone can go to production behind its release's flag, turned on only after you approve the release; a production health check runs on a schedule and opens an urgent issue when it fails.
- **Autopilot from the board**: an **Autopilot** switch in the board's top bar runs the whole build headless, one milestone per run, until a release waits for your approval; questions and permission prompts wait in Needs you while independent work goes on, and **Implementers at once** (1 to 6) sets how many tasks are built in parallel. You can close Claude Code meanwhile.
- **Adjustable autonomy**: from supervised (asks at each decision, always with a recommendation) to unattended (parks what needs you and keeps going).
- **Bugs and ideas** found at any time are classified and routed with `/dev-kit:issue`, without renumbering the plan: bugs and improvements go straight to construction; a scope change reopens conception and planning while the current milestone keeps going.
- **Existing projects too**: in a codebase not built with dev-kit, `/dev-kit:start` first tags a baseline and learns the project (stack, commands, your commit and version conventions, existing docs). You pick a mode (new feature, maintenance only, or import your own PRD/specs); audits then judge only what changed, and old problems become issues instead of blocking.
- **Live board**: `/dev-kit:board` shows the build in the browser, drawn like the diagram above: one tab per lane, each screen fitting the window, a Map of the whole flow one click away, a red **Needs you** button when something waits for you, the **Autopilot** switch, a **Live** list of what runs now, and details, metrics and activity in panels instead of long pages. It runs on this machine or is shared on your network with a private link, in English or Portuguese, light or dark. It answers questions, confirms checkpoints, approves releases and allows or denies tool requests, and its built-in worker runs what you ask there without a Claude Code session open.
- **Deploy, costs and feedback**: production deploys with backup and smoke checks (`/dev-kit:deploy`), token cost per stage (`/dev-kit:costs`) and a graded evaluation of each session (`/dev-kit:feedback`).
- **Resumable**: state lives in `.dev/` and is reconciled with git on every `/dev-kit:start`.

The kit talks to you, and writes your project's artifacts, in your language. Its own files are in English.

## Install

This repository is a Claude Code plugin marketplace (`dev-kit`) that contains the `dev-kit` plugin. In Claude Code, register the marketplace once and install the plugin:

```
/plugin marketplace add efranceschi/dev-kit
/plugin install dev-kit@dev-kit
```

To use a local clone instead, replace the first line with `/plugin marketplace add /path/to/this/folder`.

To try it without installing, for example while editing the kit:

```
claude --plugin-dir ./.claude/plugins/dev-kit
```

**Teams:** to offer the plugin to everyone who opens a project, add this to the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "dev-kit": { "source": { "source": "github", "repo": "efranceschi/dev-kit" } }
  },
  "enabledPlugins": { "dev-kit@dev-kit": true }
}
```

**Claude Agent SDK:** there is no marketplace step. Clone this repository and load the plugin by path:

```python
ClaudeAgentOptions(plugins=[{"type": "local", "path": "/path/to/dev-kit/.claude/plugins/dev-kit"}])
```

```ts
query({ prompt, options: { plugins: [{ type: "local", path: "/path/to/dev-kit/.claude/plugins/dev-kit" }] } })
```

Requirements: Claude Code, `git` and Python 3.10+ (the kit's helper scripts use only the standard library), on Linux or macOS (on Windows use WSL: the board server needs `fcntl`). Keep the `core` skill installed next to the other skills; it holds the scripts and templates they share.

## Get started

Read **[GET_STARTED.md](GET_STARTED.md)** for the minimum you need to run your first project.

## Documentation

Full documentation lives in [`.claude/plugins/dev-kit/docs/`](.claude/plugins/dev-kit/docs/):

| Page | For |
|---|---|
| [getting-started](.claude/plugins/dev-kit/docs/getting-started.md) | a step-by-step first project |
| [stages](.claude/plugins/dev-kit/docs/stages.md) | each stage of the flow (conception, planning, milestones, releases, stable, coming from 2.x): what to run, what the board shows, what needs you, how to get unstuck |
| [recipes](.claude/plugins/dev-kit/docs/recipes.md) | "how do I...?" (report a bug, overnight run, costs, deploy, resume) |
| [skills](.claude/plugins/dev-kit/docs/skills.md) | every skill: when to use it, arguments, examples, outputs |
| [agents](.claude/plugins/dev-kit/docs/agents.md) | every agent and who calls it |
| [concepts](.claude/plugins/dev-kit/docs/concepts.md) | lifecycle, state, gates, autonomy, issues, deploy, costs |
| [troubleshooting](.claude/plugins/dev-kit/docs/troubleshooting.md) | when something goes wrong |
| [glossary](.claude/plugins/dev-kit/docs/glossary.md) | short definitions of the terms the kit uses |
| [maintainers](.claude/plugins/dev-kit/docs/maintainers.md) | how the kit itself is built and tested |
| [CHANGELOG](.claude/plugins/dev-kit/CHANGELOG.md) | what changed in each version of the kit |

Inside Claude Code, `/dev-kit:help` answers "what do I do next?" and `/dev-kit:help <question>` answers "how do I...?".

## Repository layout

```
.claude-plugin/marketplace.json   marketplace manifest
.claude/plugins/dev-kit/          the plugin: skills/, agents/, docs/
```
