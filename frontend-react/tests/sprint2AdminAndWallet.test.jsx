import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AdminStepUpModal from '../src/components/admin/AdminStepUpModal'
import { adminRequest } from '../src/pages/admin/adminApi'
import AdminUsers from '../src/pages/admin/AdminUsers'
import Earning from '../src/pages/transporter/earning'

vi.mock('../src/components/security/StepUpProvider', () => ({
  useStepUp: () => ({
    protectedFetch: (url, options) => fetch(url, options),
  }),
}))

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('Sprint 2 Security Frontend Remediation', () => {
  it('V1-SEC-006: adminRequest prompts AdminStepUpModal on 428 and retries with X-Admin-Step-Up-Proof', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({ csrf_token: 'csrf-1' }),
      })
      .mockResolvedValueOnce({
        status: 428,
        ok: false,
        clone() {
          return this
        },
        json: async () => ({
          success: false,
          code: 'admin_step_up_required',
          message: 'Fresh administrator reauthentication is required for this action.',
          action: {
            action_key: 'admin.withdrawal.approve',
            resource_type: 'withdrawal_request',
            resource_id: 5,
            label: 'Approve wallet withdrawal request',
            request_fingerprint: 'a'.repeat(64),
          },
        }),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
          success: true,
          step_up_proof: 'proof-token-5',
          action: { action_key: 'admin.withdrawal.approve', resource_id: 5 },
        }),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({ success: true, simulated: true }),
      })

    vi.stubGlobal('fetch', fetchMock)

    render(<AdminStepUpModal />)

    const pendingPromise = adminRequest('/api/admin/wallet/withdrawals/5/approve', {
      method: 'POST',
      body: JSON.stringify({}),
    })

    const dialog = await screen.findByRole('dialog')
    expect(dialog.textContent).toContain('Approve wallet withdrawal request')
    expect(dialog.textContent).toContain('withdrawal_request #5')

    const passwordInput = screen.getByPlaceholderText(/Enter your password/i)
    fireEvent.change(passwordInput, { target: { value: 'StrongAdminPass123!' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirm & Continue/i }))

    const result = await pendingPromise
    expect(result.success).toBe(true)

    const retryCall = fetchMock.mock.calls[3]
    expect(retryCall[0]).toBe('/api/admin/wallet/withdrawals/5/approve')
    expect(retryCall[1].headers['X-Admin-Step-Up-Proof']).toBe('proof-token-5')
    expect(retryCall[1].headers['X-CSRF-Token']).toBe('csrf-1')
  })

  it('V1-SEC-006: AdminUsers enforces 12-128 character administrator password guidance', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true, users: [], page: 1, page_size: 20, total: 0 }),
      })
    )

    render(
      <MemoryRouter>
        <AdminUsers />
      </MemoryRouter>
    )

    fireEvent.click(await screen.findByRole('button', { name: /Create Admin/i }))
    const pwInput = screen.getByPlaceholderText(/Password \(12\+ chars/i)
    expect(pwInput.minLength).toBe(12)
    expect(pwInput.maxLength).toBe(128)
    expect(screen.getByText(/12-128 characters/i)).toBeTruthy()
  })

  it('V1-SEC-010: Earning limit upgrade sends a stable Idempotency-Key header per confirmation', async () => {
    const fetchMock = vi.fn(async (url) => {
      if (url === '/api/wallet/earnings-summary') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            wallet: {
              balance: 250000,
              locked_balance: 50000,
              available_balance: 200000,
              pending_withdrawal_total: 0,
            },
            transactions: [],
            withdrawals: [],
            escrow_orders: [],
          }),
        }
      }
      if (url === '/api/wallet/withdrawal-limits') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            active_tier: 0,
            limits: { single_max: 25000, daily_max: 25000 },
            withdrawn_24h: 0,
            pending_withdrawal_total: 0,
            all_tiers: {
              1: { single_max: 100000, daily_max: 200000, fee_3yr: 5000, fee_5yr: 8000 },
            },
          }),
        }
      }
      if (url === '/api/wallet/payout-card') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ success: true, has_card: true, card: { bank_name: 'HBL', last4: '1234', masked: '****1234', cardholder_name: 'Test', expiry: '12/28' } }),
        }
      }
      if (url === '/auth/csrf-token') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ csrf_token: 'csrf-wallet' }),
        }
      }
      if (url === '/api/wallet/upgrade-limit') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ success: true, message: 'Upgraded to Tier 1.' }),
        }
      }
      return { ok: true, status: 200, json: async () => ({ success: true }) }
    })

    vi.stubGlobal('fetch', fetchMock)

    render(<Earning />)

    const buyButton = await screen.findByRole('button', { name: /Buy 3yr/i })
    fireEvent.click(buyButton)

    const confirmButton = await screen.findByRole('button', { name: /Confirm - Pay/i })
    fireEvent.click(confirmButton)

    await waitFor(() => {
      const upgradeCall = fetchMock.mock.calls.find(([callUrl]) => callUrl === '/api/wallet/upgrade-limit')
      expect(upgradeCall).toBeTruthy()
      expect(upgradeCall[1].headers['Idempotency-Key']).toBeTruthy()
    })
  })
})
