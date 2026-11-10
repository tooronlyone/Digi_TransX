/* eslint-disable no-empty */
import { useState, useEffect, useCallback } from 'react'
import { Link, useLocation } from 'react-router-dom'
import Notification from '../../components/common/Notification'
import { useAuthSession } from '../../hooks/useAuth'
import digiTransxLogo from '../../assets/brand/digi-transx-logo.png'
import heroBackground from '../../assets/backgrounds/digi-transx-login-background.PNG'
import '../../styles/pages/portal-auth-v2.css'

export default function Login() {
  const { cacheUser, clearCache, resolveRedirect } = useAuthSession()
  const location = useLocation()
  const [form, setForm] = useState({ 
    loginId: localStorage.getItem('dtx_remember_loginId') || '', 
    password: '' 
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })
  const [dismissedAuthNotice, setDismissedAuthNotice] = useState(null)
  
  const authNotice = location.state?.authNotice
  const visibleNotification = notification.message ? notification
    : authNotice !== dismissedAuthNotice && typeof authNotice?.message === 'string'
      ? { type: authNotice.type === 'success' ? 'success' : 'error', message: authNotice.message }
      : { type: '', message: '' }

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
      }
    } catch (_) {}
  }, [cacheUser, clearCache, resolveRedirect])

  useEffect(() => {
    checkLoggedIn()
  }, [checkLoggedIn])

  useEffect(() => {
    document.documentElement.style.overflow = 'hidden'
    document.body.style.overflow = 'hidden'
    return () => {
      document.documentElement.style.overflow = ''
      document.body.style.overflow = ''
    }
  }, [])

  function validate() {
    const e = {}
    if (!form.loginId) {
      e.loginId = 'Email or CNIC is required'
    } else if (!isValidEmail(form.loginId) && !isValidCnic(form.loginId)) {
      e.loginId = 'Please enter a valid email or 13 digit CNIC'
    }
    if (!form.password) {
      e.password = 'Password is required'
    }
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const loginId = form.loginId.trim()
    const password = form.password

    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }
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
        setTimeout(() => {
          window.location.href = resolveRedirect(data)
        }, 900)
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
    <main className="dtx-auth-page dtx-auth-page--login" style={{ backgroundImage: `url(${heroBackground})` }}>
      <section className="dtx-login-story" aria-label="Digi_TransX logistics platform">
        <Link to="/" className="dtx-login-brand dtx-login-brand--story" aria-label="Digi_TransX home">
          <img
            src={digiTransxLogo}
            alt=""
            className="dtx-login-brand__mark"
          />
          <span className="dtx-login-brand__copy">
            <span className="dtx-login-brand__name">
              Digi_Trans<span>X</span>
            </span>
            <span className="dtx-login-brand__tagline">A D-HAG Project</span>
          </span>
        </Link>

        <span className="dtx-login-story__accent" aria-hidden="true" />
        <h2 className="dtx-login-story__title">
          Pakistan&rsquo;s Intelligent
          <span><strong>Logistics</strong> Operating System</span>
        </h2>
        <p className="dtx-login-story__copy">
          Book, dispatch, track, and manage your freight &mdash; all in one platform.
        </p>
      </section>

      <section className="dtx-auth-panel" aria-label="Sign in">
        <Notification
          type={visibleNotification.type}
          message={visibleNotification.message}
          onClose={() => {
            setNotification({ type: '', message: '' })
            setDismissedAuthNotice(authNotice)
          }}
        />

        <div className="dtx-auth-card dtx-login-card">
          <header className="dtx-card-header dtx-login-card__header">
            <Link to="/" className="dtx-login-brand" aria-label="Digi_TransX home">
              <img
                src={digiTransxLogo}
                alt=""
                className="dtx-login-brand__mark"
              />
              <span className="dtx-login-brand__copy">
                <span className="dtx-login-brand__name">
                  Digi_Trans<span>X</span>
                </span>
                <span className="dtx-login-brand__tagline">A D-HAG Project</span>
              </span>
            </Link>
            <h1 className="dtx-card-title">Welcome Back</h1>
            <p className="dtx-card-subtitle">Sign in to your Digi_TransX account.</p>
          </header>

          <form className="dtx-form" onSubmit={handleSubmit} noValidate>
            <div className="dtx-field">
              <label htmlFor="loginId" className="dtx-sr-only">Email or CNIC</label>
              <div className={`dtx-input-wrap ${errors.loginId ? 'dtx-input-wrap--error' : ''}`}>
                <i className="far fa-envelope dtx-input-icon" aria-hidden="true" />
                <input
                  id="loginId"
                  name="loginId"
                  type="text"
                  placeholder="Email or CNIC"
                  value={form.loginId}
                  onChange={(e) => setForm((f) => ({ ...f, loginId: e.target.value }))}
                  className="dtx-input"
                  autoComplete="username"
                  autoFocus
                  aria-invalid={!!errors.loginId}
                  aria-describedby={errors.loginId ? 'loginId-error' : undefined}
                />
              </div>
              {errors.loginId && (
                <p id="loginId-error" className="dtx-error-msg">
                  <i className="fas fa-circle-exclamation" aria-hidden="true" /> {errors.loginId}
                </p>
              )}
            </div>

            <div className="dtx-field">
              <label htmlFor="password" className="dtx-sr-only">Password</label>
              <div className={`dtx-input-wrap ${errors.password ? 'dtx-input-wrap--error' : ''}`}>
                <i className="fas fa-lock dtx-input-icon" aria-hidden="true" />
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Password"
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  className="dtx-input"
                  autoComplete="current-password"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'password-error' : undefined}
                />
                <button
                  type="button"
                  className="dtx-toggle-pass-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  <i className={`far ${showPassword ? 'fa-eye-slash' : 'fa-eye'}`} aria-hidden="true" />
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="dtx-error-msg">
                  <i className="fas fa-circle-exclamation" aria-hidden="true" /> {errors.password}
                </p>
              )}
              <Link
                className="dtx-forgot-link dtx-login-forgot"
                to={`/reset-password${form.loginId ? '?loginId=' + encodeURIComponent(form.loginId) : ''}`}
              >
                Forgot password?
              </Link>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="dtx-btn-primary"
              aria-label={loading ? 'Logging in' : 'Login'}
            >
              {loading ? (
                <span className="dtx-btn-spinner" aria-hidden="true" />
              ) : (
                <>
                  <i className="fas fa-arrow-right" aria-hidden="true" />
                  <span>Login</span>
                </>
              )}
            </button>

            <div className="dtx-divider" aria-hidden="true">
              <span>or</span>
            </div>

            <div className="dtx-card-footer">
              <p>
                Don&rsquo;t have an account?{' '}
                <Link to="/signup">Create Account</Link>
              </p>
            </div>
          </form>
        </div>
      </section>
    </main>
  )
}
