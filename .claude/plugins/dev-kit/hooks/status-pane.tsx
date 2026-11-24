// dev-kit status pane: a live view of the project's .dev/ state beside the chat,
// for Claude Code builds that load function hooks (mods). Optional: nothing in
// the kit depends on it, and a Claude Code without mods ignores this file.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { PaneView, Snapshot, TaskCard } from '../types'
import { agentsByNode, autopilotLine, bar, emptySnapshot, needsYou, since, toLive, toSnapshot } from './status-pane-model'

const PANE = 'dev-kit-status'
const TITLE = 'dev-kit'
const COMMAND = 'dev-kit-pane'
const POLL_MS = 5000
// What runs now can change with no file changing (a process ends): read it again at least this often.
const LIVE_MAX_AGE_MS = 30000
// The run files `dev_board.py pane` reads: a change in any of them reads it again.
const LIVE_FILES = [
  'run/agents.jsonl', 'run/autopilot.json', 'run/autopilot-run.json', 'run/round.json', 'run/round-activity.json',
  'run/worker.json', 'run/worker-auto.json', 'run/board.json', 'run/inbox', 'run/approvals',
]

// Change a shape tag when its fields change: an earlier version's value is declined.
const snapshot = atom({ plugin: 'dev-kit', key: 'snapshot' } as const, emptySnapshot(false), {
  shape: 'snapshot-2',
})
const view = atom({ plugin: 'dev-kit', key: 'view' } as const, { scope: 'current', showDone: true } as PaneView, {
  shape: 'view-1',
})

/** Walks up from the session's directory to the folder holding .dev/state.json. */
async function findRoot($: EngineInterface): Promise<string | undefined> {
  let dir = await $.session.cwd()
  for (let i = 0; i < 40; i++) {
    try {
      const st = await $.fs.stat(`${dir}/.dev/state.json`)
      if (st.kind === 'file') return dir
    } catch {
      // not here: go up
    }
    const up = dir.replace(/\/[^/]+\/?$/, '') || '/'
    if (up === dir) return undefined
    dir = up
  }
  return undefined
}

/** Signature of the files the snapshot depends on, to skip a read when nothing moved. */
async function signature($: EngineInterface, root: string, files = ['state.json', 'open-questions.md']): Promise<string> {
  const parts: string[] = []
  for (const f of files) {
    try {
      const st = await $.fs.stat(`${root}/.dev/${f}`)
      parts.push(`${st.mtimeMs}:${st.size}`)
    } catch {
      parts.push('-')
    }
  }
  return parts.join('|')
}

let lastSig = ''
let lastLiveSig = ''
let lastLiveAt = 0
let isReading = false
// Opened once in this module's life: after that only the person opens it again.
let wasOpened = false

async function refresh($: EngineInterface, force = false): Promise<Snapshot> {
  if (isReading) return read($, snapshot)
  isReading = true
  try {
    const root = await findRoot($)
    if (!root) {
      lastSig = ''
      const none = emptySnapshot(false)
      await update($, snapshot, () => none)
      return none
    }
    const sig = await signature($, root)
    const liveSig = await signature($, root, LIVE_FILES)
    const now = await $.clock.now()
    const liveDue = force || liveSig !== lastLiveSig || now - lastLiveAt >= LIVE_MAX_AGE_MS
    if (!force && sig === lastSig) {
      if (!liveDue) return read($, snapshot)
      const live = await readLive($, root, now)
      lastLiveSig = liveSig
      const cur = await read($, snapshot)
      const snap = { ...cur, ...(live ? { live } : {}) }
      await update($, snapshot, () => snap)
      return snap
    }
    const script = `${$.plugin.root}/skills/core/scripts/dev_state.py`
    const ran = await $.process.run(['python3', '-I', script, '--root', root, 'status', '--json', '--quiet-if-missing'], {
      cwd: root,
      timeoutMs: 20000,
    })
    let snap: Snapshot
    if (ran.exitCode !== 0) {
      snap = { ...(await read($, snapshot)), isProject: true, error: (ran.stderr.trim().split('\n').pop() || `exit ${ran.exitCode}`).slice(0, 160) }
    } else if (!ran.stdout.trim()) {
      snap = emptySnapshot(false)
    } else {
      snap = toSnapshot(JSON.parse(ran.stdout), now)
      lastSig = sig
    }
    if (snap.isProject) {
      const live = liveDue ? await readLive($, root, now) : (await read($, snapshot)).live
      if (liveDue) lastLiveSig = liveSig
      if (live) snap = { ...snap, live }
    }
    await update($, snapshot, () => snap)
    return snap
  } catch (err) {
    const snap = { ...(await read($, snapshot)), error: `could not read the state: ${String(err).slice(0, 120)}` }
    await update($, snapshot, () => snap)
    return snap
  } finally {
    isReading = false
  }
}

/** What runs now: the Autopilot, its round, the agents, the board's requests and permission prompts. */
async function readLive($: EngineInterface, root: string, now: number) {
  lastLiveAt = now
  try {
    const ran = await $.process.run(['python3', '-I', `${$.plugin.root}/skills/core/scripts/dev_board.py`, '--root', root, 'pane', '--json'], {
      cwd: root,
      timeoutMs: 20000,
    })
    if (ran.exitCode !== 0 || !ran.stdout.trim()) return undefined
    return toLive(JSON.parse(ran.stdout), now)
  } catch {
    return undefined // an older kit without `pane`, or a busy disk: the task board still shows
  }
}

async function isOpen($: EngineInterface): Promise<boolean> {
  return (await $.ui.panes()).some(p => p.id === PANE)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({ name: COMMAND, description: 'Show or hide the dev-kit status pane', immediate: true })
    const snap = await refresh($, true)
    if (snap.isProject) {
      wasOpened = true
      void $.ui.open({ id: PANE, title: TITLE })
    }
    $.clock.every(POLL_MS, () => {
      void (async () => {
        if (await isOpen($)) await refresh($)
      })().catch(() => {})
    })
    return started
  })

  on('command.run', { command: COMMAND }, async $ => {
    if (await isOpen($)) {
      await $.ui.close({ id: PANE })
      return { text: 'dev-kit status pane closed.' }
    }
    const snap = await refresh($, true)
    wasOpened = true
    const opened = await $.ui.open({ id: PANE, title: TITLE })
    if (!snap.isProject) return { text: 'dev-kit status pane opened (no .dev/ project here yet).' }
    return { text: opened.isPlaced ? 'dev-kit status pane opened.' : 'dev-kit status pane will show when there is room.' }
  }).catch(($, e, next) => (next.called ? next(e) : { text: 'dev-kit status pane: could not open it.' }))

  // A turn may have run tasks, answered questions or closed a gate.
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    try {
      if (await isOpen($)) void refresh($).catch(() => {})
      else if (!wasOpened && (await findRoot($))) {
        // The turn created the project (/dev-kit:start): show it once, unasked.
        wasOpened = true
        await refresh($, true)
        void $.ui.open({ id: PANE, title: TITLE })
      }
    } catch {
      // the pane is a view: never fail a turn
    }
    return done
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const snap = await read($, snapshot)
    const v = await read($, view)

    if (!snap.isProject) {
      return (
        <Box flexDirection="column">
          <Text dimColor>No dev-kit project in this folder.</Text>
          <Text dimColor>Start one with /dev-kit:start.</Text>
        </Box>
      )
    }

    const now = await $.clock.now()
    const cur = snap.milestones.find(m => m.id === snap.current)
    const phase = [snap.phase, snap.step && snap.step !== snap.phase ? snap.step : ''].filter(Boolean).join(' › ')
    const needs = needsYou(snap)

    if (e.props.placement === 'widget') {
      const running = snap.tasks.filter(t => t.status === 'in_progress').map(t => t.id)
      const ap = snap.live?.autopilot
      const apMark = ap && (ap.state === 'running' || ap.state === 'stopping') ? `AP ${ap.where === 'session' ? 'here' : 'bg'}` : ap?.on ? `AP ${ap.state}` : ''
      const nAgents = snap.live?.agents.length ?? 0
      return (
        <Text wrap="truncate-end">
          {[phase, cur ? `${cur.id} ${cur.done}/${cur.total}` : '', apMark, running.length ? `▶ ${running.join(' ')}` : '',
            nAgents ? `⚙ ${nAgents}` : '', needs.length ? `! ${needs.length}` : '']
            .filter(Boolean)
            .join(' · ')}
        </Text>
      )
    }

    const scoped = v.scope === 'all' || !snap.current ? snap.tasks : snap.tasks.filter(t => t.milestone === snap.current)
    const tag = (t: TaskCard) => (v.scope === 'all' ? `${t.milestone} ` : '')
    const group = (status: TaskCard['status']) => scoped.filter(t => t.status === status)
    const running = group('in_progress')
    const blocked = group('blocked')
    const todo = group('todo')
    const done = group('done').sort((a, b) => (b.doneAt ?? '').localeCompare(a.doneAt ?? ''))

    // Rows: the pane's room less the fixed lines (header, milestone bar, next, keys).
    const apText = autopilotLine(snap.live, now)
    let room = Math.max(4, (e.props.scroll?.bodyRows ?? e.viewport?.rows ?? 24) - 5 - (apText ? 1 : 0))
    const take = <T,>(list: T[], keepHeader = true): T[] => {
      if (!list.length) return []
      const n = Math.max(0, Math.min(list.length, room - (keepHeader ? 1 : 0)))
      room -= n + (keepHeader ? 1 : 0)
      return list.slice(0, n)
    }
    // Priority order: Needs you > Agents > Running > Blocked > To do > Done > issues > milestones.
    const byNode = agentsByNode(snap.live)
    const agents = v.showAgents === false ? [] : (snap.live?.agents ?? [])
    const needsShown = take(needs)
    const agentsShown = take(agents)
    const runningShown = take(running)
    const blockedShown = take(blocked)
    const todoShown = take(todo)
    const doneShown = v.showDone ? take(done) : []
    const issuesShown = take(snap.issues)
    const others = snap.milestones.filter(m => m.id !== snap.current)
    const othersShown = take(others)

    const card = (t: TaskCard, extra: string, color?: string, isDim = false) => (
      <Text wrap="truncate-end" color={color} dimColor={isDim}>
        {'  '}
        {tag(t)}
        <Text bold={!isDim}>{t.id}</Text> {t.title}
        {t.lane === 'hotfix' ? ' [hotfix]' : ''}
        {extra ? <Text dimColor> {extra}</Text> : ''}
      </Text>
    )
    const heading = (label: string, count: number, color?: string) => (
      <Text bold color={color}>
        {label} <Text dimColor>({count})</Text>
      </Text>
    )
    const more = (shown: number, total: number) =>
      total > shown ? <Text dimColor>{'  '}+{total - shown} more</Text> : null

    return (
      <Box flexDirection="column">
        <Text wrap="truncate-end">
          <Text bold>{snap.project || 'project'}</Text> <Text dimColor>· {phase}</Text>
        </Text>
        {cur ? (
          <Text wrap="truncate-end">
            {cur.id} {cur.title} {bar(cur.done, cur.total)} {cur.done}/{cur.total}
            <Text dimColor>
              {' '}
              gate {cur.gate}
              {cur.score !== undefined ? ` ${cur.score}` : ''}
            </Text>
          </Text>
        ) : (
          <Text dimColor>No milestone in progress.</Text>
        )}
        {apText ? (
          <Text
            wrap="truncate-end"
            bold={snap.live?.autopilot.state === 'running'}
            color={snap.live?.autopilot.state === 'running' ? 'success' : ['waiting_user', 'release', 'backoff', 'stopped'].includes(snap.live?.autopilot.state ?? '') ? 'warning' : undefined}
            dimColor={!snap.live?.autopilot.on}
          >
            {apText}
            {snap.live?.autopilot.round?.lastTool ? <Text dimColor> · last {snap.live.autopilot.round.lastAgent ?? snap.live.autopilot.round.lastTool}</Text> : ''}
          </Text>
        ) : null}
        {snap.error ? <Text color="warning" wrap="truncate-end">{snap.error}</Text> : null}

        {needsShown.length > 0 && heading('Needs you', needs.length, 'warning')}
        {needsShown.map(line => (
          <Text color="warning" wrap="truncate-end">
            {'  '}
            {line}
          </Text>
        ))}

        {agentsShown.length > 0 && heading('Agents at work', agents.length, 'success')}
        {agentsShown.map(a => (
          <Text wrap="truncate-end" color="success">
            {'  '}
            <Text bold>{a.agent}</Text>
            {a.node ? ` → ${a.node}` : ''}
            <Text dimColor> {since(a.startedAt, now)}</Text>
          </Text>
        ))}
        {more(agentsShown.length, agents.length)}

        {runningShown.length > 0 && heading('Running', running.length, 'success')}
        {runningShown.map(t =>
          card(t, [since(t.startedAt, now), (byNode[t.id] ?? []).map(a => a.agent).join(', ')].filter(Boolean).join(' · '), 'success'),
        )}
        {more(runningShown.length, running.length)}

        {blockedShown.length > 0 && heading('Blocked', blocked.length, 'error')}
        {blockedShown.map(t => card(t, t.blockedReason ?? '', 'error'))}
        {more(blockedShown.length, blocked.length)}

        {todoShown.length > 0 && heading('To do', todo.length)}
        {todoShown.map(t => card(t, snap.next?.task === t.id ? `← next${snap.next.reason ? `: ${snap.next.reason}` : ''}` : ''))}
        {more(todoShown.length, todo.length)}

        {v.showDone && done.length > 0 && heading('Done', done.length)}
        {doneShown.map(t => card(t, t.commit ?? '', undefined, true))}
        {v.showDone && more(doneShown.length, done.length)}

        {issuesShown.length > 0 && heading('Issues', snap.issues.length)}
        {issuesShown.map(i => (
          <Text wrap="truncate-end">
            {'  '}
            <Text bold>{i.id}</Text> {i.title} <Text dimColor>{i.cls}</Text>
          </Text>
        ))}
        {Object.keys(snap.issueCounts).length > 0 && (
          <Text dimColor wrap="truncate-end">
            Open issues:{' '}
            {Object.entries(snap.issueCounts)
              .map(([cls, n]) => `${cls} ${n}`)
              .join(' · ')}
          </Text>
        )}

        {othersShown.length > 0 && heading('Milestones', others.length)}
        {othersShown.map(m => (
          <Text dimColor wrap="truncate-end">
            {'  '}
            {m.id} {m.title} [{m.done}/{m.total}] {m.gate}
            {m.score !== undefined ? ` ${m.score}` : ''}
          </Text>
        ))}

        {snap.nextCommand ? (
          <Text wrap="truncate-end">
            Next <Text bold>{snap.nextCommand}</Text>
          </Text>
        ) : null}
        <Box flexDirection="row" gap={1}>
          <Button
            key="scope"
            hotkey="m"
            plain
            dimColor
            label={v.scope === 'all' ? 'm current milestone' : 'm all milestones'}
            onPress={() => update($, view, (x): PaneView => ({ ...x, scope: x.scope === 'all' ? 'current' : 'all' }))}
          />
          <Button
            key="done"
            hotkey="d"
            plain
            dimColor
            label={v.showDone ? 'd hide done' : 'd show done'}
            onPress={() => update($, view, x => ({ ...x, showDone: !x.showDone }))}
          />
          <Button
            key="agents"
            hotkey="a"
            plain
            dimColor
            label={v.showAgents === false ? 'a show agents' : 'a hide agents'}
            onPress={() => update($, view, (x): PaneView => ({ ...x, showAgents: x.showAgents === false }))}
          />
          <Button key="refresh" hotkey="r" plain dimColor label="r refresh" onPress={() => refresh($, true)} />
        </Box>
      </Box>
    )
  })
}
