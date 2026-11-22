import { requestAdminStepUp } from '../../components/admin/adminStepUpBridge'

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
  const baseHeaders = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData)) baseHeaders['Content-Type'] = 'application/json'
  if (method !== 'GET') baseHeaders['X-CSRF-Token'] = await getCsrfToken()

  let response = await fetch(url, { credentials: 'same-origin', ...options, headers: baseHeaders })
  if (response.status === 428) {
    const challenge = await response.clone().json().catch(() => ({}))
    if (challenge?.code === 'admin_step_up_required' && challenge.action) {
      const stepUpProof = await requestAdminStepUp(challenge.action)
      const retryHeaders = {
        ...baseHeaders,
        'X-Admin-Step-Up-Proof': stepUpProof,
      }
      if (method !== 'GET') retryHeaders['X-CSRF-Token'] = await getCsrfToken()
      response = await fetch(url, { credentials: 'same-origin', ...options, headers: retryHeaders })
    }
  }

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

