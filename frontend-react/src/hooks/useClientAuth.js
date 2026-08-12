/* eslint-disable no-unused-vars, no-empty, react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { clearAuthPresentation } from '../auth/presentation'

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
  const [ready, setReady] = useState(false)
  const [user, setUser] = useState(null)

  useEffect(() => {
    let active = true
    setReady(false)
    const isLocalDemo = sessionStorage.getItem('auth_mode') === 'local-demo'

    const cached = sessionStorage.getItem('user')
    if (cached) {
      try {
        const parsed = JSON.parse(cached)
        if (parsed?.id && isClientRole(parsed.role)) {
          setUser(parsed)
          setReady(true)
          if (isLocalDemo) {
            return () => {
              active = false
            }
          }
        } else if (parsed?.id && isEverydayRole(parsed.role)) {
          navigate('/everyday/dashboard', { replace: true })
          return () => {
            active = false
          }
        } else if (parsed?.id) {
          navigate(parsed?.organization_default_route || '/login', { replace: true })
          return () => {
            active = false
          }
        }
      } catch (_) {}
    }

    fetch('/auth/me', { credentials: 'same-origin' })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return
        if (data.success && data.user && isClientRole(data.user.role)) {
          sessionStorage.setItem('user', JSON.stringify(data.user))
          sessionStorage.setItem('user_id', String(data.user.id))
          sessionStorage.setItem('user_role', data.user.role || '')
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
          setUser(data.user)
          setReady(true)
        } else if (data.success && data.user && isEverydayRole(data.user.role)) {
          sessionStorage.setItem('user', JSON.stringify(data.user))
          navigate('/everyday/dashboard', { replace: true })
        } else if (data.success && data.redirect) {
          sessionStorage.setItem('user', JSON.stringify(data.user || {}))
          navigate(data.redirect, { replace: true })
        } else {
          clearAuthPresentation()
          navigate('/login', { replace: true })
        }
      })
      .catch(() => {
        if (!active) return
        clearAuthPresentation()
        navigate('/login', { replace: true })
      })

    return () => {
      active = false
    }
  }, [navigate])

  return { ready, user }
}
