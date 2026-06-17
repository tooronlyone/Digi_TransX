import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AuthCard from '../../components/common/AuthCard'
import Notification from '../../components/common/Notification'
import { useAuthSession } from '../../hooks/useAuth'

export default function Unlock() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [status, setStatus] = useState('Checking trusted-device access...')
  const [showMpin, setShowMpin] = useState(false)
  const [mpin, setMpin] = useState('')
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })
  const [maskedEmail, setMaskedEmail] = useState('')

  useEffect(() => {
    fetch('/auth/fast-login/options', { credentials: 'include' })
      .then(response => response.json())
      .then(data => {
        if (data?.available) {
          setMaskedEmail(data.masked_email || '')
          setStatus('Enter your 4 digit MPIN for the last logged-in account on this device.')
          setShowMpin(true)
        } else {
          setStatus('Fast login is not available on this device yet.')
        }
      })
      .catch(() => setStatus('Could not load fast login options.'))
  }, [])

  async function handleMpinSubmit(event) {
    event.preventDefault()
    if (!/^\d{4}$/.test(mpin)) {
      setNotification({ type: 'error', message: 'Enter your 4 digit MPIN.' })
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/auth/fast-login/mpin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ mpin }),
      })
      const data = await response.json()
      if (response.ok && data.success) {
        cacheUser(data)
        setNotification({ type: 'success', message: 'Unlocked! Redirecting...' })
        setTimeout(() => { window.location.href = resolveRedirect(data) }, 900)
      } else {
        setNotification({ type: 'error', message: data.message || 'Invalid MPIN.' })
      }
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Fast Login" subtitle={status}>
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />

      {maskedEmail && (
        <p className="mb-4 text-center text-sm text-gray-500">
          Trusted account: <strong>{maskedEmail}</strong>
        </p>
      )}

      {showMpin && (
        <form onSubmit={handleMpinSubmit} className="mb-4">
          <label htmlFor="mpin" className="block mb-2 font-semibold text-gray-700 text-sm">4 Digit MPIN</label>
          <input
            id="mpin"
            type="password"
            inputMode="numeric"
            maxLength={4}
            placeholder="Enter 4 digit MPIN"
            value={mpin}
            onChange={event => setMpin(event.target.value.replace(/\D/g, '').slice(0, 4))}
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg text-base outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 mb-3"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {loading ? 'Unlocking...' : 'Unlock'}
          </button>
        </form>
      )}

      <div className="text-center">
        <Link to="/login" className="text-gray-500 text-sm hover:text-blue-500 hover:underline">
          Login with Password
        </Link>
      </div>
    </AuthCard>
  )
}
