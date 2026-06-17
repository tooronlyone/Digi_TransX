export async function getCsrf() {
  const cached = sessionStorage.getItem('csrf_token')
  if (cached) return cached
  try {
    const res = await fetch('/auth/csrf-token', { credentials: 'include' })
    const data = await res.json()
    const token = data?.csrf_token || ''
    if (token) sessionStorage.setItem('csrf_token', token)
    return token
  } catch (_) { return '' }
}

export function getUser() {
  try { return JSON.parse(sessionStorage.getItem('user') || '{}') } catch (_) { return {} }
}

export function fmtCurrency(n) {
  return Number(n || 0).toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-PK', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch (_) { return iso }
}

export function fmtDateTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-PK', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch (_) { return iso }
}
