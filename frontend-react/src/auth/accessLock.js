export const ACCESS_STATES = Object.freeze({
  CHECKING: 'checking',
  UNLOCKED: 'unlocked',
  LOCKED_MPIN_AVAILABLE: 'locked_mpin_available',
  LOCKED_PASSWORD_REQUIRED: 'locked_password_required',
  MPIN_PERMANENTLY_LOCKED: 'mpin_permanently_locked',
  FULL_LOGIN_REQUIRED: 'full_login_required',
  TEMPORARILY_UNAVAILABLE: 'temporarily_unavailable',
})

export const ELIGIBLE_MPIN_ROLES = Object.freeze([
  'logistics_provider',
  'service_seeker',
  'everyday_user',
])

const ELIGIBLE_ROLE_SET = new Set(ELIGIBLE_MPIN_ROLES)
const INTERCEPTOR_MARK = Symbol.for('digitransx.access-lock-fetch')

const AUTH_401_DOMAIN_ENDPOINTS = new Set([
  '/auth/login',
  '/auth/signup',
  '/auth/forgot-password',
  '/auth/password-reset/verify-otp',
  '/auth/reset-password',
  '/auth/mpin/enroll',
  '/auth/mpin/unlock',
  '/auth/mpin/password-unlock',
  '/auth/access/unlock/password',
  '/auth/mpin/change',
  '/auth/mpin/disable',
  '/auth/mpin/reset',
  '/api/profile/password/request-otp',
  '/api/profile/password',
])

const NEVER_REPLAY_PREFIXES = [
  '/auth/',
  '/api/payments',
  '/api/wallet',
  '/api/agreements/process-payments',
  '/api/agreements/apply-penalties',
  '/uploads/',
]

export function normalizeRole(role) {
  return String(role || '').trim().toLowerCase()
}

export function isMpinEligibleRole(role) {
  return ELIGIBLE_ROLE_SET.has(normalizeRole(role))
}

export function sanitizeMpinInput(value) {
  const candidate = String(value ?? '')
  return /^[0-9]{0,4}$/.test(candidate) ? candidate : ''
}

export function nextMpinInput(current, candidate) {
  const next = String(candidate ?? '')
  return /^[0-9]{0,4}$/.test(next) ? next : String(current ?? '')
}

export function isValidMpin(value) {
  return typeof value === 'string' && /^[0-9]{4}$/.test(value)
}

export function safeRelativePath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) {
    return '/'
  }
  const pathname = value.split(/[?#]/, 1)[0]
  if (!pathname || pathname.includes('..') || pathname.includes('\\') || [...pathname].some((character) => character.codePointAt(0) < 32)) {
    return '/'
  }
  return pathname
}

export function isPublicAuthPath(pathname) {
  return pathname === '/'
    || pathname === '/login'
    || pathname === '/admin/login'
    || pathname === '/reset-password'
    || pathname === '/signup'
    || pathname.startsWith('/signup/')
}

export function deriveAccessState({ authenticated, accessLocked, mpinStatus, statusUnavailable = false }) {
  if (!authenticated) return ACCESS_STATES.FULL_LOGIN_REQUIRED
  if (!accessLocked) return ACCESS_STATES.UNLOCKED
  if (statusUnavailable) return ACCESS_STATES.TEMPORARILY_UNAVAILABLE
  if (mpinStatus?.enrolled && mpinStatus?.locked) {
    return ACCESS_STATES.MPIN_PERMANENTLY_LOCKED
  }
  if (
    mpinStatus?.role_eligible === true
    && mpinStatus?.enrolled === true
    && mpinStatus?.locked === false
  ) {
    return ACCESS_STATES.LOCKED_MPIN_AVAILABLE
  }
  return ACCESS_STATES.LOCKED_PASSWORD_REQUIRED
}

export function isStructuredAccessLock(status, payload) {
  return status === 423 && payload?.code === 'access_locked'
}

export function isFullLogin401(pathname, status) {
  return status === 401 && !AUTH_401_DOMAIN_ENDPOINTS.has(pathname)
}

function requestDescriptor(input, init = {}, locationRef = globalThis.location) {
  const rawUrl = typeof input === 'string' || input instanceof URL ? String(input) : input?.url
  const base = locationRef?.origin || 'http://localhost'
  let url
  try {
    url = new URL(rawUrl, base)
  } catch {
    return null
  }
  const method = String(init.method || input?.method || 'GET').toUpperCase()
  return {
    method,
    url,
    pathname: url.pathname,
    sameOrigin: !locationRef?.origin || url.origin === locationRef.origin,
    hasBody: init.body != null || (typeof input !== 'string' && input?.body != null),
  }
}

export function isSafeReplayableRead(input, init = {}, locationRef = globalThis.location) {
  const descriptor = requestDescriptor(input, init, locationRef)
  if (!descriptor || descriptor.method !== 'GET' || descriptor.hasBody || !descriptor.sameOrigin) {
    return false
  }
  if (descriptor.url.search || descriptor.url.hash) return false
  return !NEVER_REPLAY_PREFIXES.some((prefix) => descriptor.pathname.startsWith(prefix))
}

export function createLatestRequestGate() {
  let revision = 0
  return {
    begin() {
      revision += 1
      return revision
    },
    isCurrent(candidate) {
      return candidate === revision
    },
    invalidate() {
      revision += 1
    },
  }
}

export function createAccessLockCoordinator() {
  const listeners = new Set()
  let lockLatched = false
  let pendingReplay = null

  function emit(event) {
    for (const listener of listeners) listener(event)
  }

  return {
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    notifyAccessLocked(detail = {}) {
      if (lockLatched) return false
      lockLatched = true
      emit({ type: 'access_locked', ...detail })
      return true
    },
    notifyFullLoginRequired(detail = {}) {
      lockLatched = false
      this.cancelReplay()
      emit({ type: 'full_login_required', ...detail })
    },
    waitForOneReplay(replay, fallbackResponse, signal) {
      if (pendingReplay) return null
      return new Promise((resolve) => {
        let abortHandler
        const finish = (value) => {
          if (abortHandler && signal) signal.removeEventListener('abort', abortHandler)
          resolve(value)
        }
        pendingReplay = { replay, fallbackResponse, finish }
        if (signal) {
          abortHandler = () => {
            if (pendingReplay?.finish === finish) pendingReplay = null
            finish(fallbackResponse)
          }
          if (signal.aborted) abortHandler()
          else signal.addEventListener('abort', abortHandler, { once: true })
        }
      })
    },
    async markUnlocked() {
      lockLatched = false
      const pending = pendingReplay
      pendingReplay = null
      if (!pending) return false
      try {
        pending.finish(await pending.replay())
      } catch {
        pending.finish(pending.fallbackResponse)
      }
      return true
    },
    cancelReplay() {
      const pending = pendingReplay
      pendingReplay = null
      if (pending) pending.finish(pending.fallbackResponse)
    },
    hasPendingReplay() {
      return pendingReplay !== null
    },
    resetForTests() {
      lockLatched = false
      this.cancelReplay()
      listeners.clear()
    },
  }
}

export const accessLockCoordinator = createAccessLockCoordinator()

async function safeJson(response) {
  try {
    return await response.clone().json()
  } catch {
    return null
  }
}

export function installAccessFetchInterceptor({
  globalRef = globalThis,
  coordinator = accessLockCoordinator,
} = {}) {
  if (typeof globalRef.fetch !== 'function') return () => {}
  if (globalRef.fetch[INTERCEPTOR_MARK]) return globalRef.fetch[INTERCEPTOR_MARK]

  const originalFetch = globalRef.fetch.bind(globalRef)
  const locationRef = globalRef.location

  async function accessAwareFetch(input, init = {}) {
    const descriptor = requestDescriptor(input, init, locationRef)
    const response = await originalFetch(input, init)

    if (response.status === 423) {
      const payload = await safeJson(response)
      if (isStructuredAccessLock(response.status, payload)) {
        coordinator.notifyAccessLocked({
          returnPath: safeRelativePath(locationRef?.pathname || '/'),
        })
        if (isSafeReplayableRead(input, init, locationRef)) {
          const waiting = coordinator.waitForOneReplay(
            () => originalFetch(input, init),
            response,
            init.signal || input?.signal,
          )
          if (waiting) return waiting
        }
      }
    } else if (descriptor && isFullLogin401(descriptor.pathname, response.status)) {
      coordinator.notifyFullLoginRequired({
        returnPath: safeRelativePath(locationRef?.pathname || '/'),
      })
    }
    return response
  }

  function uninstall() {
    if (globalRef.fetch === accessAwareFetch) globalRef.fetch = originalFetch
  }
  Object.defineProperty(accessAwareFetch, INTERCEPTOR_MARK, { value: uninstall })
  globalRef.fetch = accessAwareFetch
  return uninstall
}
