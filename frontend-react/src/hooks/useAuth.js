import { useNavigate } from 'react-router-dom'

export function useAuthSession() {
  const navigate = useNavigate()

  function cacheUser(data) {
    if (!data?.user) return
    sessionStorage.setItem('user', JSON.stringify(data.user))
    sessionStorage.setItem('user_id', String(data.user.id))
    sessionStorage.setItem('user_role', data.user.role || '')
    if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
    if (data.session?.last_active_at)
      sessionStorage.setItem('session_last_active_at', String(data.session.last_active_at))
    window.AuthSession = {
      kind: 'user',
      user: data.user,
      csrf_token: data.csrf_token || '',
      session: data.session || null,
    }
  }

  function clearCache() {
    ;['user','user_id','user_role','admin_id','admin_level','csrf_token',
      'session_last_active_at','session_expires_at','session_inactivity_window_days',
      'signup_basic','signup_role','auth_mode']
      .forEach(k => sessionStorage.removeItem(k))
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
