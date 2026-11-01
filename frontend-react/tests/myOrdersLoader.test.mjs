import assert from 'node:assert/strict'
import test from 'node:test'

import { fetchMyOrders, shouldApplyOrdersResult } from '../src/pages/client/myOrdersLoader.js'

function response(body, ok = true) {
  return {
    ok,
    json: async () => body,
  }
}

test('loads orders for initial and refresh requests', async () => {
  const calls = []
  const fetchImpl = async (url, options) => {
    calls.push({ url, options })
    return response({ success: true, orders: [{ id: calls.length }] })
  }

  assert.deepEqual(await fetchMyOrders({ fetchImpl }), [{ id: 1 }])
  assert.deepEqual(await fetchMyOrders({ fetchImpl }), [{ id: 2 }])
  assert.equal(calls.length, 2)
  assert.equal(calls[0].url, '/api/orders/my-orders')
  assert.equal(calls[0].options.credentials, 'same-origin')
})

test('surfaces API errors', async () => {
  await assert.rejects(
    fetchMyOrders({ fetchImpl: async () => response({ message: 'No access' }, false) }),
    /No access/,
  )
})

test('rejects stale or aborted results', () => {
  assert.equal(shouldApplyOrdersResult(2, 2, { aborted: false }), true)
  assert.equal(shouldApplyOrdersResult(1, 2, { aborted: false }), false)
  assert.equal(shouldApplyOrdersResult(2, 2, { aborted: true }), false)
})
