/* eslint-disable no-unused-vars, no-empty, react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import '../../styles/pages/profile.css'
import { logoutCurrentSession } from '../../auth/logout'

function getInitials(user) {
  const first = (user?.first_name || '').trim()
  const last = (user?.last_name || '').trim()
  if (first && last) return (first[0] + last[0]).toUpperCase()
  if (first) return first[0].toUpperCase()
  return (user?.username || 'U')[0].toUpperCase()
}

export default function Profile() {
  const navigate = useNavigate()
  const { get } = useApi()
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [logoutLoading, setLogoutLoading] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const cached = sessionStorage.getItem('user')
    if (cached) {
      try { setUser(JSON.parse(cached)) } catch {}
    }
    get('/auth/me')
      .then(data => {
        if (data.success && data.user) {
          setUser(data.user)
          sessionStorage.setItem('user', JSON.stringify(data.user))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleLogout() {
    setLogoutLoading(true)
    await logoutCurrentSession(navigate)
  }

  function fullName() {
    if (!user) return '-'
    const f = user.first_name || ''
    const l = user.last_name || ''
    return (f + ' ' + l).trim() || user.username || '-'
  }

  function val(v) {
    return v || '-'
  }

  return (
      <div className="page-profile">
      {msg && (
        <div style={{
          background: '#dcfce7', color: '#166534', padding: '0.75rem 1rem',
          borderRadius: '8px', marginBottom: '1rem', fontSize: '0.9rem'
        }}>{msg}</div>
      )}

      {/* Top Bar */}
      <div className="top-bar">
        <div className="page-title">
          <h1>My Profile</h1>
          <p>Manage your account information and settings</p>
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
          <i className="fas fa-spinner fa-spin"></i> Loading profile...
        </div>
      )}

      {!loading && (
        <div className="profile-container">
          {/* Profile Card */}
          <div className="profile-card">
            <div className="profile-picture">
              <div className="profile-img-placeholder" id="profileImagePlaceholder"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: '120px', height: '120px', borderRadius: '50%',
                  background: '#3b82f6', color: '#fff', fontSize: '2.5rem', fontWeight: '700' }}>
                {user ? getInitials(user) : <i className="fas fa-user-circle"></i>}
              </div>
            </div>

            <h2 className="profile-name">{fullName()}</h2>
            <div className="profile-role">{val(user?.role)}</div>

            <div className="profile-actions">
              <Link to="/transporter/settings" className="profile-btn profile-btn-primary">
                <i className="fas fa-edit"></i> Edit Profile
              </Link>
            </div>
          </div>

          {/* Profile Details */}
          <div className="profile-details">
            <h2 className="section-title">Account Details</h2>

            <div className="details-grid">
              {/* Personal Information */}
              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-icon"><i className="fas fa-user"></i></div>
                  <h3 className="detail-title">Personal Information</h3>
                </div>
                <div className="detail-content">
                  <div className="detail-row"><span className="detail-label">Full Name:</span><span className="detail-value">{fullName()}</span></div>
                  <div className="detail-row"><span className="detail-label">Username:</span><span className="detail-value">{val(user?.username)}</span></div>
                  <div className="detail-row"><span className="detail-label">Email:</span><span className="detail-value">{val(user?.email)}</span></div>
                  <div className="detail-row"><span className="detail-label">Phone:</span><span className="detail-value">{val(user?.phone)}</span></div>
                  <div className="detail-row"><span className="detail-label">Role:</span><span className="detail-value">{val(user?.role)}</span></div>
                </div>
                <Link to="/transporter/settings" className="edit-btn">
                  <i className="fas fa-edit"></i> Edit
                </Link>
              </div>

              {/* Account Status */}
              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-icon"><i className="fas fa-shield-alt"></i></div>
                  <h3 className="detail-title">Account Status</h3>
                </div>
                <div className="detail-content">
                  <div className="detail-row">
                    <span className="detail-label">Status:</span>
                    <span className="detail-value" style={{ color: '#22c55e', fontWeight: '600' }}>Active</span>
                  </div>
                  <div className="detail-row"><span className="detail-label">Account ID:</span><span className="detail-value">{val(user?.id)}</span></div>
                  <div className="detail-row"><span className="detail-label">Registered Role:</span><span className="detail-value">{val(user?.registered_role || user?.role)}</span></div>
                </div>
              </div>

              {/* Quick Links */}
              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-icon"><i className="fas fa-link"></i></div>
                  <h3 className="detail-title">Quick Links</h3>
                </div>
                <div className="detail-content">
                  <div className="detail-row"><Link to="/transporter/trucks" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-truck"></i> My Trucks</Link></div>
                  <div className="detail-row"><Link to="/transporter/available-bids" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-briefcase"></i> Available Bids</Link></div>
                  <div className="detail-row"><Link to="/transporter/my-agreements" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-file-contract"></i> My Agreements</Link></div>
                  <div className="detail-row"><Link to="/transporter/wallet" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-credit-card"></i> Wallet</Link></div>
                  <div className="detail-row"><Link to="/transporter/earnings" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-wallet"></i> Earnings</Link></div>
                  <div className="detail-row"><Link to="/transporter/settings" className="detail-value" style={{ color: '#3b82f6' }}><i className="fas fa-cog"></i> Settings</Link></div>
                </div>
              </div>

              {/* Security and session */}
              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-icon"><i className="fas fa-shield-halved"></i></div>
                  <h3 className="detail-title">Security &amp; Session</h3>
                </div>
                <div className="detail-content">
                  <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Manage MPIN access or securely end your current session.</p>
                </div>
                <div className="profile-session-actions">
                  <Link to="/transporter/security" className="edit-btn">
                    <i className="fas fa-fingerprint"></i> Security Settings
                  </Link>
                  <button className="edit-btn profile-logout-action" onClick={handleLogout} disabled={logoutLoading}>
                    <i className="fas fa-sign-out-alt"></i> {logoutLoading ? 'Logging out...' : 'Logout'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      </div>
    
  )
}
