import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
  const [ready, setReady] = useState(false)
  const [user, setUser] = useState(null)

  useEffect(() => {
    let active = true
    const isLocalDemo = sessionStorage.getItem('auth_mode') === 'local-demo'

    const cached = sessionStorage.getItem('user')
    if (cached) {
      try {
        const parsed = JSON.parse(cached)
        if (parsed?.id && isEverydayRole(parsed.role)) {
          // Synchronous hydration from the session cache is intentional (same
          // pattern as useClientAuth) — it avoids a flash before /auth/me.
          /* eslint-disable-next-line react-hooks/set-state-in-effect */
          setUser(parsed)
          setReady(true)
          if (isLocalDemo) {
            return () => { active = false }
          }
        } else if (parsed?.id && isBusinessClientRole(parsed.role)) {
          navigate('/client/dashboard', { replace: true })
          return () => { active = false }
        }
      } catch { /* ignore malformed cached user */ }
    }

    fetch('/auth/me', { credentials: 'same-origin' })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return
        if (data.success && data.user && isEverydayRole(data.user.role)) {
          sessionStorage.setItem('user', JSON.stringify(data.user))
          sessionStorage.setItem('user_id', String(data.user.id))
          sessionStorage.setItem('user_role', data.user.role || '')
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
          setUser(data.user)
          setReady(true)
        } else if (data.success && data.user && isBusinessClientRole(data.user.role)) {
          sessionStorage.setItem('user', JSON.stringify(data.user))
          navigate('/client/dashboard', { replace: true })
        } else if (data.success && data.redirect) {
          sessionStorage.setItem('user', JSON.stringify(data.user || {}))
          navigate(data.redirect, { replace: true })
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

    return () => { active = false }
  }, [navigate])

  return { ready, user }
}
