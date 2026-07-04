import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { adminRequest, adminUser } from '../../pages/admin/adminApi'

const NAV_ITEMS = [
  { path: '/admin/dashboard',   label: 'Dashboard',    icon: 'fa-gauge-high' },
  { path: '/admin/users',       label: 'Users',        icon: 'fa-users' },
  { path: '/admin/trucks',      label: 'Trucks',       icon: 'fa-truck' },
  { path: '/admin/withdrawals', label: 'Withdrawals',  icon: 'fa-money-bill-transfer' },
  { path: '/admin/agreements',  label: 'Agreements',   icon: 'fa-file-contract' },
  { path: '/admin/disputes',    label: 'Disputes',     icon: 'fa-triangle-exclamation' },
  { path: '/admin/payments',    label: 'Payments',     icon: 'fa-credit-card' },
]

export default function AdminLayout({ children }) {
  const location = useLocation()
  const navigate  = useNavigate()
  const user      = adminUser()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const initials = (user?.full_name || user?.email || 'AD').slice(0, 2).toUpperCase()

  async function logout() {
    try { await adminRequest('/auth/logout', { method: 'POST', body: JSON.stringify({}) }) } catch (_) {}
    sessionStorage.clear()
    navigate('/admin/login', { replace: true })
  }

  const activePath = NAV_ITEMS.reduce((best, item) => {
    if (!location.pathname.startsWith(item.path)) return best
    if (!best || item.path.length > best.length) return item.path
    return best
  }, '')

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', color: '#1e293b' }}>
      {/* NAVBAR */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: 70,
        background: '#ffffff', borderBottom: '1px solid #e2e8f0',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 32px', zIndex: 1100, boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}>
        {/* Logo */}
        <Link to="/admin/dashboard" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
          <div style={{
            background: 'linear-gradient(135deg,#2563eb,#3b82f6)',
            width: 40, height: 40, borderRadius: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg viewBox="0 0 32 32" fill="none" width="22" height="22">
              <g stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 9 L13 9 L19 23 L27 23"/>
                <path d="M27 9 L19 9 L13 23 L5 23"/>
              </g>
            </svg>
          </div>
          <span style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', letterSpacing: '-0.2px' }}>
            Digi_Trans<span style={{ color: '#2563eb' }}>X</span>
            <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 600, color: '#64748b', background: '#f1f5f9', padding: '2px 8px', borderRadius: 20 }}>Admin</span>
          </span>
        </Link>

        {/* Right */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#f1f5f9', padding: '6px 16px 6px 12px', borderRadius: 40 }}>
            <div style={{
              width: 38, height: 38, background: 'linear-gradient(135deg,#2563eb,#1d4ed8)',
              borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'white', fontWeight: 600, fontSize: 14,
            }}>{initials}</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', margin: 0 }}>{user?.full_name || 'Admin'}</div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>Platform Admin</div>
            </div>
          </div>
          <button onClick={logout} title="Logout" style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#64748b', fontSize: 18, padding: '6px 8px', borderRadius: 8,
          }}
            onMouseEnter={e => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.background = '#fee2e2' }}
            onMouseLeave={e => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.background = 'none' }}
          >
            <i className="fas fa-sign-out-alt" />
          </button>
        </div>
      </nav>

      {/* SIDEBAR */}
      <nav
        onMouseEnter={() => setSidebarOpen(true)}
        onMouseLeave={() => setSidebarOpen(false)}
        style={{
          position: 'fixed', top: 70, left: 0,
          width: sidebarOpen ? 260 : 70,
          height: 'calc(100% - 70px)',
          background: '#ffffff', borderRight: '1px solid #e2e8f0',
          overflowY: 'auto', overflowX: 'hidden',
          zIndex: 1000, transition: 'width 0.3s ease',
        }}
      >
        <ul style={{ listStyle: 'none', padding: '20px 0', margin: 0 }}>
          {NAV_ITEMS.map((item) => {
            const isActive = activePath === item.path
            return (
              <li key={item.path} style={{ margin: '4px 12px' }}>
                <Link to={item.path} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 16px', borderRadius: 12,
                  textDecoration: 'none', whiteSpace: 'nowrap',
                  color: isActive ? '#2563eb' : '#475569',
                  background: isActive ? 'rgba(37,99,235,0.08)' : 'transparent',
                  fontWeight: 500, fontSize: 14,
                  transition: 'all 0.2s',
                }}>
                  <i className={`fas ${item.icon}`} style={{
                    width: 22, fontSize: 18, flexShrink: 0,
                    color: isActive ? '#2563eb' : '#64748b',
                  }} />
                  <span style={{ opacity: sidebarOpen ? 1 : 0, transition: 'opacity 0.2s' }}>{item.label}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* MAIN */}
      <main style={{
        marginLeft: 70, marginTop: 70,
        minHeight: 'calc(100vh - 70px)',
        background: '#f8fafc', padding: 28,
        transition: 'margin-left 0.3s ease',
      }}>
        {children}
      </main>
    </div>
  )
}
