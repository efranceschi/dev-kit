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
| "hotfix … is still open (WIP 1)" | Only one hotfix at a time | Finish it (`implement`, `qa --scope`, `release --hotfix`) or classify the new one as standard |
| An issue never gets scheduled | Standard and intangible issues wait for the next milestone's buffer or the cool-down | `/dev-kit:backlog issues` shows the queue; `/dev-kit:issue --schedule I-003 M8` brings it into an existing milestone |
| Too many tips | Each tip shows at most twice | `dev_state.py set autonomy.tips off` |
| You do not know which skill to use | — | `/dev-kit:help <your question>` |

`dev_state.py` lives at `.claude/plugins/dev-kit/skills/core/scripts/dev_state.py` (or the installed plugin copy); run it with `python3 -I <path> --root . <command>`.
