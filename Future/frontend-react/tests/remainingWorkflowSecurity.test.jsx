// @vitest-environment jsdom
import React, { useEffect, useState } from 'react'
import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AUTH_STATUSES, AuthVerificationProvider } from '../src/auth/AuthVerificationContext'
import { clearCachedCsrfToken, getCsrfToken } from '../src/pages/client/clientUtils'
import ChatWindow from '../src/components/chat/ChatWindow'
import LocationPicker from '../src/components/common/LocationPicker'
import AgreementBids from '../src/pages/client/AgreementBids'
import PartsCartPage from '../src/pages/transporter/PartsCartPage'
import { usePartsCart } from '../src/pages/transporter/partsCart'
import { PARTS_CART_EVENT } from '../src/pages/transporter/partsCartStorage.mjs'
import DriverAssignmentPanel from '../src/components/transporter/DriverAssignmentPanel'
import DriverActiveTrip from '../src/pages/driver/DriverActiveTrip'
import DriverTrips from '../src/pages/driver/DriverTrips'
import OrderTracking from '../src/pages/transporter/OrderTracking'
import AddTruck from '../src/pages/transporter/add_truck'

const leaflet = vi.hoisted(() => ({ maps: [], markers: [] }))
vi.mock('leaflet', () => ({ default: {
  map: () => {
    const map = { handlers: {}, setView: vi.fn().mockReturnThis(), invalidateSize: vi.fn(), remove: vi.fn(),
      on(name, callback) { this.handlers[name] = callback; return this }, fire(name, payload) { this.handlers[name]?.(payload) } }
    leaflet.maps.push(map)
    return map
  },
  tileLayer: () => ({ addTo: vi.fn() }), divIcon: () => ({}),
  marker: point => {
    const marker = { point, addTo: vi.fn().mockReturnThis(), on: vi.fn().mockReturnThis(), remove: vi.fn(),
      setLatLng: vi.fn().mockReturnThis(), getLatLng: () => ({ lat: point[0], lng: point[1] }) }
    leaflet.markers.push(marker)
    return marker
  },
} }))
vi.mock('../src/components/security/StepUpProvider', () => ({ useStepUp: () => ({ protectedFetch: (...args) => fetch(...args) }) }))

vi.setConfig({ testTimeout: 15000 })
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const ownerA = { id: 7101, role: 'logistics_provider' }, ownerB = { id: 7102, role: 'logistics_provider' }
function view(child, user = ownerA, status = AUTH_STATUSES.VERIFIED) {
  return <MemoryRouter><AuthVerificationProvider value={{ user, status }}>{child}</AuthVerificationProvider></MemoryRouter>
}
function deferred() { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
function postCalls() { return fetch.mock.calls.filter(([, options]) => options?.method === 'POST') }
function message(id, content) { return { id, content, message_type: 'text', is_own: false, sender_name: 'Sender', created_at: '2026-10-25T08:00:00Z' } }
const threads = [
  { id: 1, other_party_name: 'Alice', order: { id: 11, route_label: 'Lahore to Karachi', status: 'active' }, unread_count: 0 },
  { id: 2, other_party_name: 'Bob', order: { id: 22, route_label: 'Karachi to Multan', status: 'active' }, unread_count: 0 },
]
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear(); clearCachedCsrfToken()
  sessionStorage.setItem('csrf_token', 'remaining-csrf')
  vi.stubGlobal('fetch', vi.fn())
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  leaflet.maps.length = 0; leaflet.markers.length = 0
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('switching threads discards the previous message response even when fetch ignores abort', async () => {
  const old = deferred()
  fetch.mockImplementation(url => url === '/api/chat/threads' ? Promise.resolve(response({ threads }))
    : url.includes('/1/messages') ? old.promise : Promise.resolve(response({ messages: [message(2, 'Only Bob conversation')] })))
  render(view(<ChatWindow />))
  await screen.findByRole('button', { name: /Bob/ })
  fireEvent.click(screen.getByRole('button', { name: /Bob/ }))
  expect(await screen.findByText('Only Bob conversation')).toBeTruthy()
  await act(async () => old.resolve(response({ messages: [message(1, 'Private Alice response')] })))
  expect(screen.queryByText('Private Alice response')).toBeNull()
  expect(screen.getByText('Only Bob conversation')).toBeTruthy()
})

test('A to B to A navigation cannot restore an older A request into the fresh A instance', async () => {
  const old = deferred(); let reads = 0
  fetch.mockImplementation(url => url === '/api/chat/threads' ? Promise.resolve(response({ threads }))
    : url.includes('/1/messages') ? (++reads === 1 ? old.promise : Promise.resolve(response({ messages: [message(3, 'Current Alice')] })))
      : Promise.resolve(response({ messages: [message(2, 'Bob message')] })))
  render(view(<ChatWindow />))
  fireEvent.click(await screen.findByRole('button', { name: /Bob/ }))
  await screen.findByText('Bob message')
  fireEvent.click(screen.getByRole('button', { name: /Alice/ }))
  await screen.findByText('Current Alice')
  await act(async () => old.resolve(response({ messages: [message(1, 'Obsolete Alice')] })))
  expect(screen.queryByText('Obsolete Alice')).toBeNull()
  expect(screen.getByText('Current Alice')).toBeTruthy()
})

test('polling does not repeatedly abort a slow initial conversation read', async () => {
  const pending = deferred(), timers = []
  const nativeInterval = window.setInterval.bind(window)
  vi.spyOn(window, 'setInterval').mockImplementation((callback, delay, ...args) => {
    // Capture application polling only. Testing Library also uses intervals to
    // wait for effects; intercepting those made the first-read assertion race
    // the effect without ever checking again. Negative IDs cannot cancel an
    // unrelated real jsdom timeout when the component cleans up.
    if (delay !== 4000) return nativeInterval(callback, delay, ...args)
    timers.push(callback)
    return -timers.length
  })
  fetch.mockImplementation(url => url === '/api/chat/threads' ? Promise.resolve(response({ threads })) : pending.promise)
  render(view(<ChatWindow />))
  await screen.findByRole('heading', { name: 'Alice' })
  const reads = () => fetch.mock.calls.filter(([url]) => url.includes('/messages'))
  await waitFor(() => expect(reads()).toHaveLength(1))
  const signal = reads()[0][1].signal
  await act(async () => { for (const timer of timers) { timer(); timer() } })
  expect(reads()).toHaveLength(1)
  expect(signal.aborted).toBe(false)
  await act(async () => pending.resolve(response({ messages: [message(1, 'Slow but valid conversation')] })))
  expect(await screen.findByText('Slow but valid conversation')).toBeTruthy()
})

test('a late send from A neither appends into B nor clears B composer', async () => {
  const sent = deferred()
  fetch.mockImplementation((url, options) => options?.method === 'POST' ? sent.promise
    : Promise.resolve(response(url === '/api/chat/threads' ? { threads } : { messages: [] })))
  render(view(<ChatWindow />))
  await screen.findByRole('heading', { name: 'Alice' })
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: 'For Alice only' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() => expect(postCalls()).toHaveLength(1))
  fireEvent.click(screen.getByRole('button', { name: /Bob/ }))
  await screen.findByRole('heading', { name: 'Bob' })
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: 'Bob draft' } })
  await act(async () => sent.resolve(response({ message: message(5, 'For Alice only') })))
  expect(screen.queryByText('For Alice only')).toBeNull()
  expect(screen.getByPlaceholderText('Type your message...').value).toBe('Bob draft')
  expect(postCalls()[0][0]).toBe('/api/chat/threads/1/messages')
  expect(postCalls()[0][1].headers['X-CSRF-Token']).toBe('remaining-csrf')
})

test('a same-account thread switch preserves the intended outgoing thread while CSRF is loading', async () => {
  sessionStorage.removeItem('csrf_token'); clearCachedCsrfToken()
  const token = deferred()
  fetch.mockImplementation((url, options) => url === '/auth/csrf-token' ? token.promise
    : Promise.resolve(response(options?.method === 'POST' ? { message: message(5, 'For Alice only') }
      : url === '/api/chat/threads' ? { threads } : { messages: [] })))
  render(view(<ChatWindow />))
  await screen.findByRole('heading', { name: 'Alice' })
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: 'For Alice only' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/auth/csrf-token')).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: /Bob/ }))
  await screen.findByRole('heading', { name: 'Bob' })
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: 'Bob draft' } })
  await act(async () => token.resolve(response({ csrf_token: 'same-owner-csrf' })))
  await waitFor(() => expect(postCalls()).toHaveLength(1))
  expect(postCalls()[0][0]).toBe('/api/chat/threads/1/messages')
  expect(screen.getByPlaceholderText('Type your message...').value).toBe('Bob draft')
  expect(screen.queryByText('For Alice only')).toBeNull()
})

test('changing the verified account while CSRF is loading cancels the old chat mutation before POST', async () => {
  sessionStorage.removeItem('csrf_token'); clearCachedCsrfToken()
  const token = deferred()
  fetch.mockImplementation(url => url === '/auth/csrf-token' ? token.promise
    : Promise.resolve(response(url === '/api/chat/threads' ? { threads } : { messages: [] })))
  const mounted = render(view(<ChatWindow />))
  await screen.findByRole('heading', { name: 'Alice' })
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: 'Old owner text' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/auth/csrf-token')).toBe(true))
  mounted.rerender(view(<ChatWindow />, ownerB))
  await screen.findByRole('heading', { name: 'Alice' })
  await act(async () => token.resolve(response({ csrf_token: 'late-token' })))
  expect(postCalls()).toHaveLength(0)
  expect(screen.queryByText('Old owner text')).toBeNull()
})

test('chat identity comes from verified authority and old account thread lists cannot leak', async () => {
  const previous = deferred(); let reads = 0
  fetch.mockImplementation(url => url === '/api/chat/threads' ? (++reads === 1 ? previous.promise : Promise.resolve(response({ threads: [threads[1]] })))
    : Promise.resolve(response({ messages: [] })))
  sessionStorage.setItem('user', JSON.stringify(ownerA))
  const mounted = render(view(<ChatWindow />, ownerA, AUTH_STATUSES.PRESENTED))
  expect(fetch).not.toHaveBeenCalled()
  mounted.rerender(view(<ChatWindow />, ownerA))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  mounted.rerender(view(<ChatWindow />, ownerB))
  await screen.findByRole('button', { name: /Bob/ })
  await act(async () => previous.resolve(response({ threads: [threads[0]] })))
  expect(screen.queryByRole('button', { name: /Alice/ })).toBeNull()
})

function LocationForm({ initial, changed = () => {} }) {
  const [value, setValue] = useState(initial)
  return <><LocationPicker label="Pickup address" value={value} onChange={next => { setValue(next); changed(next) }} />
    <output data-testid="coordinates">{JSON.stringify(value)}</output></>
}
test('manually editing the address clears both coordinates, including zero values', () => {
  const changed = vi.fn()
  render(<LocationForm initial={{ location: 'Old address', lat: 0, lng: 0 }} changed={changed} />)
  fireEvent.change(screen.getByRole('textbox', { name: 'Pickup address' }), { target: { value: 'New address' } })
  expect(changed).toHaveBeenLastCalledWith({ location: 'New address', lat: null, lng: null })
  expect(screen.queryByText('0.00000, 0.00000')).toBeNull()
})

test('an old forward-geocode response cannot restore a cleared pin after address editing', async () => {
  const old = deferred(); fetch.mockReturnValue(old.promise)
  render(<LocationForm initial={{ location: 'Lahore old road', lat: 31, lng: 74 }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Locate on map' }))
  const signal = fetch.mock.calls[0][1].signal
  fireEvent.change(screen.getByRole('textbox', { name: 'Pickup address' }), { target: { value: 'Karachi new road' } })
  expect(signal.aborted).toBe(true)
  await act(async () => old.resolve(response([{ lat: '31.5', lon: '74.3' }])))
  expect(screen.getByTestId('coordinates').textContent).toBe(JSON.stringify({ location: 'Karachi new road', lat: null, lng: null }))
})

test('an old reverse-geocode response cannot replace newly typed text or its empty coordinates', async () => {
  const old = deferred(); fetch.mockReturnValue(old.promise)
  render(<LocationForm initial={{ location: '', lat: null, lng: null }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Locate on map' }))
  act(() => leaflet.maps[0].fire('click', { latlng: { lat: 31.5, lng: 74.3 } }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Pickup address' }), { target: { value: 'Manually corrected address' } })
  await act(async () => old.resolve(response({ display_name: 'Old reverse address' })))
  expect(screen.getByTestId('coordinates').textContent).toBe(JSON.stringify({ location: 'Manually corrected address', lat: null, lng: null }))
})

test('location lookup cleanup aborts requests and cannot call a removed form callback', async () => {
  const old = deferred(), changed = vi.fn(); fetch.mockReturnValue(old.promise)
  const mounted = render(<LocationForm initial={{ location: 'Lahore', lat: null, lng: null }} changed={changed} />)
  fireEvent.click(screen.getByRole('button', { name: 'Locate on map' }))
  const signal = fetch.mock.calls[0][1].signal
  mounted.unmount()
  await act(async () => old.resolve(response([{ lat: '31', lon: '74' }])))
  expect(signal.aborted).toBe(true)
  expect(changed).not.toHaveBeenCalled()
  expect(leaflet.maps[0].remove).toHaveBeenCalled()
})

test('agreement contract preview preserves dates and survives a temporarily empty date input', async () => {
  fetch.mockResolvedValue(response({ post: { title: 'Freight agreement', service_area: [] }, bids: [{ id: 6, transporter_name: 'Fleet', trucks: [{ truck_id: 9, truck_number: 'ABC-1' }] }] }))
  render(<MemoryRouter initialEntries={['/bids/5']}><Routes><Route path="/bids/:postId" element={<AgreementBids />} /></Routes></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('Start date'), { target: { value: '2026-10-23' } })
  fireEvent.change(screen.getByLabelText('Duration months'), { target: { value: '1' } })
  await waitFor(() => expect(screen.getByLabelText('Contract preview').value).toContain('(2026-10-23 to 2026-11-23)'))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm & Finalize' }))
  expect(await screen.findByText('Choose a valid start date and a positive whole number of months.')).toBeTruthy()
  expect(postCalls()).toHaveLength(0)
})

function CartProbe({ capture }) {
  const { cart, addItem, clearCart } = usePartsCart()
  useEffect(() => { capture?.(clearCart) }, [capture, clearCart])
  return <div><output data-testid="cart">{cart.map(item => `${item.title}:${item.qty}`).join(',')}</output>
    <button onClick={() => addItem({ id: 7, title: 'New tyre', price: 50 })}>Add item</button><button onClick={clearCart}>Clear cart</button></div>
}
test('cart immediately switches only after verified identity and never imports the unowned v1 key', () => {
  localStorage.setItem('dtx:parts-cart:v1', JSON.stringify([{ id: 1, qty: 1, title: 'Unowned legacy' }]))
  localStorage.setItem(`dtx:parts-cart:v2:${ownerA.id}`, JSON.stringify([{ id: 1, qty: 2, title: 'A private cart' }]))
  localStorage.setItem(`dtx:parts-cart:v2:${ownerB.id}`, JSON.stringify([{ id: 2, qty: 3, title: 'B private cart' }]))
  const mounted = render(view(<CartProbe />, ownerA, AUTH_STATUSES.PRESENTED))
  expect(screen.getByTestId('cart').textContent).toBe('')
  mounted.rerender(view(<CartProbe />, ownerA))
  expect(screen.getByTestId('cart').textContent).toBe('A private cart:2')
  mounted.rerender(view(<CartProbe />, ownerB))
  expect(screen.getByTestId('cart').textContent).toBe('B private cart:3')
  mounted.rerender(view(<CartProbe />, null, AUTH_STATUSES.UNAUTHORIZED))
  expect(screen.getByTestId('cart').textContent).toBe('')
  expect(localStorage.getItem('dtx:parts-cart:v1')).toContain('Unowned legacy')
})

test('cart ignores other-account and legacy events, and stale callbacks cannot clear the new owner', () => {
  let staleClear
  const capture = callback => { staleClear = callback }
  const mounted = render(view(<CartProbe capture={capture} />, ownerA))
  fireEvent.click(screen.getByText('Add item'))
  const clearA = staleClear
  localStorage.setItem(`dtx:parts-cart:v2:${ownerB.id}`, JSON.stringify([{ id: 9, qty: 4, title: 'B product' }]))
  act(() => window.dispatchEvent(new CustomEvent(PARTS_CART_EVENT, { detail: { storageKey: `dtx:parts-cart:v2:${ownerB.id}` } })))
  act(() => window.dispatchEvent(new CustomEvent(PARTS_CART_EVENT, { detail: [{ id: 99, title: 'Legacy injected event', qty: 1 }] })))
  expect(screen.getByTestId('cart').textContent).toBe('New tyre:1')
  mounted.rerender(view(<CartProbe />, ownerB))
  act(() => clearA())
  expect(screen.getByTestId('cart').textContent).toBe('B product:4')
  expect(JSON.parse(localStorage.getItem(`dtx:parts-cart:v2:${ownerA.id}`))).toEqual([])
})

test('an interrupted A checkout cannot clear B cart, retain A address, or navigate the new account', async () => {
  const pending = deferred(); fetch.mockReturnValue(pending.promise)
  for (const owner of [ownerA, ownerB]) localStorage.setItem(`dtx:parts-cart:v2:${owner.id}`, JSON.stringify([{ id: owner.id, title: `Product ${owner.id}`, qty: 1, price: 10 }]))
  const mounted = render(view(<PartsCartPage />, ownerA))
  fireEvent.change(screen.getByPlaceholderText('Enter workshop address or roadside location'), { target: { value: 'A private address' } })
  fireEvent.click(screen.getByRole('button', { name: /Confirm & Pay/ }))
  await waitFor(() => expect(postCalls()).toHaveLength(1))
  mounted.rerender(view(<PartsCartPage />, ownerB))
  expect(screen.getByPlaceholderText('Enter workshop address or roadside location').value).toBe('')
  await act(async () => pending.resolve(response({ success: true, order: { id: 99, order_number: 'A-order' } }, 201)))
  expect(screen.getByText(`Product ${ownerB.id}`)).toBeTruthy()
  expect(JSON.parse(localStorage.getItem(`dtx:parts-cart:v2:${ownerB.id}`))).toHaveLength(1)
  expect(screen.getByRole('heading', { name: 'Your Cart' })).toBeTruthy()
})

test('account change during checkout fingerprinting aborts before another account can be charged', async () => {
  const digest = deferred(), digestCall = vi.fn(() => digest.promise)
  vi.stubGlobal('crypto', { subtle: { digest: digestCall }, randomUUID: () => webcrypto.randomUUID() })
  for (const owner of [ownerA, ownerB]) localStorage.setItem(`dtx:parts-cart:v2:${owner.id}`, JSON.stringify([{ id: owner.id, title: `Product ${owner.id}`, qty: 1, price: 10 }]))
  const mounted = render(view(<PartsCartPage />, ownerA))
  fireEvent.change(screen.getByPlaceholderText('Enter workshop address or roadside location'), { target: { value: 'A private delivery address' } })
  fireEvent.click(screen.getByRole('button', { name: /Confirm & Pay/ }))
  await waitFor(() => expect(digestCall).toHaveBeenCalledTimes(1))
  mounted.rerender(view(<PartsCartPage />, ownerB))
  await act(async () => digest.resolve(new Uint8Array(32).buffer))
  expect(postCalls()).toHaveLength(0)
  expect(screen.getByText(`Product ${ownerB.id}`)).toBeTruthy()
  expect(JSON.parse(localStorage.getItem(`dtx:parts-cart:v2:${ownerB.id}`))).toHaveLength(1)
})

test('a CSRF response from before authentication cleanup cannot overwrite the new token cache', async () => {
  sessionStorage.removeItem('csrf_token'); clearCachedCsrfToken()
  const token = deferred(); fetch.mockReturnValue(token.promise)
  const previous = getCsrfToken()
  clearCachedCsrfToken()
  sessionStorage.setItem('csrf_token', 'new-owner-token')
  const rejected = expect(previous).rejects.toHaveProperty('name', 'AbortError')
  await act(async () => token.resolve(response({ csrf_token: 'old-owner-token' })))
  await rejected
  expect(await getCsrfToken()).toBe('new-owner-token')
  expect(sessionStorage.getItem('csrf_token')).toBe('new-owner-token')
})

test('storage denial preserves functional in-memory carts without mixing accounts', () => {
  const memoryOwner = { id: 7301, role: 'logistics_provider' }
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled') })
  const mounted = render(view(<CartProbe />, memoryOwner))
  fireEvent.click(screen.getByText('Add item'))
  expect(screen.getByTestId('cart').textContent).toBe('New tyre:1')
  mounted.rerender(view(<CartProbe />, ownerB))
  expect(screen.getByTestId('cart').textContent).toBe('')
  mounted.rerender(view(<CartProbe />, memoryOwner))
  expect(screen.getByTestId('cart').textContent).toBe('New tyre:1')
})

test('truck registration explains consent and does not collect auto-link driver identity', () => {
  render(view(<AddTruck />))
  expect(screen.getByText('Driver acceptance is required')).toBeTruthy()
  expect(document.querySelector('input[name="uniqueDriverId"]')).toBeNull()
  expect(document.querySelector('input[name="driverName"]')).toBeNull()
  expect(document.querySelector('input[name="driverCnic"]')).toBeNull()
})

test('new-tab truck registration obtains CSRF before its unassigned multipart submission', async () => {
  sessionStorage.removeItem('csrf_token'); clearCachedCsrfToken()
  fetch.mockImplementation(async (url, options) => options?.method === 'POST'
    ? response({ success: false, message: 'This truck is already registered.' }, 409)
    : response({ success: true, csrf_token: 'new-tab-csrf' }))
  render(view(<AddTruck />))
  const field = name => document.querySelector(`[name="${name}"]`)
  fireEvent.change(field('truckNumber'), { target: { value: 'TEST-100' } })
  fireEvent.change(field('chassisNumber'), { target: { value: 'ABCDEFGHJKLMN' } })
  fireEvent.change(field('payload_min_tons'), { target: { value: '1' } })
  fireEvent.change(field('payload_max_tons'), { target: { value: '5' } })
  fireEvent.change(field('body_style'), { target: { value: 'Box Body' } })
  fireEvent.change(field('box_type'), { target: { value: 'Dry Box' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => expect(postCalls()).toHaveLength(1))
  expect(fetch.mock.calls[0][0]).toBe('/auth/csrf-token')
  expect(postCalls()[0][1].headers['X-CSRF-Token']).toBe('new-tab-csrf')
  const body = postCalls()[0][1].body
  expect(body.get('truckType')).toBe('Box Body')
  for (const key of ['uniqueDriverId', 'driverName', 'driverCnic']) expect(body.has(key)).toBe(false)
  expect(await screen.findByText('This truck is already registered.')).toBeTruthy()
})

function assignmentData(overrides = {}) { return { success: true, truck_id: 84, trip_id: 88, agreement_trip_id: null, can_dispatch: true, assignments: [], ...overrides } }
test('owned one-time trip invitation submits server-owned truck/source IDs and waits for driver acceptance', async () => {
  let sent = false
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { sent = true; return response({ success: true, message: 'Invitation sent to driver.' }) }
    if (url === '/api/orders/11') return response({ success: true, order: { id: 11 }, trip: { id: 88, status: 'ready_to_start' } })
    return response(assignmentData({ assignments: sent ? [{ id: 91, driver_user_id: 51, driver_name: 'Consent Driver', unique_driver_id: 'DRV-51', status: 'requested' }] : [] }))
  })
  render(<React.StrictMode><MemoryRouter initialEntries={['/orders/11']}><AuthVerificationProvider value={{ user: ownerA, status: AUTH_STATUSES.VERIFIED }}><Routes><Route path="/orders/:orderId" element={<OrderTracking />} /></Routes></AuthVerificationProvider></MemoryRouter></React.StrictMode>)
  fireEvent.click(await screen.findByRole('button', { name: 'Driver invitation & review' }))
  fireEvent.change(await screen.findByLabelText('Driver ID'), { target: { value: 'drv-51' } })
  fireEvent.change(screen.getByLabelText('Trip offer (PKR)'), { target: { value: '550.00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send trip invitation' }))
  expect(await screen.findByText(/Waiting for the driver to accept or decline/)).toBeTruthy()
  const [url, options] = postCalls()[0]
  expect(url).toBe('/api/transporter/dispatch-driver')
  expect(JSON.parse(options.body)).toEqual({ unique_driver_id: 'DRV-51', truck_id: 84, trip_id: 88, offer_amount: '550.00', notes: '' })
  expect(options.headers['X-CSRF-Token']).toBe('remaining-csrf')
  expect(screen.queryByRole('button', { name: 'Accept Trip' })).toBeNull()
})

test('completed agreement assignment review binds its IDs and reports an allegation as investigating', async () => {
  let reviewed = false
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { reviewed = true; return response({ success: true, incident_status: 'investigating' }) }
    return response(assignmentData({ can_dispatch: false, trip_id: null, agreement_trip_id: 55, assignments: [{
      id: 91, driver_user_id: 51, driver_name: 'Completed Driver', unique_driver_id: 'DRV-51', status: 'completed', reviewed, can_review: !reviewed,
    }] }))
  })
  render(view(<DriverAssignmentPanel agreementTripId={55} defaultOpen />))
  fireEvent.change(await screen.findByLabelText('Driver rating'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('Review comment'), { target: { value: 'Trip completed' } })
  fireEvent.change(screen.getByLabelText('Report an incident (optional)'), { target: { value: 'theft' } })
  fireEvent.change(screen.getByLabelText('Incident details'), { target: { value: 'Missing sealed container; please investigate.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit trip review' }))
  expect(await screen.findByText('Review recorded. The incident is investigating and has not been confirmed.')).toBeTruthy()
  expect(postCalls()[0][0]).toBe('/api/driver/rate')
  expect(JSON.parse(postCalls()[0][1].body)).toEqual({ assignment_id: 91, driver_user_id: 51, rating: 3, comment: 'Trip completed', incident_type: 'theft', incident_description: 'Missing sealed container; please investigate.' })
  expect(postCalls()[0][1].headers['X-CSRF-Token']).toBe('remaining-csrf')
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Submit trip review' })).toBeNull())
})

test('driver request panel exposes ownership failure and never renders unapproved actions', async () => {
  fetch.mockResolvedValue(response({ success: false, message: 'Trip not found in your fleet.' }, 404))
  const mounted = render(view(<DriverAssignmentPanel tripId={88} defaultOpen />))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Trip not found in your fleet.')
  expect(screen.queryByLabelText('Driver ID')).toBeNull()
  mounted.rerender(view(<DriverAssignmentPanel tripId={88} defaultOpen />, { id: 88, role: 'driver' }))
  expect(screen.queryByRole('button', { name: 'Driver invitation & review' })).toBeNull()
})

test('driver request responses from the old owner cannot display after switching accounts', async () => {
  const old = deferred(); let reads = 0
  fetch.mockImplementation(() => ++reads === 1 ? old.promise : Promise.resolve(response(assignmentData({ can_dispatch: false, assignments: [{ id: 8, driver_name: 'B driver', status: 'accepted' }] }))))
  const mounted = render(view(<DriverAssignmentPanel tripId={88} defaultOpen />))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  mounted.rerender(view(<DriverAssignmentPanel tripId={88} defaultOpen />, ownerB))
  await screen.findByText('B driver')
  await act(async () => old.resolve(response(assignmentData({ assignments: [{ id: 1, driver_name: 'A private driver', status: 'requested' }] }))))
  expect(screen.queryByText('A private driver')).toBeNull()
})

function mockGeolocation() {
  const callbacks = {}
  const geolocation = { getCurrentPosition: vi.fn(success => { callbacks.initial = success }),
    watchPosition: vi.fn(success => { callbacks.watch = success; return 0 }), clearWatch: vi.fn() }
  vi.stubGlobal('navigator', { ...navigator, geolocation })
  return { callbacks, geolocation }
}
const position = { coords: { latitude: 31.5, longitude: 74.3, speed: 0, heading: 0, altitude: 0 } }
test('driver acceptance uses the actual request ID and CSRF before refreshing its accepted state', async () => {
  let accepted = false, reads = 0
  const old = deferred()
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { accepted = true; return response({ success: true, status: 'accepted' }) }
    if (url === '/api/driver/me' && ++reads === 1) return old.promise
    return response(url.endsWith('hire-contracts') ? { success: true, contracts: [] } : {
      success: true, recent_trips: [{ id: 91, status: accepted ? 'accepted' : 'requested', truck_number: 'ABC-1', transporter_name: 'Fleet', offer_amount: 550 }],
    })
  })
  render(<React.StrictMode>{view(<DriverTrips />, { id: 81, role: 'driver' })}</React.StrictMode>)
  fireEvent.click(await screen.findByRole('button', { name: 'Accept Trip' }))
  expect(await screen.findByText('Trip Accepted successfully!')).toBeTruthy()
  expect(postCalls()[0][0]).toBe('/api/driver/trips/91/respond')
  expect(JSON.parse(postCalls()[0][1].body)).toEqual({ action: 'accept' })
  expect(postCalls()[0][1].headers['X-CSRF-Token']).toBe('remaining-csrf')
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Accept Trip' })).toBeNull())
  await act(async () => old.resolve(response({ success: true, recent_trips: [{ id: 91, status: 'requested', truck_number: 'ABC-1' }] })))
  expect(screen.queryByRole('button', { name: 'Accept Trip' })).toBeNull()
})

test('driver acceptance conflict displays the server result without claiming a second booking', async () => {
  fetch.mockImplementation(async (url, options) => options?.method === 'POST'
    ? response({ success: false, message: 'You already have an active assignment.' }, 409)
    : response(url.endsWith('hire-contracts') ? { success: true, contracts: [] } : {
      success: true, recent_trips: [{ id: 91, status: 'requested', truck_number: 'ABC-1' }],
    }))
  render(view(<DriverTrips />, { id: 81, role: 'driver' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Accept Trip' }))
  expect(await screen.findByText('Error: You already have an active assignment.')).toBeTruthy()
  expect(screen.queryByText('Trip Accepted successfully!')).toBeNull()
})

test('GPS cannot begin without an accepted assignment', async () => {
  const { geolocation } = mockGeolocation()
  fetch.mockResolvedValue(response({ success: true, driver: {}, recent_trips: [{ id: 91, status: 'requested' }] }))
  render(view(<DriverActiveTrip />, { id: 81, role: 'driver' }))
  await screen.findByRole('link', { name: 'Trip Requests' })
  expect(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }).disabled).toBe(true)
  expect(geolocation.watchPosition).not.toHaveBeenCalled()
})

test('GPS binds the accepted assignment and stops watch ID zero plus late callbacks', async () => {
  const { callbacks, geolocation } = mockGeolocation()
  fetch.mockImplementation(async (url, options) => response(options?.method === 'POST' ? { success: true } : { success: true, recent_trips: [{ id: 91, status: 'accepted', truck_number: 'ABC-1' }] }))
  render(view(<DriverActiveTrip />, { id: 81, role: 'driver' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }))
  await act(async () => callbacks.watch(position))
  await waitFor(() => expect(postCalls()).toHaveLength(1))
  expect(JSON.parse(postCalls()[0][1].body)).toEqual({ assignment_id: 91, lat: 31.5, lng: 74.3, speed_kmh: 0, heading: 0, altitude: 0 })
  expect(postCalls()[0][1].headers['X-CSRF-Token']).toBe('remaining-csrf')
  fireEvent.click(screen.getByRole('button', { name: 'Stop GPS Streaming' }))
  await act(async () => { callbacks.initial(position); callbacks.watch(position) })
  expect(geolocation.clearWatch).toHaveBeenCalledWith(0)
  expect(postCalls()).toHaveLength(1)
})

test('expired source assignment stops GPS and shows the backend rejection instead of claiming a broadcast', async () => {
  const { callbacks, geolocation } = mockGeolocation()
  fetch.mockImplementation(async (url, options) => options?.method === 'POST'
    ? response({ success: false, message: 'The assignment is no longer active for tracking.' }, 409)
    : response({ success: true, recent_trips: [{ id: 91, status: 'accepted' }] }))
  render(view(<DriverActiveTrip />, { id: 81, role: 'driver' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }))
  await act(async () => callbacks.watch(position))
  expect(await screen.findByText('The assignment is no longer active for tracking.')).toBeTruthy()
  expect(geolocation.clearWatch).toHaveBeenCalledWith(0)
  expect(screen.getByRole('button', { name: 'Start Live GPS Broadcast' }).disabled).toBe(true)
  expect(screen.getByText('BROADCAST STANDBY')).toBeTruthy()
})
