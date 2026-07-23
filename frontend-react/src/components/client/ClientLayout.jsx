import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { apiGet, getCsrfToken } from '../../pages/client/clientUtils'
import TermsUpdateNotice from '../common/TermsUpdateNotice'
import NotificationBell from '../common/NotificationBell'
import '../../styles/pages/client.css'

const NAV_ITEMS = [
  { label: 'Dashboard', icon: 'fa-home', path: '/client/dashboard' },
  { label: 'Post Order', icon: 'fa-shipping-fast', path: '/client/post-order' },
  { label: 'My Orders', icon: 'fa-clipboard-list', path: '/client/orders' },
  { label: 'Post Agreement', icon: 'fa-file-circle-plus', path: '/client/post-agreement' },
  { label: 'My Agreements', icon: 'fa-file-contract', path: '/client/my-agreements' },
  { label: 'Messages', icon: 'fa-comments', path: '/client/messages' },
  { label: 'Your Wallet', icon: 'fa-wallet', path: '/client/wallet', match: ['/client/balance'] },
  { label: 'Your Account', icon: 'fa-user-circle', path: '/client/account' },
]

export default function ClientLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [user, setUser] = useState({ name: 'Client', role: 'Service Seeker' })
  const [unreadTotal, setUnreadTotal] = useState(0)

  useEffect(() => {
    const stored = sessionStorage.getItem('user')
    if (!stored) return
    try {
      const parsed = JSON.parse(stored)
      const full = [parsed.first_name, parsed.last_name].filter(Boolean).join(' ').trim()
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setUser({
        name: parsed.company_name || parsed.full_name || full || parsed.username || parsed.email || 'Client',
        role: parsed.organization_role_label || 'Service Seeker',
      })
    } catch { /* best-effort; ignore */ }
  }, [])

  useEffect(() => {
    let mounted = true
    async function loadUnread() {
      try {
        const json = await apiGet('/api/chat/threads')
        if (!mounted) return
        const total = (json.threads || []).reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0)
        setUnreadTotal(total)
      } catch { /* best-effort; ignore */ }
    }
    loadUnread()
    const intervalId = window.setInterval(loadUnread, 4000)
    return () => {
      mounted = false
      window.clearInterval(intervalId)
    }
  }, [])

  useEffect(() => {
    function checkViewport() {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (!mobile) setMenuOpen(false)
    }
    checkViewport()
    window.addEventListener('resize', checkViewport)
    return () => window.removeEventListener('resize', checkViewport)
  }, [])

  const initials = useMemo(() => {
    return user.name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase() || 'CL'
  }, [user.name])

  const navItems = useMemo(
    () => NAV_ITEMS.map((item) => (
      item.path === '/client/messages'
        ? { ...item, badge: unreadTotal > 0 ? String(unreadTotal) : '' }
        : item
    )),
    [unreadTotal],
  )

  async function handleLogout() {
    try {
      const csrf = await getCsrfToken()
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
    } catch { /* best-effort; ignore */ }
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  function isActive(item) {
    if (location.pathname === item.path) return true
    if (item.match?.some((prefix) => location.pathname.startsWith(prefix))) return true
    return location.pathname.startsWith(`${item.path}/`)
  }

  const sidebar = (
    <nav className="sidebar">
      <ul className="nav-menu">
        {navItems.map((item) => {
          const active = isActive(item)
          return (
            <li className="nav-item" key={item.path}>
              <Link
                to={item.path}
                className={`nav-link${active ? ' active' : ''}`}
                onClick={() => setMenuOpen(false)}
              >
                <i className={`fas ${item.icon}`} aria-hidden="true"></i>
                <span className="nav-text">{item.label}</span>
                {item.badge && <span className="dashboard-status-pill dashboard-status-pill--available">{item.badge}</span>}

              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )

  return (
    <div className="transporter-page service-seeker-page">
      <nav className="navbar">
        <div className="navbar-left">
          {isMobile && (
            <button
              type="button"
              className="logout-btn"
              onClick={() => setMenuOpen((open) => !open)}
              aria-label="Toggle navigation"
            >
              <i className={`fas ${menuOpen ? 'fa-times' : 'fa-bars'}`} aria-hidden="true"></i>
            </button>
          )}
          <Link to="/client/dashboard" className="navbar-logo">
            <div className="logo-icon">
              <i className="fas fa-truck" aria-hidden="true"></i>
            </div>
            <div className="navbar-brand">Digi_Trans<span style={{ color: '#2563eb' }}>X</span></div>
          </Link>
        </div>

        <div className="navbar-right">
          <NotificationBell orderPath={(id) => `/client/order/${id}`} />
          <div className="user-info">
            <div className="user-avatar">{initials}</div>
            <div className="user-details">
              <h3>{user.name}</h3>
              <p>{user.role}</p>
            </div>
          </div>
          <button type="button" onClick={handleLogout} className="logout-btn" title="Logout">
            <i className="fas fa-sign-out-alt" aria-hidden="true"></i>
          </button>
        </div>
      </nav>

      {!isMobile && sidebar}
      {isMobile && menuOpen && sidebar}

      <main className="main-content">
        <TermsUpdateNotice termsPath="/client/terms" />
        <div>{children}</div>
        <footer className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/client/terms">Terms &amp; Platform Fees</Link>
          </div>
        </footer>
      </main>
    </div>
  )
}
