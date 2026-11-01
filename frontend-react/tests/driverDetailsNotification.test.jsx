import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import DriverDetails from '../src/pages/auth/roledetails/DriverDetails'
import { SignupWizardContext } from '../src/auth/signupWizardContext'
import * as submitHelper from '../src/pages/auth/roledetails/_submitHelper'

vi.mock('../src/hooks/useAuth', () => ({
  useAuthSession: () => ({ cacheUser: vi.fn(), resolveRedirect: vi.fn() }),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('LEDGER-007: DriverDetails passes onClose to Notification allowing dismissal', async () => {
  vi.spyOn(submitHelper, 'submitSignup').mockResolvedValue({
    ok: false,
    message: 'License verification failed',
  })

  const dummyStore = { claimSubmission: vi.fn(), read: () => ({ role: 'driver' }) }

  render(
    <MemoryRouter>
      <SignupWizardContext.Provider value={{ store: dummyStore, draft: { role: 'driver' } }}>
        <DriverDetails />
      </SignupWizardContext.Provider>
    </MemoryRouter>
  )

  // Fill in required fields to pass validation
  fireEvent.change(screen.getByPlaceholderText('e.g. Lahore, Karachi, Rawalpindi'), {
    target: { value: 'Lahore' },
  })
  fireEvent.change(screen.getByPlaceholderText('e.g. LHR-HTV-98214'), {
    target: { value: 'LHR-HTV-12345' },
  })

  // Submit form
  fireEvent.click(screen.getByRole('button', { name: /Complete Driver Registration/i }))

  // Notification should be visible
  expect(await screen.findByText('License verification failed')).toBeTruthy()

  // Click close button on notification
  const closeBtn = screen.getByRole('button', { name: 'Close notification' })
  fireEvent.click(closeBtn)

  // Notification should be dismissed
  expect(screen.queryByText('License verification failed')).toBeNull()
})
