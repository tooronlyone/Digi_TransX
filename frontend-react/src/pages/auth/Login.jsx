/* eslint-disable no-unused-vars, no-empty, react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import Notification from '../../components/common/Notification'
import { useAuthSession } from '../../hooks/useAuth'
import '../../styles/pages/auth.css'

export default function Login() {
  const { cacheUser, clearCache, resolveRedirect, navigate } = useAuthSession()
  const [form, setForm] = useState({ loginId: '', password: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })
  const [showFastLogin, setShowFastLogin] = useState(false)

  const isValidEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
  const isValidCnic = (v) => /^\d{13}$/.test(String(v || '').replace(/\D/g, ''))

  const checkLoggedIn = useCallback(async () => {
    try {
      const res = await fetch('/auth/me', { credentials: 'include' })
      const data = await res.json()
      if (res.ok && data.success && data.user) {
        cacheUser(data)
        window.location.href = resolveRedirect(data)
      } else {
        clearCache()
        const optRes = await fetch('/auth/fast-login/options', { credentials: 'include' })
        const optData = await optRes.json()
        setShowFastLogin(!!(optRes.ok && optData?.available))
      }
    } catch (_) {}
  }, [])

  useEffect(() => { checkLoggedIn() }, [checkLoggedIn])

  function validate() {
    const e = {}
    if (!form.loginId) e.loginId = 'Email or CNIC is required'
    else if (!isValidEmail(form.loginId) && !isValidCnic(form.loginId))
      e.loginId = 'Please enter a valid email or 13 digit CNIC'
    if (!form.password) e.password = 'Password is required'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const loginId = form.loginId.trim()
    const password = form.password.trim()

    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setLoading(true)
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ loginId, password })
      })
      const data = await res.json()
      if (res.ok && data.success) {
        cacheUser(data)
        setNotification({ type: 'success', message: 'Login successful! Redirecting...' })
        setTimeout(() => { window.location.href = resolveRedirect(data) }, 1000)
        return
      }
      const field = data.field || 'password'
      const msg = data.message || 'Login failed. Please try again.'
      setErrors({ [field]: msg })
      setNotification({ type: 'error', message: msg })
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error. Please check your connection.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-shell__hero" aria-label="Digi_TransX freight platform">
        <div className="auth-shell__blob auth-shell__blob--blue" />
        <div className="auth-shell__blob auth-shell__blob--indigo" />

        <div className="auth-shell__story">
          <BrandMark className="auth-shell__hero-logo" />
          <h2>Move freight, fearlessly.</h2>
          <p>Pakistan's freight network &mdash; dispatched, tracked, and settled from one screen.</p>

          <div className="auth-shell__stats" aria-label="Platform stats">
            <div>
              <b>2,400+</b>
              <span>Verified trucks</span>
            </div>
            <div>
              <b>180k</b>
              <span>Jobs completed</span>
            </div>
            <div>
              <b>4.8&#9733;</b>
              <span>Avg. shipper rating</span>
            </div>
          </div>
        </div>
      </section>

      <section className="auth-shell__panel" aria-label="Sign in">
        <Notification
          type={notification.type}
          message={notification.message}
          onClose={() => setNotification({ type: '', message: '' })}
        />

        <div className="auth-shell__card">
          <div className="auth-shell__brand">
            <BrandMark className="auth-shell__brand-logo" />
            <span>Digi_TransX</span>
          </div>

          <div className="auth-shell__intro">
            <h1>Welcome back</h1>
            <p>Sign in to your account. Backend will decide the right portal for you.</p>
          </div>

          <form className="auth-shell__form" onSubmit={handleSubmit}>
            <div className="auth-shell__field">
                <label htmlFor="loginId">Email or CNIC</label>
              <input
                id="loginId"
                type="text"
                placeholder="Enter your email or 13 digit CNIC"
                value={form.loginId}
                onChange={e => setForm(f => ({ ...f, loginId: e.target.value }))}
                className={errors.loginId ? 'auth-shell__input auth-shell__input--error' : 'auth-shell__input'}
                aria-invalid={!!errors.loginId}
                aria-describedby={errors.loginId ? 'loginId-error' : undefined}
              />
              {errors.loginId && <p id="loginId-error" className="auth-shell__err-msg">{errors.loginId}</p>}
            </div>

            <div className="auth-shell__field">
              <div className="auth-shell__label-row">
                <label htmlFor="password">Password</label>
                <Link to={`/reset-password${form.loginId ? '?loginId=' + encodeURIComponent(form.loginId) : ''}`}>
                  Forgot password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className={errors.password ? 'auth-shell__input auth-shell__input--error' : 'auth-shell__input'}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? 'password-error' : undefined}
              />
              {errors.password && <p id="password-error" className="auth-shell__err-msg">{errors.password}</p>}
            </div>

            <button type="submit" disabled={loading} className="auth-shell__primary">
              {loading && <span className="auth-shell__spinner" aria-hidden="true" />}
              {!loading && <i className="fas fa-arrow-right-to-bracket" aria-hidden="true"></i>}
              {loading ? 'Signing in...' : 'Sign In'}
            </button>

            {showFastLogin && (
              <>
                <div className="auth-shell__divider">
                  <span>or</span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/unlock?source=user')}
                  className="auth-shell__ghost"
                >
                  <i className="fas fa-fingerprint" aria-hidden="true"></i>
                  Use Fast Login
                </button>
              </>
            )}

            <p className="auth-shell__footer">
              Don't have an account?{' '}
              <Link to="/signup">Create an account</Link>
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}

function BrandMark({ className }) {
  return (
    <div className={className} aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path d="M5 9 L13 9 L19 23 L27 23" />
        <path d="M27 9 L19 9 L13 23 L5 23" />
      </svg>
    </div>
  )
}
