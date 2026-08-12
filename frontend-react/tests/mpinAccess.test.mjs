import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  ACCESS_STATES,
  createAccessLockCoordinator,
  createLatestRequestGate,
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
import { clearSignupDraft, getSignupBasicDraft, setSignupBasicDraft } from '../src/auth/signupDraft.js'

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

test('safe replay permits only bodyless same-origin GET without query or high-risk prefix', () => {
  const locationRef = { origin: 'https://app.test' }
  assert.equal(isSafeReplayableRead('/api/orders', {}, locationRef), true)
  for (const [url, init] of [
    ['/api/orders', { method: 'POST' }],
    ['/api/orders?secret=value', {}],
    ['/api/payments', {}],
    ['/api/wallet', {}],
    ['/uploads/trucks/file', {}],
    ['/auth/me', {}],
    ['https://evil.test/api/orders', {}],
  ]) assert.equal(isSafeReplayableRead(url, init, locationRef), false, url)
})

test('concurrent access locks emit one overlay event and retain at most one replay', async () => {
  const coordinator = createAccessLockCoordinator()
  let locks = 0
  coordinator.subscribe((event) => { if (event.type === 'access_locked') locks += 1 })
  assert.equal(coordinator.notifyAccessLocked(), true)
  assert.equal(coordinator.notifyAccessLocked(), false)
  assert.equal(locks, 1)
  const fallback = { status: 423 }
  const first = coordinator.waitForOneReplay(async () => ({ status: 200 }), fallback)
  assert.equal(coordinator.waitForOneReplay(async () => ({ status: 201 }), fallback), null)
  assert.equal(await coordinator.markUnlocked(), true)
  assert.equal((await first).status, 200)
  assert.equal(await coordinator.markUnlocked(), false)
})

test('fetch interception replays at most one safe GET and never replays a mutation', async () => {
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
  const read = globalRef.fetch('/api/orders')
  const mutation = await globalRef.fetch('/api/orders', { method: 'POST', body: '{}' })
  assert.equal(mutation.status, 423)
  assert.equal(calls.length, 2)
  await coordinator.markUnlocked()
  assert.equal((await read).status, 200)
  assert.equal(calls.length, 3)
  uninstall()
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

test('signup password draft is process-memory only and can be cleared', () => {
  clearSignupDraft()
  setSignupBasicDraft({ email: 'user@example.test', password: 'not-persisted' })
  assert.deepEqual(getSignupBasicDraft(), { email: 'user@example.test', password: 'not-persisted' })
  clearSignupDraft()
  assert.equal(getSignupBasicDraft(), null)
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
