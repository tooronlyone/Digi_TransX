import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import OrgShell from './OrgShell'
import { clearOrgPortalState, getOrgAccessToken, orgAuthRequest, orgRequest, setOrgAccessToken } from '../../lib/orgPortal'

export default function OrgLoginPage({
  requiredRole,
  title,
  subtitle,
  dashboardTo,
  registerTo = '',
  registerLabel = 'Create account',
  topLinks = [],
}) {
  const navigate = useNavigate()
  const [banner, setBanner] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({ email: '', password: '' })

  useEffect(() => {
    async function bootstrap() {
      if (!getOrgAccessToken()) return
      try {
        const me = await orgAuthRequest('/api/org/auth/me', { method: 'GET' })
        if (me?.user?.role === requiredRole) {
          navigate(dashboardTo, { replace: true })
          return
        }
      } catch {
        // Ignore and clear stale tokens below.
      }
      clearOrgPortalState()
    }

    bootstrap()
  }, [dashboardTo, navigate, requiredRole])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.email || !form.password) {
      setBanner({ type: 'error', message: 'Email and password are required.' })
      return
    }
    setSubmitting(true)
    setBanner(null)
    try {
      const response = await orgRequest('/api/org/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: form.email.trim().toLowerCase(),
          password: form.password,
        }),
      })
      if (response?.user?.role !== requiredRole) {
        setBanner({ type: 'error', message: 'This account does not belong to the selected org portal.' })
        return
      }
      setOrgAccessToken(response.access_token || '')
      navigate(dashboardTo, { replace: true })
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to login.' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <OrgShell
      title={title}
      subtitle={subtitle}
      banner={banner}
      actions={
        <div className="org-inline-actions">
          {topLinks.map((item) => (
            <Link key={item.to} className="org-link" to={item.to}>
              {item.label}
            </Link>
          ))}
        </div>
      }
    >
      <section className="org-card">
        <form className="org-form-grid" onSubmit={handleSubmit}>
          <div className="org-field half">
            <span>Email</span>
            <input
              type="email"
              placeholder="name@example.com"
              autoComplete="email"
              value={form.email}
              onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
          </div>
          <div className="org-field half">
            <span>Password</span>
            <input
              type="password"
              placeholder="Enter password"
              autoComplete="current-password"
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
          </div>
          <div className="org-col-12 org-inline-actions">
            <button type="submit" className="org-button primary" disabled={submitting}>
              <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-right-to-bracket'}`}></i>
              {submitting ? 'Logging in...' : 'Login'}
            </button>
            {registerTo ? (
              <Link className="org-link" to={registerTo}>
                {registerLabel}
              </Link>
            ) : null}
          </div>
        </form>
      </section>
    </OrgShell>
  )
}
