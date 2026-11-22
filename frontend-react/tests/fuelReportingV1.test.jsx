import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DriverFuelLogs from '../src/pages/driver/DriverFuelLogs'
import TruckDetails from '../src/pages/transporter/truck_details'
import { clearCachedCsrfToken } from '../src/pages/client/clientUtils'

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  sessionStorage.clear()
  clearCachedCsrfToken()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('DriverFuelLogs renders truck metadata, trip association, vehicle filter, and excludes V2 pump options', async () => {
  const calls = []
  fetch.mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : input.url
    calls.push(url)
    if (url.startsWith('/api/driver/fuel-logs')) {
      const filtered = url.includes('truck_id=55')
      return json({
        success: true,
        vehicles: [
          { truck_id: 55, truck_number: 'LEA-4012', truck_model: 'Hino 500' },
          { truck_id: 56, truck_number: 'KHI-9001', truck_model: 'Isuzu FVR' },
        ],
        stats: {
          total_liters: filtered ? 120.5 : 200.5,
          total_fuel_spent: filtered ? 34342.5 : 57142.5,
          total_refuels: filtered ? 1 : 2,
          avg_km_per_liter: 4.5,
        },
        logs: filtered
          ? [
              {
                id: 101,
                truck_id: 55,
                truck_number: 'LEA-4012',
                truck_model: 'Hino 500',
                trip_id: 88,
                pickup_city: 'Lahore',
                dropoff_city: 'Karachi',
                pump_name: 'PSO Shahdara',
                city: 'Lahore',
                fuel_type: 'diesel',
                liters: 120.5,
                price_per_liter: 285,
                total_amount: 34342.5,
                fuel_date: '2026-11-10',
                payment_mode: 'cash',
                fuel_average_km_per_liter: 4.5,
              },
            ]
          : [
              {
                id: 101,
                truck_id: 55,
                truck_number: 'LEA-4012',
                truck_model: 'Hino 500',
                trip_id: 88,
                pickup_city: 'Lahore',
                dropoff_city: 'Karachi',
                pump_name: 'PSO Shahdara',
                city: 'Lahore',
                fuel_type: 'diesel',
                liters: 120.5,
                price_per_liter: 285,
                total_amount: 34342.5,
                fuel_date: '2026-11-10',
                payment_mode: 'cash',
                fuel_average_km_per_liter: 4.5,
              },
              {
                id: 102,
                truck_id: 56,
                truck_number: 'KHI-9001',
                truck_model: 'Isuzu FVR',
                trip_id: null,
                pump_name: 'Shell Port Qasim',
                city: 'Karachi',
                fuel_type: 'diesel',
                liters: 80,
                price_per_liter: 285,
                total_amount: 22800,
                fuel_date: '2026-11-09',
                payment_mode: 'company_card',
                fuel_average_km_per_liter: null,
              },
            ],
      })
    }
    if (url.startsWith('/api/driver/trips-for-fuel')) {
      return json({ success: true, trips: [] })
    }
    return json({ success: false }, 404)
  })

  render(
    <MemoryRouter>
      <DriverFuelLogs />
    </MemoryRouter>,
  )

  await screen.findByText('PSO Shahdara')
  expect(screen.getAllByText('LEA-4012').length).toBeGreaterThan(0)
  expect(screen.getAllByText('Hino 500').length).toBeGreaterThan(0)
  expect(screen.getByText(/Trip #88/)).toBeTruthy()
  expect(screen.getByText('Lahore → Karachi')).toBeTruthy()
  expect(screen.getByText('2026-11-10')).toBeTruthy()
  expect(screen.getByText(/34,342/)).toBeTruthy()
  expect(screen.getByText(/120.5 L/)).toBeTruthy()
  expect(screen.getAllByText(/285\/L/).length).toBe(2)
  expect(screen.getByText('Shell Port Qasim')).toBeTruthy()
  expect(screen.queryByText(/Fuel Station Fleet Card/i)).toBeNull()

  const filterSelect = screen.getByLabelText('Filter fuel logs by vehicle')
  fireEvent.change(filterSelect, { target: { value: '55' } })

  await waitFor(() => {
    expect(calls.some((u) => u.includes('/api/driver/fuel-logs?truck_id=55'))).toBe(true)
  })
  await waitFor(() => {
    expect(screen.queryByText('Shell Port Qasim')).toBeNull()
  })
  expect(calls.some((u) => u.includes('/fuelstation'))).toBe(false)
})

test('TruckDetails fetches authorized read-only /fuel-logs endpoint and never calls dead /fuel route', async () => {
  const calls = []
  fetch.mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : input.url
    calls.push(url)
    if (url === '/api/trucks/55') {
      return json({
        success: true,
        truck: {
          id: 55,
          plate_number: 'LEA-4012',
          truck_number: 'LEA-4012',
          make: 'Hino',
          model: '500',
          truck_type: 'Flatbed',
          status: 'available',
        },
      })
    }
    if (url === '/api/trucks/55/maintenance') {
      return json({ success: true, logs: [] })
    }
    if (url === '/api/trucks/55/fuel-logs') {
      return json({
        success: true,
        stats: {
          total_refuels: 2,
          total_liters: 180,
          total_fuel_spent: 51300,
          avg_km_per_liter: 4.2,
        },
        logs: [
          {
            id: 201,
            fuel_date: '2026-11-11',
            driver_name: 'Bilal Ahmed',
            pump_name: 'Attock Motorway',
            city: 'Islamabad',
            trip_id: 91,
            pickup_city: 'Lahore',
            dropoff_city: 'Islamabad',
            fuel_type: 'diesel',
            liters: 180,
            price_per_liter: 285,
            total_amount: 51300,
            fuel_average_km_per_liter: 4.2,
          },
        ],
      })
    }
    return json({ success: false }, 404)
  })

  render(
    <MemoryRouter initialEntries={['/transporter/trucks/55']}>
      <Routes>
        <Route path="/transporter/trucks/:id" element={<TruckDetails />} />
      </Routes>
    </MemoryRouter>,
  )

  const heading = await screen.findByText('Vehicle Fuel History')
  const card = heading.closest('div').parentElement.parentElement
  expect(within(card).getByText('Refuels: 2')).toBeTruthy()
  expect(within(card).getByText('180.00 L')).toBeTruthy()
  expect(within(card).getAllByText(/51,300/).length).toBeGreaterThanOrEqual(2)
  expect(within(card).getByText('Avg 4.2 km/L')).toBeTruthy()
  expect(within(card).getByText('Bilal Ahmed')).toBeTruthy()
  expect(within(card).getByText('Attock Motorway')).toBeTruthy()
  expect(within(card).queryByRole('button', { name: /delete|edit|add fuel/i })).toBeNull()

  expect(calls).toContain('/api/trucks/55/fuel-logs')
  expect(calls).not.toContain('/api/trucks/55/fuel')
})
