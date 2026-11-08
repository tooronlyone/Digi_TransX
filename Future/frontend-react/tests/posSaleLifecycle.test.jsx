import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import POSPage from '../src/pages/shopkeeper/POSPage'

const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const product = { id: 1, name: 'Engine oil', price: 100, stock_quantity: 1.5, unit: 'liter' }
const completed = {
  sale_id: 17, receipt_number: 'DTX-SAVED', purchaser_name: 'Buyer',
  total_amount: 100, amount_paid: 100, change_amount: 0,
  created_at: '2026-10-29T10:00:00Z',
  items: [{ product_name: 'Engine oil', quantity: 1, unit_price: 100, subtotal: 100 }],
}
const sales = () => fetch.mock.calls.filter(([url, options]) => url === '/api/shopkeeper/sales' && options?.method === 'POST')

beforeEach(() => {
  sessionStorage.clear()
  sessionStorage.setItem('csrf_token', 'pos-csrf')
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function serveProduct(item = product) {
  fetch.mockImplementation(async (url, options) => {
    if (url === '/api/shopkeeper/products') return json({ success: true, data: [item] })
    if (url === '/api/shopkeeper/sales' && options?.method === 'POST') return json({ success: true, data: completed }, 201)
    throw new Error('Receipt refresh unavailable')
  })
}
async function mountSale() {
  render(<MemoryRouter><POSPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('Engine oil'))
  fireEvent.change(screen.getByPlaceholderText('0'), { target: { value: '200' } })
}

test('a committed sale displays its POST receipt and cannot be resubmitted when receipt refresh is unavailable', async () => {
  serveProduct()
  await mountSale()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  expect(await screen.findByText('DTX-SAVED')).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url === '/api/shopkeeper/sales/17')).toBe(false)
  expect(sales()).toHaveLength(1)
  expect(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'New Sale' }))
  expect(screen.getByText('Click a product to add it')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }).disabled).toBe(true)
})

test('a product with less than one measured unit starts at available stock', async () => {
  serveProduct({ ...product, stock_quantity: 0.5 })
  await mountSale()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  await waitFor(() => expect(sales()).toHaveLength(1))
  expect(JSON.parse(sales()[0][1].body).items).toEqual([{ product_id: 1, quantity: 0.5 }])
})

test('repeated product additions never exceed fractional stock', async () => {
  serveProduct()
  await mountSale()
  fireEvent.click(screen.getAllByText('Engine oil')[0])
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  await waitFor(() => expect(sales()).toHaveLength(1))
  expect(JSON.parse(sales()[0][1].body).items).toEqual([{ product_id: 1, quantity: 1.5 }])
})

test('measured quantity accepts three decimal places and disables checkout while empty', async () => {
  serveProduct()
  await mountSale()
  const quantity = screen.getByRole('spinbutton', { name: 'Quantity for Engine oil' })
  expect(quantity.step).toBe('0.001')
  fireEvent.change(quantity, { target: { value: '' } })
  expect(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }).disabled).toBe(true)
  fireEvent.change(quantity, { target: { value: '0.125' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }))
  await waitFor(() => expect(sales()).toHaveLength(1))
  expect(JSON.parse(sales()[0][1].body).items).toEqual([{ product_id: 1, quantity: 0.125 }])
})

test('whole-unit products reject fractional quantity and cap edits at stock', async () => {
  serveProduct({ ...product, stock_quantity: 3, unit: 'piece' })
  await mountSale()
  const quantity = screen.getByRole('spinbutton', { name: 'Quantity for Engine oil' })
  expect(quantity.step).toBe('1')
  fireEvent.change(quantity, { target: { value: '0.5' } })
  expect(quantity.value).toBe('1')
  fireEvent.change(quantity, { target: { value: '9' } })
  expect(quantity.value).toBe('3')
})

test('quantity buttons preserve the supported three-decimal precision', async () => {
  serveProduct()
  await mountSale()
  const quantity = screen.getByRole('spinbutton', { name: 'Quantity for Engine oil' })
  fireEvent.change(quantity, { target: { value: '1.005' } })
  fireEvent.click(screen.getByRole('button', { name: '−' }))
  expect(quantity.value).toBe('0.005')
  expect(screen.getByRole('button', { name: 'Confirm Sale & Generate Receipt' }).disabled).toBe(false)
})
