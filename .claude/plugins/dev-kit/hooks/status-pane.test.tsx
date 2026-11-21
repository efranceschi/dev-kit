import { expect, test } from 'claude-code/testing'

import { needsYou, toSnapshot } from './status-pane-model'

// What `dev_state.py status --json` prints, cut to the fields the pane reads.
const STATUS = {
  project: 'Demo',
  phase: 'construction',
  step: 'implement',
  milestones: {
    M1: { title: 'Accounts', gate: 'pending' },
    M2: { title: 'Billing', gate: 'pending' },
    M10: { title: 'Later', gate: 'pending' },
  },
  tasks: {
    'T-001': { title: 'Login form', milestone: 'M1', type: 'feature', status: 'done', commit: 'abc1234def', done_at: '2026-11-21T10:00:00+00:00' },
    'T-002': { title: 'Session API', milestone: 'M1', type: 'feature', status: 'in_progress', started_at: '2026-11-21T11:00:00+00:00' },
    'T-003': { title: 'Profile page', milestone: 'M1', type: 'feature', status: 'blocked', blocked_reason: 'Waiting for API key' },
    'T-004': { title: 'Logout', milestone: 'M1', type: 'feature', status: 'todo' },
    'T-005': { title: 'Old idea', milestone: 'M1', type: 'feature', status: 'dropped' },
    'T-006': { title: 'Invoices', milestone: 'M2', type: 'feature', status: 'todo' },
  },
  issues: {
    'I-001': { title: 'Crash on login', class: 'current', status: 'scheduled', scheduled_in: 'M1' },
    'I-002': { title: 'Dark mode', class: 'standard', status: 'open' },
    'I-003': { title: 'Fixed', class: 'standard', status: 'done' },
  },
  next: { task: 'T-004', reason: 'deps done' },
  next_command: '/dev-kit:implement',
  open_questions: 2,
  lifecycle: { releases: [{ id: 'R1', status: 'awaiting_approval' }] },
}

const PANE = {
  plugin: 'dev-kit',
  component: 'Pane',
  requestId: 'dev-kit-status',
  props: {
    title: 'dev-kit',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const NOW = Date.parse('2026-11-21T11:30:00+00:00')

test('the snapshot keeps live tasks in plan order and picks the current milestone', () => {
  const snap = toSnapshot(STATUS, NOW)
  expect(snap.tasks.map(t => t.id)).toEqual(['T-001', 'T-002', 'T-003', 'T-004', 'T-006'])
  expect(snap.milestones.map(m => m.id)).toEqual(['M1', 'M2', 'M10'])
  expect(snap.current).toBe('M1')
  expect(snap.milestones[0]).toEqual({ id: 'M1', title: 'Accounts', gate: 'pending', done: 1, total: 4 })
  expect(snap.tasks[0]?.commit).toBe('abc1234')
  expect(snap.issueCounts).toEqual({ current: 1, standard: 1 })
  expect(snap.issues.map(i => i.id)).toEqual(['I-001'])
  expect(needsYou(snap)).toEqual(['Release R1 waits for your approval', '2 open questions', '1 blocked task'])
})

test('the snapshot survives a state it does not know', () => {
  const snap = toSnapshot({ tasks: { 'T-001': null }, milestones: 'x' }, NOW)
  expect(snap.isProject).toBe(true)
  expect(snap.tasks).toEqual([])
  expect(snap.current).toBe(undefined)
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the pane shows the task board on ${surface}`, async ($, on) => {
    on('command.register', () => ({ value: { command: 'dev-kit-pane' } }))
    on('ui.open', () => ({ value: { isPlaced: true } }))
    on('ui.panes', () => ({ value: [{ id: 'dev-kit-status', title: 'dev-kit', isShown: true, isFocused: false, isPlaced: true }] }))
    on('session.start', (_, e) => ({ cwd: e.cwd }))
    on('session.cwd', () => ({ value: '/work/demo' }))
    on('clock.now', () => ({ value: NOW }))
    on('fs.stat', (_, e) => {
      if (!String(e.path).startsWith('/work/demo/.dev/')) throw new Error('ENOENT')
      return { value: { kind: 'file', size: 10, mtimeMs: 1, isLink: false } }
    })
    on('process.run', () => ({
      value: { exitCode: 0, stdout: JSON.stringify(STATUS), stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    }))

    await $.session.start({ cwd: '/work/demo', surface, isInteractive: true })
    const ui = await $.ui.mount({ ...PANE, surface })

    expect((await ui.find({ type: 'Text', text: /Demo/ }))?.text).toContain('construction › implement')
    expect((await ui.find({ type: 'Text', text: /M1 Accounts/ }))?.text).toContain('1/4')
    expect((await ui.find({ type: 'Text', text: /Release R1/ }))?.text).toContain('approval')
    expect((await ui.find({ type: 'Text', text: /T-002/ }))?.text).toContain('30m')
    expect((await ui.find({ type: 'Text', text: /T-003/ }))?.text).toContain('Waiting for API key')
    expect((await ui.find({ type: 'Text', text: /T-004/ }))?.text).toContain('next')
    expect((await ui.find({ type: 'Text', text: /T-001/ }))?.text).toContain('abc1234')
    expect(await ui.find({ type: 'Text', text: /T-006/ })).toBe(undefined)
    expect(await ui.find({ type: 'Text', text: /T-005/ })).toBe(undefined)

    await ui.press({ key: 'scope' })
    expect((await ui.find({ type: 'Text', text: /T-006/ }))?.text).toContain('M2')
    await ui.press({ key: 'done' })
    expect(await ui.find({ type: 'Text', text: /T-001/ })).toBe(undefined)
    await ui.unmount()
  })
}

test('outside a dev-kit project the pane says so and is not opened', async ($, on) => {
  let opened = 0
  on('command.register', () => ({ value: { command: 'dev-kit-pane' } }))
  on('ui.open', () => {
    opened++
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/elsewhere' }))
  on('clock.every', () => ({ value: undefined }))
  on('fs.stat', () => {
    throw new Error('ENOENT')
  })

  await $.session.start({ cwd: '/elsewhere', surface: 'terminal', isInteractive: true })
  expect(opened).toBe(0)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('No dev-kit project in this folder.')
  await ui.unmount()
})
