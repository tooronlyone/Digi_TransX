import { getCsrfToken } from '../pages/client/clientUtils'
import { clearAuthPresentation } from './presentation'

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
  clearAuthPresentation()
  navigate('/login', { replace: true })
}
