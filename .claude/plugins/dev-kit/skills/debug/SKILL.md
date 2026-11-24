---
name: debug
description: Diagnoses what the kit is doing in a project when something looks stuck or wrong - writes a debug dump (state, git, worktrees, run files, logs, telemetry) under .dev/run/debug/, checks the state against git and the running processes, explains what is happening and whether it is a project problem or a dev-kit gap, and drafts a report for a dev-kit patch. Use when the user asks if a run is stuck, why the board shows something odd, what a round is doing, or for a dump to send to the dev-kit author. Changes nothing in the project.
argument-hint: "[\"what looks wrong\"] [--dump-only] [--share]"
allowed-tools: Read, Bash, Grep, Glob
---

# debug

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (what the user sees, in their words; `--dump-only` writes the dump and stops)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DD` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_debug.py" --root "${CLAUDE_PROJECT_DIR}"` and `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

## Procedure
1. Log `DS event skill_start --set skill=debug --set args_kind=none`.
2. `DD dump --json`: it writes `.dev/run/debug/dump-<stamp>.md` and returns `path` and `checks` (each with `code`, `level`, `text`, `evidence`). With `--dump-only`, show the path and the errors among the checks, then go to step 6. With `--share`, also run step 5's `DD dump --share` and give that path.
3. Read the dump. Then answer, in the user's language, the question in the input (or "what is happening now"):
   - **Is something running?** The round (`.dev/run/round.json`, its pids), the Autopilot run, the last action (`.dev/run/round-activity.json`), the tests or agents running. A round log of 0 bytes is normal while it runs (`claude -p` writes at the end).
   - **What the state says against what happens:** each `error` check, with its evidence and what it means.
   - **Cause:** read the kit's code behind it before you name one (`${CLAUDE_SKILL_DIR}/../core/scripts/` and the skill that ran, for instance `${CLAUDE_SKILL_DIR}/../implement/SKILL.md`). Say whether it is the project (a failing test, a missing permission, an answer pending in Needs you) or a gap in dev-kit (a step a skill does not cover, a command that does not record what it should).
4. **What to do now:** the commands that recover the state, as commands for the user to run (`DS reconcile`, `DS done T-nnn --commit <sha> --force`, `DS start T-nnn --resume`, `git worktree remove …`). Run none of them yourself.
5. **For a dev-kit patch or for someone else's troubleshooting** (when step 3 found a kit gap, or the user wants to send it): run `DD dump --share` and give that file as the attachment, never the dump of step 2 (that one is for this machine: it keeps task titles, paths and log lines, with only the secrets redacted). The shareable dump replaces the project and home folders and the user name, turns every project path into a stable pseudonym (`p:3fa2c1.js`) and other branches into `<branch-n>`, drops free text (titles, commit subjects, block reasons, questions, the runs' answers) keeping ids, statuses, times, counts and codes, redacts secrets, and checks its own text before writing; exit 3 means it found a leak and wrote nothing: say so and do not fall back to the other dump. Write the report the same way: what happened (ids, counts, check codes), the kit version, the cause in the kit (file and function), a proposed fix and a test that would reproduce it, with no project names, product terms, paths, secrets or source code. Remind the user to read both before sending them.
6. Log `skill_end` with `status` ok. End with one tip from `DS tip debug` on its own line (skip if empty).

## Rules
- Read-only: the only files written are the dumps under `.dev/run/debug/`, which are never committed. Never paste a dump's content or a project secret into the chat or the report beyond what step 3 needs; anything meant to leave this machine comes from `--share`. Never change the state, git or a running process, and never kill a round.
- Never guess a cause that the dump and the code do not show; say what is missing instead.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
