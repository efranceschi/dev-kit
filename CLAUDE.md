# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) containing one plugin, **dev-kit**, in `.claude/plugins/dev-kit/`. It is not an application: it is markdown skills and agents plus standard-library Python helper scripts. Everything the plugin does to a user's project is stored in that project's `.dev/` folder. Root `README.md` and `GET_STARTED.md` are user-facing; `.claude/plugins/dev-kit/docs/maintainers.md` is the authoritative maintainer guide (layout, script list, how files are found) — read it before structural changes.

## Commands

Run from `.claude/plugins/dev-kit/`:

```bash
python3 -I skills/core/tests/lint_suite.py                 # structural lint of skills, agents, docs, references
python3 -I -m unittest discover -s skills/core/tests -v    # all tests
python3 -I -m unittest skills/core/tests/test_dev_state.py # one test file (add .ClassName.test_name for one test)
python3 -I skills/core/scripts/dev_docs.py build           # regenerate generated docs
```

Try the plugin without installing: `claude --plugin-dir ./.claude/plugins/dev-kit`. Scripts always run with `python3 -I`, Python 3.10+, standard library only, Linux/macOS.

## Architecture

- `skills/<name>/SKILL.md` — 26 user-invocable skills (`/dev-kit:<name>`), prompts only. `agents/*.md` — 17 agents (implementer, architect, read-only reviewers); each must declare `model`, `effort` and `color` in frontmatter (the color is shown by Claude Code and by the board).
- `skills/core/` — a non-invocable support skill that holds everything shared: `scripts/` (`dev_state.py` is the central state machine over `.dev/state.json`; `dev_board.py` the board web server; `dev_worker.py` the board's request queue; `dev_score.py` QA scoring; plus ledger, telemetry, cost, docs, UI, hooks handler), `shared/` (`conventions.md` = rules every skill/agent follows, checklists, interview, templates, `help.json`, board front-end), and `tests/`.
- Path resolution: skills use `${CLAUDE_SKILL_DIR}/../core/...`; agents and shared files get no variable substitution and use `<KIT>` (the spawning skill passes `Kit root: <abs path>`); state commands use `${CLAUDE_PROJECT_DIR}`. Scripts import siblings by inserting their own folder in `sys.path`.
- `hooks/hooks.json` (all routed to `dev_agent_hook.py`) and `monitors/monitors.json` (board listener) are optional; nothing may depend on them.

## Rules when changing the kit

- **Every change bumps the version** in `.claude/plugins/dev-kit/.claude-plugin/plugin.json` and adds a `CHANGELOG.md` entry (commits are titled `dev-kit X.Y.Z: summary`).
- **All kit files are in English** (the lint rejects other languages; exceptions in `ALLOW_NON_ENGLISH` in `lint_suite.py`). Skills translate at display time.
- **Never hand-edit generated docs** `docs/skills.md`, `agents.md`, `recipes.md`, `glossary.md`. Add/change the skill's entry in `skills/core/shared/help.json` (its `args` must match the skill's `argument-hint`), then run `dev_docs.py build`. The lint fails on stale docs.
- Adding a skill also needs a telemetry stage, and counts in prose (e.g. "25 skills") and `conventions.md §N` references must stay correct; the lint checks these, as well as that every script command quoted in markdown exists with its flags. A skill must not tell the model to invoke a skill marked `disable-model-invocation`.
- Skill frontmatter accepts `argument-hint` and `disable-model-invocation`; uploads to claude.ai/API do not (see maintainers.md).
- Git: commit and push directly to `main`, no branches (owner's preference for this repo).
