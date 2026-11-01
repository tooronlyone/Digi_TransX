// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TruckConfiguration from '../src/pages/transporter/truck_configuration'

const mockTruck = {
  id: 42,
  truck_number: '',
  truck_company: '',
  truck_model: '',
  truck_type: '',
  max_capacity: '',
  chassis_number: '',
  operating_provinces: [],
  catalog_type_key: '',
  body_style: '',
  payload_min_tons: '',
  payload_max_tons: '',
  volume_min_cbm: '',
  volume_max_cbm: '',
  catalog_specs_json: '',
  bed_length_ft: '',
  bed_width_ft: '',
  bed_height_ft: '',
  current_city: '',
  current_lat: '',
  current_lng: '',
  service_radius_km: 100,
  tracking_id: '',
  driver_name: '',
  driver_cnic: '',
  refrigeration_supported: true,
  hazardous_supported: true,
  fragile_supported: true,
  photo: '',
  insurance_photo: '',
  rc_book_photo: '',
  status: 'inactive',
  status_reason_code: '',
  status_reason: '',
}

vi.mock('../src/hooks/useApi', () => ({
  useApi: () => ({
    get: vi.fn().mockImplementation((url) => {
      if (url.includes('/status-reasons')) {
        return Promise.resolve({ reasons: [] })
      }
      return Promise.resolve({ truck: mockTruck, configuration: mockTruck })
    }),
    put: vi.fn(),
    request: vi.fn(),
  }),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('LEDGER-009: TruckConfiguration renders standard Notification and dismisses on close', async () => {
  render(
    <MemoryRouter initialEntries={['/transporter/trucks/42/configure']}>
      <Routes>
        <Route path="/transporter/trucks/:id/configure" element={<TruckConfiguration />} />
      </Routes>
    </MemoryRouter>
  )

  // Wait for loading to finish and save button to appear
  const saveBtn = await screen.findByRole('button', { name: /Save Configuration/i })
  expect(saveBtn).toBeTruthy()

  // Click save with empty required fields to trigger validation toast
  fireEvent.click(saveBtn)

  // Standard Notification component should be visible
  const notification = screen.getByRole('status')
  expect(notification).toBeTruthy()
  expect(notification.className).toContain('app-notification')
  expect(notification.textContent).toContain('Please fill:')

  // Click close button on notification
  const closeBtn = screen.getByRole('button', { name: 'Close notification' })
  fireEvent.click(closeBtn)

  // Notification should be dismissed
  expect(screen.queryByRole('status')).toBeNull()
})
