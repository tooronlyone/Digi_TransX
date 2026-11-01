// @vitest-environment jsdom
import React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Settings from '../src/pages/transporter/settings'
import Login from '../src/pages/auth/Login'
import AccessLockProvider from '../src/components/security/AccessLockProvider'
import { accessLockCoordinator } from '../src/auth/accessLock'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'

const owner = { id: 903, role: 'logistics_provider', email: 'settings@example.test', full_name: 'Settings Fixture' }
// These flows type into the full settings page while other component files run
// concurrently; allow host scheduling without weakening behavioral assertions.
vi.setConfig({ testTimeout: 15000 })
const response = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

beforeEach(() => {
  sessionStorage.clear()
  clearCachedCsrfToken()
  const fresh = new Date(Date.now() + 60000).toISOString()
  window.__BOOTSTRAP__ = { auth: { status: 'unlocked', user: owner, fresh_until: fresh, verified_at: new Date().toISOString() } }
  window.AuthSession = { user: owner }
  sessionStorage.setItem('user', JSON.stringify(owner))
  sessionStorage.setItem('csrf_token', 'settings-csrf')
  sessionStorage.setItem('unrelated-draft', 'retain')
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete window.__BOOTSTRAP__
  delete window.AuthSession
})

function mountSettings({ passwordResult, passwordStatus = 200, otpResult } = {}) {
  let revoked = false
  fetch.mockImplementation(async (url, options = {}) => {
    if (url === '/api/profile/password/request-otp') {
      return otpResult ? otpResult() : response({ success: true, message: 'OTP sent.' })
    }
    if (url === '/api/profile/password') {
      revoked = true
      return response(passwordResult || { success: true, reauthentication_required: true, message: 'Password changed. Sign in again on every device.' }, passwordStatus)
    }
    if (url === '/api/profile' && (!options.method || options.method === 'GET')) return response({ success: true, user: owner })
    if (url === '/auth/me') {
      return revoked ? response({ success: false, message: 'Authentication required.' }, 401)
        : response({ success: true, user: owner, access_locked: false, csrf_token: 'settings-csrf', fresh_until: new Date(Date.now() + 60000).toISOString() })
    }
    return response({ success: true })
  })
  return render(<MemoryRouter initialEntries={['/transporter/settings']}><AccessLockProvider><Routes>
    <Route path="/transporter/settings" element={<Settings />} />
    <Route path="/login" element={<Login />} />
  </Routes></AccessLockProvider></MemoryRouter>)
}

async function requestCode(user) {
  await user.click(screen.getByRole('link', { name: 'Privacy & Security' }))
  await user.type(screen.getByPlaceholderText('Enter current password'), 'current-password')
  await user.type(screen.getByPlaceholderText('Enter new password'), 'replacement-password')
  await user.type(screen.getByPlaceholderText('Confirm new password'), 'replacement-password')
  await user.click(screen.getByRole('button', { name: 'Update Security' }))
  await screen.findByPlaceholderText('Enter 6 digit OTP')
}

test('confirmed password change clears authority and shows the server sign-in message', async () => {
  const events = []
  const unsubscribe = accessLockCoordinator.subscribe(event => events.push(event.type))
  try {
    mountSettings()
    const user = userEvent.setup()
    await requestCode(user)
    await user.type(screen.getByPlaceholderText('Enter 6 digit OTP'), '123456')
    await user.click(screen.getByRole('button', { name: 'Verify & Update' }))
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeTruthy()
    expect(await screen.findByText('Password changed. Sign in again on every device.')).toBeTruthy()
    const put = fetch.mock.calls.find(([url]) => url === '/api/profile/password')
    expect(put[1].method).toBe('PUT')
    expect(put[1].headers['X-CSRF-Token']).toBe('settings-csrf')
    expect(JSON.parse(put[1].body)).toEqual({ new_password: 'replacement-password', otp_code: '123456' })
    expect(events).toContain('full_login_required')
    expect(sessionStorage.getItem('user')).toBeNull()
    expect(sessionStorage.getItem('csrf_token')).toBeNull()
    expect(window.AuthSession).toBeUndefined()
    expect(window.__BOOTSTRAP__).toBeUndefined()
    expect(sessionStorage.getItem('unrelated-draft')).toBe('retain')
    expect(screen.queryByPlaceholderText('Enter current password')).toBeNull()
  } finally { unsubscribe() }
})

test.each([
  ['password_change_reconciliation_required', 'Password change outcome is pending verification. Contact support before retrying.'],
  ['password_update_rejected', 'Password update was rejected. Request a new code and choose a different password.'],
])('revoked password failure %s retains the server explanation at sign-in', async (code, message) => {
  mountSettings({ passwordStatus: 503, passwordResult: { success: false, code, message } })
  const user = userEvent.setup()
  await requestCode(user)
  await user.type(screen.getByPlaceholderText('Enter 6 digit OTP'), '123456')
  await user.click(screen.getByRole('button', { name: 'Verify & Update' }))
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeTruthy()
  expect(await screen.findByText(message)).toBeTruthy()
  expect(sessionStorage.getItem('user')).toBeNull()
  expect(screen.queryByText('Request failed')).toBeNull()
})

test('OTP resend sends the entered current password and displays a rejected response', async () => {
  let attempts = 0
  mountSettings({ otpResult: () => ++attempts === 1 ? response({ success: true })
    : response({ success: false, message: 'Wait before requesting another OTP.' }, 429) })
  const user = userEvent.setup()
  await requestCode(user)
  await user.click(screen.getByRole('button', { name: 'Resend OTP' }))
  expect(await screen.findByText('Wait before requesting another OTP.')).toBeTruthy()
  const sends = fetch.mock.calls.filter(([url]) => url === '/api/profile/password/request-otp')
  expect(sends).toHaveLength(2)
  for (const [, options] of sends) {
    expect(JSON.parse(options.body)).toEqual({ current_password: 'current-password' })
    expect(options.headers['X-CSRF-Token']).toBe('settings-csrf')
  }
  expect(screen.queryByText('OTP resent!')).toBeNull()
  expect(screen.getByRole('button', { name: 'Resend OTP' }).disabled).toBe(false)
  expect(sessionStorage.getItem('user')).not.toBeNull()
})

test('OTP resend requires the current password instead of sending an empty payload', async () => {
  mountSettings()
  const user = userEvent.setup()
  await requestCode(user)
  await user.clear(screen.getByPlaceholderText('Enter current password'))
  await user.click(screen.getByRole('button', { name: 'Resend OTP' }))
  expect(await screen.findByText('Enter your current password')).toBeTruthy()
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === '/api/profile/password/request-otp')).toHaveLength(1))
  expect(sessionStorage.getItem('user')).not.toBeNull()
})

test('sign-in preserves the exact password accepted by the password-change form', async () => {
  fetch.mockImplementation(async () => response({ success: false, message: 'Incorrect password.' }, 401))
  render(<MemoryRouter initialEntries={['/login']}><AuthVerificationProvider value={{ status: AUTH_STATUSES.UNAUTHORIZED, user: null }}>
    <Login />
  </AuthVerificationProvider></MemoryRouter>)
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('Enter your email or 13 digit CNIC'), 'settings@example.test')
  await user.type(screen.getByPlaceholderText('Enter your password'), '  replacement-password  ')
  await user.click(screen.getByRole('button', { name: 'Sign In' }))
  await waitFor(() => {
    const login = fetch.mock.calls.find(([url]) => url === '/auth/login')
    expect(login).toBeTruthy()
    expect(JSON.parse(login[1].body).password).toBe('  replacement-password  ')
  })
})

test('initial full-login denial clears stale presentation before redirecting', async () => {
  window.__BOOTSTRAP__ = { auth: { status: 'unauthorized', user: null } }
  fetch.mockResolvedValue(response({ success: false }, 401))
  render(<MemoryRouter initialEntries={['/transporter/settings']}><AccessLockProvider><Routes>
    <Route path="/transporter/settings" element={<p>Private settings</p>} />
    <Route path="/login" element={<p>Login destination</p>} />
  </Routes></AccessLockProvider></MemoryRouter>)
  expect(await screen.findByText('Login destination')).toBeTruthy()
  expect(sessionStorage.getItem('user')).toBeNull()
  expect(window.AuthSession).toBeUndefined()
  expect(window.__BOOTSTRAP__).toBeUndefined()
  expect(sessionStorage.getItem('unrelated-draft')).toBe('retain')
})
