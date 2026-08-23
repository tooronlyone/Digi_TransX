import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  ACCESS_STATES,
  authorityContextKey,
  createAccessLockCoordinator,
  createLatestRequestGate,
  createSafeReplayDescriptor,
  deriveAccessState,
  installAccessFetchInterceptor,
  isFullLogin401,
  isMpinEligibleRole,
  isPublicAuthPath,
  isSafeReplayableRead,
  isStructuredAccessLock,
  isValidMpin,
  nextMpinInput,
  safeRelativePath,
  sanitizeMpinInput,
} from '../src/auth/accessLock.js'
import { requestJson } from '../src/auth/api.js'
import { createSignupDraftStore } from '../src/auth/signupDraft.js'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('accepts exactly four ASCII digits and rejects Unicode, whitespace, and invalid types', () => {
  assert.equal(isValidMpin('0123'), true)
  for (const value of ['123', '12345', '12 3', '１２３４', '١٢٣٤', '12a3', 1234, null]) {
    assert.equal(isValidMpin(value), false, String(value))
  }
  assert.equal(sanitizeMpinInput('1234'), '1234')
  assert.equal(sanitizeMpinInput('12 3'), '')
})

test('typing, deletion, correction, and valid paste preserve one coherent value', () => {
  assert.equal(nextMpinInput('', '1'), '1')
  assert.equal(nextMpinInput('123', '12'), '12')
  assert.equal(nextMpinInput('12', '129'), '129')
  assert.equal(nextMpinInput('129', '12a9'), '129')
  assert.equal(nextMpinInput('', '9081'), '9081')
  assert.equal(nextMpinInput('9081', '90810'), '9081')
})

test('derives the seven canonical states from backend authority', () => {
  assert.equal(deriveAccessState({ authenticated: false }), ACCESS_STATES.FULL_LOGIN_REQUIRED)
  assert.equal(deriveAccessState({ authenticated: true, accessLocked: false }), ACCESS_STATES.UNLOCKED)
  assert.equal(deriveAccessState({ authenticated: true, accessLocked: true, statusUnavailable: true }), ACCESS_STATES.TEMPORARILY_UNAVAILABLE)
  assert.equal(deriveAccessState({ authenticated: true, accessLocked: true, mpinStatus: { enrolled: true, locked: false, role_eligible: true } }), ACCESS_STATES.LOCKED_MPIN_AVAILABLE)
  assert.equal(deriveAccessState({ authenticated: true, accessLocked: true, mpinStatus: { enrolled: false, locked: false, role_eligible: true } }), ACCESS_STATES.LOCKED_PASSWORD_REQUIRED)
  assert.equal(deriveAccessState({ authenticated: true, accessLocked: true, mpinStatus: { enrolled: true, locked: true, role_eligible: true } }), ACCESS_STATES.MPIN_PERMANENTLY_LOCKED)
  assert.deepEqual(Object.values(ACCESS_STATES).sort(), [
    'checking', 'full_login_required', 'locked_mpin_available', 'locked_password_required',
    'mpin_permanently_locked', 'temporarily_unavailable', 'unlocked',
  ].sort())
})

test('eligible role surface is exact and excludes admin and adjacent roles', () => {
  for (const role of ['logistics_provider', 'service_seeker', 'everyday_user']) assert.equal(isMpinEligibleRole(role), true)
  for (const role of ['platform_admin', 'admin', 'fuel_station_manager', 'shopkeeper', '', null]) assert.equal(isMpinEligibleRole(role), false)
})

test('only the exact structured 423 is a software lock', () => {
  assert.equal(isStructuredAccessLock(423, { code: 'access_locked' }), true)
  assert.equal(isStructuredAccessLock(423, { code: 'business_locked' }), false)
  assert.equal(isStructuredAccessLock(401, { code: 'access_locked' }), false)
})

test('credential-domain 401 stays local while ordinary 401 requires full login', () => {
  assert.equal(isFullLogin401('/auth/mpin/unlock', 401), false)
  assert.equal(isFullLogin401('/auth/access/unlock/password', 401), false)
  assert.equal(isFullLogin401('/api/profile/password/request-otp', 401), false)
  assert.equal(isFullLogin401('/api/orders', 401), true)
  assert.equal(isFullLogin401('/api/orders', 403), false)
})

test('return destinations are same-origin paths stripped of private query and fragments', () => {
  assert.equal(safeRelativePath('/client/orders?token=secret#x'), '/client/orders')
  assert.equal(safeRelativePath('https://evil.test/x'), '/')
  assert.equal(safeRelativePath('//evil.test/x'), '/')
  assert.equal(safeRelativePath('/a/../private'), '/')
})

test('public auth routing does not mistake every protected path as public', () => {
  for (const path of ['/', '/login', '/signup', '/signup/role', '/reset-password', '/admin/login']) assert.equal(isPublicAuthPath(path), true)
  for (const path of ['/client/orders', '/transporter/dashboard', '/everyday/security']) assert.equal(isPublicAuthPath(path), false)
})

test('automatic replay is a fail-closed exact positive policy', () => {
  const locationRef = { origin: 'https://app.test' }
  const safePath = '/api/platform/terms/current'
  assert.equal(isSafeReplayableRead(safePath, {}, locationRef), true)
  assert.equal(isSafeReplayableRead(safePath, { method: 'GET', credentials: 'same-origin' }, locationRef), true)
  assert.equal(isSafeReplayableRead(`https://app.test${safePath}`, {}, locationRef), true)

  for (const [url, init] of [
    ['/api/unknown', {}],
    [`${safePath}?page=1`, {}],
    [`${safePath}#section`, {}],
    [`https://evil.test${safePath}`, {}],
    [`//app.test${safePath}`, {}],
    [`https://user:password@app.test${safePath}`, {}],
    ['/api/platform%2fterms/current', {}],
    ['/api/platform%5cterms/current', {}],
    ['/api/platform/%2e%2e/terms/current', {}],
    ['/api/platform/../platform/terms/current', {}],
    ['/api//platform/terms/current', {}],
    ['/api/platform/%ZZ/terms/current', {}],
    [`${safePath}/`, {}],
    [`${safePath}/unsafe-operation`, {}],
    ['/api/platform/terms/currently', {}],
    [safePath, { method: 'get' }],
    [safePath, { method: 'POST' }],
    [safePath, { method: 'PUT' }],
    [safePath, { method: 'PATCH' }],
    [safePath, { method: 'DELETE' }],
    [safePath, { body: '{}' }],
    [safePath, { signal: new AbortController().signal }],
    [safePath, { headers: { Authorization: 'sensitive' } }],
    [safePath, { credentials: 'omit' }],
    ['/auth/me', {}],
    ['/auth/mpin/status', {}],
    ['/auth/mpin/unlock', {}],
    ['/auth/access/unlock/password', {}],
    ['/auth/logout', {}],
    ['/track', {}],
    ['/api/session/activity', {}],
    ['/uploads/trucks/file', {}],
    ['/uploads/chat/file', {}],
    ['/api/chat/threads/1/messages/media', {}],
    ['/api/agreements/42/trips', {}],
    ['/api/agreements/trips/7/live-location', {}],
    ['/api/trucks/9/live-location', {}],
    ['/api/orders/42/bids/7/payment-quote', {}],
    ['/api/orders/my-bids', {}],
    ['/api/payment-methods', {}],
    ['/api/wallet', {}],
    ['/api/agreements/42/payments', {}],
    ['/api/notifications/1/read', {}],
    ['/admin/payments', {}],
    ['/api/admin/reports/export', {}],
  ]) assert.equal(isSafeReplayableRead(url, init, locationRef), false, url)

  assert.equal(isSafeReplayableRead(new URL(`https://app.test${safePath}`), {}, locationRef), false)
  assert.equal(isSafeReplayableRead(new Request(`https://app.test${safePath}`), {}, locationRef), false)
  assert.equal(isSafeReplayableRead(safePath, {}, {}), false)
  assert.equal(isSafeReplayableRead(safePath, Object.assign(Object.create({ body: '{}' }), { method: 'GET' }), locationRef), false)
})

test('safe replay descriptor contains only the audited non-sensitive path', () => {
  const descriptor = createSafeReplayDescriptor(
    '/api/platform/terms/current',
    { method: 'GET', credentials: 'include' },
    { origin: 'https://app.test' },
  )
  assert.deepEqual(descriptor, { path: '/api/platform/terms/current' })
  assert.equal(Object.isFrozen(descriptor), true)
  assert.deepEqual(Object.keys(descriptor), ['path'])
  for (const key of ['body', 'headers', 'signal', 'password', 'mpin', 'token', 'file', 'provider']) {
    assert.equal(key in descriptor, false)
  }
})

test('the sole allowlisted route is a component-used SELECT-only provider-free JSON read', async () => {
  const termsRoutes = await source('../../backend/terms/routes.py')
  const commissions = await source('../../backend/shared/commissions.py')
  const notice = await source('../src/components/common/TermsUpdateNotice.jsx')
  const handler = termsRoutes.slice(
    termsRoutes.indexOf('@terms_blueprint.get("/api/platform/terms/current")'),
    termsRoutes.indexOf('@terms_blueprint.get("/api/platform/terms/history")'),
  )
  assert.match(handler, /@login_required/)
  assert.match(handler, /with open_db\(\) as db/)
  assert.match(handler, /return json_response/)
  assert.match(notice, /apiGet\('\/api\/platform\/terms\/current'\)/)

  const helperNames = [
    'get_policy_by_id', 'get_current_terms_version', 'get_terms_version_by_number',
    'has_acknowledged', 'changed_policy_types', 'requires_acknowledgement',
    'serialize_policy', 'serialize_terms_version',
  ]
  const audited = [handler]
  for (const name of helperNames) {
    const start = commissions.indexOf(`def ${name}(`)
    const next = commissions.indexOf('\ndef ', start + 1)
    assert.notEqual(start, -1, name)
    audited.push(commissions.slice(start, next === -1 ? commissions.length : next))
  }
  const combined = audited.join('\n').toLowerCase()
  for (const forbidden of [
    'db.commit', ' insert ', ' update ', ' delete ', 'download_bytes', 'upload_file_storage',
    'get_latest_position', 'register_device', 'supabase', 'send_file',
    'send_from_directory', 'signed_url', 'requests.', 'httpx.',
  ]) assert.equal(combined.includes(forbidden), false, forbidden)
})

test('concurrent access locks emit one overlay event and retain at most one replay', async () => {
  const coordinator = createAccessLockCoordinator()
  let locks = 0
  coordinator.subscribe((event) => { if (event.type === 'access_locked') locks += 1 })
  assert.equal(coordinator.notifyAccessLocked(), true)
  assert.equal(coordinator.notifyAccessLocked(), false)
  assert.equal(locks, 1)
  const fallback = { status: 423 }
  const descriptor = { path: '/api/platform/terms/current' }
  const first = coordinator.captureReplay(descriptor, fallback, async () => ({ status: 200 }))
  assert.equal(coordinator.captureReplay(descriptor, fallback, async () => ({ status: 201 })), null)
  assert.equal(await coordinator.markUnlocked(), true)
  assert.equal((await first).status, 200)
  assert.equal(await coordinator.markUnlocked(), false)
})

test('pending replay is consumed before execution and failure cannot loop', async () => {
  const coordinator = createAccessLockCoordinator()
  const fallback = { status: 423 }
  const descriptor = { path: '/api/platform/terms/current' }
  coordinator.notifyAccessLocked()
  let executions = 0
  const waiting = coordinator.captureReplay(descriptor, fallback, async () => {
    executions += 1
    assert.equal(coordinator.hasPendingReplay(), false)
    assert.equal(coordinator.captureReplay(descriptor, fallback, async () => ({})), null)
    throw new Error('replay failed')
  })
  assert.equal(await coordinator.markUnlocked(), true)
  assert.equal(await waiting, fallback)
  assert.equal(executions, 1)
  assert.equal(coordinator.hasPendingReplay(), false)
  assert.equal(await coordinator.markUnlocked(), false)
})

test('new lock, logout, full-login, and route abandonment invalidate pending replay', async () => {
  const descriptor = { path: '/api/platform/terms/current' }
  const fallback = { status: 423 }

  const stale = createAccessLockCoordinator()
  stale.notifyAccessLocked()
  let release
  const staleWaiting = stale.captureReplay(descriptor, fallback, () => new Promise((resolve) => { release = resolve }))
  const unlocking = stale.markUnlocked()
  assert.equal(stale.notifyAccessLocked(), true)
  release({ status: 200 })
  assert.equal(await unlocking, true)
  assert.equal(await staleWaiting, fallback)

  for (const cleanup of ['logout', 'full_login_required', 'route_abandonment']) {
    const coordinator = createAccessLockCoordinator()
    coordinator.notifyAccessLocked()
    const waiting = coordinator.captureReplay(descriptor, fallback, async () => ({ status: 200 }))
    if (cleanup === 'route_abandonment') coordinator.cancelReplay()
    else coordinator.notifyFullLoginRequired({ reason: cleanup })
    assert.equal(await waiting, fallback, cleanup)
    assert.equal(coordinator.hasPendingReplay(), false, cleanup)
    assert.equal(await coordinator.markUnlocked(), false, cleanup)
  }
})

test('unlock failure retains one descriptor only within the current lock generation', () => {
  const coordinator = createAccessLockCoordinator()
  coordinator.notifyAccessLocked()
  const waiting = coordinator.captureReplay(
    { path: '/api/platform/terms/current' },
    { status: 423 },
    async () => ({ status: 200 }),
  )
  assert.equal(typeof waiting?.then, 'function')
  assert.equal(coordinator.hasPendingReplay(), true)
  coordinator.cancelReplay()
})

test('fetch interception replays one exact safe GET and never replays prohibited requests', async () => {
  const coordinator = createAccessLockCoordinator()
  const calls = []
  const responses = [
    new Response(JSON.stringify({ code: 'access_locked' }), { status: 423, headers: { 'content-type': 'application/json' } }),
    new Response(JSON.stringify({ code: 'access_locked' }), { status: 423, headers: { 'content-type': 'application/json' } }),
    new Response('{}', { status: 200 }),
  ]
  const globalRef = {
    location: { origin: 'https://app.test', pathname: '/client/orders' },
    fetch: async (url, init) => { calls.push({ url, init }); return responses.shift() },
  }
  const uninstall = installAccessFetchInterceptor({ globalRef, coordinator })
  const read = globalRef.fetch('/api/platform/terms/current')
  const prohibited = await globalRef.fetch('/api/agreements/42/trips')
  assert.equal(prohibited.status, 423)
  assert.equal(calls.length, 2)
  await coordinator.markUnlocked()
  assert.equal((await read).status, 200)
  assert.equal(calls.length, 3)
  assert.equal(calls[2].url, '/api/platform/terms/current')
  assert.deepEqual(calls[2].init, { method: 'GET', credentials: 'same-origin' })
  uninstall()
})

test('concurrent safe 423 responses retain one replay and replayed 423 cannot recurse', async () => {
  const coordinator = createAccessLockCoordinator()
  let calls = 0
  const globalRef = {
    location: { origin: 'https://app.test', pathname: '/client/orders' },
    fetch: async () => {
      calls += 1
      return new Response(JSON.stringify({ code: 'access_locked' }), {
        status: 423,
        headers: { 'content-type': 'application/json' },
      })
    },
  }
  installAccessFetchInterceptor({ globalRef, coordinator })
  const first = globalRef.fetch('/api/platform/terms/current')
  const second = await globalRef.fetch('/api/platform/terms/current')
  assert.equal(second.status, 423)
  assert.equal(calls, 2)
  await coordinator.markUnlocked()
  assert.equal((await first).status, 423)
  assert.equal(calls, 3)
  assert.equal(coordinator.hasPendingReplay(), false)
  assert.equal(await coordinator.markUnlocked(), false)
})

test('ordinary 401 clears a pending replay before full-login transition', async () => {
  const coordinator = createAccessLockCoordinator()
  const responses = [
    new Response(JSON.stringify({ code: 'access_locked' }), { status: 423 }),
    new Response('{}', { status: 401 }),
  ]
  const globalRef = {
    location: { origin: 'https://app.test', pathname: '/client/orders' },
    fetch: async () => responses.shift(),
  }
  installAccessFetchInterceptor({ globalRef, coordinator })
  const waiting = globalRef.fetch('/api/platform/terms/current')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(coordinator.hasPendingReplay(), true)
  await globalRef.fetch('/api/orders/my-orders')
  assert.equal((await waiting).status, 423)
  assert.equal(coordinator.hasPendingReplay(), false)
})

test('unlock endpoints do not recursively trigger full-login handling', async () => {
  const coordinator = createAccessLockCoordinator()
  let fullLogin = 0
  coordinator.subscribe((event) => { if (event.type === 'full_login_required') fullLogin += 1 })
  const globalRef = {
    location: { origin: 'https://app.test', pathname: '/client/orders' },
    fetch: async () => new Response('{}', { status: 401 }),
  }
  installAccessFetchInterceptor({ globalRef, coordinator })
  await globalRef.fetch('/auth/mpin/unlock', { method: 'POST' })
  assert.equal(fullLogin, 0)
  await globalRef.fetch('/api/orders')
  assert.equal(fullLogin, 1)
  await globalRef.fetch('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  assert.equal(fullLogin, 2)
  await globalRef.fetch('https://provider.test/private')
  assert.equal(fullLogin, 2)
})

test('latest-request gate rejects stale and invalidated responses', () => {
  const gate = createLatestRequestGate()
  const first = gate.begin()
  const second = gate.begin()
  assert.equal(gate.isCurrent(first), false)
  assert.equal(gate.isCurrent(second), true)
  gate.invalidate()
  assert.equal(gate.isCurrent(second), false)
})

test('every JSON mutation carries the approved CSRF header and secrets stay in the body', async () => {
  const calls = []
  await requestJson('/auth/mpin/unlock', {
    method: 'POST',
    body: { mpin: '0123' },
    storage: { getItem: () => 'csrf-only-header' },
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return { ok: true, status: 200, json: async () => ({ success: true }) }
    },
  })
  assert.equal(calls[0].url, '/auth/mpin/unlock')
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'csrf-only-header')
  assert.equal(calls[0].url.includes('0123'), false)
  assert.equal(calls[0].options.credentials, 'same-origin')
})

test('signup password draft is isolated to one store instance and can be cleared', () => {
  const first = createSignupDraftStore()
  const second = createSignupDraftStore()
  first.begin({ email: 'user@example.test', password: 'not-persisted' })
  assert.equal(first.read().basic.password, 'not-persisted')
  assert.equal(second.read().basic, null)
  first.clear()
  assert.equal(first.read().basic, null)
})

test('MPIN control has one masked accessible input and four presentation-only slots', async () => {
  const input = await source('../src/components/security/MpinInput.jsx')
  assert.equal((input.match(/<input/g) || []).length, 1)
  assert.match(input, /type="password"/)
  assert.match(input, /inputMode="numeric"/)
  assert.match(input, /aria-hidden="true"/)
  assert.match(input, /\[0, 1, 2, 3\]/)
  assert.match(input, /onPaste=/)
  assert.equal(input.includes('data-'), false)
})

test('global lock is blocking, focus-trapped, escape-resistant, and keeps logout available', async () => {
  const provider = await source('../src/components/security/AccessLockProvider.jsx')
  assert.match(provider, /aria-modal="true"/)
  assert.match(provider, /inert=\{blocked/)
  assert.match(provider, /ACCESS_STATES\.CHECKING/)
  assert.match(provider, /Checking secure access/)
  assert.match(provider, /event\.key === 'Escape'/)
  assert.match(provider, /event\.key !== 'Tab'/)
  assert.match(provider, /\/auth\/logout/)
  assert.match(provider, /Unlock with password/)
  assert.match(provider, /setMpin\(''\)/)
  assert.match(provider, /accessLockCoordinator\.cancelReplay\(\)/)
  assert.equal(/remaining attempts?/i.test(provider), false)
})

test('one canonical management component owns all operations and all three role routes', async () => {
  const app = await source('../src/App.jsx')
  const management = await source('../src/components/security/MpinManagement.jsx')
  assert.equal((app.match(/<SecuritySettings/g) || []).length, 3)
  for (const endpoint of ['/auth/mpin/status', '/auth/mpin/enroll', '/auth/mpin/change', '/auth/mpin/disable', '/auth/mpin/reset']) {
    assert.match(management, new RegExp(endpoint.replaceAll('/', '\\/')))
  }
  assert.match(management, /role_eligible === true/)
  assert.match(management, /window\.confirm/)
  assert.match(management, /loadStatus\(\{ preserveMessage: true \}\)/)
})

test('legacy MPIN endpoints and browser-persisted signup secrets have no frontend callers', async () => {
  const files = [
    '../src/pages/auth/Login.jsx',
    '../src/pages/auth/Unlock.jsx',
    '../src/pages/transporter/settings.jsx',
    '../src/pages/auth/Signup.jsx',
    '../src/pages/auth/RoleSelect.jsx',
    '../src/pages/auth/roledetails/_submitHelper.js',
  ]
  const combined = (await Promise.all(files.map(source))).join('\n')
  assert.equal(combined.includes('/auth/fast-login'), false)
  assert.equal(combined.includes("sessionStorage.setItem('signup_basic'"), false)
  assert.equal(combined.includes("sessionStorage.setItem('signup_role'"), false)
})

test('responsive CSS covers required breakpoints without global overflow concealment', async () => {
  const css = await source('../src/styles/components/mpin-security.css')
  assert.match(css, /max-width: 767px/)
  assert.match(css, /max-width: 374px/)
  assert.match(css, /100dvh/)
  assert.equal(/(?:html|body|\*)[^{}]*\{[^}]*overflow-x\s*:\s*hidden/s.test(css), false)
})

test('genuine activity remains the sole trusted interaction owner', async () => {
  const provider = await source('../src/components/security/AccessLockProvider.jsx')
  const management = await source('../src/components/security/MpinManagement.jsx')
  for (const candidate of [provider, management]) {
    assert.equal(candidate.includes('/auth/session/activity'), false)
    assert.equal(candidate.includes('sendGenuineActivity'), false)
    assert.equal(candidate.includes('addEventListener'), false)
  }
})

test('authority context changes cancel pending work for every auth generation', async () => {
  const base = {
    user: { id: 7 },
    security_context: {
      session_ref: 'session-a',
      trusted_device_ref: 'device-a',
      access_proof_ref: 'proof-a',
    },
  }
  const original = authorityContextKey(base)
  for (const changed of [
    { ...base, user: { id: 8 } },
    { ...base, security_context: { ...base.security_context, session_ref: 'session-b' } },
    { ...base, security_context: { ...base.security_context, trusted_device_ref: 'device-b' } },
    { ...base, security_context: { ...base.security_context, access_proof_ref: 'proof-b' } },
  ]) assert.notEqual(authorityContextKey(changed), original)

  assert.equal(authorityContextKey({ user: { id: 7 } }), null)
  const coordinator = createAccessLockCoordinator()
  const events = []
  coordinator.subscribe((event) => events.push(event.type))
  coordinator.notifyAccessLocked()
  const fallback = { status: 423 }
  const waiting = coordinator.captureReplay(
    { path: '/api/platform/terms/current' },
    fallback,
    async () => ({ status: 200 }),
  )
  coordinator.notifyIdentityContextChanged()
  assert.equal(await waiting, fallback)
  assert.equal(coordinator.hasPendingReplay(), false)
  assert.equal(await coordinator.markUnlocked(), false)
  assert.deepEqual(events, ['access_locked', 'identity_context_changed'])
})
