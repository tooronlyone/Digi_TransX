import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_STATUSES, useAuthVerification } from '../auth/AuthVerificationContext'

// /client/* is the BUSINESS service-seeker surface only. Everyday users have
// their own /everyday/* surface and are redirected there.
function isClientRole(role) {
  const value = String(role || '').trim().toLowerCase()
  return value === 'client' || value === 'service_seeker'
}

function isEverydayRole(role) {
  return String(role || '').trim().toLowerCase() === 'everyday_user'
}

export default function useClientAuth() {
  const navigate = useNavigate()
  const { status, user } = useAuthVerification()

  useEffect(() => {
    if (!user?.id) return
    if (isEverydayRole(user.role)) {
      navigate('/everyday/dashboard', { replace: true })
    } else if (!isClientRole(user.role)) {
      navigate(user.organization_default_route || '/login', { replace: true })
    }
  }, [navigate, user])

  return { ready: Boolean(user?.id) || status !== AUTH_STATUSES.CHECKING, user, status }
}
