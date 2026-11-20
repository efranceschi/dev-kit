# Board autonomy check

A one-off script to confirm, on your Claude Code version, the three things the autonomous board relies on and that the kit's tests cannot reach: the plugin monitor wakes an idle session, the `PermissionRequest` hook answers from the board, and the process ids line up. It takes about 15 minutes. At the end you zip one folder and send it to the kit's author.

Nothing here touches a real project: it works in a scratch folder.

## Before you start

- Claude Code with this plugin at version 1.27.0 or later (`/plugin`, Installed tab). Run `/reload-plugins` or start a new session after updating.
- A terminal you can leave open (tmux works well), and a browser on the same machine or through an SSH tunnel.

## 1. Prepare the scratch project (in a shell)

```bash
mkdir -p ~/dev-kit-check && cd ~/dev-kit-check && git init -q
export DEV_KIT_HOOK_TRACE=1        # the plugin's hooks log what they see to .dev/run/hook-trace.jsonl
claude
```

`DEV_KIT_HOOK_TRACE=1` must be set before `claude` starts. It records event names, process ids, the keys of each payload and, for permission prompts, the tool name and Claude Code's suggested rules. It never records commands, file contents or prompts.

## 2. Paste this prompt into that Claude Code session

> Run a dev-kit board autonomy check in this folder. Work step by step and write every observation to `.dev/run/autonomy-check/notes.md` (create it), each step under its own heading, with exact command outputs.
>
> 1. Create a tiny dev-kit project here, already past conception and planning so it starts in construction: `dev_state.py init --project autonomy-check`; one-line `.dev/brief.md`, `.dev/prd.md` and `.dev/architecture.md`; a `plan.md` with one milestone M1 and two tasks: T-001 "Create hello.txt" (writes `hello.txt` with the text hello, type chore) and T-002 "Run ls" (runs `ls -la` in Bash and records the output in `out.txt`, type chore); then `dev_state.py sync-plan`, `dev_state.py artifact mark all`, `dev_state.py review prd pass --score 90`, `dev_state.py review design n/a --note "no UI"` and `dev_state.py review plan pass --score 90`. `dev_state.py status --short` must say `phase: construction · M1`. Use the kit's scripts through `${CLAUDE_PLUGIN_ROOT}` as the dev-kit skills do.
> 2. Record in the notes: `claude --version`, `echo $PPID` from Bash, and `ps -o pid,ppid,comm -p $PPID`.
> 3. Run `/dev-kit:board --no-open`. Record its full output, especially the `requests:` line and whether `DW arm` said `listening` or `not listening`. Record the output of `dev_worker.py status --json` and the content of `.dev/run/worker-armed.json` and `.dev/run/worker-watch.json`. Record whether `/tasks` lists a monitor named `board-requests`.
> 4. Stop and tell me: "Board ready. Open <the URL> in the browser, then follow step 3 of docs/board-autonomy-check.md." Then end your turn and do nothing else until a notification arrives.

## 3. In the browser, while the session sits idle

Do these one at a time, and for each one write in `.dev/run/autonomy-check/manual.md` what you saw (copy the text of the Requests card, the time it took, and anything the terminal printed):

1. **Wake-up.** Click ▶ next to "Next step" (`/dev-kit:implement`). Within a few seconds the terminal should show a notification `dev-kit board: request R-001 is waiting...` and Claude should start `/dev-kit:worker` by itself. Note whether it did, how long it took, and what the card said ("listening", "working on R-001").
2. **Permission from the board.** When Claude reaches T-002 it needs Bash (`ls -la`). If your permission settings already allow it, the board shows nothing; in that case, in the session's settings remove any allow rule for `Bash(ls:*)` before step 1, or write the observation and continue. When "Claude Code asks permission" appears in Needs you, note: did the terminal *also* show a permission dialog? Wait about 2 minutes, then click **Allow for this session** (or **Allow** if that button is missing). Note whether the work continued, and whether a second `ls` later in the same session asked again.
3. **Deny.** Queue `/dev-kit:status` with ▶ (or any other runnable command), and while it runs, if a permission appears, click **Deny**. Note what Claude did next.
4. **Timeout.** If you can, let one permission go unanswered: it should be denied after 10 minutes. Note when the terminal moved on.
5. **Tab alert.** With a question or permission waiting, note the tab's title and icon.
6. **Go on by itself.** Turn it on. Note which steps started alone and the reason shown when it stopped.

## 4. Collect and send

Back in the terminal session, paste:

> Finish the dev-kit board autonomy check: append to `.dev/run/autonomy-check/notes.md` the output of `dev_worker.py status --json` and `dev_worker.py list --all`, then copy `.dev/run/hook-trace.jsonl`, `.dev/run/worker-watch.json`, `.dev/run/worker-armed.json`, `.dev/run/board.log` and `.dev/log.md` into `.dev/run/autonomy-check/`, and run `cd .dev/run && zip -r ~/dev-kit-autonomy-check.zip autonomy-check`. Tell me the path of the zip.

Send `~/dev-kit-autonomy-check.zip`. It contains only this scratch project's files, process ids, event names and permission rule suggestions.

## What the author looks for

- Monitor: started by `/dev-kit:board` (`on-skill-invoke:board`), its parent chain contains the armed Claude Code pid, and one line woke the idle session. If not, the fallback is a `Stop` hook with `asyncRewake` running `dev_worker.py wait`.
- `PermissionRequest`: the hook's pid chain reaches the executor; the terminal dialog's behaviour while the hook waits; the decision applied after minutes; `updatedPermissions` with destination `session` stopped further prompts for the same rule; the 660 s hook timeout held for a 600 s wait.
- `$PPID` in Bash equals the Claude Code process seen by hooks and the monitor.
