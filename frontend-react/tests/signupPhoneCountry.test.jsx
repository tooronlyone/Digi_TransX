import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Signup from '../src/pages/auth/Signup'
import { SignupWizardContext } from '../src/auth/signupWizardContext'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderSignup(draft = {}, store = { begin: vi.fn() }) {
  return render(
    <MemoryRouter initialEntries={['/signup']}>
      <SignupWizardContext.Provider value={{ draft, store }}>
        <Signup />
      </SignupWizardContext.Provider>
    </MemoryRouter>
  )
}

describe('Signup Phone Number with Country Selection and Digit Limits', () => {
  it('defaults to Pakistan with 11 digits limit', () => {
    renderSignup()

    const countrySelect = screen.getByLabelText(/Select Country/i)
    expect(countrySelect.value).toBe('PK')

    const phoneInput = screen.getByLabelText(/Phone Number/i)
    expect(phoneInput.getAttribute('maxLength')).toBe('11')
    expect(phoneInput.getAttribute('placeholder')).toBe('03001234567')

    expect(screen.getByText(/Limit: 11 digits/i)).toBeTruthy()
    expect(screen.getByText(/0 \/ 11 digits/i)).toBeTruthy()
  })

  it('restricts Pakistan phone input to digits only and at most 11 digits', () => {
    renderSignup()

    const phoneInput = screen.getByLabelText(/Phone Number/i)

    // Type letters and characters - non-digits stripped
    fireEvent.change(phoneInput, { target: { value: 'abc03001234567xyz' } })
    expect(phoneInput.value).toBe('03001234567')
    expect(phoneInput.value.length).toBe(11)

    // Attempting to exceed 11 digits is capped at 11
    fireEvent.change(phoneInput, { target: { value: '030012345678999' } })
    expect(phoneInput.value).toBe('03001234567')
    expect(phoneInput.value.length).toBe(11)

    expect(screen.getByText(/11 \/ 11 digits/i)).toBeTruthy()
  })

  it('updates digit limit and truncates input when selecting another country', () => {
    renderSignup()

    const countrySelect = screen.getByLabelText(/Select Country/i)
    const phoneInput = screen.getByLabelText(/Phone Number/i)

    // Type 11 digits for Pakistan
    fireEvent.change(phoneInput, { target: { value: '03001234567' } })
    expect(phoneInput.value).toBe('03001234567')

    // Switch to United States (10 digits limit)
    fireEvent.change(countrySelect, { target: { value: 'US' } })

    expect(countrySelect.value).toBe('US')
    expect(phoneInput.getAttribute('maxLength')).toBe('10')
    // Automatically truncated from 11 to 10 digits
    expect(phoneInput.value).toBe('0300123456')
    expect(phoneInput.value.length).toBe(10)
    expect(screen.getByText(/10 \/ 10 digits/i)).toBeTruthy()

    // Switch to Qatar (8 digits limit)
    fireEvent.change(countrySelect, { target: { value: 'QA' } })
    expect(phoneInput.getAttribute('maxLength')).toBe('8')
    expect(phoneInput.value).toBe('03001234')
    expect(phoneInput.value.length).toBe(8)
    expect(screen.getByText(/8 \/ 8 digits/i)).toBeTruthy()
  })

  it('validates Pakistan phone number requiring exactly 11 digits', () => {
    renderSignup()

    const nameInput = screen.getByLabelText(/Full Name/i)
    const emailInput = screen.getByLabelText(/Email Address/i)
    const phoneInput = screen.getByLabelText(/Phone Number/i)
    const cnicInput = screen.getByLabelText(/CNIC Number/i)
    const passwordInput = screen.getByLabelText(/Password/i)
    const submitBtn = screen.getByRole('button', { name: /Continue to select your role/i })

    fireEvent.change(nameInput, { target: { value: 'Test User' } })
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(cnicInput, { target: { value: '1234567890123' } })
    fireEvent.change(passwordInput, { target: { value: 'StrongPass123!' } })

    // Only 10 digits entered for Pakistan
    fireEvent.change(phoneInput, { target: { value: '0300123456' } })
    fireEvent.click(submitBtn)

    expect(screen.getByText(/Pakistan phone number must be exactly 11 digits/i)).toBeTruthy()

    // Enter the complete 11 digits
    fireEvent.change(phoneInput, { target: { value: '03001234567' } })
    expect(screen.queryByText(/Pakistan phone number must be exactly 11 digits/i)).toBeNull()
  })

  it('passes country and phone to store on valid submission', () => {
    const store = { begin: vi.fn() }
    renderSignup({}, store)

    const nameInput = screen.getByLabelText(/Full Name/i)
    const emailInput = screen.getByLabelText(/Email Address/i)
    const phoneInput = screen.getByLabelText(/Phone Number/i)
    const cnicInput = screen.getByLabelText(/CNIC Number/i)
    const passwordInput = screen.getByLabelText(/Password/i)
    const submitBtn = screen.getByRole('button', { name: /Continue to select your role/i })

    fireEvent.change(nameInput, { target: { value: 'Ali Khan' } })
    fireEvent.change(emailInput, { target: { value: 'ali@example.com' } })
    fireEvent.change(phoneInput, { target: { value: '03001234567' } })
    fireEvent.change(cnicInput, { target: { value: '3520112345671' } })
    fireEvent.change(passwordInput, { target: { value: 'Secret123!' } })

    fireEvent.click(submitBtn)

    expect(store.begin).toHaveBeenCalledWith({
      name: 'Ali Khan',
      email: 'ali@example.com',
      country: 'PK',
      localPhone: '03001234567',
      phone: '03001234567',
      password: 'Secret123!',
      cnic: '3520112345671',
    })
  })
})
