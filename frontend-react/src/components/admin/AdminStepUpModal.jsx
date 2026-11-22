import { useEffect, useState } from 'react'
import { registerAdminStepUpHandler } from './adminStepUpBridge'

async function resolveCsrfToken() {
  const stored = sessionStorage.getItem('csrf_token')
  if (stored) return stored
  const response = await fetch('/auth/csrf-token', { credentials: 'same-origin' })
  const json = await response.json().catch(() => ({}))
  if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
  return json.csrf_token || ''
}

export default function AdminStepUpModal() {
  const [challenge, setChallenge] = useState(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    return registerAdminStepUpHandler((action) => {
      return new Promise((resolve, reject) => {
        setPassword('')
        setError('')
        setBusy(false)
        setChallenge({ action, resolve, reject })
      })
    })
  }, [])

  if (!challenge) return null

  function handleCancel() {
    if (busy) return
    const current = challenge
    setChallenge(null)
    setPassword('')
    setError('')
    current.reject(new Error('Administrator reauthentication was cancelled.'))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (busy || !password) return
    setBusy(true)
    setError('')
    try {
      const csrfToken = await resolveCsrfToken()
      const response = await fetch('/api/admin/step-up', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          password,
          action: {
            action_key: challenge.action.action_key,
            resource_type: challenge.action.resource_type,
            resource_id: challenge.action.resource_id,
            request_fingerprint: challenge.action.request_fingerprint,
          },
        }),
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false || !json.step_up_proof) {
        throw new Error(json.message || `Verification failed (${response.status})`)
      }
      if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
      const current = challenge
      setChallenge(null)
      setPassword('')
      setError('')
      current.resolve(json.step_up_proof)
    } catch (err) {
      setError(err.message || 'Could not verify administrator password.')
    } finally {
      setBusy(false)
    }
  }

  const { action } = challenge
  const targetDetail = action?.resource_id && action.resource_id > 0
    ? `${action.resource_type || 'resource'} #${action.resource_id}`
    : (action?.resource_type || 'platform')

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-step-up-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2500,
        display: 'grid',
        placeItems: 'center',
        background: 'rgba(15, 23, 42, 0.55)',
        padding: 16,
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: '#fff',
          borderRadius: 16,
          border: '1px solid #e2e8f0',
          boxShadow: '0 20px 45px rgba(15, 23, 42, 0.22)',
          padding: 28,
          width: '100%',
          maxWidth: 440,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <span
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: '#eff6ff',
              color: '#2563eb',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <i className="fas fa-shield-halved" />
          </span>
          <h2 id="admin-step-up-title" style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>
            Verify Administrator Password
          </h2>
        </div>

        <p style={{ margin: '0 0 12px', fontSize: 13, color: '#475569', lineHeight: 1.5 }}>
          Re-enter your password to authorize a single-use approval for:{' '}
          <strong>{action?.label || action?.action_key}</strong> ({targetDetail}).
        </p>

        {error && (
          <div
            role="alert"
            style={{
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 8,
              padding: '10px 12px',
              color: '#dc2626',
              fontSize: 13,
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}

        <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 6 }}>
          Administrator Password
          <input
            type="password"
            autoComplete="current-password"
            autoFocus
            required
            disabled={busy}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            style={{
              display: 'block',
              width: '100%',
              boxSizing: 'border-box',
              marginTop: 6,
              padding: '10px 14px',
              borderRadius: 10,
              border: '1.5px solid #e2e8f0',
              fontSize: 14,
              outline: 'none',
              background: '#f8fafc',
              color: '#1e293b',
            }}
          />
        </label>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <button
            type="button"
            disabled={busy}
            onClick={handleCancel}
            style={{
              background: '#fff',
              color: '#334155',
              border: '1.5px solid #e2e8f0',
              padding: '10px 18px',
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 600,
              cursor: busy ? 'not-allowed' : 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !password}
            style={{
              background: '#2563eb',
              color: '#fff',
              border: 'none',
              padding: '10px 18px',
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 600,
              cursor: busy || !password ? 'not-allowed' : 'pointer',
              opacity: busy || !password ? 0.6 : 1,
            }}
          >
            {busy ? 'Verifying...' : 'Confirm & Continue'}
          </button>
        </div>
      </form>
    </div>
  )
}
