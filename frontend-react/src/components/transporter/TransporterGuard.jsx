import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getTransporterDefaultRoute, isTransporterPathAllowed } from './accessControl'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'

export default function TransporterGuard({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { status, user } = useAuthVerification()

  useEffect(() => {
    if (!user?.id) return
    const role = String(user.role || '').trim().toLowerCase()
    if (role !== 'transporter' && role !== 'logistics_provider') {
      const fallbackRedirect = user.organization_default_route
        || (role === 'client' || role === 'service_seeker' ? '/client/dashboard'
          : role === 'everyday_user' ? '/everyday/dashboard'
            : '/login')
      navigate(fallbackRedirect, { replace: true })
      return
    }
    if (!isTransporterPathAllowed(user, location.pathname)) {
      navigate(getTransporterDefaultRoute(user), { replace: true })
    }
  }, [location.pathname, navigate, user])

  if (!user?.id && status === AUTH_STATUSES.CHECKING) {
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
