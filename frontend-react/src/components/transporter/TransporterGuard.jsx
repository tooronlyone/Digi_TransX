import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getTransporterDefaultRoute, isTransporterPathAllowed } from './accessControl'

export default function TransporterGuard({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true
    setReady(false)
    const isLocalDemo = sessionStorage.getItem('auth_mode') === 'local-demo'

    function authorize(user) {
      const role = String(user?.role || '').trim().toLowerCase() // ROLE BUG FIX (frontend)
      if (role !== 'transporter' && role !== 'logistics_provider') { // ROLE BUG FIX (frontend)
        const fallbackRedirect = user?.organization_default_route
          || (role === 'client' || role === 'service_seeker' || role === 'everyday_user'
            ? '/client/dashboard'
            : role === 'shopkeeper'
              ? '/shopkeeper/dashboard'
              : role === 'fuel_station_manager'
                ? '/fuelstation/dashboard'
                : '/login')
        navigate(fallbackRedirect, { replace: true }) // ROLE BUG FIX (frontend)
        return false // ROLE BUG FIX (frontend)
      } // ROLE BUG FIX (frontend)
      if (!isTransporterPathAllowed(user, location.pathname)) {
        navigate(getTransporterDefaultRoute(user), { replace: true })
        return false
      }
      return true
    }

    const cached = sessionStorage.getItem('user')
    if (cached) {
      try {
        const parsed = JSON.parse(cached)
        if (parsed && parsed.id) {
          if (!authorize(parsed)) return () => { active = false }
          if (isLocalDemo) {
            setReady(true)
            return () => {
              active = false
            }
          }
        }
      } catch {}
    }

    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (!active) return
        if (data.success && data.user) {
          sessionStorage.setItem('user', JSON.stringify(data.user))
          sessionStorage.setItem('user_id', String(data.user.id))
          sessionStorage.setItem('user_role', data.user.role || '')
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
          if (!authorize({ ...data.user, organization_default_route: data.redirect })) return
          setReady(true)
        } else {
          sessionStorage.clear()
          navigate('/login', { replace: true })
        }
      })
      .catch(() => {
        if (!active) return
        sessionStorage.clear()
        navigate('/login', { replace: true })
      })

    return () => {
      active = false
    }
  }, [location.pathname, navigate])

  if (!ready) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '100vh', flexDirection: 'column', gap: '1rem'
      }}>
        <i className="fas fa-spinner fa-spin" style={{ fontSize: '2rem', color: '#3b82f6' }}></i>
        <p style={{ color: '#64748b', fontSize: '0.95rem' }}>Checking session...</p>
      </div>
    )
  }

  return children
}
