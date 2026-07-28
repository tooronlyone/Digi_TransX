export async function fetchMyOrders({ signal, fetchImpl = fetch } = {}) {
  const response = await fetchImpl('/api/orders/my-orders', {
    credentials: 'same-origin',
    signal,
  })
  const json = await response.json().catch(() => ({}))
  if (!response.ok || json.success === false) {
    throw new Error(json.message || 'Unable to load orders.')
  }
  return Array.isArray(json.orders) ? json.orders : []
}

export function shouldApplyOrdersResult(requestId, latestRequestId, signal) {
  return requestId === latestRequestId && !signal?.aborted
}
