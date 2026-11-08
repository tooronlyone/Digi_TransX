// @vitest-environment jsdom
import React from 'react'
import { webcrypto } from 'node:crypto'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AdminDisputes from '../src/pages/admin/AdminDisputes'
import BidCheckout from '../src/pages/client/BidCheckout'
import ClientOrderDetail from '../src/pages/client/ClientOrderDetail'
import FuelDispensePOS from '../src/pages/fuelstation/FuelDispensePOS'
import TripOperationalActions from '../src/components/business/TripOperationalActions'
import { productMoney, shortfallMoney, legacyTopupPreview } from '../src/lib/exactMoney'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'
import { FeeBreakdown, InsuranceNotice, MarketReference, SettlementSummary, moneyText } from '../src/components/business/BusinessRules'
import DeliveryClientHandshake from '../src/components/business/DeliveryClientHandshake'
import FuelVoucherPanel from '../src/components/business/FuelVoucherPanel'
import FuelVoucherRedemption from '../src/components/business/FuelVoucherRedemption'
import OperationalInvestigations from '../src/components/business/OperationalInvestigations'

vi.mock('../src/components/security/StepUpProvider', () => ({ useStepUp: () => ({ protectedFetch: (...args) => fetch(...args) }) }))
vi.mock('../src/components/fuelstation/FuelStationLayout', () => ({ default: ({ children }) => <div>{children}</div> }))
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const auth = child => <AuthVerificationProvider value={{ user: { id: 77, role: 'client' }, status: AUTH_STATUSES.VERIFIED }}>{child}</AuthVerificationProvider>
beforeEach(() => {
  sessionStorage.clear(); clearCachedCsrfToken(); sessionStorage.setItem('csrf_token', 'business-csrf')
  vi.stubGlobal('fetch', vi.fn()); vi.stubGlobal('crypto', webcrypto)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('decimal formatting preserves large exact amounts without conversion to floating point', () => {
  expect(moneyText('9007199254740993.01')).toBe('PKR 9,007,199,254,740,993.01')
  expect(moneyText(null)).toBe('Unavailable')
})

test('insurance acknowledgement includes the approved notice and preserves mandatory liability', () => {
  const changed = vi.fn()
  render(<InsuranceNotice accepted={false} onChange={changed} />)
  expect(screen.getByText("Goods Insurance is recommended. Uninsured cargo is transported at shipper's own risk.")).toBeTruthy()
  expect(screen.getByText(/mandatory legal obligations/)).toBeTruthy()
  fireEvent.click(screen.getByRole('checkbox'))
  expect(changed).toHaveBeenCalledWith(true)
})

test('first bid market bootstrap displays an awaiting state without fabricated bounds', async () => {
  fetch.mockResolvedValue(response({ market_average: null, bootstrap: true, minimum_bid: null, maximum_bid: null }))
  render(<MarketReference orderId={11} showRange />)
  await screen.findByText('Market Average Rate: Awaiting first eligible bid')
  expect(screen.queryByText(/Your permitted bid range/)).toBeNull()
})

test('market reference uses server corridor and rejects a late response after truck change', async () => {
  let resolveOld
  fetch.mockImplementation(url => url.includes('truck_id=1') ? new Promise(resolve => { resolveOld = resolve }) : Promise.resolve(response({ market_average: '55000.00', minimum_bid: '44000.00', maximum_bid: '77000.00' })))
  const view = render(<MarketReference orderId={11} truckId={1} showRange />)
  view.rerender(<MarketReference orderId={11} truckId={2} showRange />)
  await screen.findByText('Your permitted bid range: PKR 44,000.00 – PKR 77,000.00')
  await act(async () => resolveOld(response({ market_average: '1.00' })))
  expect(screen.queryByText('Market Average Rate: PKR 1.00')).toBeNull()
})

test('invoice displays every server fee item and exact total without recalculation', () => {
  render(<FeeBreakdown snapshot={{ total_fee: '20000.01', net_amount: '80000.04', components: [
    { code: 'core', label: 'Digi_TransX Core Platform & Software Licensing Fee', percentage: '10', amount: '10000.01' },
    { code: 'gps', label: 'Live Satellite GPS Tracking & Fleet Security Services', percentage: '5', amount: '5000.00' },
    { code: 'wallet', label: 'Digital Payment Gateway & Secure Wallet Processing', percentage: '3', amount: '3000.00' },
    { code: 'escrow', label: 'Escrow Guarantee & Dispute Protection Fund', percentage: '2', amount: '2000.00' },
  ] }} />)
  expect(screen.getByText('Total Platform Deductions: PKR 20,000.01')).toBeTruthy()
  expect(screen.getByText(/Software Licensing Fee \(10%\)/)).toBeTruthy()
  expect(screen.getByText(/GPS Tracking.*\(5%\)/)).toBeTruthy()
  expect(screen.getByText(/Wallet Processing \(3%\)/)).toBeTruthy()
  expect(screen.getByText(/Dispute Protection Fund \(2%\)/)).toBeTruthy()
  expect(fetch).not.toHaveBeenCalled()
})

test('fuel zero commission schedule is loaded from the authoritative server', async () => {
  fetch.mockResolvedValue(response({ fuel: { percentage: '0', components: [] } }))
  render(<FeeBreakdown kind="fuel" />)
  await screen.findByText('Platform commission: 0%')
  expect(fetch.mock.calls[0][0]).toBe('/api/business-rules/fees')
})

test('delivery OTP remains hidden until client protected reveal succeeds and is never persisted', async () => {
  fetch.mockResolvedValue(response({ otp: '12345678', expires_at: '2026-10-26T12:10:00Z' }))
  render(auth(<DeliveryClientHandshake orderId={11} trip={{ id: 5, status: 'awaiting_client_confirmation' }} />))
  expect(screen.queryByText('12345678')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /reveal delivery OTP/ }))
  await screen.findByText('12345678')
  expect(fetch.mock.calls[0][0]).toBe('/api/orders/11/trips/5/delivery-otp')
  expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBe('business-csrf')
  expect([...Array(sessionStorage.length)].map((_, i) => sessionStorage.getItem(sessionStorage.key(i))).join()).not.toContain('12345678')
})

test('new client account cannot retain a delivery code from a previous account', async () => {
  fetch.mockResolvedValue(response({ otp: '12345678', expires_at: '2026-10-26T12:10:00Z' }))
  const view = render(auth(<DeliveryClientHandshake orderId={11} trip={{ id: 5, status: 'awaiting_client_confirmation' }} />))
  fireEvent.click(screen.getByRole('button', { name: /reveal delivery OTP/ }))
  await screen.findByText('12345678')
  view.rerender(<AuthVerificationProvider value={{ user: { id: 78, role: 'client' }, status: AUTH_STATUSES.VERIFIED }}><DeliveryClientHandshake orderId={11} trip={{ id: 5, status: 'awaiting_client_confirmation' }} /></AuthVerificationProvider>)
  expect(screen.queryByText('12345678')).toBeNull()
})

test('delivery dispute submits evidence references and displays server cutoff rejection', async () => {
  fetch.mockResolvedValue(response({ success: false, message: 'The 90-minute delivery dispute window has closed.' }, 409))
  render(auth(<DeliveryClientHandshake orderId={11} trip={{ id: 5, status: 'completed' }} settlement={{ id: 8 }} />))
  fireEvent.change(screen.getByLabelText('Dispute reason'), { target: { value: 'Seal was broken' } })
  fireEvent.change(screen.getByLabelText(/Evidence references/), { target: { value: 'handoff:11\nphoto:22' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit delivery dispute' }))
  await screen.findByRole('alert')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ reason: 'Seal was broken', evidence: ['handoff:11', 'photo:22'] })
  expect(screen.getByText('The 90-minute delivery dispute window has closed.')).toBeTruthy()
})

test('fuel authorization sends capped exact decimal strings and reuses idempotency key after network failure', async () => {
  fetch.mockRejectedValueOnce(new Error('Network disconnected')).mockResolvedValueOnce(response({ voucher: { id: 9, max_amount: '25000.01' }, otp: 'secure-code' }))
  render(<AuthVerificationProvider value={{ user: { id: 77, role: 'transporter' }, status: AUTH_STATUSES.VERIFIED }}><FuelVoucherPanel tripId={5} truckId={8} /></AuthVerificationProvider>)
  fireEvent.change(screen.getByLabelText('Maximum authorized amount (PKR)'), { target: { value: '25000.01' } })
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText('Network disconnected')
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText('secure-code')
  const calls = fetch.mock.calls
  expect(calls[0][1].headers['Idempotency-Key']).toBe(calls[1][1].headers['Idempotency-Key'])
  expect(calls[0][1].headers['X-DTX-Expected-User-Id']).toBe('77')
  expect(JSON.parse(calls[1][1].body)).toEqual({ trip_id: 5, truck_id: 8, request_mode: 'amount', fuel_type: 'diesel', max_amount: '25000.01' })
})

test('fuel station cannot finalize until funding is verified and uses bound truck and pump', async () => {
  fetch.mockResolvedValueOnce(response({ voucher: { id: 9, truck_plate: 'LES-123', fuel_type: 'diesel', max_amount: '25000.00', max_liters: '100', trip_id: 5, redeemed_station_id: 4 }, redemption_token: 'single-redemption' }))
    .mockResolvedValueOnce(response({ voucher: { truck_plate: 'LES-123', actual_liters: '50.01', actual_amount: '15003.00' } }))
  render(<FuelVoucherRedemption pumps={[{ id: 2, fuel_type: 'diesel' }]} />)
  expect(screen.queryByRole('button', { name: /Finalize dispense/ })).toBeNull()
  fireEvent.change(screen.getByLabelText('Fuel Voucher OTP'), { target: { value: 'voucher-secret' } })
  fireEvent.change(screen.getByLabelText('Dispense pump'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: /Verify OTP/ }))
  await screen.findByText('Authorized digital dispense slip')
  expect(screen.getByText('4')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Actual dispensed liters'), { target: { value: '50.01' } })
  fireEvent.click(screen.getByRole('button', { name: /Finalize dispense/ }))
  await screen.findByText('Dispense finalized. Fuel Station credited.')
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ redemption_token: 'single-redemption', pump_id: '2', actual_liters: '50.01', truck_plate: 'LES-123', fuel_type: 'diesel' })
})

test('lost fuel authorization response can be retried, cancelled, and explicitly reissued with a new code', async () => {
  fetch.mockRejectedValueOnce(new Error('Authorization response lost'))
    .mockResolvedValueOnce(response({ voucher: { id: 9, status: 'authorized', max_amount: '25000.00' }, otp: null, replayed: true }))
    .mockResolvedValueOnce(response({ voucher: { id: 9, status: 'cancelled', max_amount: '25000.00' } }))
    .mockResolvedValueOnce(response({ voucher: { id: 10, status: 'authorized', max_amount: '25000.00' }, otp: 'replacement-single-use-code' }))
  render(<AuthVerificationProvider value={{ user: { id: 77, role: 'transporter' }, status: AUTH_STATUSES.VERIFIED }}><FuelVoucherPanel tripId={5} truckId={8} /></AuthVerificationProvider>)
  fireEvent.change(screen.getByLabelText('Maximum authorized amount (PKR)'), { target: { value: '25000.00' } })
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText('Authorization response lost')
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText(/The secret code is not redisplayed/)
  expect(screen.getByRole('button', { name: /Reserve funding/ }).disabled).toBe(true)
  expect(fetch.mock.calls).toHaveLength(2)
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
  fireEvent.click(screen.getByRole('button', { name: 'Cancel unused authorization & release funding' }))
  await screen.findByText(/Unused funding released/)
  const cancellation = fetch.mock.calls[2]
  expect(cancellation[0]).toBe('/api/fuel/vouchers/9/cancel')
  expect(cancellation[1].headers['X-CSRF-Token']).toBe('business-csrf')
  expect(cancellation[1].headers['X-DTX-Expected-User-Id']).toBe('77')
  expect(screen.queryByText(/Single-use Fuel Voucher OTP:/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText('replacement-single-use-code')
  expect(fetch.mock.calls[3][1].headers['Idempotency-Key']).not.toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
})

test('fuel authorization cancellation awaiting CSRF cannot dispatch from a different owner', async () => {
  let resolveCsrf
  fetch.mockImplementation(url => url === '/auth/csrf-token' ? new Promise(resolve => { resolveCsrf = resolve })
    : Promise.resolve(response({ voucher: { id: 9, status: 'authorized', max_amount: '1000.00' }, otp: 'private-owner-A-code' })))
  const owner = id => <AuthVerificationProvider value={{ user: { id, role: 'transporter' }, status: AUTH_STATUSES.VERIFIED }}><FuelVoucherPanel tripId={5} truckId={8} /></AuthVerificationProvider>
  const view = render(owner(77))
  fireEvent.change(screen.getByLabelText('Maximum authorized amount (PKR)'), { target: { value: '1000.00' } })
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  await screen.findByText('private-owner-A-code')
  sessionStorage.clear(); clearCachedCsrfToken()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel unused authorization & release funding' }))
  await waitFor(() => expect(resolveCsrf).toBeTypeOf('function'))
  expect(screen.queryByText('private-owner-A-code')).toBeNull()
  view.rerender(owner(78))
  await act(async () => resolveCsrf(response({ csrf_token: 'owner-B-csrf' })))
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/cancel'))).toHaveLength(0)
  expect(screen.getByLabelText('Maximum authorized amount (PKR)').value).toBe('')
})

test('settlement shows worker eligibility and server-provided tranche amounts', () => {
  render(<SettlementSummary settlement={{ gross_amount: '100000.00', company_fee: '20000.00', tranche1_amount: '40000.00', tranche2_amount: '40000.00', release_eligible_at: '2026-10-26T14:00:00Z', status: 'pending_release' }} />)
  expect(screen.getByText(/processed by the scheduled worker/)).toBeTruthy()
  expect(screen.getAllByText('PKR 40,000.00')).toHaveLength(2)
})


test('exact financial previews round products and gateway fees without binary currency arithmetic', () => {
  expect(productMoney('300.00', '50.01')).toBe('15003.00')
  expect(productMoney('0.50', '0.01')).toBe('0.01')
  expect(shortfallMoney('30000.00', '29999.99')).toBe('0.01')
  expect(legacyTopupPreview('123.45')).toEqual({ gross: '123.45', fee: '3.09', net: '120.36' })
})

test('fuel authorization awaiting CSRF is cancelled before dispatch on account change', async () => {
  sessionStorage.clear(); clearCachedCsrfToken()
  let releaseCsrf
  fetch.mockImplementation(url => url === '/auth/csrf-token' ? new Promise(resolve => { releaseCsrf = resolve }) : Promise.resolve(response({ success: true })))
  const owner = (id, child) => <AuthVerificationProvider value={{ user: { id, role: 'transporter' }, status: AUTH_STATUSES.VERIFIED }}>{child}</AuthVerificationProvider>
  const view = render(owner(77, <FuelVoucherPanel tripId={5} truckId={8} />))
  fireEvent.change(screen.getByLabelText('Maximum authorized amount (PKR)'), { target: { value: '25000.00' } })
  fireEvent.click(screen.getByRole('button', { name: /Reserve funding/ }))
  view.rerender(owner(78, <FuelVoucherPanel tripId={5} truckId={8} />))
  await act(async () => releaseCsrf(response({ csrf_token: 'next-csrf' })))
  expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  expect(screen.getByLabelText('Maximum authorized amount (PKR)').value).toBe('')
})

test('driver emergency reporting preserves evidence without exposing trip cancellation', async () => {
  fetch.mockResolvedValue(response({ success: true, message: 'Incident recorded for investigation.' }))
  render(<TripOperationalActions assignment={{ id: 9, status: 'in_progress' }} />)
  expect(screen.queryByRole('button', { name: 'Request trip cancellation' })).toBeNull()
  fireEvent.change(screen.getByLabelText('Incident description'), { target: { value: 'Truck stopped at unsafe location' } })
  fireEvent.change(screen.getByLabelText('Incident evidence references'), { target: { value: 'gps:77' } })
  fireEvent.click(screen.getByRole('button', { name: 'Report incident or emergency' }))
  await screen.findByText('Incident recorded for investigation.')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ assignment_id: 9, incident_type: 'emergency', description: 'Truck stopped at unsafe location', evidence: ['gps:77'] })
})

test('transporter can request policy-reviewed cancellation for its assigned trip', async () => {
  fetch.mockResolvedValue(response({ success: true, message: 'Cancellation pending policy review.' }))
  render(<TripOperationalActions transporter assignment={{ id: 9, status: 'accepted' }} />)
  fireEvent.change(screen.getByLabelText('Transporter cancellation reason'), { target: { value: 'Vehicle unavailable' } })
  fireEvent.click(screen.getByRole('button', { name: 'Request trip cancellation' }))
  await screen.findByText('Cancellation pending policy review.')
  expect(fetch.mock.calls[0][0]).toBe('/api/transporter/trips/9/cancellation-request')
})

test('full wallet escrow shortfall disables booking acceptance and removes card fallback', async () => {
  fetch.mockImplementation(url => Promise.resolve(response(url.includes('payment-quote') ? { quote: {
    client_kind: 'business', wallet_escrow_required: true, can_checkout: false, bid_amount: '100000.00', wallet_available: '99999.99', wallet_funded_amount: '0.00', wallet_shortfall: '0.01', commission_breakdown: { total_fee: '20000.00', components: [] },
  } } : { order: { id: 11 }, bids: [{ id: 2 }] })))
  render(<MemoryRouter initialEntries={['/client/order/11/bid/2/checkout']}><Routes><Route path="/client/order/:orderId/bid/:bidId/checkout" element={<BidCheckout />} /></Routes></MemoryRouter>)
  await screen.findByText('Insufficient balance. Please top up PKR 0.01 to accept this bid.')
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByRole('button', { name: 'Accept & lock PKR 100,000' }).disabled).toBe(true)
  expect(screen.queryByText('Card Details')).toBeNull()
  expect(screen.getByRole('link', { name: 'Top up wallet' }).getAttribute('href')).toBe('/client/balance')
})

test('new settlement admin resolution requires evidence and sends exact held-fund allocation', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  fetch.mockImplementation((url, options) => {
    if (options?.method === 'POST') return Promise.resolve(response({ success: true }))
    if (url === '/api/admin/disputes') return Promise.resolve(response({ disputes: [] }))
    if (url.includes('?status=open')) return Promise.resolve(response({ disputes: [{ id: 4, shipment_id: 11, trigger: 'client_no' }] }))
    return Promise.resolve(response({ dispute: { id: 4, shipment_id: 11, evidence: [{ evidence: ['photo:12'] }], settlement: { id: 8, status: 'disputed', tranche2_amount: '40000.00', fee_breakdown: { total_fee: '20000.00', components: [] } } } }))
  })
  render(<MemoryRouter><AdminDisputes /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Review →' }))
  await screen.findByLabelText('Verified investigation result')
  expect(screen.getByRole('button', { name: 'Resolve Dispute' }).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Client refund from held funds (PKR)'), { target: { value: '1234.56' } })
  fireEvent.change(screen.getByLabelText('Verified investigation result'), { target: { value: 'verified_accident' } })
  fireEvent.change(screen.getByLabelText('Decision evidence references (required, one per line)'), { target: { value: 'verified:report-12' } })
  fireEvent.change(screen.getByPlaceholderText('Admin notes (required)'), { target: { value: 'Verified incident reviewed against handoff and cargo inspection.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Resolve Dispute' }))
  await screen.findByRole('button', { name: 'Review →' })
  const post = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(post[0]).toBe('/api/admin/freight-settlements/8/resolve')
  expect(JSON.parse(post[1].body)).toEqual({ client_refund_amount: '1234.56', investigation_result: 'verified_accident', evidence: ['verified:report-12'], notes: 'Verified incident reviewed against handoff and cargo inspection.' })
})

function clientOrderView(id) {
  return <MemoryRouter initialEntries={['/client/order/11']}><AuthVerificationProvider value={{ user: { id, role: 'service_seeker' }, status: AUTH_STATUSES.VERIFIED }}><Routes><Route path="/client/order/:orderId" element={<ClientOrderDetail />} /></Routes></AuthVerificationProvider></MemoryRouter>
}

function clientOrder(notes, legacyDelivery = false) {
  return { success: true, order: { id: 11, status: legacyDelivery ? 'in_progress' : 'open', pickup_city: 'Lahore', dropoff_city: 'Karachi', notes }, bids: [],
    ...(legacyDelivery ? { trip: { id: 5, status: 'awaiting_client_confirmation' }, payment: { status: 'held', bid_amount: '1000.00' } } : {}) }
}

function stationView(id) {
  return <AuthVerificationProvider value={{ user: { id, role: 'fuel_station_manager' }, status: AUTH_STATUSES.VERIFIED }}><FuelDispensePOS /></AuthVerificationProvider>
}

const stationPumps = { success: true, pumps: [{ id: 2, pump_number: 'Verified pump', fuel_type: 'diesel', status: 'active', price_per_liter: '300.00', current_stock_liters: '100.00' }] }

test('client order account switch aborts the old read and ignores its late private result', async () => {
  let resolveOld, oldSignal, reads = 0
  fetch.mockImplementation((url, options) => {
    if (url === '/api/orders/11') {
      if (++reads === 1) { oldSignal = options.signal; return new Promise(resolve => { resolveOld = resolve }) }
      return Promise.resolve(response(clientOrder('Account B private order')))
    }
    return Promise.resolve(response({ market_average: null, bootstrap: true }))
  })
  const view = render(clientOrderView(77))
  await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
  view.rerender(clientOrderView(78))
  expect(oldSignal.aborted).toBe(true)
  await screen.findByText('Account B private order')
  await act(async () => resolveOld(response(clientOrder('Account A confidential shipment'))))
  expect(screen.queryByText('Account A confidential shipment')).toBeNull()
  expect(screen.getByText('Account B private order')).toBeTruthy()
})

test('client delivery action awaiting CSRF cannot dispatch from the next account', async () => {
  sessionStorage.clear(); clearCachedCsrfToken()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.spyOn(window, 'prompt').mockReturnValue('Verified handoff problem')
  let resolveCsrf, reads = 0
  fetch.mockImplementation(url => {
    if (url === '/auth/csrf-token') return new Promise(resolve => { resolveCsrf = resolve })
    if (url === '/api/orders/11') return Promise.resolve(response(++reads === 1 ? clientOrder('Account A', true) : clientOrder('Account B')))
    return Promise.resolve(response({ market_average: null, bootstrap: true }))
  })
  const view = render(clientOrderView(77))
  fireEvent.click(await screen.findByRole('button', { name: 'No, there is a problem' }))
  await waitFor(() => expect(resolveCsrf).toBeTypeOf('function'))
  view.rerender(clientOrderView(78))
  await screen.findByText('Account B')
  await act(async () => resolveCsrf(response({ csrf_token: 'next-account-csrf' })))
  expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
})

test('station account switch aborts voucher verification and discards its late redemption token', async () => {
  let resolveVerify, verificationSignal
  fetch.mockImplementation((url, options) => {
    if (url === '/api/fuelstation/vouchers/verify') {
      verificationSignal = options.signal
      return new Promise(resolve => { resolveVerify = resolve })
    }
    return Promise.resolve(response(stationPumps))
  })
  const view = render(stationView(800))
  await screen.findByRole('option', { name: 'Pump 2 · diesel' })
  fireEvent.change(screen.getByLabelText('Fuel Voucher OTP'), { target: { value: 'station-A-private-voucher' } })
  fireEvent.change(screen.getByLabelText('Dispense pump'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: /Verify OTP/ }))
  await waitFor(() => expect(resolveVerify).toBeTypeOf('function'))
  view.rerender(stationView(801))
  expect(verificationSignal.aborted).toBe(true)
  await act(async () => resolveVerify(response({ voucher: { id: 9, truck_plate: 'PRIVATE-A', fuel_type: 'diesel', max_amount: '1000.00', redeemed_station_id: 800 }, redemption_token: 'station-A-only-token' })))
  expect(screen.queryByText('Authorized digital dispense slip')).toBeNull()
  expect(screen.queryByText('PRIVATE-A')).toBeNull()
  expect(screen.queryByRole('button', { name: /Finalize dispense/ })).toBeNull()
  expect(screen.getByLabelText('Fuel Voucher OTP').value).toBe('')
})

test.each(['voucher', 'cash'])('station %s action awaiting CSRF is cancelled before account-switch dispatch', async mode => {
  let resolveCsrf
  fetch.mockImplementation(url => url === '/auth/csrf-token'
    ? new Promise(resolve => { resolveCsrf = resolve })
    : Promise.resolve(response(stationPumps)))
  const view = render(stationView(800))
  await screen.findByRole('option', { name: 'Pump 2 · diesel' })
  sessionStorage.clear(); clearCachedCsrfToken()
  if (mode === 'voucher') {
    fireEvent.change(screen.getByLabelText('Fuel Voucher OTP'), { target: { value: 'private-voucher-A' } })
    fireEvent.change(screen.getByLabelText('Dispense pump'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /Verify OTP/ }))
  } else {
    fireEvent.change(screen.getByPlaceholderText('e.g. LES-4921, KHI-8832'), { target: { value: 'PRIVATE-A' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. 150'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dispense Fuel & Print Receipt' }))
  }
  await waitFor(() => expect(resolveCsrf).toBeTypeOf('function'))
  view.rerender(stationView(801))
  await act(async () => resolveCsrf(response({ csrf_token: 'station-B-csrf' })))
  expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  expect(screen.getByLabelText('Fuel Voucher OTP').value).toBe('')
  expect(screen.getByPlaceholderText('e.g. LES-4921, KHI-8832').value).toBe('')
})

function investigation(id, description) {
  return { id, assignment_id: 9, truck_id: 8, trip_id: 5, incident_type: 'abandonment', description, status: 'investigating', evidence: '["gps:77","https://evidence.invalid/private-photo"]' }
}

function investigationsView(id = 77) {
  return <AuthVerificationProvider value={{ user: { id, role: 'platform_admin' }, status: AUTH_STATUSES.VERIFIED }}><OperationalInvestigations /></AuthVerificationProvider>
}

test('operational investigation requires reviewed evidence and records an explicit CSRF-backed decision without charging funds', async () => {
  let decided = false
  const item = investigation(4, 'Verified assignment and GPS evidence require review.')
  fetch.mockImplementation((url, options) => {
    if (options?.method === 'POST') { decided = true; return Promise.resolve(response({ status: 'confirmed', financial_adjustment: 'blocked_pending_approved_penalty_policy' })) }
    return Promise.resolve(response(url.startsWith('/api/admin/operational-incidents?') ? { incidents: decided ? [] : [item] } : { incident: item }))
  })
  render(investigationsView())
  fireEvent.click(await screen.findByRole('button', { name: 'Review incident #4' }))
  await screen.findByText(item.description)
  expect(screen.getByRole('button', { name: 'Confirm verified incident' }).disabled).toBe(true)
  expect(screen.getByText(/https:\/\/evidence.invalid\/private-photo/)).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url.startsWith('https://'))).toBe(false)
  fireEvent.change(screen.getByLabelText('Investigation decision evidence and notes'), { target: { value: 'GPS timestamps and authenticated handoff communications confirm the reported incident.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm verified incident' }))
  await screen.findByText(/Investigation #4 confirmed.*without an automatic financial penalty/)
  const [url, options] = fetch.mock.calls.find(([, request]) => request?.method === 'POST')
  expect(url).toBe('/api/admin/operational-incidents/4/decision')
  expect(options.headers['X-CSRF-Token']).toBe('business-csrf')
  expect(options.headers['X-DTX-Expected-User-Id']).toBe('77')
  expect(JSON.parse(options.body)).toEqual({ status: 'confirmed', decision_evidence: 'GPS timestamps and authenticated handoff communications confirm the reported incident.' })
})

test('operational investigation ignores late foreign evidence and refuses a mismatched selected-case response', async () => {
  let resolveOld, oldSignal
  const items = [investigation(1, 'Old case private evidence'), investigation(2, 'Current case evidence'), investigation(3, 'Foreign case')]
  fetch.mockImplementation((url, options) => {
    if (url.startsWith('/api/admin/operational-incidents?')) return Promise.resolve(response({ incidents: items }))
    if (url === '/api/operational-incidents/1') { oldSignal = options.signal; return new Promise(resolve => { resolveOld = resolve }) }
    return Promise.resolve(response({ incident: url.endsWith('/2') ? items[1] : items[0] }))
  })
  render(investigationsView())
  fireEvent.click(await screen.findByRole('button', { name: 'Review incident #1' }))
  await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
  fireEvent.click(screen.getByRole('button', { name: 'Review incident #2' }))
  expect(oldSignal.aborted).toBe(true)
  await screen.findByText('Current case evidence')
  await act(async () => resolveOld(response({ incident: items[0] })))
  expect(screen.queryByText('Old case private evidence')).toBeNull()
  expect(screen.getByText('Current case evidence')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Review incident #3' }))
  await screen.findByText('Returned incident evidence did not match the selected investigation.')
  expect(screen.queryByRole('button', { name: 'Confirm verified incident' })).toBeNull()
  expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
})

test('operational investigation decision awaiting CSRF is cancelled when the verified admin changes', async () => {
  const item = investigation(4, 'Admin A loaded evidence')
  let resolveCsrf
  fetch.mockImplementation(url => {
    if (url === '/auth/csrf-token') return new Promise(resolve => { resolveCsrf = resolve })
    return Promise.resolve(response(url.startsWith('/api/admin/operational-incidents?') ? { incidents: [item] } : { incident: item }))
  })
  const view = render(investigationsView())
  fireEvent.click(await screen.findByRole('button', { name: 'Review incident #4' }))
  await screen.findByText('Admin A loaded evidence')
  fireEvent.change(screen.getByLabelText('Investigation decision evidence and notes'), { target: { value: 'Authenticated GPS and inspection evidence reviewed.' } })
  sessionStorage.clear(); clearCachedCsrfToken()
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss unsubstantiated incident' }))
  await waitFor(() => expect(resolveCsrf).toBeTypeOf('function'))
  view.rerender(investigationsView(78))
  await act(async () => resolveCsrf(response({ csrf_token: 'admin-B-csrf' })))
  expect(screen.queryByText('Admin A loaded evidence')).toBeNull()
  expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
})
