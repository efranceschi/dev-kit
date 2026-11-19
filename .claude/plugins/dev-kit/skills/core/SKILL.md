---
name: core
description: Support files for the dev-kit skills (scripts, templates, checklists, interview script, tests, docs). Not a task; never invoke it. Keep this folder installed next to the other dev-kit skills.
disable-model-invocation: true
user-invocable: false
---

# core (support files)

Source of truth for the dev-kit suite; there is no generated copy.

- `shared/`: conventions, interview script and autonomy policy, templates, checklists, auditor output contract.
- `scripts/`: `dev_state.py` (project state in `.dev/`), `dev_score.py` (quality scores), `dev_detect_stack.py`, `dev_board.py` (local read-only board server for `/dev-kit:board`; its page lives in `shared/board/`).
- `tests/`: `test_dev_state.py` and `lint_suite.py`, for whoever maintains the suite. Not used at run time.
- `docs/`: README, flow diagram and the manual end-to-end checklist.

The other dev-kit skills reference these files as `${CLAUDE_SKILL_DIR}/../core/...`, and agents receive the same path as `Kit root:` in their prompt.
