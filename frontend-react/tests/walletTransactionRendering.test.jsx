import React from 'react'
import { cleanup, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'
import AcHistory from '../src/pages/transporter/ac_history'
import WalletWorkspace from '../src/components/wallet/WalletWorkspace'
import NotificationBell from '../src/components/common/NotificationBell'
import { useApi } from '../src/hooks/useApi'

const json = body => new Response(JSON.stringify(body), { status: 200 })
const transactions = [
  { id: 1, type: 'topup', amount: 100, description: 'Wallet credit' },
  { id: 2, type: 'agreement_payment_paid', amount: -30, description: 'Monthly debit' },
  { id: 3, type: 'payout', amount: -5, description: 'Payout debit' },
  { id: 4, type: 'lock', amount: 40, description: 'Deposit reservation' },
  { id: 5, type: 'unlock', amount: 10, description: 'Deposit release' },
]

beforeEach(() => {
  sessionStorage.clear()
  clearCachedCsrfToken()
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('history uses signed movements, excludes reservations from totals/filters and labels loaded coverage', async () => {
  fetch.mockImplementation(async () => json({ success: true, transactions, total: 120 }))
  render(<MemoryRouter><AcHistory /></MemoryRouter>)
  await screen.findByText('Monthly debit')
  expect(screen.getByText('Total Credits').parentElement.textContent).toContain('PKR 100')
  expect(screen.getByText('Total Debits').parentElement.textContent).toContain('PKR 35')
  expect(screen.getByText('Net Movement').parentElement.textContent).toContain('PKR 65')
  expect(screen.getByText(/Showing the latest 5 of 120 transactions/)).toBeTruthy()
  expect(screen.getByText('- PKR 30')).toBeTruthy()
  expect(screen.getByText('PKR 40 (reserved)')).toBeTruthy()
  expect(screen.getByText('PKR 10 (released)')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Credits' }))
  expect(screen.getByText('Wallet credit')).toBeTruthy()
  expect(screen.queryByText('Monthly debit')).toBeNull()
  expect(screen.queryByText('Deposit reservation')).toBeNull()
  expect(screen.queryByText('Deposit release')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Debits' }))
  expect(screen.getByText('Monthly debit')).toBeTruthy()
  expect(screen.getByText('Payout debit')).toBeTruthy()
  expect(screen.queryByText('Wallet credit')).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
})

test('wallet shows one debit sign and identifies reservations without an income sign', async () => {
  fetch.mockImplementation(async url => json(url.includes('transactions')
    ? { success: true, transactions }
    : { success: true, wallet: { balance: 100, available_balance: 60, locked_balance: 40, minimum_required: 0, is_minimum_met: true } }))
  render(<MemoryRouter><AuthVerificationProvider value={{ status: AUTH_STATUSES.VERIFIED, user: { id: 7 } }}>
    <WalletWorkspace />
  </AuthVerificationProvider></MemoryRouter>)
  const debit = (await screen.findByText('Agreement Payment Paid')).closest('tr')
  expect(within(debit).getAllByRole('cell')[2].textContent).toBe('-PKR 30')
  const payout = screen.getByText('Payout').closest('tr')
  expect(within(payout).getAllByRole('cell')[2].textContent).toBe('-PKR 5')
  const lock = screen.getByText('Lock').closest('tr')
  expect(within(lock).getAllByRole('cell')[2].textContent).toBe('PKR 40 (reserved)')
})

test('general notifications omit empty order metadata while order notifications retain it', async () => {
  fetch.mockResolvedValue(json({ success: true, unread_count: 0, notifications: [
    { id: 1, order_id: null, message: 'Withdrawal approved', is_read: true, created_at: new Date().toISOString() },
    { id: 2, order_id: 42, message: 'Trip completed', is_read: true, created_at: new Date().toISOString() },
  ] }))
  render(<MemoryRouter><NotificationBell /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Notifications' }))
  const generic = await screen.findByRole('button', { name: /Withdrawal approved/ })
  expect(generic.textContent).not.toContain('Order #')
  expect(screen.getByRole('button', { name: /Trip completed/ }).textContent).toContain('Order #42')
})

test('the stable API client reads the current CSRF token on each mutation', async () => {
  fetch.mockImplementation(async () => json({ success: true }))
  const { result, rerender } = renderHook(() => useApi())
  const client = result.current
  rerender()
  expect(result.current).toBe(client)
  sessionStorage.setItem('csrf_token', 'first')
  await client.post('/api/example', {})
  sessionStorage.setItem('csrf_token', 'rotated')
  await result.current.post('/api/example', {})
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBe('first')
  expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe('rotated')
})
