---
name: status
description: Read-only dashboard of a dev-kit project - lifecycle phase and step, next release, milestones, task progress, gates, blockers, open questions and the next task. Use when the user asks for progress, status, what's blocked, or what comes next. Makes no changes to the project or its state (it only records which tip was shown).
argument-hint: "[--json]"
allowed-tools: Read, Bash, Grep, Glob
---

# status

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

!`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status`

Arguments: $ARGUMENTS

## Procedure
1. If the output above says there is no state, say so and suggest `/dev-kit:start`.
2. When the status shows a production health check (`autonomy.production.health` set), run `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" prod-check --due` once: it does nothing until its interval passed, and a failure opens one expedite issue (`conventions.md` §21). This is the only command besides the status itself; include its line in the report.
3. Present the status in the user's language as: one line per milestone with progress, gate and score; the review scores (prd, design, plan, ux, docs) and the cut-offs in force (`Quality cut-off` line); the in-progress or next task; blocked tasks with reasons; open questions count (read `.dev/open-questions.md` and list the open ones briefly); last three lines of `.dev/log.md`; the `Issues:` line when present (details with `/dev-kit:backlog`); the `Stale:` and `Locks:` lines when present (stale documents are refreshed by the next `review`; a lock held by an agent that no longer runs is freed by `/dev-kit:start`). Close with the line "Help: /dev-kit:help" (translated). `dev_state.py status` already prints one tip at the end (`💡 …`): relay it on its own line, translated into the user's language; do not call `tip` again (each tip shows at most twice).
4. If `--json` was passed, print the raw JSON from `dev_state.py status --json` instead.
5. End with the single recommended next command. Do not run it. To change how the kit behaves, point to `/dev-kit:settings`.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).

## Existing projects (brownfield)

When state has `brownfield`: include the `Brownfield:` line (mode, baseline tag and sha, first milestone, commit style) from `dev_state.py status`, the number of pre-existing failures in `.dev/qa/baseline.md`, reviews recorded `n/a` with their note, and any missing stage artifact (`conventions.md` §16 "Missing stages") as the recommended next command.
