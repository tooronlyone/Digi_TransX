import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getTransporterAllowedPaths, isTransporterPathAllowed } from './accessControl'
import { NAV_ITEMS } from './navItems'
import { apiGet, getCsrfToken } from '../../pages/client/clientUtils'
import '../../styles/transporter.css'
import '../../styles/extra.css'

export default function TransporterLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState({
    name: 'Transporter',
    role: 'Transporter',
    organization_allowed_paths: [],
    defaultRoute: '/transporter/dashboard',
  })
  const [unreadTotal, setUnreadTotal] = useState(0)

  useEffect(() => {
    const stored = sessionStorage.getItem('user')
    if (stored) {
      try {
        const u = JSON.parse(stored)
        setUser({
          name: u.first_name || u.username || u.email || 'Transporter',
          role: u.organization_role_label || u.role || 'Transporter',
          organization_allowed_paths: getTransporterAllowedPaths(u),
          defaultRoute: u.organization_default_route || '/transporter/dashboard',
        })
      } catch (_) {}
    }
  }, [])

  useEffect(() => {
    let mounted = true

    async function loadUnread() {
      try {
        const json = await apiGet('/api/chat/threads')
        if (!mounted) return
        const total = (json.threads || []).reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0)
        setUnreadTotal(total)
      } catch (_) {}
    }

    loadUnread()
    const intervalId = window.setInterval(loadUnread, 4000)
    return () => {
      mounted = false
      window.clearInterval(intervalId)
    }
  }, [])

  async function handleLogout() {
    try {
      const csrf = await getCsrfToken()
      await fetch('/auth/logout', { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrf } })
    } catch (_) {}
    sessionStorage.clear()
    navigate('/login')
  }

  const initials = user.name.slice(0, 2).toUpperCase()
  const visibleNavItems = NAV_ITEMS
    .map((item) => (
      item.path === '/transporter/messages'
        ? { ...item, badge: unreadTotal > 0 ? String(unreadTotal) : '' }
        : item
    ))
    .filter((item) => isTransporterPathAllowed(user, item.path))
  const activePath = visibleNavItems.reduce((best, item) => {
    const exactMatch = location.pathname === item.path
    const nestedMatch = location.pathname.startsWith(`${item.path}/`)
    if (!exactMatch && !nestedMatch) return best
    if (!best || item.path.length > best.length) return item.path
    return best
  }, '')

  return (
    <div className="transporter-page">
      {/* Navbar */}
      <nav className="navbar">
        <div className="navbar-left">
          <Link to={user.defaultRoute} className="navbar-logo">
            <div className="logo-icon">
              <svg viewBox="0 0 32 32" fill="none" width="22" height="22" aria-hidden="true">
                <g stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 9 L13 9 L19 23 L27 23"/>
                  <path d="M27 9 L19 9 L13 23 L5 23"/>
                </g>
              </svg>
            </div>
            <div className="navbar-brand">
              Digi_Trans
              <span style={{
                background: 'linear-gradient(135deg,#2563eb,#3b82f6)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}>X</span>
            </div>
          </Link>
        </div>

        <div className="navbar-right">
          <div className="user-info">
            <div className="user-avatar">{initials}</div>
            <div className="user-details">
              <h3>{user.name}</h3>
              <p>{user.role}</p>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="Logout">
            <i className="fas fa-sign-out-alt"></i>
          </button>
        </div>
      </nav>

      {/* Sidebar */}
      <nav className="sidebar">
        <ul className="nav-menu">
          {visibleNavItems.map((item) => {
            return (
              <li className="nav-item" key={item.path}>
                <Link
                  to={item.path}
                  className={`nav-link${activePath === item.path ? ' active' : ''}`}
                >
                  <i className={`fas ${item.icon}`}></i>
                  <span className="nav-text">{item.label}</span>
                  {item.badge && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">{item.badge}</span>}
                </Link>
              </li>
            )
          })}

        </ul>
      </nav>

      {/* Main Content */}
      <div className="main-content">
        {children}
      </div>
    </div>
  )
}
