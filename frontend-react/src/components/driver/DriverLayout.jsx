import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { logoutCurrentSession } from '../../auth/logout'
import { useAuthVerification } from '../../auth/AuthVerificationContext'
import digiTransxLogo from '../../assets/brand/digi-transx-logo.png'
import NotificationBell from '../common/NotificationBell'
import '../../styles/pages/driver.css'

const DRIVER_NAV = [
  { label: 'Overview', icon: 'fa-gauge-high', path: '/driver/dashboard' },
  { label: 'Active trip', icon: 'fa-location-crosshairs', path: '/driver/active-trip' },
  { label: 'Trip requests', icon: 'fa-route', path: '/driver/trips' },
  { label: 'Fuel log', icon: 'fa-gas-pump', path: '/driver/fuel-logs' },
  { label: 'Wallet', icon: 'fa-wallet', path: '/driver/wallet' },
  { label: 'Reputation', icon: 'fa-shield-halved', path: '/driver/reputation' },
  { label: 'Profile', icon: 'fa-user', path: '/driver/profile' },
]

const PAGE_COPY = {
  '/driver/dashboard': ['Overview', 'Your workday at a glance'],
  '/driver/active-trip': ['Active trip', 'Location and delivery controls'],
  '/driver/trips': ['Trip requests', 'Review dispatch and employment offers'],
  '/driver/fuel-logs': ['Fuel log', 'Track refuels and mileage'],
  '/driver/wallet': ['Wallet', 'Balances, reserves and payouts'],
  '/driver/reputation': ['Reputation', 'Your verified trust record'],
  '/driver/profile': ['Profile', 'Driver identity and credentials'],
}

export default function DriverLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useAuthVerification()
  const [menuOpen, setMenuOpen] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
  const logoutPending = useRef(false)
  const [pageTitle, pageSubtitle] = PAGE_COPY[location.pathname] || ['Driver workspace', 'Digi_TransX']

  async function handleLogout() {
    if (logoutPending.current) return
    logoutPending.current = true
    setLoggingOut(true)
    setLogoutError('')
    try {
      await logoutCurrentSession(navigate)
    } catch (error) {
      setLogoutError(error.message || 'Logout could not be confirmed. Please retry.')
    } finally {
      logoutPending.current = false
      setLoggingOut(false)
    }
  }

  function isActive(path) {
    return location.pathname === path || location.pathname.startsWith(`${path}/`)
  }

  return (
    <div className="driver-portal-layout">
      <aside className={`driver-sidebar ${menuOpen ? 'is-open' : ''}`} aria-label="Driver navigation">
        <div className="driver-sidebar-brand">
          <img src={digiTransxLogo} alt="Digi_TransX" />
          <button type="button" className="driver-sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation">
            <i className="fas fa-xmark" aria-hidden="true" />
          </button>
        </div>

        <div className="driver-account-summary">
          <span className="driver-account-avatar" aria-hidden="true"><i className="fas fa-steering-wheel" /></span>
          <span>
            <strong>{user?.name || user?.full_name || 'Driver account'}</strong>
            <small><i className="fas fa-circle-check" aria-hidden="true" /> Secure driver access</small>
          </span>
        </div>

        <p className="driver-nav-label">Workspace</p>
        <nav>
          <ul className="driver-nav-list">
            {DRIVER_NAV.map((item) => (
              <li key={item.path}>
                <Link to={item.path} onClick={() => setMenuOpen(false)} className={`driver-nav-link ${isActive(item.path) ? 'active' : ''}`} aria-current={isActive(item.path) ? 'page' : undefined}>
                  <span className="driver-nav-icon"><i className={`fas ${item.icon}`} aria-hidden="true" /></span>
                  <span>{item.label}</span>
                  {isActive(item.path) && <i className="fas fa-chevron-right driver-nav-arrow" aria-hidden="true" />}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="driver-sidebar-note">
          <i className="fas fa-headset" aria-hidden="true" />
          <div>
            <strong>Need help on a trip?</strong>
            <span>Contact your assigned transporter before changing the trip status.</span>
          </div>
        </div>
      </aside>

      {menuOpen && <button type="button" className="driver-sidebar-backdrop" onClick={() => setMenuOpen(false)} aria-label="Close navigation" />}

      <div className="driver-workspace">
        <header className="driver-header">
          <div className="driver-header-context">
            <button type="button" className="driver-menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open navigation" aria-expanded={menuOpen}>
              <i className="fas fa-bars" aria-hidden="true" />
            </button>
            <div><h1>{pageTitle}</h1><p>{pageSubtitle}</p></div>
          </div>

          <div className="driver-header-actions">
            <span className="driver-header-role"><i className="fas fa-id-badge" aria-hidden="true" /> Driver workspace</span>
            <NotificationBell orderPath={() => '/driver/active-trip'} />
            <button type="button" onClick={handleLogout} disabled={loggingOut} className="driver-logout-btn">
              <i className="fas fa-arrow-right-from-bracket" aria-hidden="true" />
              <span>{loggingOut ? 'Signing out…' : 'Sign out'}</span>
            </button>
          </div>
        </header>

        {logoutError && <p className="driver-alert driver-alert--error driver-shell-alert" role="alert">{logoutError}</p>}
        <main className="driver-main-content">{children}</main>
      </div>
    </div>
  )
}
