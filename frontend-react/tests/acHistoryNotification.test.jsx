// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import AcHistory from '../src/pages/transporter/ac_history'

vi.mock('../src/hooks/useApi', () => {
  const api = {
    get: vi.fn().mockImplementation((url) => {
      if (url.includes('/api/wallet/transactions')) {
        return Promise.resolve({ transactions: [] })
      }
      return Promise.resolve({})
    }),
  }
  return { useApi: () => api }
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('LEDGER-010: AcHistory renders standard Notification and dismisses on close', async () => {
  render(
    <MemoryRouter>
      <AcHistory />
    </MemoryRouter>
  )

  // Find Apply button in filters
  const applyBtn = await screen.findByRole('button', { name: /Apply/i })
  expect(applyBtn).toBeTruthy()

  // Click Apply to trigger showToast('Filters applied')
  fireEvent.click(applyBtn)

  // Standard Notification component should be visible
  const notification = screen.getByRole('status')
  expect(notification).toBeTruthy()
  expect(notification.className).toContain('app-notification')
  expect(notification.textContent).toContain('Filters applied')

  // Click close button on notification
  const closeBtn = screen.getByRole('button', { name: 'Close notification' })
  fireEvent.click(closeBtn)

  // Notification should be dismissed
  expect(screen.queryByRole('status')).toBeNull()
})
