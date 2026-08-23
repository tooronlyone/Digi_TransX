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

// Sole positive owner for automatic replay. The exact current-Terms read is
// used by the global Terms notice and is safe because its backend handler and
// helpers perform SELECT-only local database reads: no commit, activity or
// expiry refresh, provider/storage I/O, file/stream response, signed URL,
// token generation, acknowledgement, reservation, claim, or transition.
// Every other route fails closed and must be refreshed by its component owner.
const SAFE_AUTOMATIC_REPLAY_PATHS = new Set([
  '/api/platform/terms/current',
])

const SAFE_REPLAY_INIT_KEYS = new Set(['method', 'credentials'])

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
  return {
    method: String(init.method || input?.method || 'GET').toUpperCase(),
    url,
    pathname: url.pathname,
    sameOrigin: !locationRef?.origin || url.origin === locationRef.origin,
  }
}

export function createSafeReplayDescriptor(input, init = {}, locationRef = globalThis.location) {
  // Request and URL objects are intentionally not retained or normalized for
  // replay. A plain canonical string is the only accepted URL owner.
  if (typeof input !== 'string' || !input) return null
  if (!init || typeof init !== 'object') return null
  if (typeof locationRef?.origin !== 'string' || !locationRef.origin) return null
  const initPrototype = Object.getPrototypeOf(init)
  if (initPrototype !== Object.prototype && initPrototype !== null) return null
  if (Reflect.ownKeys(init).some((key) => typeof key !== 'string' || !SAFE_REPLAY_INIT_KEYS.has(key))) return null

  const rawUrl = input
  if (
    rawUrl.startsWith('//')
    || rawUrl.includes('?')
    || rawUrl.includes('#')
    || rawUrl.includes('%')
    || rawUrl.includes('\\')
    || [...rawUrl].some((character) => {
      const codePoint = character.codePointAt(0)
      return codePoint < 32 || codePoint === 127
    })
  ) return null

  const descriptor = requestDescriptor(input, init, locationRef)
  if (!descriptor) return null
  const { url } = descriptor
  const canonical = rawUrl.startsWith('/')
    ? rawUrl === url.pathname
    : rawUrl === `${url.origin}${url.pathname}`
  const pathSegments = url.pathname.split('/')
  if (
    (init.method !== undefined && init.method !== 'GET')
    || !descriptor.sameOrigin
    || !canonical
    || url.username
    || url.password
    || url.pathname.includes('//')
    || pathSegments.includes('.')
    || pathSegments.includes('..')
    || (init.credentials !== undefined && !['same-origin', 'include'].includes(init.credentials))
    || descriptor.url.search
    || descriptor.url.hash
    || !SAFE_AUTOMATIC_REPLAY_PATHS.has(descriptor.pathname)
  ) return null
  return Object.freeze({ path: descriptor.pathname })
}

export function isSafeReplayableRead(input, init = {}, locationRef = globalThis.location) {
  return createSafeReplayDescriptor(input, init, locationRef) !== null
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

export function authorityContextKey(auth) {
  const context = auth?.security_context
  const userId = auth?.user?.id
  if (userId == null || !context?.session_ref || !context?.trusted_device_ref) return null
  return JSON.stringify([
    String(userId),
    String(context.session_ref),
    String(context.trusted_device_ref),
    context.access_proof_ref == null ? null : String(context.access_proof_ref),
  ])
}

export function createAccessLockCoordinator() {
  const listeners = new Set()
  let lockLatched = false
  let lockGeneration = 0
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
      this.cancelReplay()
      lockLatched = true
      lockGeneration += 1
      emit({ type: 'access_locked', generation: lockGeneration, ...detail })
      return true
    },
    notifyFullLoginRequired(detail = {}) {
      lockLatched = false
      lockGeneration += 1
      this.cancelReplay()
      emit({ type: 'full_login_required', ...detail })
    },
    notifyIdentityContextChanged(detail = {}) {
      lockLatched = false
      lockGeneration += 1
      this.cancelReplay()
      emit({ type: 'identity_context_changed', ...detail })
    },
    captureReplay(descriptor, fallbackResponse, executeReplay) {
      if (!lockLatched || pendingReplay || !descriptor || typeof executeReplay !== 'function') return null
      return new Promise((resolve) => {
        pendingReplay = {
          descriptor,
          executeReplay,
          fallbackResponse,
          finish: resolve,
          generation: lockGeneration,
        }
      })
    },
    async markUnlocked() {
      lockLatched = false
      const pending = pendingReplay
      // Consume before execution so the replay cannot recursively schedule
      // itself and concurrent unlock completions cannot execute it twice.
      pendingReplay = null
      if (!pending) return false
      try {
        const response = await pending.executeReplay(pending.descriptor)
        const stillCurrent = pending.generation === lockGeneration && !lockLatched
        pending.finish(stillCurrent ? response : pending.fallbackResponse)
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
      lockGeneration = 0
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
  const executeSafeReplay = (descriptor) => originalFetch(descriptor.path, {
    method: 'GET',
    credentials: 'same-origin',
  })

  async function accessAwareFetch(input, init = {}) {
    const descriptor = requestDescriptor(input, init, locationRef)
    const response = await originalFetch(input, init)

    if (response.status === 423) {
      const payload = await safeJson(response)
      if (isStructuredAccessLock(response.status, payload)) {
        coordinator.notifyAccessLocked({
          returnPath: safeRelativePath(locationRef?.pathname || '/'),
        })
        const replayDescriptor = createSafeReplayDescriptor(input, init, locationRef)
        if (replayDescriptor) {
          const waiting = coordinator.captureReplay(
            replayDescriptor,
            response,
            executeSafeReplay,
          )
          if (waiting) return waiting
        }
      }
    } else if (descriptor?.sameOrigin && isFullLogin401(descriptor.pathname, response.status)) {
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
