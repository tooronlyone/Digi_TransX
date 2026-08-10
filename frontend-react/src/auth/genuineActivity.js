export const GENUINE_ACTIVITY_ENDPOINT = '/auth/session/activity'
export const CLIENT_ACTIVITY_THROTTLE_MS = 15 * 60 * 1000
export const GENUINE_ACTIVITY_EVENT_TYPES = Object.freeze([
  'pointerdown',
  'touchstart',
  'keydown',
])

export async function sendGenuineActivity({
  storage = globalThis.sessionStorage,
  fetchImpl = globalThis.fetch,
} = {}) {
  const csrfToken = storage?.getItem?.('csrf_token') || ''
  if (!csrfToken || typeof fetchImpl !== 'function') return false

  try {
    const response = await fetchImpl(GENUINE_ACTIVITY_ENDPOINT, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken },
    })
    return response.status === 204
  } catch {
    return false
  }
}

export function createGenuineActivityHandler({
  documentRef,
  send = sendGenuineActivity,
  now = Date.now,
  throttleMs = CLIENT_ACTIVITY_THROTTLE_MS,
} = {}) {
  let inFlight = false
  let lastAttemptAt = Number.NEGATIVE_INFINITY

  return function handleGenuineActivity(event) {
    const observedAt = now()
    if (
      !event?.isTrusted ||
      documentRef?.visibilityState !== 'visible' ||
      inFlight ||
      observedAt - lastAttemptAt < throttleMs
    ) {
      return false
    }

    inFlight = true
    lastAttemptAt = observedAt
    void Promise.resolve(send())
      .catch(() => false)
      .finally(() => {
        inFlight = false
      })
    return true
  }
}

export function installGenuineActivityListeners(documentRef, handler) {
  if (!documentRef?.addEventListener || typeof handler !== 'function') {
    return () => {}
  }
  const options = { capture: true, passive: true }
  for (const eventType of GENUINE_ACTIVITY_EVENT_TYPES) {
    documentRef.addEventListener(eventType, handler, options)
  }
  return () => {
    for (const eventType of GENUINE_ACTIVITY_EVENT_TYPES) {
      documentRef.removeEventListener(eventType, handler, options)
    }
  }
}
