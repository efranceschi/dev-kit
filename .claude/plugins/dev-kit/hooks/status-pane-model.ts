// Pure part of the status pane: turns `dev_state.py status --json` into the
// Snapshot the pane draws, and picks what fits. No `$`, so tests call it directly.
import type { IssueCard, LiveAgent, LiveView, MilestoneRow, Snapshot, TaskCard, TaskStatus } from '../types'

type Json = Record<string, unknown>

const SHOWN: readonly TaskStatus[] = ['todo', 'in_progress', 'blocked', 'done']
const OPEN_ISSUE = ['open', 'scheduled', 'in_progress']

const obj = (v: unknown): Json => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Json) : {})
const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined)
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)

/** Numeric order of ids like M2, M5.1 (after M5, before M6), T-014, I-003. */
export const byId = (a: string, b: string): number => {
  const n = (s: string) => (s.match(/\d+/g) || ['0']).map(Number)
  const x = n(a), y = n(b)
  return ((x[0] ?? 0) - (y[0] ?? 0)) || ((x[1] ?? 0) - (y[1] ?? 0)) || a.localeCompare(b)
}

export const emptySnapshot = (isProject: boolean, error?: string): Snapshot => ({
  isProject,
  ...(error ? { error } : {}),
  project: '',
  phase: '',
  step: '',
  milestones: [],
  tasks: [],
  nextCommand: '',
  openQuestions: 0,
  releasesWaiting: [],
  issueCounts: {},
  issues: [],
  readAt: 0,
})

export function toSnapshot(raw: unknown, readAt: number): Snapshot {
  const s = obj(raw)
  const tasks: TaskCard[] = []
  for (const [id, value] of Object.entries(obj(s.tasks))) {
    const t = obj(value)
    const status = t.status as TaskStatus
    if (!SHOWN.includes(status)) continue
    tasks.push({
      id,
      title: str(t.title) ?? id,
      milestone: str(t.milestone) ?? '',
      type: str(t.type) ?? '',
      status,
      ...(str(t.lane) ? { lane: str(t.lane) } : {}),
      ...(str(t.started_at) ? { startedAt: str(t.started_at) } : {}),
      ...(str(t.done_at) ? { doneAt: str(t.done_at) } : {}),
      ...(str(t.commit) ? { commit: str(t.commit)!.slice(0, 7) } : {}),
      ...(str(t.blocked_reason) ? { blockedReason: str(t.blocked_reason) } : {}),
    })
  }
  tasks.sort((a, b) => byId(a.id, b.id))

  const milestones: MilestoneRow[] = Object.entries(obj(s.milestones))
    .sort(([a], [b]) => byId(a, b))
    .map(([id, value]) => {
      const m = obj(value)
      const own = tasks.filter(t => t.milestone === id)
      return {
        id,
        title: str(m.title) ?? id,
        gate: str(m.gate) ?? 'pending',
        ...(num(m.score) !== undefined ? { score: num(m.score) } : {}),
        done: own.filter(t => t.status === 'done').length,
        total: own.length,
      }
    })
  // As dev_statusline.py: the first milestone with a pending gate and live tasks.
  const current = milestones.find(m => m.gate === 'pending' && m.total > 0)?.id

  const issueCounts: Record<string, number> = {}
  const issues: IssueCard[] = []
  for (const [id, value] of Object.entries(obj(s.issues))) {
    const i = obj(value)
    if (!OPEN_ISSUE.includes(str(i.status) ?? '')) continue
    const cls = str(i.class) ?? 'standard'
    issueCounts[cls] = (issueCounts[cls] ?? 0) + 1
    if (current && str(i.scheduled_in) === current) issues.push({ id, title: str(i.title) ?? id, cls })
  }
  issues.sort((a, b) => byId(a.id, b.id))

  const lifecycle = obj(s.lifecycle)
  const releases = Array.isArray(lifecycle.releases) ? lifecycle.releases : []
  const releasesWaiting = releases
    .map(obj)
    .filter(r => r.status === 'awaiting_approval')
    .map(r => str(r.id) ?? '?')

  const next = obj(s.next)
  return {
    isProject: true,
    project: str(s.project) ?? '',
    phase: str(s.phase) ?? '',
    step: str(s.step) ?? '',
    ...(current ? { current } : {}),
    milestones,
    tasks,
    ...(str(next.task) ? { next: { task: str(next.task)!, reason: str(next.reason) ?? '' } } : {}),
    nextCommand: str(s.next_command) ?? '',
    openQuestions: num(s.open_questions) ?? 0,
    releasesWaiting,
    issueCounts,
    issues,
    readAt,
  }
}

/** "12m", "3h", "2d" since an ISO time; empty when unknown. */
export function since(iso: string | undefined, now: number): string {
  const at = iso ? Date.parse(iso) : NaN
  if (!Number.isFinite(at)) return ''
  const min = Math.max(0, Math.floor((now - at) / 60000))
  if (min < 60) return `${min}m`
  if (min < 48 * 60) return `${Math.floor(min / 60)}h`
  return `${Math.floor(min / 1440)}d`
}

export function bar(done: number, total: number, width = 12): string {
  const full = total > 0 ? Math.round((done / total) * width) : 0
  return '█'.repeat(full) + '░'.repeat(width - full)
}

const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

/** `dev_board.py pane --json` into the LiveView the pane draws; anything it does not know is left out. */
export function toLive(raw: unknown, readAt: number): LiveView {
  const s = obj(raw)
  const ap = obj(s.autopilot)
  const rd = obj(ap.round)
  const last = obj(rd.last)
  const round = str(rd.skill)
    ? {
        skill: str(rd.skill)!,
        ...(str(rd.scope) ? { scope: str(rd.scope) } : {}),
        ...(str(rd.since) ? { since: str(rd.since) } : {}),
        tasks: arr(rd.tasks).filter((t): t is string => typeof t === 'string'),
        unregistered: rd.unregistered === true,
        ...(str(last.tool) ? { lastTool: str(last.tool) } : {}),
        ...(str(last.agent) ? { lastAgent: str(last.agent) } : {}),
        ...(str(last.at) ? { lastAt: str(last.at) } : {}),
      }
    : undefined
  const agents: LiveAgent[] = arr(s.agents).map(obj).filter(a => str(a.agent)).map(a => ({
    agent: str(a.agent)!,
    ...(str(a.node) ? { node: str(a.node) } : {}),
    ...(str(a.started_at) ? { startedAt: str(a.started_at) } : {}),
  }))
  return {
    board: obj(s.board).running === true,
    autopilot: {
      on: ap.on === true,
      state: str(ap.state) ?? 'off',
      ...(str(ap.where) ? { where: str(ap.where) } : {}),
      ...(str(ap.handoff) ? { handoff: str(ap.handoff) } : {}),
      ...(str(ap.since) ? { since: str(ap.since) } : {}),
      ...(str(ap.reason) ? { reason: str(ap.reason) } : {}),
      ...(num(ap.until) !== undefined ? { until: num(ap.until) } : {}),
      ...(round ? { round } : {}),
    },
    agents,
    runs: arr(s.runs).map(obj).filter(r => str(r.skill)).map(r => ({
      skill: str(r.skill)!,
      ...(str(r.scope) ? { scope: str(r.scope) } : {}),
      ...(str(r.started_at) ? { startedAt: str(r.started_at) } : {}),
    })),
    requests: arr(s.requests).map(obj).filter(r => str(r.id)).map(r => ({
      id: str(r.id)!,
      action: str(r.action) ?? '',
      status: str(r.status) ?? '',
      ...(str(r.question) ? { question: str(r.question) } : {}),
    })),
    approvals: arr(s.approvals).map(obj).filter(a => str(a.tool)).map(a => ({
      tool: str(a.tool)!,
      target: str(a.target) ?? '',
      ...(num(a.seconds_left) !== undefined ? { secondsLeft: num(a.seconds_left) } : {}),
    })),
    executor: str(obj(s.executor).state) ?? 'offline',
    readAt,
  }
}

const AP_WORDS: Record<string, string> = {
  off: 'off',
  idle: 'on, starting the next run',
  running: 'running',
  stopping: 'finishing the step, then off',
  waiting_user: 'waiting for you (Needs you)',
  release: 'a release waits for your approval',
  stable: 'stable: nothing left',
  waiting_session: 'waiting for another run',
  backoff: 'a run failed, trying again',
  stopped: 'stopped',
}

/** One line on the Autopilot: its state, where it runs, its round and since when. */
export function autopilotLine(live: LiveView | undefined, now: number): string {
  if (!live) return ''
  const ap = live.autopilot
  if (!ap.on && ap.state === 'off') return 'Autopilot off'
  const parts = [`Autopilot ${AP_WORDS[ap.state] ?? ap.state}`]
  if (ap.state === 'running' || ap.state === 'stopping') {
    if (ap.where === 'session') parts.push(ap.handoff === 'pending' ? 'handed to this session, not started yet' : 'in this session')
    else parts.push('headless')
    const rd = ap.round
    if (rd) parts.push(`${rd.skill}${rd.scope ? ` ${rd.scope}` : ''}${rd.tasks.length ? ` ${rd.tasks.join(' ')}` : ''}`)
    const t = since(ap.since, now)
    if (t) parts.push(t)
  } else if (ap.state === 'stopped' && ap.reason) parts.push(ap.reason.replace(/_/g, ' '))
  return parts.join(' · ')
}

/** The agent working on each task, to show beside it. */
export function agentsByNode(live: LiveView | undefined): Record<string, LiveAgent[]> {
  const out: Record<string, LiveAgent[]> = {}
  for (const a of live?.agents ?? []) if (a.node) (out[a.node] ??= []).push(a)
  return out
}

/** The "Needs you" lines, most urgent first. */
export function needsYou(snap: Snapshot): string[] {
  const out: string[] = []
  for (const a of snap.live?.approvals ?? [])
    out.push(`Permission: ${a.tool} ${a.target}`.trim() + (a.secondsLeft !== undefined ? ` (${Math.max(0, Math.ceil(a.secondsLeft / 60))}m left)` : ''))
  for (const r of snap.releasesWaiting) out.push(`Release ${r} waits for your approval`)
  const hotfix = snap.tasks.filter(t => t.lane === 'hotfix' && t.status !== 'done')
  if (hotfix.length) out.push(`Hotfix: ${hotfix.map(t => t.id).join(', ')}`)
  if (snap.openQuestions) out.push(`${snap.openQuestions} open question${snap.openQuestions > 1 ? 's' : ''}`)
  const blocked = snap.tasks.filter(t => t.status === 'blocked').length
  if (blocked) out.push(`${blocked} blocked task${blocked > 1 ? 's' : ''}`)
  const waiting = (snap.live?.requests ?? []).filter(r => r.status === 'pending')
  if (waiting.length) out.push(`${waiting.length} board request${waiting.length > 1 ? 's' : ''} waiting (${waiting.map(r => r.id).join(', ')})`)
  return out
}
