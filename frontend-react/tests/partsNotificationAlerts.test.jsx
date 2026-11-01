import { cleanup, fireEvent, render, screen, waitForElementToBeRemoved } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import PartsMarketplace from '../src/pages/transporter/PartsMarketplace'
import * as clientUtils from '../src/pages/client/clientUtils'

vi.mock('../src/auth/AuthVerificationContext', () => ({
  AUTH_STATUSES: { VERIFIED: 'VERIFIED' },
  useAuthVerification: () => ({ status: 'VERIFIED', user: { id: 1, role: 'transporter' } }),
  ShellPageSkeleton: () => <div>Loading...</div>,
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('LEDGER-011: PartsMarketplace renders Notification with working onClose instead of window.alert', async () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})

  vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
    if (url === '/api/marketplace/parts') {
      return Promise.resolve({ ok: true, json: async () => ({ success: true, parts: [] }) })
    }
    if (url === '/api/trucks/my-trucks') {
      return Promise.resolve({ ok: true, json: async () => ({ success: true, trucks: [] }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({ success: true }) })
  }))

  vi.spyOn(clientUtils, 'apiSend').mockRejectedValue(new Error('The request could not be sent. Please retry.'))

  render(
    <MemoryRouter>
      <PartsMarketplace />
    </MemoryRouter>
  )

  await waitForElementToBeRemoved(() => screen.queryByText('Preparing the parts catalogue'))

  // Open "Request a Missing Part" modal
  const rfqBtn = screen.getByRole('button', { name: /Request a Missing Part/i })
  fireEvent.click(rfqBtn)

  // Fill in required part name
  const partInput = screen.getByPlaceholderText(/Hino 500 radiator hose/i)
  fireEvent.change(partInput, { target: { value: 'Brake booster valve' } })

  // Submit RFQ form
  const submitBtn = screen.getByRole('button', { name: /Send Request/i })
  fireEvent.click(submitBtn)

  // Assert window.alert was NOT called
  expect(alertSpy).not.toHaveBeenCalled()

  // Assert Notification is shown
  const notif = await screen.findByText('The request could not be sent. Please retry.')
  expect(notif).toBeTruthy()

  // Close notification
  const closeBtn = screen.getByRole('button', { name: 'Close notification' })
  fireEvent.click(closeBtn)

  // Notification is dismissed
  expect(screen.queryByText('The request could not be sent. Please retry.')).toBeNull()
})
