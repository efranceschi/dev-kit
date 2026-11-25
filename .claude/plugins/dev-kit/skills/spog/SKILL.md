---
name: spog
description: One local page for every dev-kit project on this machine (single pane of glass), read-only - starts a small web server on 127.0.0.1 and opens a page with a card per project - whether it waits for you, runs or sits idle and since when, and what needs you (the board's Needs you items, plus a Claude Code session of the project waiting on a permission or a question) - sorted so the projects that need you come first, with the count in the tab's title. It can be run from any Claude Code session, inside a project or not. A project joins the list when /dev-kit:board or /dev-kit:spog runs in it; a project whose folder is gone stays greyed until it is forgotten. Use when the user works on several projects at once and wants to follow them all in one place, asks which project needs them, or asks to stop it, list the projects or forget one.
argument-hint: "[stop | status | list | forget PATH... | forget --missing | --open | --no-open | --port N | --idle-min N]"
allowed-tools: Bash, Read
---

# spog

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the session's folder (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Arguments: $ARGUMENTS

Let `SP` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_spog.py"` and `DS` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}"`.

The page is read-only, like the board: it reads each registered project's `.dev/` and writes only `~/.dev-kit/` (the list `projects.json` and its own run files). It never changes a project and never starts Claude Code: each card shows what needs the user and the command that goes on in that project's own session. It listens on 127.0.0.1 only (no sharing on the network in this version). Its only action is **Stop server** in the page's ⋯ menu.

## Procedure
1. When `${CLAUDE_PROJECT_DIR}/.dev/state.json` exists, log `DS event skill_start --set skill=spog --set args_kind=<start|stop|status|list|forget>`; outside a dev-kit project skip every `DS` step.
2. Pick the action from the arguments:
   - `stop` → run `SP stop`.
   - `status` → run `SP status`.
   - `list` → run `SP list`.
   - `forget PATH...` → run `SP forget PATH...` with the paths as the user gave them (quoted); `forget --missing` → `SP forget --missing`. Forget only what the user named: never add `--missing` on your own.
   - anything else (empty, `--open`, `--no-open`, `--port N`, `--idle-min N`) → run `SP start --register "${CLAUDE_PROJECT_DIR}"` with those flags (registering is skipped by itself when the folder is not a dev-kit project). Do not add `&` or `run_in_background`: `start` detaches the server itself and returns in a few seconds.
3. When step 1 logged, log `DS event skill_end --set skill=spog --set status=ok`. Then report in the user's language, in one or two lines:
   - `started: URL` → the URL, that it opened in the default browser (or that they should open it when the output says so), how many projects it shows, that it only shows (decisions and runs stay in each project's Claude Code session), and how to stop it: **Stop server** in the ⋯ menu or `/dev-kit:spog stop`. With 0 projects, say a project joins when `/dev-kit:board` or `/dev-kit:spog` runs in it.
   - `already running: URL` → the URL and that no new tab was opened; `/dev-kit:spog --open` opens another.
   - `restarted` → the page now runs the new version of the kit.
   - `stopped` / `not running` → say so.
   - `list` → the projects as printed, the ones that need the user first; for a project shown as `missing` or `not_project`, offer `/dev-kit:spog forget <path>`.
   - `forgot ...` / `nothing to forget` → say so.
   - Exit 1 → show the last lines of `~/.dev-kit/run/spog.log` and the error.
   - Remote machine (SSH session, no display, or the output says to open the URL): the page only listens on 127.0.0.1, so tell the user to open an SSH tunnel from their own computer, `ssh -N -L <local port>:127.0.0.1:<port> <user>@<this host>`, and open `http://localhost:<local port>/`.
   Mention that it stops by itself after 4 hours with no open tab (`--idle-min N` changes it; `0` = never), and that "waiting on a permission or a question" needs the kit's hooks (without them the rest of the page still works).
4. Do not run anything else.

**Last line** (`conventions.md` §15): inside a dev-kit project, end the final report with the next command alone on the last line, written in full: the one `dev_state.py status --next` prints. Outside one, end without it.
