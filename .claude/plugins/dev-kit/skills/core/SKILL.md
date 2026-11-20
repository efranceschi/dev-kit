---
name: core
description: Support files for the dev-kit skills (scripts, templates, checklists, interview script, tests, docs). Not a task; never invoke it. Keep this folder installed next to the other dev-kit skills.
disable-model-invocation: true
user-invocable: false
---

# core (support files)

Source of truth for the dev-kit suite; there is no generated copy.

- `shared/`: conventions, onboarding of existing projects, interview script and autonomy policy, templates, checklists, auditor output and isolation contracts, `help.json` and `tips.json` catalogs, and the board page (`board/`).
- `scripts/`: `dev_state.py` (project state in `.dev/`), `dev_score.py` (quality scores, consolidation and auditor selection), `dev_ledger.py` (work ledger, imported by `dev_state.py`), `dev_telemetry.py` (session log and stage grades), `dev_cost.py` (token usage and cost), `dev_docs.py` (generated docs and help answers), `dev_detect_stack.py`, `dev_board.py` (local read-only board server for `/dev-kit:board`) and `dev_agent_hook.py` (hook that feeds the board's live agents).
- `tests/`: `lint_suite.py` and the `test_*.py` suites, for whoever maintains the kit. Not used at run time.

The plugin's user docs, flow diagram and manual end-to-end checklist live in the plugin's `docs/` folder, not here.

The other dev-kit skills reference these files as `${CLAUDE_SKILL_DIR}/../core/...`, and agents receive the same path as `Kit root:` in their prompt.
