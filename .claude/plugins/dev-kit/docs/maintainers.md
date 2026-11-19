# Maintainers

How the plugin is built, tested and documented. Users do not need this page.

## Layout

```
.claude/plugins/dev-kit/
  .claude-plugin/plugin.json     name, version, description
  README.md                      landing page
  docs/                          user docs (four of them generated, see below), e2e checklist, flow diagram
  agents/*.md                    17 agents (model + effort in the frontmatter, conventions §9)
  skills/*/SKILL.md              23 skills, invoked as /dev-kit:<name>
  skills/core/                   support skill, not invocable
    SKILL.md                     marker (disable-model-invocation: true, user-invocable: false)
    scripts/dev_state.py         state: init, sync-plan, next, start, done, block, add-task, add-question, gate, review,
                                 set, status, issues (add-issue, issue, pull-issues, cooldown, backlog), preview, deploy,
                                 cleanup, event, feedback, telemetry, tip, tips
    scripts/dev_score.py         0–100 score per dimension (low cap, dedupe, delta mode)
    scripts/dev_telemetry.py     allowlisted session log, stage grades (imported by the other scripts)
    scripts/dev_cost.py          token usage and estimated cost from Claude Code transcripts
    scripts/dev_docs.py          generated docs and /dev-kit:help answers
    scripts/dev_detect_stack.py  stack detection from manifests
    shared/conventions.md        the rules every skill and agent follows (§1–§15)
    shared/help.json             catalog for help and the generated docs (English only)
    shared/tips.json             contextual tips (English only)
    shared/interview/ templates/ checklists/ prompts/   interview script, artifact templates, review checklists, output and isolation contracts
    tests/                       lint_suite.py, test_dev_state.py, test_dev_cost.py, test_dev_docs.py
```

## How the kit finds its own files

- Skills reference support files as `${CLAUDE_SKILL_DIR}/../core/...`; install `core` together with the other skills (`start` warns if it is missing).
- Agents and shared files get no variable substitution: they use `<KIT>`, and the skill that spawns an agent passes `Kit root: <absolute path>` in the prompt.
- State commands use `${CLAUDE_PROJECT_DIR}` so they keep pointing at the project.
- Scripts run with `python3 -I`; modules next to them are imported by inserting the script folder into `sys.path` explicitly.
- No hooks are installed.

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

The lint checks frontmatter, references to support files, `<KIT>` use in agents, agent models, the reviewer ↔ score dimension mapping, English-only text and the generated docs. One test copies only `skills/` and `agents/` elsewhere and runs the commands embedded in the skills. Manual end-to-end script: [e2e-checklist](e2e-checklist.md).
