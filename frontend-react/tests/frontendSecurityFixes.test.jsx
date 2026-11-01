// @vitest-environment jsdom
import React from 'react'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'
import { accessLockCoordinator } from '../src/auth/accessLock'
import AccessLockProvider from '../src/components/security/AccessLockProvider'
import DriverLayout from '../src/components/driver/DriverLayout'
import AdminLogin from '../src/pages/admin/AdminLogin'
import AiChat from '../src/pages/shared/AiChat'
import GlobalAiAssistant from '../src/components/ai/GlobalAiAssistant'
import { loadAssistantConversations, saveAssistantConversations, loadAssistantMemory, saveAssistantMemory } from '../src/lib/aiAssistant'

const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const driver = { id: 901, role: 'driver', email: 'driver@example.test' }
function authView(user, status, child) {
  return <MemoryRouter initialEntries={['/ai-chat']}><AuthVerificationProvider value={{ user, status }}>{child}</AuthVerificationProvider></MemoryRouter>
}
function history(text) {
  return [{ id: `conversation-${text}`, title: text, createdAt: 1, updatedAt: 1, messages: [{ id: `message-${text}`, role: 'user', text, createdAt: 1 }] }]
}
beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  clearCachedCsrfToken()
  delete window.__BOOTSTRAP__
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('logout uses confirmed server revocation and the shared authority owner', () => {
  function mountDriver(logoutStatus) {
    const fresh = new Date(Date.now() + 60000).toISOString()
    window.__BOOTSTRAP__ = { auth: { status: 'unlocked', user: driver, fresh_until: fresh, verified_at: new Date().toISOString() } }
    sessionStorage.setItem('user', JSON.stringify(driver))
    sessionStorage.setItem('csrf_token', 'csrf-audit')
    sessionStorage.setItem('unrelated-draft', 'keep')
    fetch.mockImplementation(async url => url === '/auth/logout'
      ? response(logoutStatus === 200 ? { success: true } : { success: false, message: 'Revocation unavailable. Please retry.' }, logoutStatus)
      : response({ success: true, user: driver, csrf_token: 'csrf-audit', access_locked: false, fresh_until: fresh }))
    return render(<MemoryRouter initialEntries={['/driver/dashboard']}><AccessLockProvider><Routes>
      <Route path="/driver/dashboard" element={<DriverLayout><p>Private driver workspace</p></DriverLayout>} />
      <Route path="/login" element={<p>Login page</p>} />
    </Routes></AccessLockProvider></MemoryRouter>)
  }
  test('driver logout supplies CSRF, clears authority, and preserves unrelated drafts', async () => {
    const events = []
    const unsubscribe = accessLockCoordinator.subscribe(event => events.push(event.type))
    mountDriver(200)
    await userEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByText('Login page')).toBeTruthy()
    const call = fetch.mock.calls.find(([url]) => url === '/auth/logout')
    expect(call[1].headers['X-CSRF-Token']).toBe('csrf-audit')
    expect(events).toContain('full_login_required')
    expect(sessionStorage.getItem('user')).toBeNull()
    expect(sessionStorage.getItem('unrelated-draft')).toBe('keep')
    expect(screen.queryByText('Private driver workspace')).toBeNull()
    unsubscribe()
  })
  test('failed revocation remains signed in and exposes a retryable error', async () => {
    mountDriver(503)
    await userEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Revocation unavailable. Please retry.')
    expect(screen.getByText('Private driver workspace')).toBeTruthy()
    expect(screen.queryByText('Login page')).toBeNull()
    expect(sessionStorage.getItem('user')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Logout' }).disabled).toBe(false)
  })
})

test('admin navigation waits for authoritative sign-in refresh', async () => {
  let resolveAuthority
  const refreshAuthority = vi.fn(() => new Promise(resolve => { resolveAuthority = resolve }))
  fetch.mockResolvedValue(response({ success: true, user: { id: 3, role: 'platform_admin' }, csrf_token: 'admin-csrf' }))
  render(<MemoryRouter initialEntries={['/admin/login']}><AuthVerificationProvider value={{ status: AUTH_STATUSES.UNAUTHORIZED, user: null, refreshAuthority }}><Routes>
    <Route path="/admin/login" element={<AdminLogin />} />
    <Route path="/admin/dashboard" element={<p>Verified admin workspace</p>} />
  </Routes></AuthVerificationProvider></MemoryRouter>)
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('admin@digitransx.com'), 'admin@example.test')
  await user.type(screen.getByPlaceholderText('Enter password'), 'AdminPass123')
  await user.click(screen.getByRole('button', { name: 'Sign In to Admin Panel' }))
  await waitFor(() => expect(refreshAuthority).toHaveBeenCalledWith({ force: true }))
  expect(screen.queryByText('Verified admin workspace')).toBeNull()
  await act(async () => resolveAuthority())
  expect(await screen.findByText('Verified admin workspace')).toBeTruthy()
})

test('AI history mounts only after verification and switches immediately between same-role accounts', async () => {
  const accountA = { id: 11, role: 'service_seeker' }
  const accountB = { id: 12, role: 'service_seeker' }
  saveAssistantConversations(history('A-private-shipment'), accountA.id)
  saveAssistantConversations(history('B-private-shipment'), accountB.id)
  fetch.mockImplementation(async () => response({}, 404))
  const view = render(authView(accountA, AUTH_STATUSES.PRESENTED, <AiChat />))
  expect(screen.queryByText('A-private-shipment')).toBeNull()
  expect(fetch).not.toHaveBeenCalled()
  view.rerender(authView(accountA, AUTH_STATUSES.VERIFIED, <AiChat />))
  expect((await screen.findAllByText('A-private-shipment')).length).toBeGreaterThan(0)
  view.rerender(authView(accountB, AUTH_STATUSES.VERIFIED, <AiChat />))
  expect(screen.queryByText('A-private-shipment')).toBeNull()
  expect((await screen.findAllByText('B-private-shipment')).length).toBeGreaterThan(0)
  view.rerender(authView(null, AUTH_STATUSES.UNAUTHORIZED, <AiChat />))
  expect(screen.queryByText('B-private-shipment')).toBeNull()
})

test('a late AI reply after switching identity cannot enter the next account history', async () => {
  const a = { id: 21, role: 'service_seeker' }, b = { id: 22, role: 'service_seeker' }
  let finishReply
  fetch.mockImplementation(url => url.endsWith('/interpret')
    ? new Promise(resolve => { finishReply = resolve }) : Promise.resolve(response({}, 404)))
  const view = render(authView(a, AUTH_STATUSES.VERIFIED, <AiChat />))
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('Type anything. The assistant can answer questions and perform supported app actions.'), 'A confidential request')
  await user.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() => expect(finishReply).toBeTypeOf('function'))
  view.rerender(authView(b, AUTH_STATUSES.VERIFIED, <AiChat />))
  await act(async () => finishReply(response({ success: true, responseText: 'A private delayed answer' })))
  expect(screen.queryByText('A confidential request')).toBeNull()
  expect(screen.queryByText('A private delayed answer')).toBeNull()
  expect(JSON.stringify(loadAssistantConversations(b.id))).not.toContain('confidential')
  expect(JSON.stringify(loadAssistantConversations(b.id))).not.toContain('private delayed')
})

test('global assistant resets private memory and terminates recognition when identity changes', async () => {
  const a = { id: 31, role: 'service_seeker' }, b = { id: 32, role: 'service_seeker' }
  const initial = { ...loadAssistantMemory('/client/dashboard', a.role, a.id), pendingQuestion: true, pendingQuestionPrompt: 'A private followup' }
  saveAssistantMemory(initial, a.id)
  const instances = []
  class Recognition {
    constructor() { this.abort = vi.fn(); this.start = vi.fn(); this.stop = vi.fn(); instances.push(this) }
  }
  vi.stubGlobal('SpeechRecognition', Recognition)
  fetch.mockImplementation(async () => response({}, 404))
  // Widget is hidden on /ai-chat; use a portal pathname to exercise the visible owner.
  const wrap = user => <MemoryRouter initialEntries={['/client/dashboard']}><AuthVerificationProvider value={{ status: AUTH_STATUSES.VERIFIED, user }}><GlobalAiAssistant /></AuthVerificationProvider></MemoryRouter>
  const view = render(wrap(a))
  expect(await screen.findByText('A private followup')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Open AI Assistant' }))
  await userEvent.click(screen.getAllByRole('button', { name: 'Mic' })[0])
  expect(instances).toHaveLength(1)
  view.rerender(wrap(b))
  expect(screen.queryByText('A private followup')).toBeNull()
  expect(instances[0].abort).toHaveBeenCalledOnce()
  expect(instances[0].onresult).toBeNull()
  expect(loadAssistantMemory('/client/dashboard', b.role, b.id).lastQuestion).toBe('')
})
