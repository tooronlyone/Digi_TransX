export function adminUser() {
  try {
    return JSON.parse(sessionStorage.getItem('user') || 'null')
  } catch {
    return null
  }
}

export async function getCsrfToken() {
  const stored = sessionStorage.getItem('csrf_token')
  if (stored) return stored
  const response = await fetch('/auth/csrf-token', { credentials: 'same-origin' })
  const json = await response.json().catch(() => ({}))
  if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
  return json.csrf_token || ''
}

export async function adminRequest(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRF-Token'] = await getCsrfToken()
  const response = await fetch(url, { credentials: 'same-origin', ...options, headers })
  const json = await response.json().catch(() => ({}))
  if (!response.ok || json.success === false) throw new Error(json.message || `Request failed (${response.status})`)
  if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
  return json
}

export function qs(params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') search.set(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function money(value) {
  return `Rs ${Number(value || 0).toLocaleString()}`
}

export function dateText(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

