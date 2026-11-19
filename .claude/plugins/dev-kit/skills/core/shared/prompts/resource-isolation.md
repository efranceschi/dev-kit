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

## Files and git
- Format and lint **only the files you changed** (`ruff format <files>`, `ruff check <files>`, `prettier --write <files>`, `eslint <files>`). Never run a formatter on the whole tree.
- Never run `git stash`, `git checkout`, `git reset`, `git commit` or the pre-commit hooks; the orchestrator commits. Read-only git (`status`, `diff`, `log`) is fine.
- Type-check with the command that covers every project reference (e.g. `tsc -b`, not `tsc --noEmit` on a solution with references), as written in `.dev/architecture.md` §8.
