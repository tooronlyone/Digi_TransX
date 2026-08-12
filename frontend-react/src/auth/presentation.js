export const AUTH_PRESENTATION_KEYS = Object.freeze([
  'user',
  'user_id',
  'user_role',
  'admin_id',
  'admin_level',
  'csrf_token',
  'session_last_active_at',
  'session_expires_at',
  'session_inactivity_window_days',
  'auth_mode',
])

export function cacheAuthPresentation(data, storage = globalThis.sessionStorage) {
  if (!data?.user || !storage) return
  storage.setItem('user', JSON.stringify(data.user))
  storage.setItem('user_id', String(data.user.id))
  storage.setItem('user_role', data.user.role || '')
  if (data.csrf_token) storage.setItem('csrf_token', data.csrf_token)
  if (data.session?.last_active_at) {
    storage.setItem('session_last_active_at', String(data.session.last_active_at))
  }
}

export function clearAuthPresentation(storage = globalThis.sessionStorage) {
  if (!storage) return
  for (const key of AUTH_PRESENTATION_KEYS) storage.removeItem(key)
  if (typeof globalThis.window !== 'undefined') delete globalThis.window.AuthSession
}

export function currentPresentedUser(storage = globalThis.sessionStorage) {
  try {
    return JSON.parse(storage?.getItem('user') || 'null')
  } catch {
    return null
  }
}
