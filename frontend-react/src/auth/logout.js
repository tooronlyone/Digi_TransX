import { ApiResponseError } from './api'
import { clearCachedCsrfToken, getCsrfToken } from '../pages/client/clientUtils'
import { clearAuthPresentation } from './presentation'

export function clearLocalAuthenticationState() {
  clearCachedCsrfToken()
  clearAuthPresentation()
}

export function finishFullLogout(navigate) {
  clearLocalAuthenticationState()
  navigate('/login', { replace: true })
}

export async function requestLogoutAll(protectedFetch, password) {
  const csrf = await getCsrfToken()
  const body = password === undefined ? {} : { password }
  const response = await protectedFetch('/auth/logout-all', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload?.success === false) {
    throw new ApiResponseError(
      payload?.message || 'Unable to log out from all devices.',
      { status: response.status, code: payload?.code || '', payload },
    )
  }
  return payload
}

export async function logoutCurrentSession(navigate) {
  try {
    const csrf = await getCsrfToken()
    await fetch('/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrf },
    })
  } catch {
    // Local presentation cleanup is required even when persistence is unavailable.
  }
  finishFullLogout(navigate)
}
