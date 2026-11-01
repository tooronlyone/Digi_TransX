import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import SignupTerms from '../src/pages/auth/SignupTerms'
import { SignupWizardContext } from '../src/auth/signupWizardContext'
import { createSignupDraftStore } from '../src/auth/signupDraft'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('loads the selected role agreement and requires a deliberate checkbox before details', async () => {
  const store = createSignupDraftStore()
  store.begin({ password: 'test-only' })
  store.selectRole('service_seeker')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    success: true, role: 'service_seeker', role_label: 'Service Seeker', version: 'signup-test-v1',
    sections: [{ title: 'Goods insurance', text: 'Goods insurance is recommended.' }],
  }) }))
  render(<MemoryRouter initialEntries={['/signup/terms']}>
    <SignupWizardContext.Provider value={{ store, draft: store.read() }}>
      <Routes>
        <Route path="/signup/terms" element={<SignupTerms />} />
        <Route path="/signup/details/service-seeker" element={<p>Role details</p>} />
      </Routes>
    </SignupWizardContext.Provider>
  </MemoryRouter>)
  const button = await screen.findByRole('button', { name: 'Agree and continue' })
  expect(button.disabled).toBe(true)
  expect(screen.getByRole('checkbox').checked).toBe(false)
  expect(store.claimSubmission()).toBeNull()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(button)
  await waitFor(() => expect(screen.getByText('Role details')).toBeTruthy())
  expect(store.read().terms).toEqual({ version: 'signup-test-v1', role: 'service_seeker' })
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('prevents acceptance if the agreement cannot load', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Connection unavailable')))
  render(<MemoryRouter><SignupWizardContext.Provider value={{
    draft: { role: 'driver' }, store: createSignupDraftStore(),
  }}><SignupTerms /></SignupWizardContext.Provider></MemoryRouter>)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Agree and continue' })).toBeNull()
})
