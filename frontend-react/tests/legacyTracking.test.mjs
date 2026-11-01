import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  buildPageVisitPayload,
  sanitizeTrackingPath,
  sendPageVisit,
} from '../src/hooks/useTracker.js'


test('builds only the fixed safe page-visit payload and removes query/fragment', () => {
  assert.deepEqual(
    buildPageVisitPayload('/client/orders?token=secret#private'),
    {
      action_type: 'page_visit',
      action_name: 'page_view',
      page_url: '/client/orders',
      metadata: { navigation_source: 'router' },
    },
  )
})

test('rejects absolute, traversal, user-content, and oversized paths', () => {
  assert.equal(sanitizeTrackingPath('https://example.test/private'), null)
  assert.equal(sanitizeTrackingPath('/client/../private'), null)
  assert.equal(sanitizeTrackingPath('/profile/user@example.test'), null)
  assert.equal(sanitizeTrackingPath(`/${'x'.repeat(256)}`), null)
})

test('sends CSRF only as a header and never as analytics identity', async () => {
  const calls = []
  const ok = await sendPageVisit('/client/dashboard?secret=value', {
    csrfToken: 'csrf-header-only',
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return { ok: true }
    },
  })

  assert.equal(ok, true)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/track')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'csrf-header-only')
  const body = JSON.parse(calls[0].options.body)
  assert.equal(body.page_url, '/client/dashboard')
  assert.equal('session_id' in body, false)
  assert.equal('user_id' in body, false)
  assert.equal('user_email' in body, false)
  assert.equal(JSON.stringify(body).includes('csrf-header-only'), false)
})

test('does not send anonymous tracking without a CSRF-backed session', async () => {
  let called = false
  const result = await sendPageVisit('/login', {
    storage: { getItem: () => '' },
    fetchImpl: async () => {
      called = true
      return { ok: true }
    },
  })

  assert.equal(result, false)
  assert.equal(called, false)
})

test('ActivityTracker has no fetch, click, form, body, or text interception', async () => {
  const source = await readFile(
    new URL('../src/components/ActivityTracker.jsx', import.meta.url),
    'utf8',
  )
  for (const forbidden of [
    'window.fetch',
    'FormData',
    'addEventListener',
    'textContent',
    'input_data',
    'output_result',
    'element_text',
    'button_click',
    'form_submit',
    'api_call',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
  assert.equal(source.includes('sendPageVisit(location.pathname)'), true)
})
