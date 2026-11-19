---
name: docs
description: Generates project documentation from the dev-kit artifacts and the code - README (purpose, setup, run, test, deploy), user guide per persona, API reference when there is an API, CHANGELOG from task commits, and a CLAUDE.md section pointing to .dev/. Use before a release or when the user asks for docs.
argument-hint: "[readme | guide | api | changelog | all]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# docs

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status`, `duration_s` and a brief `feedback` on the dev-kit itself), agent and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says, with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS (default: all)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

## Procedure
1. Read `.dev/brief.md` block 10 (documentation expected, audience), `.dev/prd.md`, `.dev/architecture.md`, `.dev/decisions.md`, and `git log --format='%h %s%n%b' --reverse`. Documentation for end users is written in the **application language(s)**; developer docs in the user's language unless the brief says otherwise (open source → English).
2. **README.md** (repo root): what it is and for whom, screenshots if `.dev/qa/ux/screenshots/` exists, prerequisites, setup (env var names from `.env.example`), run, test, lint, deploy, project structure (from architecture §3), link to `.dev/` artifacts and ADRs, licence. Never include secret values.
3. **User guide** (`docs/user-guide.md`): one section per persona journey from `ux-flows.md`, step by step, with the copy the UI actually shows (grep the code, do not invent).
4. **API reference** (`docs/api.md`) when `architecture.md` §5 defines contracts: generate from the actual routes/schemas (OpenAPI if the stack produces it; otherwise derive from code), with auth, errors and examples.
5. **CHANGELOG.md**: Keep-a-Changelog format; group `[T-xxx]` commits by type under the next version; include fix tasks from QA as "Fixed".
6. **CLAUDE.md**: add or update a short section "dev-kit" telling future sessions that state lives in `.dev/`, how to resume (`/dev-kit:start`), the test/lint commands and the commit convention. Do not duplicate the whole brief.
7. Verify every command in the docs actually runs (`--help` or dry run) and every file path exists. `dev_state.py set phase docs` if earlier; summarise files written. Next: `review docs` (the docs reviewer executes the commands and checks the guide against the UI), then `release`.
