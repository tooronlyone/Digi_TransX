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

export function bootstrapUser(globalObject = globalThis) {
  const bootstrap = globalObject?.window?.__BOOTSTRAP__ || globalObject?.__BOOTSTRAP__ || null
  return bootstrap?.auth?.user || bootstrap?.user || null
}

export function bootstrapAuth(globalObject = globalThis) {
  const auth = globalObject?.window?.__BOOTSTRAP__?.auth || globalObject?.__BOOTSTRAP__?.auth || null
  if (!auth || typeof auth !== 'object') return null
  return auth
}

export function cacheBootstrapUser(storage = globalThis.sessionStorage, globalObject = globalThis) {
  const user = bootstrapUser(globalObject)
  if (!user || !storage) return null
  storage.setItem('user', JSON.stringify(user))
  storage.setItem('user_id', String(user.id))
  storage.setItem('user_role', user.role || '')
  return user
}

export function clearAuthPresentation(storage = globalThis.sessionStorage) {
  if (!storage) return
  for (const key of AUTH_PRESENTATION_KEYS) storage.removeItem(key)
  if (typeof globalThis.window !== 'undefined') {
    delete globalThis.window.AuthSession
    delete globalThis.window.__BOOTSTRAP__
  }
}

export function currentPresentedUser(storage = globalThis.sessionStorage) {
  const bootstrapped = cacheBootstrapUser(storage)
  if (bootstrapped) return bootstrapped
  try {
    return JSON.parse(storage?.getItem('user') || 'null')
  } catch {
    return null
  }
}
