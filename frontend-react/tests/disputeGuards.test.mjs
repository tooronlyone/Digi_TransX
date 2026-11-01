import assert from 'node:assert/strict'
import test from 'node:test'

import {
  detailMatchesSelection,
  detailRequestError,
  disputeDetailFromResponse,
  normalizeDisputeId,
  shouldAcceptDetail,
} from '../src/pages/admin/disputeGuards.js'

test('extracts the real dispute detail response shape', () => {
  const detail = disputeDetailFromResponse({ success: true, dispute: { id: 6 } })
  assert.deepEqual(detail, { id: 6 })
  assert.equal(disputeDetailFromResponse({ success: true }), null)
})

test('normalizes safe numeric and numeric-string dispute ids', () => {
  assert.equal(normalizeDisputeId(6), '6')
  assert.equal(normalizeDisputeId(' 6 '), '6')
  assert.equal(normalizeDisputeId(0), null)
  assert.equal(normalizeDisputeId('6x'), null)
})

test('accepts only the latest response for the selected dispute', () => {
  assert.equal(shouldAcceptDetail(6, '6', 3, 3), true)
  assert.equal(shouldAcceptDetail(6, 7, 3, 3), false)
  assert.equal(shouldAcceptDetail(6, 6, 2, 3), false)
})

test('enables resolution only for matching evidence', () => {
  assert.equal(detailMatchesSelection({ id: '6' }, { id: 6 }), true)
  assert.equal(detailMatchesSelection({ id: 6 }, { id: 7 }), false)
  assert.equal(detailMatchesSelection(null, { id: 6 }), false)
})

test('ignores aborted, stale, and unmounted request failures', () => {
  assert.equal(detailRequestError({ name: 'AbortError' }, true, 3, 3), null)
  assert.equal(detailRequestError(new Error('late'), true, 2, 3), null)
  assert.equal(detailRequestError(new Error('unmounted'), false, 3, 3), null)
})

test('returns a visible error for the current mounted request', () => {
  assert.equal(detailRequestError(new Error('Request failed (500)'), true, 3, 3), 'Request failed (500)')
  assert.equal(detailRequestError({}, true, 3, 3), 'Unable to load dispute details.')
})
