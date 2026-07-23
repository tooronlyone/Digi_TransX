import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getTransporterAllowedPaths, isTransporterPathAllowed } from './accessControl'
import { NAV_ITEMS } from './navItems'
import { apiGet, getCsrfToken } from '../../pages/client/clientUtils'
import TermsUpdateNotice from '../common/TermsUpdateNotice'
import NotificationBell from '../common/NotificationBell'

function getTransporterDisplayName(u = {}) {
  const full = [u.first_name, u.last_name].filter(Boolean).join(' ').trim()
  return (u.company_name || u.full_name || full || u.username || u.email || 'Transporter').trim()
}

function getTransporterInitials(name) {
  return (name || 'Transporter')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase() || 'TR'
}

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
    function applyUser(rawUser) {
      const u = rawUser || {}
      setUser({
        name: getTransporterDisplayName(u),
        role: u.organization_role_label || u.role || 'Transporter',
        organization_allowed_paths: getTransporterAllowedPaths(u),
        defaultRoute: u.organization_default_route || '/transporter/dashboard',
      })
    }

    const stored = sessionStorage.getItem('user')
    if (stored) {
      try { applyUser(JSON.parse(stored)) } catch { /* ignore malformed cached user */ }
    }

    apiGet('/api/profile')
      .then((json) => {
        if (!json?.user) return
        sessionStorage.setItem('user', JSON.stringify(json.user))
        applyUser(json.user)
      })
      .catch(() => undefined)

    function handleUserUpdate(event) {
      if (event.detail) {
        applyUser(event.detail)
        return
      }
      const latest = sessionStorage.getItem('user')
      if (!latest) return
      try { applyUser(JSON.parse(latest)) } catch { /* ignore malformed cached user */ }
    }

    window.addEventListener('dtx:user-updated', handleUserUpdate)
    return () => window.removeEventListener('dtx:user-updated', handleUserUpdate)
  }, [])

  useEffect(() => {
    let mounted = true

    async function loadUnread() {
      try {
        const json = await apiGet('/api/chat/threads')
        if (!mounted) return
        const total = (json.threads || []).reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0)
        setUnreadTotal(total)
      } catch { /* ignore transient errors; next poll retries */ }
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
    } catch { /* logout is best-effort */ }
    sessionStorage.clear()
    navigate('/login')
  }

  const initials = getTransporterInitials(user.name)
  const visibleNavItems = NAV_ITEMS
    .filter((item) => item.path !== '/transporter/trucks/add')
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

  const isMessagesPage = location.pathname === '/transporter/messages'

  return (
    <div className={`transporter-page${isMessagesPage ? ' transporter-page--messages' : ''}`}>
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
          <NotificationBell orderPath={(id) => `/transporter/order/${id}`} />
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
      <div className={`main-content${isMessagesPage ? ' main-content--messages' : ''}`}>
        {!isMessagesPage && <TermsUpdateNotice termsPath="/transporter/terms" />}
        {children}

        {!isMessagesPage && <div className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/transporter/about">About Us</Link>
            <Link to="/transporter/contact">Contact</Link>
            <Link to="/transporter/terms">Terms &amp; Conditions</Link>
            <Link to="/transporter/privacy">Privacy Policy</Link>
            <Link to="/transporter/help">Help Center</Link>
            <Link to="/transporter/partner">Partner With Us</Link>
          </div>
        </div>}
      </div>
    </div>
  )
}
