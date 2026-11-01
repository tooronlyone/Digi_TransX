// The route-scoped store owns the only cross-step password copy. A submission
// claim prevents duplicate sends and makes stale completions harmless.
export async function submitSignup(roleData, cacheUser, resolveRedirect, store, options = {}) {
  const claim = store.claimSubmission()
  if (!claim) return { ok: false, duplicate: true, message: 'Signup is already being submitted.' }

  const fetchImpl = options.fetchImpl || globalThis.fetch
  const navigateTo = options.navigateTo || ((destination) => { window.location.href = destination })
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
      body: JSON.stringify({
        ...claim.basic, ...roleData, role: claim.role,
        signup_terms_accepted: true,
        signup_terms_version: claim.terms.version,
        signup_terms_role: claim.terms.role,
      }),
    })
    const data = await res.json()
    if (res.ok && data.success) {
      if (!store.completeSubmission(claim.token)) {
        return { ok: false, stale: true, message: 'This signup attempt is no longer active.' }
      }
      await cacheUser(data)
      const destination = resolveRedirect(data)
      navigateTo(destination)
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
