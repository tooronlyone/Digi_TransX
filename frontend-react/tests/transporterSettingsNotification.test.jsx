// @vitest-environment jsdom
import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Settings from '../src/pages/transporter/settings'

const owner = { id: 903, role: 'logistics_provider', email: 'settings@example.test', full_name: 'Settings Fixture' }

beforeEach(() => {
  sessionStorage.clear()
  window.__BOOTSTRAP__ = { auth: { status: 'unlocked', user: owner, fresh_until: new Date(Date.now() + 60000).toISOString(), verified_at: new Date().toISOString() } }
  window.AuthSession = { user: owner }
  sessionStorage.setItem('user', JSON.stringify(owner))
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() =>
    Promise.resolve(new Response(JSON.stringify({ success: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  ))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete window.__BOOTSTRAP__
  delete window.AuthSession
})

test('Settings displays Notification on user action and dismisses on close button click', async () => {
  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>
  )

  // Switch to advanced section
  const advancedTab = screen.getByRole('link', { name: /Advanced/i })
  await user.click(advancedTab)

  // Click "Clear Cache" button which calls showToast('Cache cleared!')
  const clearCacheBtn = screen.getByRole('button', { name: /Clear Cache/i })
  await user.click(clearCacheBtn)

  // Expect standard Notification component
  const notification = screen.getByRole('status')
  expect(notification).toBeTruthy()
  expect(notification.className).toContain('app-notification')
  expect(notification.textContent).toContain('Cache cleared!')

  // Click close button on Notification
  const closeBtn = screen.getByRole('button', { name: /Close notification/i })
  await user.click(closeBtn)

  // Notification should be dismissed
  expect(screen.queryByRole('status')).toBeNull()
})
