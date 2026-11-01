import { useNavigate } from 'react-router-dom'
import { cacheAuthPresentation, clearAuthPresentation } from '../auth/presentation'
import { useAuthVerification } from '../auth/AuthVerificationContext'

export function useAuthSession() {
  const navigate = useNavigate()
  const { refreshAuthority } = useAuthVerification()

  async function cacheUser(data) {
    if (!data?.user) return
    cacheAuthPresentation(data)
    window.AuthSession = {
      kind: 'user',
      user: data.user,
      csrf_token: data.csrf_token || '',
      session: data.session || null,
    }
    if (typeof refreshAuthority === 'function') await refreshAuthority({ force: true })
  }

  function clearCache() {
    clearAuthPresentation()
  }

  function resolveRedirect(data) {
    if (data?.redirect) return data.redirect
    if (data?.user?.organization_default_route) return data.user.organization_default_route
    const role = (data?.user?.role || '').trim().toLowerCase()
    const map = {
      client:               '/client/dashboard',
      service_seeker:       '/client/dashboard',
      logistics_provider:   '/transporter/dashboard',
      transporter:          '/transporter/dashboard',
      everyday_user:        '/everyday/dashboard',
      fuel_station_manager: '/fuelstation/dashboard',
      shopkeeper:           '/shopkeeper/dashboard',
    }
    return map[role] || '/transporter/dashboard'
  }

  return { cacheUser, clearCache, resolveRedirect, navigate }
}
