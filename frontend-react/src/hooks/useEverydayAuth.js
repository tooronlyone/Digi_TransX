import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_STATUSES, useAuthVerification } from '../auth/AuthVerificationContext'

// The /everyday/* surface is for everyday individual users only. Business
// service seekers are sent to their /client/* surface; everyone else to login.
function isEverydayRole(role) {
  return String(role || '').trim().toLowerCase() === 'everyday_user'
}

function isBusinessClientRole(role) {
  const value = String(role || '').trim().toLowerCase()
  return value === 'client' || value === 'service_seeker'
}

export default function useEverydayAuth() {
  const navigate = useNavigate()
  const { status, user } = useAuthVerification()

  useEffect(() => {
    if (!user?.id) return
    if (isBusinessClientRole(user.role)) {
      navigate('/client/dashboard', { replace: true })
    } else if (!isEverydayRole(user.role)) {
      navigate(user.organization_default_route || '/login', { replace: true })
    }
  }, [navigate, user])

  return { ready: Boolean(user?.id) || status !== AUTH_STATUSES.CHECKING, user, status }
}
