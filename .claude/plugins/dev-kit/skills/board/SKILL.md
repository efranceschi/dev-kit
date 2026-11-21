---
name: board
description: Live board of a dev-kit project in the browser - starts a small web server on 127.0.0.1 (or shared on the network with an access key, or behind a reverse proxy) and opens a dashboard navigated by lifecycle phase - conception, planning, construction and stable are its tabs, each showing only its part (steps, reviews and decisions; plan, roadmap, issue queue and a Plan view to drag tasks and issues; the milestones with their stages, running tasks and agents, kanban, burndown, velocity and gates; production and releases) - with a "Needs you" strip (questions, permission requests, blocked tasks, hotfixes) and recent activity on every phase, light or dark, live. From the page the user asks Claude Code for work (run the next step, new issue, answers, plan drafts); this session then listens and runs each request as it arrives. One server per project; stop it from the page or with "stop". Use when the user wants to see or drive the project visually, a dashboard, a board or a panel, or asks to stop or check it.
argument-hint: "[stop | status | --open | --no-open | --port N | --host IP | --trusted-host NAME | --idle-min N | --actions on|off]"
allowed-tools: Bash, Read
---

# board

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Arguments: $ARGUMENTS

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`, `DB` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_board.py" --root "${CLAUDE_PROJECT_DIR}"` and `DW` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_worker.py" --root "${CLAUDE_PROJECT_DIR}"`.

The server never changes the project: it reads `.dev/` and writes only in `.dev/run/` - its own files (`board.json`, `board.lock`, `board.log`) and the requests the page queues for Claude Code (`dev_worker.py`), which `/dev-kit:worker` runs in a Claude Code session. Starting the board from a session makes that session the one that listens: the plugin's monitor (`dev_worker.py watch`) tells it when a request arrives, so nobody has to type at the console.

## Procedure
1. Log `DS event skill_start --set skill=board --set args_kind=<start|stop|status>` (skip if there is no `.dev/state.json`).
2. Pick the action from the arguments:
   - `stop` → run `DW disarm`, then `DB stop`.
   - `status` → run `DB status`.
   - anything else (empty, `--open`, `--no-open`, `--port N`, `--host IP`, `--trusted-host NAME`, `--idle-min N`, `--actions on|off`) → run `DB start` with those flags, then, when it started or was already running with requests on, `DW arm --pid $PPID --wait 8` in a separate Bash command (`$PPID` there is this Claude Code process). Pass `--trusted-host` only with the host name the user gave for their reverse proxy (it is remembered for the project; `--trusted-host none` forgets it). Pass `--host` only when the user asked for it in this request (e.g. "bind on 0.0.0.0", "share it on the network", "open it from my phone"); never add it on your own. Do not add `&` or `run_in_background`: `start` detaches the server itself and returns in a few seconds.
3. Report in the user's language, in one or two lines:
   - `started: URL` → the URL, that it opened in the default browser (or that they should open the URL when the output says so, e.g. on a remote machine without a display), and the two ways to stop it: **Stop server** in the page's ⋯ menu or `/dev-kit:board stop`.
   - `exposed on ...` lines (started with `--host` on a non-loopback address such as `0.0.0.0`): give the `access link:` URL(s) - other devices open the board with them, the key turns into a browser cookie - and say plainly that it is plain HTTP on the network, anyone with the link can see the board and stop it, so only on a trusted network; `/dev-kit:board --host 127.0.0.1` stops sharing. Opening the address without the link answers "Access link required"; `/dev-kit:board status` prints the link again.
   - Remote machine (SSH session, no display, or the output says to open the URL) and no `--host`: the board only listens on 127.0.0.1, so tell the user to open an SSH tunnel from their own computer, `ssh -N -L <local port>:127.0.0.1:<board port> <user>@<this host>`, and open `http://localhost:<local port>/`. Any local port works (editor port forwarding too), and so does opening it by IP address (e.g. a LAN forward `ssh -L 0.0.0.0:<port>:...`); host names are refused on purpose (DNS rebinding protection), so with a name use the IP instead. If they want to reach it from other devices on their network without a tunnel, `/dev-kit:board --host 0.0.0.0` does that with an access key. Behind their own reverse proxy (with its TLS and login), `/dev-kit:board --trusted-host <the proxy's host name>` makes the board answer to that name. Never suggest exposing the port to the internet without one of these.
   - `already running: URL` → the URL and that no new tab was opened, so the existing tab is the one to use; `/dev-kit:board --open` opens another tab if they closed it.
   - `stopped` / `not running` → say so.
   - Exit 2 (no `.dev/state.json`) → there is no dev-kit project here; suggest `/dev-kit:start`.
   - Exit 1 → show the last lines of `.dev/run/board.log` and the error.
   - `trusted host names: ...` → the board also answers to that name; say that the proxy's own login is what protects it there.
4. Requests, from the output of `DW arm`: `listening` → one line: buttons on the page (run the next step, new issue, answers, plan drafts) start work in this session by themselves, and it keeps listening while the session stays open. `not listening` → the monitor did not start (an older Claude Code, or a session that cannot run monitors): say that requests still queue and `/dev-kit:worker` runs them here when asked. Then run `DW list`: when it shows a request still `pending`, or `needs_input` with its question answered, and the board has requests on, invoke the skill `dev-kit:worker` right away so a queue left from before the board started is drained without waiting for a notification. A restart line saying the kit was updated means the board now runs the new version. Mention that the board stops by itself after 2 hours with no open tab and no session listening (`--idle-min N` changes it; `0` = never).
5. When a notification `dev-kit board: request R-nnn is waiting` arrives later in this session, invoke the skill `dev-kit:worker` and follow it; do not answer the notification in any other way. When the notification says `the kit was updated`, run `/dev-kit:board` again (steps 2-4): it replaces the board server and the listener with the new version.
6. Sharing on the network is the user's explicit request in this turn, so it does not go through `pause_policy.public_exposure`; never start it with `--host` from an autonomous run. Do not run anything else.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
