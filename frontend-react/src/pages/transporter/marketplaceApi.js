import { apiSend } from '../client/clientUtils'

const memoryAttempts = new Map()

function canonicalPayload(value) {
  if (Array.isArray(value)) return value.map(canonicalPayload)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonicalPayload(value[key])]))
  }
  return value
}

// Persist only a hash and a random attempt key, never delivery details/payment data.
export async function checkoutAttempt(payload, userId, storage = globalThis.sessionStorage) {
  if (!userId) throw new Error('Please sign in before checkout.')
  if (!globalThis.crypto?.subtle || !globalThis.crypto?.randomUUID) {
    throw new Error('Secure checkout requires an HTTPS connection.')
  }
  const bytes = new TextEncoder().encode(JSON.stringify(canonicalPayload(payload)))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const fingerprint = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('')
  const slot = `dtx:parts-checkout:v1:${encodeURIComponent(String(userId))}:${fingerprint}`
  let key = memoryAttempts.get(slot)
  try { key = storage?.getItem(slot) || key } catch { /* Keep the same in-memory attempt when storage is unavailable. */ }
  if (!key) key = crypto.randomUUID()
  memoryAttempts.set(slot, key)
  try { storage?.setItem(slot, key) } catch { /* The current page still retains the attempt. */ }
  return {
    key,
    complete() {
      memoryAttempts.delete(slot)
      try { storage?.removeItem(slot) } catch { /* A confirmed response remains safe to replay. */ }
    },
  }
}

export async function checkoutParts(payload, userId, { signal } = {}) {
  if (signal?.aborted) throw new DOMException('Checkout cancelled after account change.', 'AbortError')
  const attempt = await checkoutAttempt(payload, userId)
  if (signal?.aborted) throw new DOMException('Checkout cancelled after account change.', 'AbortError')
  const result = await apiSend('/api/marketplace/orders', payload, 'POST', (url, options) => {
    // apiSend may await a CSRF request. Recheck immediately before dispatch,
    // rather than sending a previous account's cart with a new login's cookies.
    if (signal?.aborted) throw new DOMException('Checkout cancelled after account change.', 'AbortError')
    return fetch(url, {
      ...options, ...(signal ? { signal } : {}),
      headers: { ...options.headers, 'Idempotency-Key': attempt.key, 'X-DTX-Expected-User-Id': String(userId) },
    })
  })
  attempt.complete()
  return result
}
