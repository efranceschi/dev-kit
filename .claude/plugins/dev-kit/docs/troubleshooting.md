# Troubleshooting

| Symptom | Why | What to do |
|---|---|---|
| Autopilot stops overnight waiting for a permission | Claude Code asks before Bash commands and edits; the kit's own pauses are not the cause | Run `/fewer-permission-prompts` and start with `--permission-mode acceptEdits`; use the `unattended` autonomy level |
| The session froze or the machine rebooted | Long runs can be interrupted | `/dev-kit:start` reconciles the state with git; `/dev-kit:autopilot` continues from the current phase |
| Processes still running after a run (ports busy, high load) | An agent left a background process | `dev_state.py cleanup` (only processes inside the project); `status` shows "Leftover agent processes" |
| A gate keeps failing | Real problems, or the same finding coming back | Read `.dev/qa/<M>/report.md`; from round 2 only previous findings and new medium+ findings count (delta mode). When rounds are exhausted the kit asks (or applies your pause policy) |
| `dev_state.py` refuses a gate or review | The score is below the cut-off | Fix the findings and re-run; forcing needs your decision and an ADR, and is never allowed with security below its minimum or critical/high open |
| `/dev-kit:costs` shows nothing or "partial" | No Claude Code transcripts for this project on this machine | Costs come from `~/.claude/projects/<project>/`; on another machine only the token totals the skills logged are available |
| A model shows `n/d` in costs | No price for it in `.dev/costs/prices.json` | Add the model to that file (US$ per million tokens) |
| A task cannot start: "gate of Mn is pending" | Milestones are sequential | Finish and pass `qa Mn`; only hotfix tasks bypass this |
| "hotfix … is still open (WIP 1)" | Only one hotfix at a time | Finish it (`implement`, `qa --scope`, `release --hotfix`, which also deploys it) or classify the new one as standard |
| An issue never gets scheduled | Standard and intangible issues wait for the next milestone's buffer or the cool-down (in maintenance mode they are scheduled straight into the open maintenance milestone) | `/dev-kit:backlog issues` shows the queue; `/dev-kit:issue --schedule I-003 M8` brings it into an existing milestone |
| Too many tips | Each tip shows at most twice | `dev_state.py set autonomy.tips off` |
| `start` says the `core` skill is missing | The support skill was not installed next to the others | Reinstall the plugin (`/plugin install dev-kit@dev-kit`); `core` holds the scripts and templates |
| "add the task to Mn+1": `add-task` refuses a milestone | Its gate already passed | Use the next milestone (`--milestone-title` creates a maintenance one), or `--lane hotfix` for a critical/high bug |
| A task dropped in a replan still blocks the milestone | It was blocked instead of dropped (before 1.12.0) | `dev_state.py drop T-xxx --reason "dropped in replan ADR-nnn"` |
| The wrong commit was recorded for a task | A hook rewrote it or the SHA was taken too early | `dev_state.py done T-xxx --commit <right sha> --force` |
| "event rejected" in a skill | A field or feedback area is not allowlisted | Use the areas in conventions §13; never put project text into an event. Before `init`, events are skipped on purpose |
| "review … n/a needs --note" | `n/a` must say why | `dev_state.py review design n/a --note "no new UI"` |
| `set phase` warns that an artifact is missing | An earlier stage was skipped | Run the skill named in the warning, or `/dev-kit:start` to be routed there |
| An auditor result shows `F-000` "no parsable result" | The agent wrote no valid result file, even after the `check` output was sent back | Re-run `qa` (the gate cannot pass silently); report it with `/dev-kit:feedback` |
| `dev_score.py check` says a result is INVALID | Unknown severity or auditor, no `findings` list, broken JSON | Send the agent the `check` output; synonyms (`status`, `Major`, `nit`…) are fixed by `check --fix` on their own |
| `/dev-kit:costs` shows very few requests or `n/d` | Transcripts with `requestId: "unknown"` or gateway model names (before 1.15.0) | Update the kit and run `dev_cost.py ingest` again: ids fall back to the message id and `system.ai.*`-style names are priced (a family match says "priced as") |
| Auditors all run on the orchestrator's model | The host ignores the agent frontmatter | Since 1.15.0 every Agent call passes `model` and `effort`; check `agent_spawn` in `dev_state.py telemetry summary` |
| A parallel implementer hit a merge conflict | Two tasks touched the same shared file | It is re-run alone after the others; mark such files as shared in the plan |
| `release` stops on missing reviews | Every review must be `pass` (or `n/a` in existing projects) | Run `/dev-kit:review <target>` or `/dev-kit:usability` |
| `deploy` stops before installing | A prerequisite is missing, the gate is not passed, or the tree is dirty outside `.dev/` | Provide the prerequisite (by name, never in the chat), pass the gate, commit; `--dry-run` shows what it would do |
| Existing project: the version proposed by `release` looks wrong | Manifest and latest tag disagree | `release` asks which one is right; the tag prefix follows the project |
| Existing project: QA flags old code | It should be `legacy` | Legacy findings never score and become issues; check that `brownfield` is in `state.json` (run `/dev-kit:start` to onboard) |
| Board: "Access link required" | It was shared with `--host` and opened without the key | Open the `access link:` URL; `/dev-kit:board status` prints it again |
| Board: a host name is refused | DNS rebinding protection | Open it by IP or `localhost` (SSH tunnel: `ssh -N -L 8765:127.0.0.1:<port> <host>`) |
| Board stopped by itself | No open tab for 2 hours | Start it again; `--idle-min N` changes the limit (0 = never) |
| Board: "started by another version" | The kit was updated while it ran | `/dev-kit:board stop`, then start it again |
| Agents in worktrees fail on `npm`/`node` with missing modules | Worktrees have no `node_modules` | Since 1.17.0 implementers link the main checkout's `node_modules` (never install there); check that `.gitignore` has `node_modules` without a trailing slash |
| Visual and a11y audits are "static reading, confidence low" | No browser or harness available | Let `plan` add the QA harness task (`qa:shots`, `qa:a11y`), or install Playwright and a Chromium; `dev_detect_stack.py --tools` shows what is found |
| The same long test suite runs several times per gate | Runs were not recorded | `implement` and `qa` record green runs with `dev_state.py tests record`; `tests lookup` shows whether one is reusable (a dirty tree never is) |
| Read-only commands keep asking for permission, or a guard refuses heredocs and `cd … &&` | The host's permission rules | Run `/fewer-permission-prompts`, or allow at least `Bash(python3 -I *dev_state.py*)`, `Bash(python3 -I *dev_score.py*)`, `Bash(python3 -I *dev_cost.py*)`, `Bash(python3 -I *dev_detect_stack.py*)`, `Bash(git status*)`, `Bash(git diff*)`, `Bash(git log*)`, `Bash(git rev-parse*)` and the project's test, lint and type-check commands |
| You do not know which skill to use | — | `/dev-kit:help <your question>` |

`dev_state.py` lives at `.claude/plugins/dev-kit/skills/core/scripts/dev_state.py` (or the installed plugin copy); run it with `python3 -I <path> --root . <command>`.
