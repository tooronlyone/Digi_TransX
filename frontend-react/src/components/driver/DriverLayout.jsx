import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { logoutCurrentSession } from '../../auth/logout'
import NotificationBell from '../common/NotificationBell'
import '../../styles/pages/driver.css'

const DRIVER_NAV = [
  { label: 'Dashboard', icon: 'fa-gauge-high', path: '/driver/dashboard' },
  { label: 'Active Trip & GPS', icon: 'fa-location-crosshairs', path: '/driver/active-trip' },
  { label: 'Trip Requests', icon: 'fa-route', path: '/driver/trips' },
  { label: 'Fuel & Diesel Log', icon: 'fa-gas-pump', path: '/driver/fuel-logs' },
  { label: 'Driver Wallet', icon: 'fa-wallet', path: '/driver/wallet' },
  { label: 'Reputation & Score', icon: 'fa-star', path: '/driver/reputation' },
  { label: 'Profile', icon: 'fa-user', path: '/driver/profile' },
]

export default function DriverLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [logoutError, setLogoutError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
  const logoutPending = useRef(false)

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
      <header className="driver-header">
        <div className="driver-brand">
          <i className="fas fa-truck-moving"></i>
          <span>Digi_Trans<strong style={{ color: '#3b82f6' }}>X</strong> Driver Console</span>
        </div>
        <div className="driver-header-actions">
          <NotificationBell orderPath={() => '/driver/active-trip'} />
          <button type="button" onClick={handleLogout} disabled={loggingOut} className="driver-logout-btn" title="Logout">
            <i className="fas fa-sign-out-alt"></i> {loggingOut ? 'Logging out...' : 'Logout'}
          </button>
        </div>
      </header>
      {logoutError && <p className="security-message is-error" role="alert">{logoutError}</p>}

      <div className="driver-body">
        <nav className="driver-sidebar" aria-label="Driver Navigation">
          <ul className="driver-nav-list">
            {DRIVER_NAV.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`driver-nav-link ${isActive(item.path) ? 'active' : ''}`}
                >
                  <i className={`fas ${item.icon}`}></i>
                  <span>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <main className="driver-main-content">
          {children}
        </main>
      </div>
    </div>
  )
}
