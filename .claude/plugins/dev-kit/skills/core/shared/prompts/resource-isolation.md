# Resource isolation for agents that run commands

Several agents may run at the same time on the same host, against the same project. Every agent that runs commands (the implementer and every auditor with Bash) follows these rules. The orchestrator gives you a slot on the `Slot: N` line of your prompt; if there is none, use slot 0 and assume you are alone.

## Your resources (derived from the slot)
| resource | value |
|---|---|
| port | `base + N*10` (base = the dev port in `.dev/architecture.md`, else 8000); use `base + N*10 + 1…9` for extra services |
| database | `<db>_agent<N>`: create it (or clone the template) and run migrations in it; never migrate, seed or drop another database; drop yours at the end |
| connection pool | at most 5 connections when the app lets you set it (env var or config flag) |
| scratch folder | `.dev/tmp/<your-agent-name>-<N>/` for logs, builds, screenshots that are not deliverables |
| e2e / test workers | at most `max(1, nproc // 4)` (e.g. `--workers`, `-n`, `--maxWorkers`) |

## Processes
- Every process you start in the background: append its PID to `.dev/run/<your-agent-name>-<N>.pids` right after starting it (`cmd & echo $! >> .dev/run/<name>-<N>.pids`).
- Never use `pkill`, `killall`, `kill` by name, or `pgrep -f`. Never wait with loops such as `until ! pgrep …` (they match their own command line and never end). Wait with `wait <pid>`, or poll a URL or file with a timeout (`timeout 60 sh -c 'until curl -fs …; do sleep 1; done'`).
- Before your final message, stop exactly the PIDs you recorded (`kill <pid>`), check they are gone, and remove your pid file. Leave nothing running in the background. The orchestrator runs `dev_state.py cleanup` after you as a safety net, not as your cleanup.

## Long commands
A command that takes minutes (integration suite, build, scan, data load): start it in the background with its output in your scratch folder (`cmd > .dev/tmp/<name>-<N>/run.log 2>&1 & echo $! >> .dev/run/<name>-<N>.pids`), read code while it runs, then wait for it with `wait <pid>` or a bounded poll of the log. When your prompt has `Time budget: <min>`, stop starting new commands when it is spent and report what you measured.

## Files and git
- Format and lint **only the files you changed** (`ruff format <files>`, `ruff check <files>`, `prettier --write <files>`, `eslint <files>`). Never run a formatter on the whole tree.
- Never run `git stash`, `git checkout`, `git reset`, `git commit` or the pre-commit hooks; the orchestrator commits. Read-only git (`status`, `diff`, `log`) is fine.
- Type-check with the command that covers every project reference (e.g. `tsc -b`, not `tsc --noEmit` on a solution with references), as written in `.dev/architecture.md` §8.

## Worktrees
- Your worktree is the folder on the `Worktree:` line of your prompt, created by the kit from the work branch. Run `cd <Worktree>` first and work only there: the fence denies edits outside it (the main checkout included) and Bash commands run from outside it.
- A git worktree has the code but not the installed dependencies. When `node_modules` (or `.venv`) exists in the Project root and is missing in your worktree, and your task does not change a manifest or lockfile, link it (`ln -s <Project root>/node_modules node_modules`) and check `git check-ignore -q node_modules` (an entry `node_modules/` with a trailing slash does not ignore a symlink). Never install packages in a worktree: through the link it rewrites the main checkout's dependencies. Tasks that change manifests run alone in the main checkout.

## Credentials for QA
Screens behind a login are reached with the **QA access** in `.dev/architecture.md` §8: a local seed user or read token, read from the env var it names. Use the variable by name; never print, store, paste or ask for its value, never use production credentials, and never put one in a finding, screenshot name or report. Without QA access, use the QA harness mocks (`<KIT>/shared/templates/qa-harness.md`) or audit only the public screens and say so.

## Commands
Permission guards often allow simple read-only commands and stop compound ones. Prefer:
- the Read, Grep and Glob tools over `cat`, `grep -r`, `find` and `ls` chains;
- one command per Bash call, run from the project root (your worktree when you have one; or `git -C <dir>`, `--root <dir>`, `npm --prefix <dir>`) instead of `cd <dir> && …`;
- no heredocs or inline multi-line scripts: put a script in your scratch folder with the Write tool (when you have it) and run it, or pass arguments to an existing command;
- no `| head`, `2>&1 | tail` decorations when the tool output is already short; use the command's own limit flags.

