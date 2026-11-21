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
}

/** How the person set the pane: which milestones and whether done tasks show. */
export type PaneView = { scope: 'current' | 'all'; showDone: boolean }

declare module 'claude-code' {
  interface PluginState {
    'dev-kit': {
      snapshot: Shaped<Snapshot>
      view: Shaped<PaneView>
    }
  }
}
