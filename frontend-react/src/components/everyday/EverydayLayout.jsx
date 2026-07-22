import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getCsrfToken } from '../../pages/client/clientUtils'
import TermsUpdateNotice from '../common/TermsUpdateNotice'
import '../../styles/pages/client.css'

// Everyday users get the simple one-time-order flow only: NO wallet, NO
// agreements, NO saved cards, NO company/business configuration. The shared
// order pages are reused under /everyday/* via useClientBasePath.
const NAV_ITEMS = [
  { label: 'Dashboard', icon: 'fa-home', path: '/everyday/dashboard' },
  { label: 'Post Order', icon: 'fa-shipping-fast', path: '/everyday/post-order' },
  { label: 'My Orders', icon: 'fa-clipboard-list', path: '/everyday/orders' },
  { label: 'Messages', icon: 'fa-comments', path: '/everyday/messages' },
  { label: 'Terms & Fees', icon: 'fa-file-lines', path: '/everyday/terms' },
]

// Read the display name from the session cache once (lazy init) so there is no
// setState-in-effect just to hydrate the header.
function readUser() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem('user') || 'null')
    if (parsed) {
      const full = [parsed.first_name, parsed.last_name].filter(Boolean).join(' ').trim()
      return { name: parsed.full_name || full || parsed.email || 'You', role: 'Everyday User' }
    }
  } catch { /* ignore malformed cached user */ }
  return { name: 'You', role: 'Everyday User' }
}

export default function EverydayLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [user] = useState(readUser)

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
      .toUpperCase() || 'EU'
  }, [user.name])

  async function handleLogout() {
    try {
      const csrf = await getCsrfToken()
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
    } catch { /* logout is best-effort */ }
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  function isActive(item) {
    if (location.pathname === item.path) return true
    return location.pathname.startsWith(`${item.path}/`)
  }

  const sidebar = (
    <nav className="sidebar">
      <ul className="nav-menu">
        {NAV_ITEMS.map((item) => {
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
          <Link to="/everyday/dashboard" className="navbar-logo">
            <div className="logo-icon">
              <i className="fas fa-truck" aria-hidden="true"></i>
            </div>
            <div className="navbar-brand">Digi_Trans<span style={{ color: '#2563eb' }}>X</span></div>
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
          <button type="button" onClick={handleLogout} className="logout-btn" title="Logout">
            <i className="fas fa-sign-out-alt" aria-hidden="true"></i>
          </button>
        </div>
      </nav>

      {!isMobile && sidebar}
      {isMobile && menuOpen && sidebar}

      <main className="main-content">
        <TermsUpdateNotice termsPath="/everyday/terms" />
        <div>{children}</div>
        <footer className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/everyday/terms">Terms &amp; Platform Fees</Link>
          </div>
        </footer>
      </main>
    </div>
  )
}
