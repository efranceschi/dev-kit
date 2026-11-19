---
name: board
description: Live Scrum board of a dev-kit project in the browser - starts a small read-only web server on 127.0.0.1 and opens the default browser on a dashboard with the sprint (current milestone) goal, kanban of tasks, burndown, velocity, product backlog, impediments, definition of done and recent activity, updating by itself while work goes on. One server per project (PID-controlled, never opened twice); stop it from the page or with "stop". Use when the user wants to see the project visually, a dashboard, a board or a panel, or asks to stop or check it.
argument-hint: "[stop | status | --open | --no-open | --port N]"
allowed-tools: Bash, Read
---

# board

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Arguments: $ARGUMENTS

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `DB` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_board.py" --root "${CLAUDE_PROJECT_DIR}"`.

Read-only for the project: the server only reads `.dev/` and writes its own files in `.dev/run/` (`board.json`, `board.lock`, `board.log`).

## Procedure
1. Log `DS event skill_start --set skill=board --set args_kind=<start|stop|status>` (skip if there is no `.dev/state.json`).
2. Pick the action from the arguments:
   - `stop` → run `DB stop`.
   - `status` → run `DB status`.
   - anything else (empty, `--open`, `--no-open`, `--port N`) → run `DB start` with those flags. Do not add `&` or `run_in_background`: `start` detaches the server itself and returns in a few seconds.
3. Report in the user's language, in one or two lines:
   - `started: URL` → the URL, that it opened in the default browser (or that they should open the URL when the output says so, e.g. on a remote machine without a display), and the two ways to stop it: the **Stop server** button on the page or `/dev-kit:board stop`.
   - Remote machine (SSH session, no display, or the output says to open the URL): the board only listens on 127.0.0.1, so tell the user to open an SSH tunnel from their own computer, `ssh -N -L <local port>:127.0.0.1:<board port> <user>@<this host>`, and open `http://localhost:<local port>/`. Any local port works (editor port forwarding too); never suggest exposing the port to the network.
   - `already running: URL` → the URL and that no new tab was opened, so the existing tab is the one to use; `/dev-kit:board --open` opens another tab if they closed it.
   - `stopped` / `not running` → say so.
   - Exit 2 (no `.dev/state.json`) → there is no dev-kit project here; suggest `/dev-kit:start`.
   - Exit 1 → show the last lines of `.dev/run/board.log` and the error.
4. Mention that the board stops by itself after 2 hours with no open tab. Do not run anything else.
