---
name: backlog
description: Everything still pending in a dev-kit project, shown in the chat - open hotfix, issue queue by class of service, buffer of the next milestone, pending and blocked tasks per milestone, open and parked questions, deferred QA findings and pending deploys - ending with a recommended next step. Use when the user asks what is pending, what is left, the list of issues or bugs, or what to do next. Read-only.
argument-hint: "[issues | tasks | questions | findings | deploy]"
allowed-tools: Read, Bash, Grep, Glob
---

# backlog

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Input: $ARGUMENTS (optional section filter)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

Read-only: this skill changes nothing.

## Procedure
1. Log `DS event skill_start --set skill=backlog --set args_kind=section`. Run `DS backlog --json` (`conventions.md` §15 explains classes, buffer and cool-down).
2. Show in the chat, in the user's language, only the sections that have something (or only the requested one):
   - **Hotfix:** the open hotfix task, if any (there is at most one).
   - **Issue queue:** by class (`expedite`, `current`, `standard`, `intangible`, `change`): id · type · severity · age in days · title. Then the scheduled ones (`→ Mn`, with their tasks and status).
   - **Next milestone's buffer:** capacity, used, and which queued issues would enter if it started now (the first `free` items of the queue, standard before intangible, by severity and age). Existing project in `maintenance` mode (`brownfield.mode` in the JSON): there is no buffer; issues are scheduled straight into the open maintenance milestone, so show the queued ones as "to schedule" instead.
   - Issues with `origin: baseline` (or a `legacy:` note) are pre-existing debt of an existing project: mark them as such.
   - **Pending tasks** per milestone: id · type · lane · status; blocked ones with the reason.
   - **Questions and parked items:** count, and the command to resolve them.
   - **Deferred findings:** count by severity and the 5 most relevant (scope, id, severity, title).
   - **Deploy:** the `Production:` drift line(s).
   - **Warnings:** e.g. expedite overused.
3. **Suggested next step:** one or two lines, recommended option first with the reason, chosen in this order: open hotfix → `/dev-kit:implement <task>`; blocked tasks or parked questions → `/dev-kit:interview --gaps`; milestone in progress → `/dev-kit:implement` (or `/dev-kit:autopilot`); a relevant deferred finding → `/dev-kit:issue --from <F-id> <scope>`; maintenance mode with queued issues → `/dev-kit:issue --schedule <I-id> <open maintenance milestone>`; production behind → `/dev-kit:deploy`.
4. Log `skill_end`. End with one tip from `DS tip backlog` (or `DS tip expedite_overuse` when that warning is present), on its own line; skip if empty. (`DS backlog --json` prints no tip, so this is the only one.)

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the suggested next step. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
