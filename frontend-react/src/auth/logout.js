import { ApiResponseError } from './api'
import { clearCachedCsrfToken, getCsrfToken } from '../pages/client/clientUtils'
import { clearAuthPresentation } from './presentation'
import { accessLockCoordinator } from './accessLock'

export function clearLocalAuthenticationState() {
  clearCachedCsrfToken()
  clearAuthPresentation()
}

export function finishFullLogout(navigate, authNotice = null) {
  clearLocalAuthenticationState()
  const notice = typeof authNotice?.message === 'string'
    ? { type: authNotice.type === 'success' ? 'success' : 'error', message: authNotice.message }
    : null
  accessLockCoordinator.notifyFullLoginRequired({ returnPath: '/login', ...(notice ? { authNotice: notice } : {}) })
  if (notice) navigate('/login', { replace: true, state: { authNotice: notice } })
  else navigate('/login', { replace: true })
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
  const csrf = await getCsrfToken()
  const response = await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': csrf },
  })
  const payload = await response.json().catch(() => ({}))
  // An already expired session is also a completed logout. A failed revocation
  // must leave the current UI intact so the user can retry rather than auto-login.
  if (response.status !== 401 && (!response.ok || payload?.success !== true)) {
    throw new ApiResponseError(payload?.message || 'Logout could not be confirmed. Please retry.', {
      status: response.status, code: payload?.code || '', payload,
    })
  }
  finishFullLogout(navigate)
}
