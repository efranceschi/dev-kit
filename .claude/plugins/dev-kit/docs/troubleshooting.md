# Troubleshooting

| Symptom | Why | What to do |
|---|---|---|
| Autopilot stops overnight waiting for a permission | Claude Code asks before Bash commands and edits; the kit's own pauses are not the cause | Run `/fewer-permission-prompts` and start with `--permission-mode acceptEdits`; use the `unattended` autonomy level |
| The session froze or the machine rebooted | Long runs can be interrupted | `/dev-kit:start` reconciles the state with git; `/dev-kit:autopilot` continues from the current lifecycle step |
| Processes still running after a run (ports busy, high load) | An agent left a background process | `/dev-kit:start` stops them (only processes inside the project) and frees expired locks; `/dev-kit:status` shows leftovers |
| A gate keeps failing | Real problems, or the same finding coming back | Read `.dev/qa/<M>/report.md`; from round 2 only previous findings and new medium+ findings count (delta mode). When rounds are exhausted the kit asks (or applies your pause policy) |
| A gate or review is refused | The score is below the cut-off | Fix the findings and re-run; forcing needs your decision and an ADR, and is never allowed with security below its minimum or critical/high open |
| `/dev-kit:costs` shows nothing or "partial" | No Claude Code transcripts for this project on this machine | Costs come from `~/.claude/projects/<project>/`; on another machine only the token totals the skills logged are available |
| A model shows `n/d` in costs | No price for it in `.dev/costs/prices.json` | Add the model to that file (US$ per million tokens) |
| A task cannot start: "gate of Mn is pending" | Milestones are sequential | Finish and pass `qa Mn`; only hotfix tasks bypass this |
| "hotfix … is still open (WIP 1)" | Only one hotfix at a time | Finish it (`implement`, `qa --scope`, `release --hotfix`, which also deploys it) or classify the new one as standard |
| An issue never gets scheduled | Standard and intangible issues wait for the next milestone's buffer or the cool-down (in maintenance mode they are scheduled straight into the open maintenance milestone) | `/dev-kit:backlog issues` shows the queue; `/dev-kit:issue --schedule I-003 M8` brings it into an existing milestone |
| Too many tips | Each tip shows at most twice | `/dev-kit:settings tips off` (`tips reset` shows them again) |
| `start` says the `core` skill is missing | The support skill was not installed next to the others | Reinstall the plugin (`/plugin install dev-kit@dev-kit`); `core` holds the scripts and templates |
| "add the task to Mn+1": `add-task` refuses a milestone | Its gate already passed | Use the next milestone (`--milestone-title` creates a maintenance one), or `--lane hotfix` for a critical/high bug |
| A task dropped in a replan still blocks the milestone | It was blocked instead of dropped (before 1.12.0) | `/dev-kit:plan replan` drops it properly (kept for history, no longer counted) |
| The wrong commit was recorded for a task | A hook rewrote it or the SHA was taken too early | `/dev-kit:start` finds the commit that carries the task and fixes the record after asking you |
| "event rejected" in a skill | A field or feedback area is not allowlisted | Use the areas in conventions §13; never put project text into an event. Before `init`, events are skipped on purpose |
| "review … n/a needs --note" | `n/a` must say why | Nothing to do: the skill records the reason and continues; if it repeats, `/dev-kit:feedback` |
| `set phase` is refused | The phase is derived from `.dev/` (conventions §19) | Run the skill of the step `status` shows; `/dev-kit:start` routes there |
| The phase went back to `conception` in the middle of construction | A PRD or design file changed after its review (a scope change, or a hand edit): conception is *reopened* | Finish the change: the step's review (`/dev-kit:review prd`), the refreshed downstream specs and `/dev-kit:plan replan`; the milestone in construction keeps its state. A hand edit with no impact: `dev_state.py artifact mark <name> --note "no impact: …"` and re-run the review |
| The project never reaches `stable` | A closed milestone waits in the release train, or an issue is queued | `/dev-kit:status` shows the release train; release it (`/dev-kit:release`) or schedule the issue (`/dev-kit:backlog`) |
| An auditor result shows `F-000` "no parsable result" | The agent wrote no valid result file, even after the `check` output was sent back | Re-run `qa` (the gate cannot pass silently); report it with `/dev-kit:feedback` |
| A QA report mentions an agent result "not valid" | The agent wrote a result outside the contract | Nothing to do: the skill sends the problem back to the agent and re-checks; synonyms are fixed on their own. If it keeps happening, `/dev-kit:feedback` |
| `/dev-kit:costs` shows very few requests or `n/d` | Transcripts with `requestId: "unknown"` or gateway model names (before 1.15.0) | Update the kit and run `/dev-kit:costs` again: it re-reads the transcripts, and gateway names are priced (a family match says "priced as") |
| Auditors all run on the orchestrator's model | The host ignores the agent frontmatter | Since 1.15.0 every agent call passes its model and effort; `/dev-kit:costs --by agent` and `--by model` show which model each agent used |
| A parallel implementer hit a merge conflict | Two tasks touched the same shared file | It is re-run alone after the others; mark such files as shared in the plan |
| `release` stops on missing reviews | Every review must be `pass` (or `n/a` in existing projects) | Run `/dev-kit:review <target>` or `/dev-kit:usability` |
| `deploy` stops before installing | A prerequisite is missing, the gate is not passed, or the tree is dirty outside `.dev/` | Provide the prerequisite (by name, never in the chat), pass the gate, commit; `--dry-run` shows what it would do |
| Existing project: the version proposed by `release` looks wrong | Manifest and latest tag disagree | `release` asks which one is right; the tag prefix follows the project |
| Existing project: QA flags old code | It should be `legacy` | Legacy findings never score and become issues; check that `brownfield` is in `state.json` (run `/dev-kit:start` to onboard) |
| Board: "Access link required" | It was shared with `--host` and opened without the key | Open the `access link:` URL; `/dev-kit:board status` prints it again |
| Board: a host name is refused | DNS rebinding protection | Open it by IP or `localhost` (SSH tunnel: `ssh -N -L 8765:127.0.0.1:<port> <host>`); behind your reverse proxy, `/dev-kit:board --trusted-host <its host name>` |
| Board behind a proxy: buttons answer "forbidden origin" | The proxy's host name is not trusted | `/dev-kit:board --trusted-host <name>` (without scheme or port) |
| Board stopped by itself | No open tab and no session listening for 2 hours | Start it again; `--idle-min N` changes the limit (0 = never) |
| Board: requests stay "waiting" | No Claude Code session is listening | Run `/dev-kit:board` in the project's Claude Code session (it then listens), or `/dev-kit:worker` to run the queue once; the Requests card says "Claude Code: not running" until one does |
| Board: "Claude Code: open, not listening" | That session ran `/dev-kit:worker` but did not open the board, or its Claude Code has no plugin monitors | Run `/dev-kit:board` there; if it still says "not listening", update Claude Code, and meanwhile `/dev-kit:worker` runs the queue when you ask |
| Board: a permission waits in Needs you | Claude Code needs it for the request it runs | Allow, Allow for this session (the rule shown, until the session ends) or Deny; with no answer it is denied after 10 minutes |
| The terminal still asks for permissions during a board request | No board is running, or the request is not a board request | Start the board with `/dev-kit:board`; outside board requests the terminal prompt applies as usual |
| Board: "It stopped going on by itself" | Continuous mode met something that needs you; the card says what | Deal with it, then "Go on" |
| Board: "actions off" or no ▶ buttons | It was started with `--actions off` | `/dev-kit:board --actions on` |
| Board: "another session is the executor" | Two Claude Code sessions ran `/dev-kit:worker` | Keep one; the other is refused while the first is alive |
| Board: "started by another version" | The kit was updated while it ran | `/dev-kit:board stop`, then start it again |
| Agents in worktrees fail on `npm`/`node` with missing modules | Worktrees have no `node_modules` | Since 1.17.0 implementers link the main checkout's `node_modules` (never install there); check that `.gitignore` has `node_modules` without a trailing slash |
| Visual and a11y audits are "static reading, confidence low" | No browser or harness available | The QA report says which tools were missing; `/dev-kit:plan replan` adds the QA harness task (Playwright with mocks, axe), or install Playwright and a Chromium |
| The same long test suite runs several times per gate | Runs were not recorded (before 1.17.0) | Update the kit: `implement` and `qa` record green runs per commit and reuse them until the code changes; the QA report shows what was reused |
| Read-only commands keep asking for permission, or a guard refuses heredocs and `cd … &&` | The host's permission rules | Run `/fewer-permission-prompts`, or allow at least `Bash(python3 -I *dev_state.py*)`, `Bash(python3 -I *dev_score.py*)`, `Bash(python3 -I *dev_cost.py*)`, `Bash(python3 -I *dev_detect_stack.py*)`, `Bash(git status*)`, `Bash(git diff*)`, `Bash(git log*)`, `Bash(git rev-parse*)` and the project's test, lint and type-check commands |
| A QA round re-audits files that did not change | No earlier clean review of them (round 1), or a checklist, spec or kit update invalidated it | Expected; the QA report's "Reused work" line says why each file was reviewed. `/dev-kit:settings` turns reuse off if you prefer |
| You suspect the reuse hid a problem | Reuse only skips unchanged files that were clean, with spot checks | `/dev-kit:qa M<n> --full` audits everything again; `release` always does |
| Two parallel tasks fought over a session, database or device | It is an exclusive resource nobody listed | Ask `/dev-kit:architecture` to add it to "Exclusive resources"; agents then lock it while in use, and `/dev-kit:status` shows who holds it |
| CHANGELOG or README conflicts when merging parallel tasks | Tasks edited them directly | Tasks write `changelog.d/T-xxx.md` and `docs/setup.d/T-xxx.md`; `docs` merges them |
| You do not know which skill to use | — | `/dev-kit:help <your question>` |

You never need to run the kit's scripts yourself: every fix above goes through a skill. `/dev-kit:help <question>` finds the right one.
| The dev-kit status line does not appear | The project already had its own `statusLine` (kept), hooks or the status line are off (`disableAllHooks`), or a higher settings level sets one | `/dev-kit:settings` shows what is on; `/status` in Claude Code lists the settings files it loaded |
| No dev-kit tips under the spinner | Tips load at session start, or `spinnerTipsEnabled` is false | Start a new session; turn tips on in `/config` (Show tips) and with `/dev-kit:settings` |
| The grey suggestion is not the next command | Claude Code predicts it and skips it in plan mode, after an error, with a cold cache or with suggestions off | Type the command shown on the last line of the report (or in the status line); `promptSuggestionEnabled` turns suggestions back on |
| No desktop notification | Notifications are off, or the terminal ignores OSC 9 | `/dev-kit:settings` notifications on; the same text also shows as a line in the chat at the end of the turn |
