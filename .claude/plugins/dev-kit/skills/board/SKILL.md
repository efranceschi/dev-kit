---
name: board
description: Live board of a dev-kit project in the browser, read-only - starts a small web server on 127.0.0.1 (or shared on the network with an access key, or behind a reverse proxy) and opens a dashboard laid out like the kit's flow diagram - its tabs are the lanes (conception, planning, milestones, releases, stable) plus a map and the architecture diagram, each screen fitting the window: the lane's steps as a flow, then same-size blocks (documents, reviews, roadmap, backlog, the task board, releases, production health), details in modals - with a "Needs you" button that turns red when something waits, what runs now (skills, agents, the Autopilot) and an activity drawer, light or dark. It only shows the project: every decision and every run happens in Claude Code. One server per project; stop it from the page or with "stop". Use when the user wants to see or follow the project visually, a dashboard, a board or a panel, or asks to stop or check it.
argument-hint: "[stop | status | --open | --no-open | --port N | --host IP | --trusted-host NAME | --idle-min N]"
allowed-tools: Bash, Read
---

# board

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Arguments: $ARGUMENTS

Let `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"` and `DB` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_board.py" --root "${CLAUDE_PROJECT_DIR}"`.

The board is read-only: the server reads `.dev/` and writes only its own files in `.dev/run/` (`board.json`, `board.lock`, `board.log`, `board-config.json`). It never changes the project and never starts Claude Code: questions, confirmations, release approvals, plan changes and runs (including `/dev-kit:autopilot`) all happen in a Claude Code session, and the board shows them as they happen (the **Live** card lists the skills and agents running, the top bar shows the Autopilot while it runs). Its only action is **Stop server** in the page's ⋯ menu.

## Procedure
1. Log `DS event skill_start --set skill=board --set args_kind=<start|stop|status>` (skip if there is no `.dev/state.json`).
2. Pick the action from the arguments:
   - `stop` → run `DB stop`.
   - `status` → run `DB status`.
   - anything else (empty, `--open`, `--no-open`, `--port N`, `--host IP`, `--trusted-host NAME`, `--idle-min N`) → run `DB start` with those flags. Pass `--trusted-host` only with the host name the user gave for their reverse proxy (it is remembered for the project; `--trusted-host none` forgets it). Pass `--host` only when the user asked for it in this request (e.g. "bind on 0.0.0.0", "share it on the network", "open it from my phone"); never add it on your own. Do not add `&` or `run_in_background`: `start` detaches the server itself and returns in a few seconds.
3. Log `DS event skill_end --set skill=board --set status=ok` (skip if there is no `.dev/state.json`): the board is not work in progress, and a run left open would show on it as one. Then report in the user's language, in one or two lines:
   - `started: URL` → the URL, that it opened in the default browser (or that they should open the URL when the output says so, e.g. on a remote machine without a display), that the board only shows the project (decisions and runs stay here in Claude Code), and the two ways to stop it: **Stop server** in the page's ⋯ menu or `/dev-kit:board stop`.
   - `exposed on ...` lines (started with `--host` on a non-loopback address such as `0.0.0.0`): give the `access link:` URL(s) - other devices open the board with them, the key turns into a browser cookie - and say plainly that it is plain HTTP on the network, anyone with the link can see the board and stop it, so only on a trusted network; `/dev-kit:board --host 127.0.0.1` stops sharing. Opening the address without the link answers "Access link required"; `/dev-kit:board status` prints the link again.
   - Remote machine (SSH session, no display, or the output says to open the URL) and no `--host`: the board only listens on 127.0.0.1, so tell the user to open an SSH tunnel from their own computer, `ssh -N -L <local port>:127.0.0.1:<board port> <user>@<this host>`, and open `http://localhost:<local port>/`. Any local port works (editor port forwarding too), and so does opening it by IP address (e.g. a LAN forward `ssh -L 0.0.0.0:<port>:...`); host names are refused on purpose (DNS rebinding protection), so with a name use the IP instead. If they want to reach it from other devices on their network without a tunnel, `/dev-kit:board --host 0.0.0.0` does that with an access key. Behind their own reverse proxy (with its TLS and login), `/dev-kit:board --trusted-host <the proxy's host name>` makes the board answer to that name. Never suggest exposing the port to the internet without one of these.
   - `already running: URL` → the URL and that no new tab was opened, so the existing tab is the one to use; `/dev-kit:board --open` opens another tab if they closed it.
   - `restarted` (or a line saying the kit was updated) → the board now runs the new version.
   - `stopped` / `not running` → say so.
   - Exit 2 (no `.dev/state.json`) → there is no dev-kit project here; suggest `/dev-kit:start`.
   - Exit 1 → show the last lines of `.dev/run/board.log` and the error.
   - `trusted host names: ...` → the board also answers to that name; say that the proxy's own login is what protects it there.
   Mention that the board stops by itself after 2 hours with no open tab (`--idle-min N` changes it; `0` = never).
4. Sharing on the network is the user's explicit request in this turn, so it does not go through `pause_policy.public_exposure`; never start it with `--host` from an autonomous run. Do not run anything else.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
