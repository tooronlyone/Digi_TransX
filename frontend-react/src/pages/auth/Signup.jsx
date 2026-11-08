import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthCard from '../../components/common/AuthCard'
import InputField from '../../components/common/InputField'
import Notification from '../../components/common/Notification'
import '../../styles/pages/auth.css'
import { useSignupWizard } from '../../auth/signupWizardContext'
import { COUNTRIES, DEFAULT_COUNTRY_CODE, getCountryByCode } from '../../constants/countries'

function getPasswordStrength(password) {
  let score = 0
  if (password.length >= 8) score++
  if (/[A-Z]/.test(password)) score++
  if (/[0-9]/.test(password)) score++
  if (/[^A-Za-z0-9]/.test(password)) score++
  return score
}

const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong']
const strengthColors = ['', 'bg-red-400', 'bg-yellow-400', 'bg-blue-400', 'bg-green-500']

export default function Signup() {
  const navigate = useNavigate()
  const { draft, store } = useSignupWizard()
  const [form, setForm] = useState(() => ({
    name: draft.basic?.name || '',
    email: draft.basic?.email || '',
    country: draft.basic?.country || DEFAULT_COUNTRY_CODE,
    phone: draft.basic?.localPhone || draft.basic?.phone || '',
    password: '',
    cnic: draft.basic?.cnic || '',
  }))
  const [errors, setErrors] = useState({})
  const [notification, setNotification] = useState(() => ({
    type: draft.failure ? 'error' : '',
    message: draft.failure || '',
  }))
  const strength = getPasswordStrength(form.password)
  const currentCountry = getCountryByCode(form.country)

  function handlePhoneChange(event) {
    const raw = event.target.value
    let digits = raw.replace(/\D/g, '')

    // If pasted or typed with leading 92 for Pakistan, normalize to local format starting with 0
    if (form.country === 'PK' && digits.startsWith('92') && digits.length > 10) {
      digits = '0' + digits.slice(2)
    }

    const limited = digits.slice(0, currentCountry.maxDigits)
    setForm(current => ({ ...current, phone: limited }))

    if (errors.phone) {
      setErrors(prev => {
        const next = { ...prev }
        delete next.phone
        return next
      })
    }
  }

  function handleCountryChange(event) {
    const nextCode = event.target.value
    const nextCountry = getCountryByCode(nextCode)
    setForm(current => ({
      ...current,
      country: nextCode,
      phone: current.phone.slice(0, nextCountry.maxDigits),
    }))

    if (errors.phone) {
      setErrors(prev => {
        const next = { ...prev }
        delete next.phone
        return next
      })
    }
  }

  function validate() {
    const nextErrors = {}
    if (!form.name.trim()) nextErrors.name = 'Full name is required'
    if (!form.email) nextErrors.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) nextErrors.email = 'Invalid email address'

    if (!form.phone) {
      nextErrors.phone = 'Phone number is required'
    } else {
      const digits = form.phone.replace(/\D/g, '')
      if (currentCountry.minDigits === currentCountry.maxDigits) {
        if (digits.length !== currentCountry.maxDigits) {
          nextErrors.phone = `${currentCountry.name} phone number must be exactly ${currentCountry.maxDigits} digits`
        }
      } else {
        if (digits.length < currentCountry.minDigits || digits.length > currentCountry.maxDigits) {
          nextErrors.phone = `${currentCountry.name} phone number must be ${currentCountry.minDigits} to ${currentCountry.maxDigits} digits`
        }
      }
    }

    if (!form.password) nextErrors.password = 'Password is required'
    else if (form.password.length < 8) nextErrors.password = 'Password must be at least 8 characters'
    if (!form.cnic.trim()) nextErrors.cnic = 'CNIC is required'
    else if (!/^\d{13}$/.test(form.cnic.replace(/\D/g, ''))) nextErrors.cnic = 'CNIC must be 13 digits'
    return nextErrors
  }

  function handleNext(event) {
    event.preventDefault()
    const nextErrors = validate()
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    const trimmedPhone = form.phone.trim()
    const fullPhone = form.country === 'PK'
      ? trimmedPhone
      : (trimmedPhone.startsWith('+') ? trimmedPhone : `${currentCountry.dialCode}${trimmedPhone}`)

    setErrors({})
    store.begin({
      name: form.name.trim(),
      email: form.email.trim().toLowerCase(),
      country: form.country,
      localPhone: trimmedPhone,
      phone: fullPhone,
      password: form.password,
      cnic: form.cnic.trim(),
    })
    navigate('/signup/role')
  }

  const setField = (field) => (event) => setForm(current => ({ ...current, [field]: event.target.value }))

  return (
    <AuthCard pageClassName="signup-page" useBrandLogo title="Create Account" subtitle="Join DigiTransX - Pakistan's transport platform">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />

      <div className="auth-steps signup-steps" aria-label="Signup progress">
        <div className="auth-step auth-step--active">
          <span>1</span>
          <strong>Basic Info</strong>
        </div>
        <div className="auth-step-line" />
        <div className="auth-step">
          <span>2</span>
          <strong>Select Role</strong>
        </div>
        <div className="auth-step-line" />
        <div className="auth-step">
          <span>3</span>
          <strong>Terms</strong>
        </div>
        <div className="auth-step-line" />
        <div className="auth-step">
          <span>4</span>
          <strong>Details</strong>
        </div>
      </div>

      <form className="signup-form" onSubmit={handleNext}>
        <div className="signup-form-grid">
          <section className="signup-form-section" aria-labelledby="signup-identity-title">
            <div className="signup-form-section__heading">
              <span className="signup-form-section__icon" aria-hidden="true">
                <i className="fas fa-id-card" />
              </span>
              <div>
                <h2 id="signup-identity-title">Personal &amp; contact details</h2>
                <p>Tell us who will use this account.</p>
              </div>
            </div>

            <div className="signup-form-section__fields">
              <div className="auth-form-field signup-name-field">
                <label htmlFor="name">Full Name</label>
                <input
                  id="name"
                  type="text"
                  autoComplete="name"
                  placeholder="Enter your full name"
                  value={form.name}
                  onChange={setField('name')}
                  className={`auth-form-input ${errors.name ? 'border-red-400' : ''}`}
                />
                {errors.name && <p className="auth-error">{errors.name}</p>}
              </div>

              <div className="auth-form-field signup-phone-field">
                <div className="signup-field-header">
                  <label htmlFor="phone">Phone Number</label>
                  <span className={`auth-digit-limit-badge ${currentCountry.code === 'PK' ? 'is-pk' : ''}`}>
                    {currentCountry.minDigits === currentCountry.maxDigits
                      ? `Limit: ${currentCountry.maxDigits} digits`
                      : `Limit: ${currentCountry.minDigits}-${currentCountry.maxDigits} digits`}
                  </span>
                </div>

                <div className="signup-phone-input-row">
                  <div className="signup-country-select-wrapper">
                    <select
                      id="country"
                      aria-label="Select Country"
                      value={form.country}
                      onChange={handleCountryChange}
                      className="auth-form-select signup-country-select"
                    >
                      {COUNTRIES.map(c => (
                        <option key={c.code} value={c.code}>
                          {c.flag} {c.name} ({c.dialCode})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="signup-phone-input-wrapper">
                    <input
                      id="phone"
                      type="tel"
                      inputMode="numeric"
                      autoComplete="tel"
                      placeholder={currentCountry.placeholder}
                      value={form.phone}
                      onChange={handlePhoneChange}
                      maxLength={currentCountry.maxDigits}
                      className={`auth-form-input signup-phone-input ${errors.phone ? 'border-red-400' : ''}`}
                    />
                  </div>
                </div>

                {errors.phone ? (
                  <p className="auth-error">{errors.phone}</p>
                ) : (
                  <div className="signup-phone-footer">
                    <p className="auth-help">
                      {currentCountry.code === 'PK'
                        ? 'Pakistan format: 11 digits (e.g. 03001234567)'
                        : `Allowed format: ${currentCountry.formatExample}`}
                    </p>
                    <span className={`signup-phone-counter ${form.phone.length === currentCountry.maxDigits ? 'is-limit' : ''}`}>
                      {form.phone.length} / {currentCountry.maxDigits} digits
                    </span>
                  </div>
                )}
              </div>

              <div className="auth-form-field signup-cnic-field">
                <label htmlFor="cnic">CNIC Number</label>
                <input
                  id="cnic"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="13 digits, no dashes"
                  value={form.cnic}
                  onChange={setField('cnic')}
                  maxLength={13}
                  className={`auth-form-input ${errors.cnic ? 'border-red-400' : ''}`}
                />
                {errors.cnic && <p className="auth-error">{errors.cnic}</p>}
                <p className="auth-help">Enter 13 digits without dashes.</p>
              </div>
            </div>
          </section>

          <section className="signup-form-section" aria-labelledby="signup-access-title">
            <div className="signup-form-section__heading">
              <span className="signup-form-section__icon" aria-hidden="true">
                <i className="fas fa-shield-halved" />
              </span>
              <div>
                <h2 id="signup-access-title">Account security</h2>
                <p>Use your email and a strong password to sign in.</p>
              </div>
            </div>

            <div className="signup-form-section__fields signup-form-section__fields--access">
              <InputField
                label="Email Address"
                id="email"
                type="email"
                autoComplete="email"
                placeholder="Enter your email"
                value={form.email}
                onChange={setField('email')}
                error={errors.email}
              />

              <div className="auth-form-field signup-password-field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Create a strong password"
                  value={form.password}
                  onChange={setField('password')}
                  className={`auth-form-input ${errors.password ? 'border-red-400' : ''}`}
                />
                {form.password && (
                  <div className="auth-strength">
                    <div className="auth-strength__bars" aria-hidden="true">
                      {[1, 2, 3, 4].map(index => (
                        <span
                          key={index}
                          className={`auth-strength__bar auth-strength__bar--${index <= strength ? strengthLabels[strength].toLowerCase() : 'empty'} ${index <= strength ? strengthColors[strength] : 'bg-gray-200'}`}
                        />
                      ))}
                    </div>
                    <p className="auth-help">{strengthLabels[strength]}</p>
                  </div>
                )}
                {errors.password && <p className="auth-error">{errors.password}</p>}
                <p className="auth-help">At least 8 characters with letters and numbers.</p>
              </div>
            </div>
          </section>
        </div>

        <button
          type="submit"
          className="auth-submit"
        >
          Continue to select your role
          <i className="fas fa-arrow-right" aria-hidden="true" />
        </button>

        <div className="auth-card-footer">
          <p>
            Already have an account?{' '}
            <Link to="/login">Login here</Link>
          </p>
        </div>
      </form>
    </AuthCard>
  )
}
