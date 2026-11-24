// Type contract of the dev-kit status pane (hooks/status-pane.tsx).

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done'

export type TaskCard = {
  id: string
  title: string
  milestone: string
  type: string
  status: TaskStatus
  lane?: string
  startedAt?: string
  doneAt?: string
  commit?: string
  blockedReason?: string
}

export type MilestoneRow = {
  id: string
  title: string
  gate: string
  score?: number
  done: number
  total: number
}

export type IssueCard = { id: string; title: string; cls: string }

/** An agent at work, from the plugin's hooks: its type and the task or milestone it works on. */
export type LiveAgent = { agent: string; node?: string; startedAt?: string }

export type LiveRound = {
  skill: string
  scope?: string
  since?: string
  tasks: string[]
  unregistered: boolean
  lastTool?: string
  lastAgent?: string
  lastAt?: string
}

/** What runs now, built from `dev_board.py pane --json`. */
export type LiveView = {
  board: boolean
  autopilot: {
    on: boolean
    state: string
    /** "session" when the board handed the run to the session that listens */
    where?: string
    handoff?: string
    since?: string
    reason?: string
    until?: number
    round?: LiveRound
  }
  agents: LiveAgent[]
  runs: { skill: string; scope?: string; startedAt?: string }[]
  requests: { id: string; action: string; status: string; question?: string }[]
  approvals: { tool: string; target: string; secondsLeft?: number }[]
  executor: string
  readAt: number
}

/** What the pane draws, built from `dev_state.py status --json`. */
export type Snapshot = {
  /** false when the session is not inside a dev-kit project */
  isProject: boolean
  /** a short line when the state could not be read */
  error?: string
  project: string
  phase: string
  step: string
  current?: string
  milestones: MilestoneRow[]
  tasks: TaskCard[]
  next?: { task: string; reason: string }
  nextCommand: string
  openQuestions: number
  releasesWaiting: string[]
  issueCounts: Record<string, number>
  issues: IssueCard[]
  readAt: number
  /** what runs now (the Autopilot, agents, board requests); absent until first read */
  live?: LiveView
}

/** How the person set the pane: which milestones and whether done tasks show. */
export type PaneView = { scope: 'current' | 'all'; showDone: boolean; showAgents?: boolean }

declare module 'claude-code' {
  interface PluginState {
    'dev-kit': {
      snapshot: Shaped<Snapshot>
      view: Shaped<PaneView>
    }
  }
}
