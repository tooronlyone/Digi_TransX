// @vitest-environment jsdom
import React from 'react'
import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'
import { checkoutAttempt, checkoutParts } from '../src/pages/transporter/marketplaceApi'
import ShopkeeperPartsOrders from '../src/pages/shopkeeper/ShopkeeperPartsOrders'
import PartsMarketplace from '../src/pages/transporter/PartsMarketplace'
import PartsCartPage from '../src/pages/transporter/PartsCartPage'
import PartsOrdersPage from '../src/pages/transporter/PartsOrdersPage'
import FuelDispensePOS from '../src/pages/fuelstation/FuelDispensePOS'

vi.mock('../src/components/fuelstation/FuelStationLayout', () => ({ default: ({ children }) => <div>{children}</div> }))
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const account = { id: 501, role: 'logistics_provider' }
function wrapped(child, user = account) {
  return <MemoryRouter><AuthVerificationProvider value={{ status: AUTH_STATUSES.VERIFIED, user }}>{child}</AuthVerificationProvider></MemoryRouter>
}
const payload = { items: [{ part_id: 1, quantity: 1 }], delivery_type: 'delivery', delivery_address: 'Private workshop address', payment_method: 'wallet_escrow' }
function mutations() { return fetch.mock.calls.filter(([, options]) => options?.method === 'POST') }
function assertCsrf() {
  for (const [, options] of mutations()) expect(options.headers['X-CSRF-Token']).toBe('market-csrf')
}
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear(); clearCachedCsrfToken()
  sessionStorage.setItem('csrf_token', 'market-csrf')
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  vi.stubGlobal('fetch', vi.fn())
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('checkout reuses its key after uncertain failure, isolates accounts/payloads, and never persists addresses', async () => {
  fetch.mockRejectedValueOnce(new TypeError('Connection interrupted'))
  await expect(checkoutParts(payload, account.id)).rejects.toThrow('Connection interrupted')
  const first = mutations()[0][1].headers['Idempotency-Key']
  fetch.mockResolvedValue(json({ success: true, order: { id: 1 } }, 201))
  await checkoutParts(payload, account.id)
  expect(mutations()[1][1].headers['Idempotency-Key']).toBe(first)
  assertCsrf()
  const attempt = await checkoutAttempt(payload, account.id)
  expect(attempt.key).not.toBe(first)
  expect((await checkoutAttempt({ ...payload, items: [{ part_id: 1, quantity: 2 }] }, account.id)).key).not.toBe(attempt.key)
  expect((await checkoutAttempt(payload, 999)).key).not.toBe(attempt.key)
  expect(JSON.stringify({ ...sessionStorage })).not.toContain('Private workshop address')
})

test('cart checkout uses CSRF and idempotency through the real rendered handler', async () => {
  localStorage.setItem(`dtx:parts-cart:v2:${account.id}`, JSON.stringify([{ id: 1, title: 'Tyre', price: 500, qty: 1 }]))
  fetch.mockResolvedValue(json({ success: true, order: { id: 2, order_number: 'ORDER2' } }, 201))
  render(wrapped(<PartsCartPage />))
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('Enter workshop address or roadside location'), 'Workshop')
  await user.click(screen.getByRole('button', { name: /Confirm & Pay/ }))
  await waitFor(() => expect(mutations()).toHaveLength(1))
  assertCsrf()
  expect(mutations()[0][1].headers['Idempotency-Key']).toBeTruthy()
  expect(mutations()[0][1].headers['X-DTX-Expected-User-Id']).toBe(String(account.id))
  expect(JSON.parse(mutations()[0][1].body).items).toEqual([{ part_id: 1, quantity: 1 }])
})

test('buyer RFQ posts through the shared CSRF transport', async () => {
  fetch.mockImplementation(async (url, options) => options?.method === 'POST'
    ? json({ success: true }) : json(url === '/api/trucks' ? { success: true, trucks: [] } : { success: true, parts: [] }))
  render(wrapped(<PartsMarketplace />))
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Request a Missing Part' }))
  await user.type(screen.getByPlaceholderText('e.g. Hino 500 radiator hose or front shock absorber'), 'Radiator')
  await user.click(screen.getByRole('button', { name: 'Send Request' }))
  expect(await screen.findByText('Request sent successfully')).toBeTruthy()
  expect(mutations()[0][0]).toBe('/api/marketplace/rfq')
  assertCsrf()
})

test('seller status and six-digit handoff verification carry CSRF and respect delivery phases', async () => {
  let status = 'placed'
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') {
      if (url.endsWith('/status')) status = JSON.parse(options.body).status
      return json({ success: true, message: 'Delivery verified' })
    }
    return json({ success: true, orders: [{ id: 44, order_number: 'FOUR', fulfillment_status: status, delivery_type: 'delivery', net_total: 500, items: [], created_at: '2026-10-24' }] })
  })
  render(wrapped(<ShopkeeperPartsOrders />, { id: 601, role: 'shopkeeper' }))
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Confirm & Pack' }))
  expect(screen.queryByRole('button', { name: 'Verify OTP & Claim Funds' })).toBeNull()
  await user.click(await screen.findByRole('button', { name: 'Dispatch with Rider' }))
  await user.click(await screen.findByRole('button', { name: 'Verify OTP & Claim Funds' }))
  await user.type(screen.getByPlaceholderText('6-digit handoff code'), '123456')
  await user.click(screen.getByRole('button', { name: 'Verify OTP & Release Funds' }))
  await waitFor(() => expect(mutations()).toHaveLength(3))
  expect(JSON.parse(mutations()[2][1].body)).toEqual({ otp: '123456' })
  assertCsrf()
})

test('seller catalog creation and RFQ quote both use the shared CSRF transport', async () => {
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') return json({ success: true })
    if (url.endsWith('/rfq')) return json({ success: true, rfqs: [{ id: 7, part_name: 'Brake pads' }] })
    return json({ success: true, orders: [], parts: [] })
  })
  render(wrapped(<ShopkeeperPartsOrders />, { id: 602, role: 'shopkeeper' }))
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /Listed Parts/ }))
  await user.click(await screen.findByRole('button', { name: 'Add New Part / Tyre' }))
  await user.type(screen.getByPlaceholderText('e.g. Dunlop 11R22.5 SP320 Heavy Truck Tyre'), 'New tyre')
  const price = screen.getByText('Price (PKR) *').parentElement.querySelector('input')
  fireEvent.change(price, { target: { value: '500' } })
  await user.click(screen.getByRole('button', { name: 'Save and Publish Part' }))
  await waitFor(() => expect(mutations()).toHaveLength(1))
  await user.click(screen.getByRole('button', { name: /RFQs Broadcast/ }))
  await user.click(await screen.findByRole('button', { name: 'Submit Price Quote' }))
  await user.type(screen.getByPlaceholderText('e.g. 18500'), '550')
  await user.click(screen.getByRole('button', { name: 'Send Quote to Transporter' }))
  await waitFor(() => expect(mutations()).toHaveLength(2))
  expect(mutations().map(([url]) => url)).toEqual(['/api/marketplace/shop/parts', '/api/marketplace/rfq/7/bid'])
  assertCsrf()
})

test('buyer handoff code is obtained on demand and cleared on account switch', async () => {
  fetch.mockImplementation(async (url, options) => options?.method === 'POST'
    ? json({ success: true, delivery_otp: '908172', expires_at: new Date(Date.now() + 1200000).toISOString() })
    : json({ success: true, orders: [{ id: 77, order_number: 'SEVEN', fulfillment_status: 'dispatched', delivery_type: 'delivery', items: [] }] }))
  const view = render(wrapped(<PartsOrdersPage />))
  await userEvent.click(await screen.findByRole('button', { name: /SEVEN/ }))
  expect(screen.queryByText('908172')).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Request handoff code' }))
  expect(await screen.findByText('908172')).toBeTruthy()
  assertCsrf()
  expect(mutations()[0][0]).toBe('/api/marketplace/orders/77/delivery-otp')
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('908172')
  view.rerender(wrapped(<PartsOrdersPage />, { id: 777, role: 'logistics_provider' }))
  expect(screen.queryByText('908172')).toBeNull()
})

test('fuel dispense requires active stock, uses readonly pump pricing, and refreshes stock after success', async () => {
  let stock = 10
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') {
      stock = 7
      return json({ success: true, receipt: { id: 1, liters: 3, price_per_liter: 280, total_pkr: 840, payment_method: 'cash' } })
    }
    return json({ success: true, pumps: [
      { id: 1, pump_number: 'Active pump', status: 'active', price_per_liter: 280, current_stock_liters: stock, fuel_type_label: 'Diesel' },
      { id: 2, pump_number: 'Inactive pump', status: 'inactive', price_per_liter: 1, current_stock_liters: 999, fuel_type_label: 'Diesel' },
    ] })
  })
  render(wrapped(<FuelDispensePOS />, { id: 800, role: 'fuel_station_manager' }))
  const rate = await screen.findByRole('spinbutton', { name: 'Stored pump rate per liter' })
  await waitFor(() => expect(rate.value).toBe('280'))
  expect(rate.readOnly).toBe(true)
  expect(screen.queryByRole('option', { name: /Inactive pump/ })).toBeNull()
  expect(screen.queryByRole('option', { name: /Wallet|Voucher/ })).toBeNull()
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('e.g. LES-4921, KHI-8832'), 'TEST-123')
  await user.type(screen.getByPlaceholderText('e.g. 150'), '3')
  await user.click(screen.getByRole('button', { name: 'Dispense Fuel & Print Receipt' }))
  expect(await screen.findByText('Fuel successfully dispensed and logged!')).toBeTruthy()
  await waitFor(() => expect(screen.getByRole('option', { name: /Active pump/ }).textContent).toContain('Stock: 7 L'))
  const body = JSON.parse(mutations()[0][1].body)
  expect(body).toMatchObject({ pump_id: 1, liters: 3, payment_method: 'cash' })
  expect(body).not.toHaveProperty('price_per_liter')
  expect(body).not.toHaveProperty('fuel_type')
  assertCsrf()
})

test('zero pump stock remains zero and cannot create an untracked manual sale', async () => {
  fetch.mockResolvedValue(json({ success: true, pumps: [{ id: 1, pump_number: 'Empty', status: 'active', price_per_liter: 280, current_stock_liters: 0 }] }))
  render(wrapped(<FuelDispensePOS />, { id: 800, role: 'fuel_station_manager' }))
  expect(await screen.findByRole('option', { name: /Stock: 0 L/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Dispense Fuel & Print Receipt' }).disabled).toBe(true)
  expect(mutations()).toHaveLength(0)
})
