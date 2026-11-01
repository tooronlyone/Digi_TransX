import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AdminLayout from '../src/components/admin/AdminLayout'
import DriverLayout from '../src/components/driver/DriverLayout'

vi.mock('../src/pages/admin/adminApi', () => ({
  adminUser: () => ({ full_name: 'Admin User', email: 'admin@example.com' }),
  adminRequest: vi.fn(),
}))

vi.mock('../src/auth/logout', () => ({
  logoutCurrentSession: vi.fn(),
}))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      success: true,
      unread_count: 2,
      notifications: [
        { id: 1, order_id: 10, notification_type: 'trip_started', message: 'Trip started', is_read: false },
      ],
    }),
  }))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('LEDGER-017: AdminLayout renders NotificationBell', async () => {
  render(
    <MemoryRouter>
      <AdminLayout>
        <div>Admin Content</div>
      </AdminLayout>
    </MemoryRouter>
  )

  const bellButton = await screen.findByRole('button', { name: /Notifications/i })
  expect(bellButton).toBeTruthy()
})

it('LEDGER-017: DriverLayout renders NotificationBell', async () => {
  render(
    <MemoryRouter>
      <DriverLayout>
        <div>Driver Content</div>
      </DriverLayout>
    </MemoryRouter>
  )

  const bellButton = await screen.findByRole('button', { name: /Notifications/i })
  expect(bellButton).toBeTruthy()
})
