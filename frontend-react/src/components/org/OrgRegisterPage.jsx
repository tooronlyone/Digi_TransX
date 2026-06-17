import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import OrgShell from './OrgShell'
import { orgRequest } from '../../lib/orgPortal'

export default function OrgRegisterPage({ role, title, subtitle, loginTo, loginLabel = 'Back to login' }) {
  const navigate = useNavigate()
  const [banner, setBanner] = useState(null)
  const [registering, setRegistering] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [resending, setResending] = useState(false)
  const [devOtp, setDevOtp] = useState('')
  const [registerForm, setRegisterForm] = useState({ email: '', password: '' })
  const [verifyForm, setVerifyForm] = useState({ email: '', code: '' })

  async function handleRegister(event) {
    event.preventDefault()
    if (!registerForm.email || !registerForm.password) {
      setBanner({ type: 'error', message: 'Email and password are required.' })
      return
    }
    setRegistering(true)
    setBanner(null)
    setDevOtp('')
    try {
      const response = await orgRequest('/api/org/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email: registerForm.email.trim().toLowerCase(),
          password: registerForm.password,
          role,
        }),
      })
      setVerifyForm((prev) => ({
        ...prev,
        email: registerForm.email.trim().toLowerCase(),
        code: response.dev_otp ? String(response.dev_otp) : prev.code,
      }))
      setDevOtp(response.dev_otp ? String(response.dev_otp) : '')
      setBanner({ type: 'success', message: response.message || 'Account created. Verify your Gmail to continue.' })
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to create account.' })
    } finally {
      setRegistering(false)
    }
  }

  async function handleVerify(event) {
    event.preventDefault()
    if (!verifyForm.email || !verifyForm.code) {
      setBanner({ type: 'error', message: 'Email and verification code are required.' })
      return
    }
    setVerifying(true)
    setBanner(null)
    try {
      await orgRequest('/api/org/auth/verify/confirm', {
        method: 'POST',
        body: JSON.stringify({
          email: verifyForm.email.trim().toLowerCase(),
          code: verifyForm.code.trim(),
        }),
      })
      setBanner({ type: 'success', message: 'Gmail verified. Redirecting to login...' })
      setTimeout(() => navigate(loginTo), 900)
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Verification failed.' })
    } finally {
      setVerifying(false)
    }
  }

  async function handleResend() {
    if (!verifyForm.email) {
      setBanner({ type: 'error', message: 'Enter your email first.' })
      return
    }
    setResending(true)
    setBanner(null)
    setDevOtp('')
    try {
      const response = await orgRequest('/api/org/auth/verify/request', {
        method: 'POST',
        body: JSON.stringify({
          email: verifyForm.email.trim().toLowerCase(),
        }),
      })
      setDevOtp(response.dev_otp ? String(response.dev_otp) : '')
      if (response.dev_otp) {
        setVerifyForm((prev) => ({ ...prev, code: String(response.dev_otp) }))
      }
      setBanner({ type: 'success', message: response.message || 'Verification code issued.' })
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to resend code.' })
    } finally {
      setResending(false)
    }
  }

  return (
    <OrgShell
      title={title}
      subtitle={subtitle}
      banner={banner}
      actions={<Link className="org-link" to={loginTo}>{loginLabel}</Link>}
    >
      <div className="org-auth-split">
        <section className="org-card">
          <h2 className="org-card__title">Create account</h2>
          <p className="org-card__meta">Use a real email address because verification is required before login.</p>

          <form className="org-form-grid" onSubmit={handleRegister}>
            <div className="org-field half">
              <span>Email</span>
              <input
                type="email"
                placeholder="name@example.com"
                autoComplete="email"
                value={registerForm.email}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, email: event.target.value }))}
                required
              />
            </div>
            <div className="org-field half">
              <span>Password</span>
              <input
                type="password"
                placeholder="At least 8 chars with upper/lower/number/symbol"
                autoComplete="new-password"
                value={registerForm.password}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, password: event.target.value }))}
                required
              />
            </div>
            <div className="org-col-12">
              <button type="submit" className="org-button primary" disabled={registering}>
                <i className={`fas ${registering ? 'fa-spinner fa-spin' : 'fa-user-plus'}`}></i>
                {registering ? 'Creating...' : 'Create account'}
              </button>
            </div>
          </form>
        </section>

        <section className="org-card">
          <h2 className="org-card__title">Verify Gmail</h2>
          <p className="org-card__meta">Enter the verification code sent after signup. In development, the preview code appears here.</p>

          <form className="org-form-grid" onSubmit={handleVerify}>
            <div className="org-field half">
              <span>Email</span>
              <input
                type="email"
                placeholder="name@example.com"
                autoComplete="email"
                value={verifyForm.email}
                onChange={(event) => setVerifyForm((prev) => ({ ...prev, email: event.target.value }))}
                required
              />
            </div>
            <div className="org-field half">
              <span>Verification code</span>
              <input
                type="text"
                placeholder="6 digits"
                inputMode="numeric"
                value={verifyForm.code}
                onChange={(event) => setVerifyForm((prev) => ({ ...prev, code: event.target.value }))}
                required
              />
              {devOtp ? <div className="org-field__hint">Dev OTP: {devOtp}</div> : null}
            </div>
            <div className="org-col-12 org-inline-actions">
              <button type="submit" className="org-button primary" disabled={verifying}>
                <i className={`fas ${verifying ? 'fa-spinner fa-spin' : 'fa-envelope-circle-check'}`}></i>
                {verifying ? 'Verifying...' : 'Verify Gmail'}
              </button>
              <button type="button" className="org-button secondary" onClick={handleResend} disabled={resending}>
                <i className={`fas ${resending ? 'fa-spinner fa-spin' : 'fa-rotate-right'}`}></i>
                {resending ? 'Sending...' : 'Resend code'}
              </button>
            </div>
          </form>
        </section>
      </div>
    </OrgShell>
  )
}
