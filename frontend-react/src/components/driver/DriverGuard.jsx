import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'

export default function DriverGuard({ children }) {
  const navigate = useNavigate()
  const { status, user } = useAuthVerification()

  useEffect(() => {
    if (!user?.id) return
    if (String(user.role || '').trim().toLowerCase() !== 'driver') {
      navigate(user.redirect || user.organization_default_route || '/login', { replace: true })
    }
  }, [navigate, user])

  if (!user?.id && status === AUTH_STATUSES.CHECKING) {
    return (
      <div className="driver-auth-loading" role="status" aria-live="polite">
        <span className="driver-auth-loading__mark"><i className="fas fa-truck-moving" aria-hidden="true" /></span>
        <div>
          <strong>Opening your driver workspace</strong>
          <p>Verifying secure access…</p>
        </div>
      </div>
    )
  }

  if (status !== AUTH_STATUSES.VERIFIED) return <ShellPageSkeleton />

  return children
}
