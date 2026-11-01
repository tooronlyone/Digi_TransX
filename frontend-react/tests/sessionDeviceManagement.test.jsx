// @vitest-environment jsdom

import React from 'react'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  logout: vi.fn(),
  navigate: vi.fn(),
  requestJson: vi.fn(),
}))

vi.mock('../src/auth/api.js', () => {
  class ApiResponseError extends Error {
    constructor(message, { status = 0, code = '', payload = null } = {}) {
      super(message)
      this.status = status
      this.code = code
      this.payload = payload
    }
  }
  return { ApiResponseError, requestJson: mocks.requestJson }
})
vi.mock('../src/auth/logout.js', () => ({ logoutCurrentSession: mocks.logout }))
vi.mock('react-router-dom', () => ({ useNavigate: () => mocks.navigate }))

import { ApiResponseError } from '../src/auth/api.js'
import SessionDeviceManagement from '../src/components/security/SessionDeviceManagement.jsx'

const listing = {
  success: true,
  sessions: [
    { management_ref: 'session_current', category_label: 'Active session', created_at: '2026-08-30', last_activity_at: '2026-08-30', is_current: true },
    { management_ref: 'session_other', category_label: 'Active session', created_at: '2026-08-29', last_activity_at: '2026-08-29', is_current: false, raw_token: 'never-render-session-secret' },
  ],
  trusted_devices: [
    { management_ref: 'device_current', category_label: 'Trusted device', created_at: '2026-08-30', last_activity_at: '2026-08-30', is_current: true },
    { management_ref: 'device_other', category_label: 'Trusted device', created_at: '2026-08-28', last_activity_at: '2026-08-28', is_current: false, token_digest: 'never-render-device-digest' },
  ],
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail })
  return { promise, reject, resolve }
}

beforeEach(() => {
  mocks.logout.mockReset()
  mocks.navigate.mockReset()
  mocks.requestJson.mockReset()
  vi.restoreAllMocks()
})

afterEach(() => cleanup())

describe('SessionDeviceManagement rendered behavior', () => {
  test('renders authoritative safe lists, exact current markers, and both canonical logout actions', async () => {
    mocks.requestJson.mockResolvedValueOnce(listing)
    const user = userEvent.setup()
    const { container } = render(<SessionDeviceManagement />)

    expect(await screen.findByText('Active Sessions')).toBeTruthy()
    expect(screen.getAllByText('Active session')).toHaveLength(2)
    expect(screen.getAllByText('Trusted device')).toHaveLength(2)
    expect(screen.getByText('Current session')).toBeTruthy()
    expect(screen.getByText('Current device')).toBeTruthy()
    expect(screen.queryByText(/never-render/)).toBeNull()
    expect(container.querySelector('.security-management__grid')).toBeTruthy()
    expect(container.querySelectorAll('.security-management__row')).toHaveLength(4)

    const logoutButtons = screen.getAllByRole('button', { name: 'Log out' })
    expect(logoutButtons).toHaveLength(2)
    await user.click(logoutButtons[0])
    await user.click(logoutButtons[1])
    expect(mocks.logout).toHaveBeenCalledTimes(2)
    expect(mocks.logout).toHaveBeenNthCalledWith(1, mocks.navigate)
    expect(mocks.logout).toHaveBeenNthCalledWith(2, mocks.navigate)
  })

  test('keyboard cancellation keeps focus and performs no mutation', async () => {
    mocks.requestJson.mockResolvedValueOnce(listing)
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<SessionDeviceManagement />)
    const button = (await screen.findAllByRole('button', { name: 'Revoke' }))[0]
    button.focus()
    await user.keyboard('{Enter}')
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(mocks.requestJson).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(button)
  })

  test('confirmation performs exactly one correctly encoded mutation and never retries it', async () => {
    mocks.requestJson
      .mockResolvedValueOnce(listing)
      .mockResolvedValueOnce({ success: true })
      .mockResolvedValueOnce({ ...listing, sessions: listing.sessions.slice(0, 1) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<SessionDeviceManagement />)
    const sessions = await screen.findByRole('heading', { name: 'Active Sessions' })
    const section = sessions.closest('section')
    await user.click(within(section).getByRole('button', { name: 'Revoke' }))

    await screen.findByText('Session revoked.')
    expect(mocks.requestJson).toHaveBeenCalledTimes(3)
    expect(mocks.requestJson).toHaveBeenNthCalledWith(
      2,
      '/auth/security/sessions/session_other',
      { method: 'DELETE', signal: expect.any(AbortSignal) },
    )
  })

  test.each(['stale', 'not_found'])('%s response refreshes while persistent accessible feedback retains focus', async (code) => {
    mocks.requestJson
      .mockResolvedValueOnce(listing)
      .mockRejectedValueOnce(new ApiResponseError('gone', { status: 409, code }))
      .mockResolvedValueOnce({ ...listing, sessions: listing.sessions.slice(0, 1) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<SessionDeviceManagement />)
    const sessions = await screen.findByRole('heading', { name: 'Active Sessions' })
    await user.click(within(sessions.closest('section')).getByRole('button', { name: 'Revoke' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('no longer active')
    expect(document.activeElement).toBe(alert)
    await waitFor(() => expect(screen.getAllByText('Active session')).toHaveLength(1))
    expect(screen.getByRole('alert').textContent).toContain('no longer active')
    expect(mocks.requestJson).toHaveBeenCalledTimes(3)
  })

  test('device mutation uses the device endpoint and exposes errors accessibly', async () => {
    mocks.requestJson
      .mockResolvedValueOnce(listing)
      .mockRejectedValueOnce(new ApiResponseError('Service unavailable', { status: 503 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<SessionDeviceManagement />)
    const devices = await screen.findByRole('heading', { name: 'Trusted Devices' })
    await user.click(within(devices.closest('section')).getByRole('button', { name: 'Revoke' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Service unavailable')
    expect(mocks.requestJson).toHaveBeenNthCalledWith(
      2,
      '/auth/security/devices/device_other',
      { method: 'DELETE', signal: expect.any(AbortSignal) },
    )
    expect(mocks.requestJson).toHaveBeenCalledTimes(2)
  })

  test('never persists, logs, analyzes, or places sensitive values in mutation URLs', async () => {
    mocks.requestJson.mockResolvedValueOnce(listing)
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    const consoleMethods = [vi.spyOn(console, 'log'), vi.spyOn(console, 'warn'), vi.spyOn(console, 'error')]
    const analytics = vi.fn()
    window.analytics = { track: analytics }
    render(<SessionDeviceManagement />)
    await screen.findByText('Active Sessions')
    expect(storage).not.toHaveBeenCalled()
    expect(analytics).not.toHaveBeenCalled()
    for (const method of consoleMethods) expect(method).not.toHaveBeenCalled()
    expect(mocks.requestJson.mock.calls.flat().join(' ')).not.toContain('never-render')
    delete window.analytics
  })

  test('unmount aborts a pending load and causes no post-unmount state update', async () => {
    const pending = deferred()
    mocks.requestJson.mockReturnValueOnce(pending.promise)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = render(<SessionDeviceManagement />)
    await waitFor(() => expect(mocks.requestJson).toHaveBeenCalledOnce())
    const signal = mocks.requestJson.mock.calls[0][1].signal
    unmount()
    expect(signal.aborted).toBe(true)
    pending.resolve(listing)
    await Promise.resolve()
    await Promise.resolve()
    expect(consoleError).not.toHaveBeenCalled()
  })
})


test('pending confirmation suppresses repeated and other-row submissions until completion', async () => {
  const pending = deferred()
  mocks.requestJson.mockResolvedValueOnce(listing).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(listing)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const user = userEvent.setup()
  render(<SessionDeviceManagement />)
  const buttons = await screen.findAllByRole('button', { name: 'Revoke' })
  await user.dblClick(buttons[0])
  await user.click(buttons[1])
  expect(window.confirm).toHaveBeenCalledOnce()
  expect(mocks.requestJson.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(1)
  expect(buttons.every((button) => button.disabled)).toBe(true)
  await act(async () => pending.resolve({ success: true }))
  const status = await screen.findByText('Session revoked.')
  await waitFor(() => expect(document.activeElement).toBe(status))
})

test('pending mutation is aborted on unmount and cannot reload or navigate afterwards', async () => {
  const pending = deferred()
  mocks.requestJson.mockResolvedValueOnce(listing).mockReturnValueOnce(pending.promise)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const user = userEvent.setup()
  const { unmount } = render(<SessionDeviceManagement />)
  await user.click((await screen.findAllByRole('button', { name: 'Revoke' }))[0])
  const signal = mocks.requestJson.mock.calls[1][1].signal
  unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => pending.resolve({ success: true }))
  expect(mocks.requestJson).toHaveBeenCalledTimes(2)
  expect(mocks.navigate).not.toHaveBeenCalled()
})

test('keyboard confirmation focuses error feedback and does not retry a failed mutation', async () => {
  mocks.requestJson.mockResolvedValueOnce(listing).mockRejectedValueOnce(new ApiResponseError('Unable to revoke', { status: 503 }))
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const user = userEvent.setup()
  render(<SessionDeviceManagement />)
  const button = (await screen.findAllByRole('button', { name: 'Revoke' }))[0]
  button.focus()
  await user.keyboard(' ')
  const alert = await screen.findByRole('alert')
  await waitFor(() => expect(document.activeElement).toBe(alert))
  expect(alert.textContent).toBe('Unable to revoke')
  expect(mocks.requestJson).toHaveBeenCalledTimes(2)
})

test('refresh failure replaces success feedback and a later action clears the error', async () => {
  mocks.requestJson.mockResolvedValueOnce(listing).mockResolvedValueOnce({ success: true }).mockRejectedValueOnce(new Error('Refresh unavailable'))
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const user = userEvent.setup()
  render(<SessionDeviceManagement />)
  await user.click((await screen.findAllByRole('button', { name: 'Revoke' }))[0])
  expect((await screen.findByRole('alert')).textContent).toBe('Refresh unavailable')
  expect(screen.queryByText('Session revoked.')).toBeNull()
  mocks.requestJson.mockResolvedValueOnce(listing)
  expect(mocks.requestJson).toHaveBeenCalledTimes(3)
  const retryButton = screen.getByRole('button', { name: 'Try again' })
  retryButton.focus()
  await user.keyboard('{Enter}')
  await screen.findByRole('heading', { name: 'Active Sessions' })
  expect(screen.queryByRole('alert')).toBeNull()
  expect(mocks.requestJson).toHaveBeenCalledTimes(4)
  expect(mocks.requestJson).toHaveBeenLastCalledWith('/auth/security/sessions', { signal: expect.any(AbortSignal) })
  expect(mocks.requestJson.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(1)
})

test('all sensitive sinks remain untouched through a confirmed mutation and reload', async () => {
  mocks.requestJson.mockResolvedValueOnce(listing).mockResolvedValueOnce({ success: true }).mockResolvedValueOnce(listing)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const user = userEvent.setup()
  const sinks = [vi.spyOn(Storage.prototype, 'setItem'), vi.spyOn(history, 'pushState'), vi.spyOn(history, 'replaceState'), vi.spyOn(console, 'log'), vi.spyOn(console, 'warn'), vi.spyOn(console, 'error')]
  const locationBefore = location.href
  render(<SessionDeviceManagement />)
  await user.click((await screen.findAllByRole('button', { name: 'Revoke' }))[0])
  await screen.findByText('Session revoked.')
  for (const sink of sinks) expect(sink).not.toHaveBeenCalled()
  expect(location.href).toBe(locationBefore)
  expect(JSON.stringify(mocks.requestJson.mock.calls)).not.toContain('never-render')
})
