import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  GENUINE_ACTIVITY_ENDPOINT,
  GENUINE_ACTIVITY_EVENT_TYPES,
  createGenuineActivityHandler,
  installGenuineActivityListeners,
  sendGenuineActivity,
} from '../src/auth/genuineActivity.js'

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function fakeDocument(visibilityState = 'visible') {
  const listeners = new Map()
  return {
    visibilityState,
    listeners,
    addEventListener(type, handler) {
      const handlers = listeners.get(type) || new Set()
      handlers.add(handler)
      listeners.set(type, handlers)
    },
    removeEventListener(type, handler) {
      listeners.get(type)?.delete(handler)
    },
  }
}

test('sends only the empty same-origin CSRF-backed activity signal', async () => {
  const calls = []
  const result = await sendGenuineActivity({
    storage: { getItem: (key) => key === 'csrf_token' ? 'csrf-header-only' : '' },
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return { status: 204 }
    },
  })

  assert.equal(result, true)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, GENUINE_ACTIVITY_ENDPOINT)
  assert.deepEqual(calls[0].options, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': 'csrf-header-only' },
  })
  assert.equal('body' in calls[0].options, false)
})

test('does not send without an existing CSRF-backed browser session', async () => {
  let called = false
  assert.equal(await sendGenuineActivity({
    storage: { getItem: () => '' },
    fetchImpl: async () => {
      called = true
      return { status: 204 }
    },
  }), false)
  assert.equal(called, false)
})

test('rejects synthetic and background events and accepts trusted interaction types', async () => {
  let sent = 0
  let observedAt = 1_000_000
  const documentRef = fakeDocument()
  const handler = createGenuineActivityHandler({
    documentRef,
    send: async () => { sent += 1 },
    now: () => observedAt,
    throttleMs: 100,
  })
  const cleanup = installGenuineActivityListeners(documentRef, handler)

  for (const type of GENUINE_ACTIVITY_EVENT_TYPES) {
    for (const listener of documentRef.listeners.get(type)) listener({ isTrusted: false })
  }
  await flush()
  assert.equal(sent, 0)

  documentRef.visibilityState = 'hidden'
  for (const listener of documentRef.listeners.get('pointerdown')) listener({ isTrusted: true })
  await flush()
  assert.equal(sent, 0)

  documentRef.visibilityState = 'visible'
  for (const type of GENUINE_ACTIVITY_EVENT_TYPES) {
    observedAt += 100
    for (const listener of documentRef.listeners.get(type)) listener({ isTrusted: true })
    await flush()
  }
  assert.equal(sent, 3)
  cleanup()
})

test('deduplicates in-flight signals and throttles repeated interaction', async () => {
  const documentRef = fakeDocument()
  let resolveSend
  let sent = 0
  let observedAt = 5_000
  const handler = createGenuineActivityHandler({
    documentRef,
    send: () => {
      sent += 1
      return new Promise((resolve) => { resolveSend = resolve })
    },
    now: () => observedAt,
    throttleMs: 1_000,
  })

  assert.equal(handler({ isTrusted: true }), true)
  assert.equal(handler({ isTrusted: true }), false)
  assert.equal(sent, 1)
  resolveSend(true)
  await flush()
  observedAt += 999
  assert.equal(handler({ isTrusted: true }), false)
  observedAt += 1
  assert.equal(handler({ isTrusted: true }), true)
  assert.equal(sent, 2)
})

test('a failed request remains throttled and cannot create a retry storm', async () => {
  const documentRef = fakeDocument()
  let observedAt = 10_000
  let sent = 0
  const handler = createGenuineActivityHandler({
    documentRef,
    send: async () => {
      sent += 1
      throw new Error('sentinel provider failure')
    },
    now: () => observedAt,
    throttleMs: 1_000,
  })

  assert.equal(handler({ isTrusted: true }), true)
  await flush()
  assert.equal(handler({ isTrusted: true }), false)
  assert.equal(sent, 1)
  observedAt += 1_000
  assert.equal(handler({ isTrusted: true }), true)
  await flush()
  assert.equal(sent, 2)
})

test('StrictMode-style cleanup and remount leaves exactly one listener per type', () => {
  const documentRef = fakeDocument()
  const first = createGenuineActivityHandler({ documentRef, send: async () => true })
  const cleanupFirst = installGenuineActivityListeners(documentRef, first)
  cleanupFirst()
  const second = createGenuineActivityHandler({ documentRef, send: async () => true })
  const cleanupSecond = installGenuineActivityListeners(documentRef, second)

  for (const type of GENUINE_ACTIVITY_EVENT_TYPES) {
    assert.equal(documentRef.listeners.get(type).size, 1)
  }
  cleanupSecond()
  for (const type of GENUINE_ACTIVITY_EVENT_TYPES) {
    assert.equal(documentRef.listeners.get(type).size, 0)
  }
})

test('installs no passive activity sources or broad browser interception', () => {
  assert.deepEqual(GENUINE_ACTIVITY_EVENT_TYPES, [
    'pointerdown',
    'touchstart',
    'keydown',
  ])
  const documentRef = fakeDocument()
  const cleanup = installGenuineActivityListeners(documentRef, () => true)
  for (const passive of [
    'scroll',
    'mousemove',
    'focus',
    'visibilitychange',
  ]) {
    assert.equal(documentRef.listeners.has(passive), false)
  }
  cleanup()
})

test('analytics, notification polling, and chat polling do not own activity refresh', async () => {
  const passiveOwners = [
    '../src/components/ActivityTracker.jsx',
    '../src/hooks/useTracker.js',
    '../src/components/common/NotificationBell.jsx',
    '../src/components/chat/ChatWindow.jsx',
  ]
  for (const relative of passiveOwners) {
    const source = await readFile(new URL(relative, import.meta.url), 'utf8')
    assert.equal(source.includes(GENUINE_ACTIVITY_ENDPOINT), false, relative)
    assert.equal(source.includes('sendGenuineActivity'), false, relative)
  }
})
