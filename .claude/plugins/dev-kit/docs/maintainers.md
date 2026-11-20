# Maintainers

How the plugin is built, tested and documented. Users do not need this page.

## Layout

```
.claude/plugins/dev-kit/
  .claude-plugin/plugin.json     name, version, description
  README.md                      landing page
  docs/                          user docs (four of them generated, see below), e2e checklist, flow diagram
  CHANGELOG.md                   kit versions (bump .claude-plugin/plugin.json and add an entry for every change)
  agents/*.md                    17 agents (model + effort in the frontmatter, conventions §9)
  hooks/hooks.json               optional SessionStart / SubagentStart / SubagentStop hooks for the board's live agents
  skills/*/SKILL.md              23 skills, invoked as /dev-kit:<name>
  skills/core/                   support skill, not invocable
    SKILL.md                     marker (disable-model-invocation: true, user-invocable: false)
    scripts/dev_state.py         state: init, sync-plan, next, start, done, block, unblock, drop, add-task, add-question,
                                 fix-tasks, gate, review, artifact, stale, xref, tests, ledger, brief, lock, strings, contrast, set, status, issues (add-issue, issue, pull-issues, cooldown, backlog),
                                 preview, deploy, cleanup, event, feedback, telemetry, tip, tips
    scripts/dev_score.py         0–100 score per dimension (low cap, dedupe, delta mode, legacy findings ignored)
    scripts/dev_ledger.py        work ledger: fingerprints of verified work, incremental plans, spot checks (conventions §18)
    scripts/dev_telemetry.py     allowlisted session log, stage grades (imported by the other scripts)
    scripts/dev_cost.py          token usage and estimated cost from Claude Code transcripts
    scripts/dev_docs.py          generated docs and /dev-kit:help answers
    scripts/dev_detect_stack.py  stack detection (manifests, manifests in subfolders, source files); --tools: QA tooling
    scripts/dev_board.py         local board server for /dev-kit:board (page in shared/board/)
    scripts/dev_agent_hook.py    hook handler that feeds the board's live agents (.dev/run/agents.jsonl)
    shared/conventions.md        the rules every skill and agent follows (§0–§18)
    shared/onboarding.md         adoption of an existing codebase (run by start)
    shared/help.json             catalog for help and the generated docs (English only)
    shared/tips.json             contextual tips (English only)
    shared/board/                index.html, board.js, board.css, favicon of the board
    shared/interview/ templates/ checklists/ prompts/   interview script, artifact templates, review checklists, output and isolation contracts
    tests/                       lint_suite.py, test_dev_state.py, test_dev_state_gaps.py, test_dev_board.py,
                                 test_dev_cost.py, test_dev_docs.py, test_dev_score.py, test_dev_ledger.py, test_dev_spec.py
```

Requirements: Python 3.10+ (standard library only) on Linux or macOS. Process checks (`cleanup`, board liveness) read `/proc` and are best effort on macOS; the board server uses `fcntl` and does not run on native Windows (use WSL).

## How the kit finds its own files

- Skills reference support files as `${CLAUDE_SKILL_DIR}/../core/...`; install `core` together with the other skills (`start` warns if it is missing).
- Agents and shared files get no variable substitution: they use `<KIT>`, and the skill that spawns an agent passes `Kit root: <absolute path>` in the prompt.
- State commands use `${CLAUDE_PROJECT_DIR}` so they keep pointing at the project.
- Scripts run with `python3 -I`; modules next to them are imported by inserting the script folder into `sys.path` explicitly.
- One optional hook set (`hooks/hooks.json`: SessionStart, SubagentStart, SubagentStop) feeds the board's live Agents panel through `dev_agent_hook.py`, which stores only ids and the agent type in `.dev/run/agents.jsonl`. It writes only inside a dev-kit project (`.dev/state.json` exists). Nothing depends on it: where the environment does not run plugin hooks, the board still shows agents logged by the skills (`agent_spawn`/`agent_end`), and the live badges simply do not appear for agents outside dev-kit skills.

## Frontmatter

Skills use `argument-hint` and `disable-model-invocation`, which Claude Code accepts. Uploads to claude.ai and to the API accept only `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`; for such uploads remove the other two fields (write-oriented skills may then be triggered automatically). Agents must declare `model` (haiku | sonnet | opus) and `effort`.

## Language

Every file of the kit is in English. Skills translate at display time into the user's language (tips, help, reports). The lint rejects non-English text; the only exceptions are listed in `ALLOW_NON_ENGLISH` in `lint_suite.py` (language examples and the Portuguese e2e scenario).

## Documentation

- Hand-written: `README.md`, `docs/getting-started.md`, `docs/concepts.md`, `docs/troubleshooting.md`, this page, `docs/e2e-checklist.md`.
- Generated from `skills/core/shared/help.json` and the frontmatter: `docs/skills.md`, `docs/agents.md`, `docs/recipes.md`, `docs/glossary.md`. Never edit them by hand.
- Adding or changing a skill: add or update its entry in `help.json` (category, one_line, when, args, examples, produces, related), then:

```bash
python3 -I skills/core/scripts/dev_docs.py build
```

The lint runs `dev_docs.py check`, which fails if a skill has no catalog entry, the catalog names a skill that does not exist, an example does not use its own skill, or a generated doc is stale.

- Flow diagram: edit `docs/dev-kit-flow.dot`, then `cd docs && dot -Tsvg dev-kit-flow.dot -o dev-kit-flow.svg && dot -Tpng -Gdpi=110 dev-kit-flow.dot -o dev-kit-flow.png`.

## Verification

Run from `.claude/plugins/dev-kit/`:

```bash
python3 -I skills/core/tests/lint_suite.py
python3 -I -m unittest discover -s skills/core/tests -v
```

The lint checks frontmatter, references to support files, `<KIT>` use in agents, agent models, the reviewer ↔ score dimension mapping, English-only text and the generated docs, plus (since 1.12.0) that every script command quoted in the markdown exists with its flags, that `help.json` args match each `argument-hint`, that counts and section ranges in the prose are right, that every skill has a telemetry stage and the feedback areas listed in conventions §13 match the script, that `conventions.md §N` references exist, and that no skill tells the model to invoke a skill marked `disable-model-invocation`. One test copies only `skills/` and `agents/` elsewhere and runs the commands embedded in the skills. Manual end-to-end script: [e2e-checklist](e2e-checklist.md).
