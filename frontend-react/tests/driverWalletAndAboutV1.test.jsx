import React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DriverWallet from '../src/pages/driver/DriverWallet'
import About from '../src/pages/transporter/about'

vi.mock('../src/auth/AuthVerificationContext', () => ({
  AUTH_STATUSES: { VERIFIED: 'verified' },
  ShellPageSkeleton: () => <div>Loading shell</div>,
  useAuthVerification: () => ({
    status: 'verified',
    user: { id: 77, role: 'driver', name: 'Test Driver' },
  }),
}))

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Digi_TransX V1 DriverWallet and About contract fixes', () => {
  it('LEDGER-013: DriverWallet fetches canonical /api/wallet and never calls absent balance/withdraw routes', async () => {
    const calls = []
    fetch.mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : input.url
      calls.push(url)
      if (url === '/api/wallet') {
        return json({
          success: true,
          wallet: {
            id: 12,
            balance: 18500,
            available_balance: 8500,
            locked_balance: 10000,
            minimum_required: 10000,
            role: 'driver',
          },
        })
      }
      throw new Error(`Unexpected endpoint call: ${url}`)
    })

    render(<DriverWallet />)

    await waitFor(() => {
      expect(screen.getByText(/^PKR 8,500$/)).toBeTruthy()
    })
    expect(screen.getByText(/Total ledger balance:\s*PKR 18,500/)).toBeTruthy()
    expect(screen.getByText(/Frozen wallet funds:\s*PKR 10,000/)).toBeTruthy()
    expect(screen.getByText(/Payouts unavailable in V1 private testing/i)).toBeTruthy()
    expect(calls).toContain('/api/wallet')
    expect(calls.some((u) => u.includes('/api/wallet/balance') || u.includes('/api/wallet/withdraw'))).toBe(false)
  })

  it('LEDGER-015: About page renders maintained static V1 content without calling absent /api/about routes', () => {
    render(<About />)
    expect(screen.getByText(/About Digi_TransX/i)).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
  })
})
