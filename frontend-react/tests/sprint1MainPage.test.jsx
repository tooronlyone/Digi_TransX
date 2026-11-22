import React from 'react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import process from 'node:process'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import MainPage from '../src/pages/main/MainPage'
import ResetPassword from '../src/pages/auth/ResetPassword'

beforeEach(() => {
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  )
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete globalThis.window?.switchTab
})

test('MainPage renders cleanly with React state tabs and zero inline HTML/JS', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/pages/main/MainPage.jsx'), 'utf8')
  expect(source).not.toMatch(/dangerouslySetInnerHTML/i)
  expect(source).not.toMatch(/\bon[a-z]+\s*=\s*['"]/i)
  expect(source).not.toMatch(/window\.switchTab/)

  const { container } = render(
    <MemoryRouter>
      <MainPage />
    </MemoryRouter>,
  )

  const clientPanel = container.querySelector('#panel-client')
  const transporterPanel = container.querySelector('#panel-transporter')
  expect(clientPanel?.className).toContain('active')
  expect(transporterPanel?.className).not.toContain('active')

  fireEvent.click(screen.getByRole('button', { name: 'For Transporters' }))
  expect(transporterPanel?.className).toContain('active')
  expect(clientPanel?.className).not.toContain('active')

  const navToggle = screen.getByRole('button', { name: 'Toggle navigation menu' })
  expect(navToggle.getAttribute('aria-expanded')).toBe('false')
  fireEvent.click(navToggle)
  expect(navToggle.getAttribute('aria-expanded')).toBe('true')
})

test('ResetPassword handles non-enumerating forgot-password response without masked_email', async () => {
  fetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        success: true,
        message: 'If an account exists, a 6 digit code has been sent to the registered email.',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ),
  )

  render(
    <MemoryRouter>
      <ResetPassword />
    </MemoryRouter>,
  )

  fireEvent.change(screen.getByPlaceholderText(/Enter your email or 13 digit CNIC/i), {
    target: { value: 'driver@example.test' },
  })
  fireEvent.click(screen.getByRole('button', { name: /Request reset/i }))

  await waitFor(() => {
    expect(screen.getByPlaceholderText(/Enter 6 digit OTP/i)).toBeTruthy()
  })
  expect(screen.getByText(/If an account exists, a 6 digit code has been sent/i)).toBeTruthy()
})
