# Maintainers

How the plugin is built, tested and documented. Users do not need this page.

## Layout

```
.claude/plugins/dev-kit/
  .claude-plugin/plugin.json     name, version, description
  README.md                      landing page
  docs/                          user docs (four of them generated, see below), e2e checklist, flow diagram
  CHANGELOG.md                   kit versions (bump .claude-plugin/plugin.json and add an entry for every change)
  agents/*.md                    17 agents (model + effort + color in the frontmatter, conventions §9 and §13)
  hooks/hooks.json               optional SessionStart / UserPromptSubmit / PermissionRequest / SubagentStart / SubagentStop /
                                 Stop hooks: board's live agents, session title and banner, desktop notifications, requests
                                 waiting on the board; its `modules` names the status pane below
  hooks/status-pane.tsx          optional terminal status pane (a Claude Code function-hooks module, TypeScript), with
                                 status-pane-model.ts (pure snapshot logic) and status-pane.test.tsx (claude plugin test)
  types/index.d.ts               the pane's $.state contract, named as "types" in plugin.json
  monitors/monitors.json         the board's listener (dev_worker.py watch), started the first time /dev-kit:board runs
  skills/*/SKILL.md              25 skills, invoked as /dev-kit:<name>
  skills/core/                   support skill, not invocable
    SKILL.md                     marker (disable-model-invocation: true, user-invocable: false)
    scripts/dev_state.py         state: init, sync-plan, next, start, done, block, unblock, drop, add-task, add-question,
                                 fix-tasks, gate, review, artifact, stale, xref, tests, ledger, brief, tier, set-risk, risk-profile,
                                 risk-report, lock, strings, contrast, set, status, issues (add-issue, issue, pull-issues, cooldown, backlog),
                                 preview, deploy, cleanup, event, feedback, telemetry, tip, tips, notify,
                                 board plan edits (move-task, new-milestone, reorder, plan-apply), answer-question, release-record;
                                 lifecycle() derives the project phase (conventions §19) for status, next command,
                                 status line, banner and board: never stored except as a cache in state.json
    scripts/dev_worker.py        the board's request queue to Claude Code: validation, lifecycle, executor, modes, approvals,
                                 the listener (watch, arm) and continuous mode (continue-next)
    scripts/dev_risk.py          risk tier of a task (signals, weights, floors) and risk profile of a milestone, predicted ×
                                 real rows (imported by dev_state.py and dev_router.py; no command line)
    scripts/dev_router.py        model/effort router with feedback loops over .dev/router.json: route, observe, learn, explain,
                                 reset (conventions §9 "Router"); dev_state.py calls it on start, done, block, reopen and gate
    scripts/dev_score.py         0–100 score per dimension (low cap, dedupe, delta mode, legacy findings ignored)
    scripts/dev_ledger.py        work ledger: fingerprints of verified work, incremental plans, spot checks (conventions §18)
    scripts/dev_telemetry.py     allowlisted session log, stage grades (imported by the other scripts)
    scripts/dev_cost.py          token usage and estimated cost from Claude Code transcripts
    scripts/dev_docs.py          generated docs and /dev-kit:help answers
    scripts/dev_detect_stack.py  stack detection (manifests, manifests in subfolders, source files); --tools: QA tooling
    scripts/dev_board.py         local board server for /dev-kit:board (page in shared/board/)
    scripts/dev_agent_hook.py    hook handler: board's live agents (.dev/run/agents.jsonl), session title, notifications
    scripts/dev_ui.py            Claude Code interface: spinner tips and status line in .claude/settings.local.json
    scripts/dev_statusline.py    the status line itself (read-only, one line, silent outside a dev-kit project)
    shared/conventions.md        the rules every skill and agent follows (§0–§19)
    shared/onboarding.md         adoption of an existing codebase (run by start)
    shared/help.json             catalog for help and the generated docs (English only)
    shared/tips.json             contextual tips (English only)
    shared/board/                index.html, board.js, board.css, favicon of the board (and its "needs you" variant)
    shared/interview/ templates/ checklists/ prompts/   interview script, artifact templates, review checklists, output and isolation contracts
    tests/                       lint_suite.py, test_dev_state.py, test_dev_state_gaps.py, test_dev_board.py,
                                 test_dev_cost.py, test_dev_docs.py, test_dev_score.py, test_dev_ledger.py, test_dev_spec.py,
                                 test_dev_ui.py, test_dev_worker.py, test_dev_router.py
```

Requirements: Python 3.10+ (standard library only) on Linux or macOS. Process checks (`cleanup`, board liveness) read `/proc` and are best effort on macOS; the board server uses `fcntl` and does not run on native Windows (use WSL).

## How the kit finds its own files

- Skills reference support files as `${CLAUDE_SKILL_DIR}/../core/...`; install `core` together with the other skills (`start` warns if it is missing).
- Agents and shared files get no variable substitution: they use `<KIT>`, and the skill that spawns an agent passes `Kit root: <absolute path>` in the prompt.
- State commands use `${CLAUDE_PROJECT_DIR}` so they keep pointing at the project.
- Scripts run with `python3 -I`; modules next to them are imported by inserting the script folder into `sys.path` explicitly.
- One optional hook set (`hooks/hooks.json`: SessionStart, SubagentStart, SubagentStop, Stop) feeds the board's live Agents panel through `dev_agent_hook.py`, which stores only ids, the agent type and the path of the subagent's own transcript in `.dev/run/agents.jsonl`; the board reads the `Scope:` line of the agent's prompt from that transcript to put it on its task card (conventions §13). It writes only inside a dev-kit project (`.dev/state.json` exists). Nothing depends on it: where the environment does not run plugin hooks, the board still shows agents logged by the skills (`agent_spawn`/`agent_end`), and the live badges simply do not appear for agents outside dev-kit skills. The same handler sets the session title and a one-line banner with the next command on a new session (`autonomy.ui.title`), and at the end of each turn shows the notices `dev_state.py` queued in `.dev/run/notify.jsonl` (`autonomy.ui.notify`) as a chat line and an OSC 9 desktop notification.
- The status pane (`hooks/status-pane.tsx`, listed under `modules` in `hooks/hooks.json`) is a Claude Code function-hooks module: in a build that loads them it opens a pane beside the chat, at the start of a session inside a dev-kit project and only when the terminal has room, showing the phase, the current milestone's progress and gate, its tasks grouped as Running, Blocked, To do and Done, what needs the user, issues, the other milestones and the next command. It never reads `state.json` itself: it runs `dev_state.py --root <project> status --json --quiet-if-missing` through `$.process.run`, at session start, after each turn and every 5 s while the pane is open, and only when the mtime or size of `state.json` or `open-questions.md` changed. Keys in the pane: `m` current milestone or all, `d` show or hide done tasks, `r` refresh; `/dev-kit-pane` opens or closes it. Nothing depends on it: a Claude Code without function hooks ignores `modules`, and the command hooks in the same file run as before. `.ts`/`.tsx` files are outside the lint's English check (`TEXT_SUFFIXES`), so keep the pane's strings in English by hand. Check it with `claude plugin validate`, `claude plugin test` and `tsc` (the tsconfig is in the header of the engine's `claude-code.d.ts`).
- The board reaches a session through one plugin monitor (`monitors/monitors.json`, `when: on-skill-invoke:board`): Claude Code starts `dev_worker.py watch` the first time `/dev-kit:board` runs in a session and delivers each line it prints to Claude as a notification. The watcher prints only for the session `/dev-kit:board` armed (`dev_worker.py arm --pid $PPID`: it checks that the armed process is one of its own parents), so it is silent everywhere else, including projects without `.dev/state.json`, where it exits at once. Monitors do not start with `claude -p`, and a Claude Code without plugin monitors ignores the file: the board then says "not listening" and `/dev-kit:worker` runs the queue by hand. Every line a monitor prints costs a turn, so the watcher never prints progress, only a request that waits. After a plugin update the running processes keep the old code: the board server hashes every script and page asset (`code_id()`) and stops itself when they change on disk, and the watcher stops with one `the kit was updated` notification when `plugin.json` changes; `/dev-kit:board` then starts both again. `/dev-kit:board` also drains requests already pending by invoking `/dev-kit:worker` once.
- A plugin cannot ship `settings.json`, so the spinner tips and the status line are written by `dev_ui.py` to the project's `.claude/settings.local.json` (added to `.git/info/exclude` when git does not ignore it yet). Ownership is by marker: tips starting with `dev-kit: ` and a `statusLine` whose command runs `dev_statusline.py`; nothing else in the file is touched, and a status line of the user's own is never replaced. The command holds the absolute script path (settings do not expand `${CLAUDE_PLUGIN_ROOT}`); `start` runs `dev_ui.py repair` so a plugin update does not leave it pointing at an old version. Project and local settings accept only plain-string spinner tips (no id, cooldown or label), which is why the prefix marks them.
- The project phase is derived, not stored: `dev_state.lifecycle()` reads artifacts and `stale_report()`, reviews, milestones and gates, the issue queue and `state.releases`, and returns the phase, the step, each phase's state and the next release. `next_command()` and the board build on it; `Store.save()` caches `phase`/`step`/`reopened` for readers that load `state.json` directly; `migrate_legacy_phase()` converts the straight-line phases of kits before 1.30 on load. A skill moves the lifecycle only by leaving its normal trace (`artifact mark`, `review`, `gate`, `release-record`), so there is no phase to forget or set wrong.
- Claude Code's prompt suggestion (greyed-out, Tab or Right arrow) cannot be set by a plugin; it is predicted from the conversation. Every skill ends its report with the next command on the last line (conventions §15), and `dev_state.py status --next` computes it the same way for the status line and the banner.

## Frontmatter

Skills use `argument-hint` and `disable-model-invocation`, which Claude Code accepts. Uploads to claude.ai and to the API accept only `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`; for such uploads remove the other two fields (write-oriented skills may then be triggered automatically). Agents must declare `model` (haiku | sonnet | opus), `effort` and `color` (red | blue | green | yellow | purple | orange | pink | cyan: Claude Code shows it, and the board uses the same color for the agent).

## Language

Every file of the kit is in English. Skills translate at display time into the user's language (tips, help, reports). The lint rejects non-English text; the only exceptions are listed in `ALLOW_NON_ENGLISH` in `lint_suite.py` (language examples and the Portuguese e2e scenario).

## Documentation

- Hand-written: `README.md`, `docs/getting-started.md`, `docs/concepts.md`, `docs/troubleshooting.md`, this page, `docs/e2e-checklist.md`.
- Generated from `skills/core/shared/help.json` and the frontmatter: `docs/skills.md`, `docs/agents.md`, `docs/recipes.md`, `docs/glossary.md`. Never edit them by hand.
- Adding or changing a skill: add or update its entry in `help.json` (category, one_line, when, args, examples, produces, related), then:

```bash
python3 -I skills/core/scripts/dev_docs.py build
```

The lint runs `dev_docs.py check`, which fails if a skill has no catalog entry, the catalog names a skill that does not exist, an example does not use its own skill, or a generated doc is stale.

- Flow diagram: edit `docs/dev-kit-flow.dot`, then `cd docs && dot -Tsvg dev-kit-flow.dot -o dev-kit-flow.svg && dot -Tpng -Gdpi=110 dev-kit-flow.dot -o dev-kit-flow.png`.

## Verification

Run from `.claude/plugins/dev-kit/`:

```bash
python3 -I skills/core/tests/lint_suite.py
python3 -I -m unittest discover -s skills/core/tests -v
```

The lint checks frontmatter, references to support files, `<KIT>` use in agents, agent models, the reviewer ↔ score dimension mapping, English-only text and the generated docs, plus (since 1.12.0) that every script command quoted in the markdown exists with its flags, that `help.json` args match each `argument-hint`, that counts and section ranges in the prose are right, that every skill has a telemetry stage and the feedback areas listed in conventions §13 match the script, that `conventions.md §N` references exist, and that no skill tells the model to invoke a skill marked `disable-model-invocation`. One test copies only `skills/` and `agents/` elsewhere and runs the commands embedded in the skills. Manual end-to-end script: [e2e-checklist](e2e-checklist.md).
