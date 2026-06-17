// Shared helper: reads sessionStorage, calls API, handles response
export async function submitSignup(roleData, cacheUser, resolveRedirect) {
  const basic = JSON.parse(sessionStorage.getItem('signup_basic') || '{}')
  const role  = sessionStorage.getItem('signup_role') || ''

  const csrfRes  = await fetch('/auth/csrf-token', { credentials: 'include' })
  const csrfData = await csrfRes.json()
  const csrf     = csrfData?.csrf_token || ''

  const res = await fetch('/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    credentials: 'include',
    body: JSON.stringify({ ...basic, role, ...roleData }),
  })
  const data = await res.json()
  if (res.ok && data.success) {
    cacheUser(data)
    setTimeout(() => { window.location.href = resolveRedirect(data) }, 1200)
    return { ok: true }
  }
  return { ok: false, message: data.message || 'Signup failed. Please try again.', field: data.field }
}
