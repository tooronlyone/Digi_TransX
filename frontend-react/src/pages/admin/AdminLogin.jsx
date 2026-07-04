import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function AdminLogin() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/auth/login', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ loginId: form.email, password: form.password }),
      })
      const json = await res.json().catch(() => ({}))
      if (!res.ok || json.success === false) throw new Error(json.message || 'Login failed.')
      if ((json.user?.role || '').trim().toLowerCase() !== 'platform_admin')
        throw new Error('This account does not have admin access.')
      sessionStorage.setItem('user', JSON.stringify(json.user))
      sessionStorage.setItem('user_id', String(json.user.id))
      sessionStorage.setItem('user_role', json.user.role)
      if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
      navigate('/admin/dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Unable to login.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', background: '#f8fafc',
    }}>
      {/* Left panel */}
      <div style={{
        flex: 1, background: 'linear-gradient(135deg,#1e3a8a 0%,#2563eb 60%,#3b82f6 100%)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        padding: 48, color: 'white',
      }}>
        <div style={{
          width: 72, height: 72, background: 'rgba(255,255,255,0.15)',
          borderRadius: 18, display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 24, backdropFilter: 'blur(10px)',
        }}>
          <svg viewBox="0 0 32 32" fill="none" width="40" height="40">
            <g stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 9 L13 9 L19 23 L27 23"/>
              <path d="M27 9 L19 9 L13 23 L5 23"/>
            </g>
          </svg>
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: '0 0 12px', textAlign: 'center' }}>Digi_TransX</h1>
        <p style={{ fontSize: 16, opacity: 0.85, textAlign: 'center', maxWidth: 320, lineHeight: 1.6 }}>
          Platform Administration — Manage users, trucks, payments, and operations from one place.
        </p>
        <div style={{ marginTop: 48, display: 'flex', flexDirection: 'column', gap: 16, width: '100%', maxWidth: 300 }}>
          {[
            ['fa-users', '8 Registered Users'],
            ['fa-truck', '3 Active Trucks'],
            ['fa-shield-halved', 'Secure Admin Access'],
          ].map(([icon, text]) => (
            <div key={icon} style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'rgba(255,255,255,0.1)', borderRadius: 12, padding: '12px 16px' }}>
              <i className={`fas ${icon}`} style={{ width: 20, textAlign: 'center' }} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div style={{
        width: 480, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 48, background: '#ffffff',
      }}>
        <div style={{ width: '100%', maxWidth: 380 }}>
          <div style={{ marginBottom: 36 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#2563eb', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>Platform Admin</div>
            <h2 style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', margin: 0 }}>Sign in to Admin</h2>
            <p style={{ color: '#64748b', fontSize: 14, marginTop: 8 }}>Restricted access — authorized personnel only.</p>
          </div>

          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Email Address</label>
              <input
                type="email" required placeholder="admin@digitransx.com"
                value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}
                style={{
                  width: '100%', padding: '12px 16px', borderRadius: 10, boxSizing: 'border-box',
                  border: '1.5px solid #e2e8f0', outline: 'none', fontSize: 14, color: '#1e293b',
                  background: '#f8fafc', transition: 'border 0.2s',
                }}
                onFocus={e => e.target.style.borderColor = '#2563eb'}
                onBlur={e => e.target.style.borderColor = '#e2e8f0'}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPass ? 'text' : 'password'} required placeholder="Enter password"
                  value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                  style={{
                    width: '100%', padding: '12px 44px 12px 16px', borderRadius: 10, boxSizing: 'border-box',
                    border: '1.5px solid #e2e8f0', outline: 'none', fontSize: 14, color: '#1e293b',
                    background: '#f8fafc',
                  }}
                  onFocus={e => e.target.style.borderColor = '#2563eb'}
                  onBlur={e => e.target.style.borderColor = '#e2e8f0'}
                />
                <button type="button" onClick={() => setShowPass(!showPass)} style={{
                  position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 15,
                }}>
                  <i className={`fas ${showPass ? 'fa-eye-slash' : 'fa-eye'}`} />
                </button>
              </div>
            </div>

            {error && (
              <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13 }}>
                <i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}
              </div>
            )}

            <button type="submit" disabled={loading} style={{
              padding: '14px', borderRadius: 10, border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
              background: loading ? '#93c5fd' : 'linear-gradient(135deg,#2563eb,#3b82f6)',
              color: 'white', fontWeight: 700, fontSize: 15,
              boxShadow: '0 4px 14px rgba(37,99,235,0.3)', transition: 'all 0.2s',
            }}>
              {loading ? <><i className="fas fa-circle-notch fa-spin" style={{ marginRight: 8 }} />Signing in...</> : 'Sign In to Admin Panel'}
            </button>
          </form>

          <p style={{ marginTop: 32, textAlign: 'center', fontSize: 12, color: '#94a3b8' }}>
            <i className="fas fa-lock" style={{ marginRight: 6 }} />Secured connection · Admin access only
          </p>
        </div>
      </div>
    </div>
  )
}
