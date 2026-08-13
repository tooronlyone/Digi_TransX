// The route-scoped store owns the only cross-step password copy. A submission
// claim prevents duplicate sends and makes stale completions harmless.
export async function submitSignup(roleData, cacheUser, resolveRedirect, store, options = {}) {
  const claim = store.claimSubmission()
  if (!claim) return { ok: false, duplicate: true, message: 'Signup is already being submitted.' }

  const fetchImpl = options.fetchImpl || globalThis.fetch
  const scheduleRedirect = options.scheduleRedirect || ((callback) => setTimeout(callback, 1200))
  try {
    const csrfRes = await fetchImpl('/auth/csrf-token', {
      credentials: 'include',
      signal: claim.signal,
    })
    const csrfData = await csrfRes.json()
    const csrf = csrfData?.csrf_token || ''
    if (!store.isSubmissionActive(claim.token)) {
      return { ok: false, stale: true, message: 'This signup attempt is no longer active.' }
    }

    const res = await fetchImpl('/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      credentials: 'include',
      signal: claim.signal,
      body: JSON.stringify({ ...claim.basic, role: claim.role, ...roleData }),
    })
    const data = await res.json()
    if (res.ok && data.success) {
      if (!store.completeSubmission(claim.token)) {
        return { ok: false, stale: true, message: 'This signup attempt is no longer active.' }
      }
      cacheUser(data)
      scheduleRedirect(() => { window.location.href = resolveRedirect(data) })
      return { ok: true }
    }
    const message = data.message || 'Signup failed. Please try again.'
    store.failSubmission(claim.token, message)
    return { ok: false, message, field: data.field }
  } catch (error) {
    store.failSubmission(claim.token)
    throw error
  }
}
