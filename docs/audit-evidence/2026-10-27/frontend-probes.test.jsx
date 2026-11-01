// Evidence counterexamples: passing tests demonstrate existing bugs.
// Copy to frontend-react/tests/auditReview20261027.test.jsx, run Vitest on that
// single file, then remove the temporary copy. Imports are relative to tests/.
import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import POSPage from '../src/pages/shopkeeper/POSPage'
import FuelVoucherPanel from '../src/components/business/FuelVoucherPanel'
import { AuthVerificationProvider, AUTH_STATUSES } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'

vi.mock('../src/components/security/StepUpProvider', () => ({ useStepUp: () => ({ protectedFetch: (...args) => fetch(...args) }) }))
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => {
  sessionStorage.clear(); clearCachedCsrfToken(); sessionStorage.setItem('csrf_token', 'audit-csrf')
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('FE-012: successful sale and failed receipt read permits a second sale', async () => {
  let sales = 0
  fetch.mockImplementation(async (url, options = {}) => {
    if (url === '/api/shopkeeper/products') return response({ success: true, data: [{ id: 1, name: 'Audit oil', unit: 'liter', price: '10.00', stock_quantity: 10 }] })
    if (url === '/api/shopkeeper/sales' && options.method === 'POST') {
      ++sales
      return response({ success: true, data: { sale_id: sales, total_amount: '10.00', items: [] } }, 201)
    }
    if (String(url).startsWith('/api/shopkeeper/sales/')) throw new Error('simulated receipt read failure')
    throw new Error(`Unexpected fetch: ${url}`)
  })
  render(<MemoryRouter><POSPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('Audit oil'))
  fireEvent.change(screen.getByPlaceholderText('0'), { target: { value: '10' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  await screen.findByText('We could not connect to the shop service. Please try again.')
  expect(sales).toBe(1)
  const retry = screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' })
  expect(retry.disabled).toBe(false)
  fireEvent.click(retry)
  await waitFor(() => expect(sales).toBe(2))
})

test('FE-011: adding 0.5L of available inventory submits a 1L sale', async () => {
  let submitted
  fetch.mockImplementation(async (url, options = {}) => {
    if (url === '/api/shopkeeper/products') return response({ success: true, data: [{ id: 2, name: 'Half liter', unit: 'liter', price: '10.00', stock_quantity: 0.5 }] })
    if (url === '/api/shopkeeper/sales') {
      submitted = JSON.parse(options.body)
      return response({ success: false, message: 'Only 0.5 liters remain' }, 409)
    }
    throw new Error(`Unexpected fetch: ${url}`)
  })
  render(<MemoryRouter><POSPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('Half liter'))
  fireEvent.change(screen.getByPlaceholderText('0'), { target: { value: '10' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  await waitFor(() => expect(submitted?.items).toEqual([{ product_id: 2, quantity: 1 }]))
})

test('LEDGER-023: remount loses active fuel voucher and its cancel control', async () => {
  fetch.mockResolvedValue(response({ success: true, voucher: { id: 91, status: 'authorized', max_amount: '100.00' }, otp: '12345678' }))
  const view = () => <AuthVerificationProvider value={{ user: { id: 5, role: 'transporter' }, status: AUTH_STATUSES.VERIFIED }}><FuelVoucherPanel tripId={3} truckId={4} /></AuthVerificationProvider>
  const mounted = render(view())
  fireEvent.change(screen.getByLabelText('Maximum authorized amount (PKR)'), { target: { value: '100' } })
  fireEvent.click(screen.getByRole('button', { name: 'Reserve funding & create voucher' }))
  await screen.findByRole('button', { name: 'Cancel unused authorization & release funding' })
  mounted.unmount()
  fetch.mockClear()
  render(view())
  expect(screen.queryByRole('button', { name: 'Cancel unused authorization & release funding' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Reserve funding & create voucher' }).disabled).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
})
