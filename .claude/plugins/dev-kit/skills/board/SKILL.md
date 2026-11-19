---
name: board
description: Live Scrum board of a dev-kit project in the browser - starts a small read-only web server on 127.0.0.1 (or, on request, shared on the local network with an access key) and opens the default browser on a dashboard with the sprint (current milestone) goal, kanban of tasks with a Graph view (left-to-right DAG of the milestone's tasks and QA gate with direction arrows, parallel groups and failure loops, actual or planned), running agents shown as live badges on the task or QA gate they work on (agents not tied to a task in a thin strip), burndown, velocity, product backlog, impediments, definition of done and recent activity, updating by itself while work goes on. One server per project (PID-controlled, never opened twice); stop it from the page or with "stop". Use when the user wants to see the project visually, a dashboard, a board or a panel, or asks to stop or check it.
argument-hint: "[stop | status | --open | --no-open | --port N | --host IP]"
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
   - anything else (empty, `--open`, `--no-open`, `--port N`, `--host IP`) → run `DB start` with those flags. Pass `--host` only when the user asked for it in this request (e.g. "bind on 0.0.0.0", "share it on the network", "open it from my phone"); never add it on your own. Do not add `&` or `run_in_background`: `start` detaches the server itself and returns in a few seconds.
3. Report in the user's language, in one or two lines:
   - `started: URL` → the URL, that it opened in the default browser (or that they should open the URL when the output says so, e.g. on a remote machine without a display), and the two ways to stop it: the **Stop server** button on the page or `/dev-kit:board stop`.
   - `exposed on ...` lines (started with `--host` on a non-loopback address such as `0.0.0.0`): give the `access link:` URL(s) - other devices open the board with them, the key turns into a browser cookie - and say plainly that it is plain HTTP on the network, anyone with the link can see the board and stop it, so only on a trusted network; `/dev-kit:board --host 127.0.0.1` stops sharing. Opening the address without the link answers "Access link required"; `/dev-kit:board status` prints the link again.
   - Remote machine (SSH session, no display, or the output says to open the URL) and no `--host`: the board only listens on 127.0.0.1, so tell the user to open an SSH tunnel from their own computer, `ssh -N -L <local port>:127.0.0.1:<board port> <user>@<this host>`, and open `http://localhost:<local port>/`. Any local port works (editor port forwarding too), and so does opening it by IP address (e.g. a LAN forward `ssh -L 0.0.0.0:<port>:...`); host names are refused on purpose (DNS rebinding protection), so with a name use the IP instead. If they want to reach it from other devices on their network without a tunnel, `/dev-kit:board --host 0.0.0.0` does that with an access key. Never suggest exposing the port to the internet.
   - `already running: URL` → the URL and that no new tab was opened, so the existing tab is the one to use; `/dev-kit:board --open` opens another tab if they closed it.
   - `stopped` / `not running` → say so.
   - Exit 2 (no `.dev/state.json`) → there is no dev-kit project here; suggest `/dev-kit:start`.
   - Exit 1 → show the last lines of `.dev/run/board.log` and the error.
4. Mention that the board stops by itself after 2 hours with no open tab. Do not run anything else.
