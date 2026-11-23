# dev-kit

A [Claude Code](https://claude.com/claude-code) plugin where a team of specialised agents builds a complete application and keeps it evolving: from the requirements interview to releases, and on through every bug, improvement and scope change until the product is stable.

You answer one thorough interview. The kit then writes the PRD, architecture and design, plans the work, implements it milestone by milestone with tests, audits every milestone and ships releases. It stops only when it needs a decision from you, and everything it produces is kept in a `.dev/` folder inside your project, so you can stop and resume at any time.

## How a project moves

<p align="center">
  <img src=".github/assets/dev-kit-lifecycle.svg" alt="The project lifecycle as four chevrons: 1 conception (interview, PRD, architecture, UX, UI, each reviewed), 2 planning (milestones grouped into releases R1, R2…), 3 construction (milestone by milestone, release by release) and 4 stable (nothing open, everything released). Under construction, two levels: the milestone loop runs on its own (plan, build, QA and fixes, smoke, deploy when per milestone, closed); a release, once all its milestones are closed, goes through audit, release review, your approval, production and smoke, released, and a rejection becomes a fixes milestone in the same release. Arrows back: a bug or improvement returns to construction, a scope change to conception." width="900">
</p>

**Conception** and **planning** happen once at the start, and again, only for what changed, whenever the scope changes. **Construction** builds the product one milestone at a time: each milestone has its own cycle (build, QA and fixes, deploy), so building and QA are never "the project's phase", they happen in every milestone. The plan groups milestones into **releases**: milestones run on their own, and each release waits for **your approval** before it goes to production (a rejection becomes a fixes milestone in the same release). When nothing is open and everything is released, the project is **stable**; the next issue starts the cycle again. The kit works out the phase from what is in `.dev/`, so it never gets out of step with the work ([concepts](.claude/plugins/dev-kit/docs/concepts.md#lifecycle-conception-planning-construction-19)).

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/dev-kit-board-dark.png">
    <img src=".github/assets/dev-kit-board.png" alt="dev-kit board of a sample project, Larder: the project lifecycle as chevrons (conception and planning done, construction current with 3 of 6 milestones closed, stable next, 1 of 3 releases released), a highlighted Needs you strip with an open question and its recommended answer, the releases R1 to R3 with the stages of the current one (milestones, release review, your approval, production, released), the milestones M3 and M4 with the stages of M4 and two implementer agents running in Build, the forecast to finish, the Requests panel and the activity log" width="900">
  </picture>
  <br>
  <sub><code>/dev-kit:board</code> shows the build in <b>real time</b> in your browser: where the project is in its lifecycle, what needs you, the stage of the release and of the milestone with what is running in it, a forecast to finish, then the task kanban, quality gates, burndown and activity. More screenshots, and the full flow as a diagram, in the <a href="GET_STARTED.md">quickstart</a>.</sub>
</p>

## What it does

- **Skills for the whole lifecycle**, invoked as `/dev-kit:<name>`, such as `interview`, `prd`, `architecture`, `ux`, `ui`, `plan`, `implement`, `test`, `qa`, `review`, `usability`, `docs`, `release`, `deploy`, plus `autopilot`, `status`, `board`, `backlog`, `issue`, `costs`, `feedback`, `help` and `start`.
- **Specialised agents** that the skills call: an implementer, an architecture consultant and a team of read-only reviewers (code, security, tests, accessibility, data, performance, copy and more).
- **Quality gates**: each milestone ends with a scored review (0-100 per dimension) that must clear a cut-off before the next one starts.
- **Planned releases with one human gate**: the plan groups milestones into releases (R1, R2…: a complete value journey each, 2–5 milestones, a risky delivery ends one). Milestones run on their own; when a release is complete, `/dev-kit:release` audits it, writes a release review and waits for you to approve (production deploy, smoke, release) or reject with what must change (a fixes milestone in the same release).
- **Checkpoints where your judgement matters**: after their reviews pass, you confirm the PRD and the plan on the board (or ask for changes) before the cycle goes on. Each milestone has an `exit_check` (a test, a command or acceptance criteria) that must pass at its gate, besides a hard floor of build, tests and secrets.
- **Deploy without release** (optional): with release flags, each milestone can go to production behind its release's flag, turned on only after you approve the release; a production health check runs on a schedule and opens an urgent issue when it fails.
- **Adjustable autonomy**: from supervised (asks at each decision, always with a recommendation) to unattended (parks what needs you and keeps going).
- **Bugs and ideas** found at any time are classified and routed with `/dev-kit:issue`, without renumbering the plan: bugs and improvements go straight to construction; a scope change reopens conception and planning while the current milestone keeps going.
- **Existing projects too**: in a codebase not built with dev-kit, `/dev-kit:start` first tags a baseline and learns the project (stack, commands, your commit and version conventions, existing docs). You pick a mode (new feature, maintenance only, or import your own PRD/specs); audits then judge only what changed, and old problems become issues instead of blocking.
- **Live board**: `/dev-kit:board` shows the build in the browser, on this machine or shared on your network with a private link, in English or Portuguese. It answers questions, confirms checkpoints, approves releases and allows or denies tool requests, and its built-in worker runs what you ask there without a Claude Code session open.
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
