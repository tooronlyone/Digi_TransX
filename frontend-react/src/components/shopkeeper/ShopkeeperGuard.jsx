import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function ShopkeeperGuard({ children }) {
  const navigate = useNavigate()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true

    const cached = sessionStorage.getItem('user')
    if (cached) {
      try {
        const parsed = JSON.parse(cached)
        if (parsed?.id && parsed?.role === 'shopkeeper') {
          setReady(true)
          // still verify with server in background
        }
      } catch (_) {}
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
          if (data.user.role !== 'shopkeeper') {
            navigate(data.redirect || '/login', { replace: true })
            return
          }
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

    return () => { active = false }
  }, [navigate])

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center flex-col gap-3">
        <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-500 text-sm">Checking session...</p>
      </div>
    )
  }

  return children
}
