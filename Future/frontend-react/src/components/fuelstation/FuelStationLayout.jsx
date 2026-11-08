import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { clearAuthPresentation } from '../../auth/presentation'
import '../../styles/pages/fuelstation.css'

const navigation = [
  { label: 'Dashboard', path: '/fuelstation/dashboard', icon: 'fa-house' },
  { label: 'Dispense Fuel (POS)', path: '/fuelstation/dispense', icon: 'fa-gas-pump' },
  { label: 'Pumps & Pricing', path: '/fuelstation/pumps', icon: 'fa-sliders' },
  { label: 'Dispense History', path: '/fuelstation/history', icon: 'fa-receipt' },
  { label: 'Station Profile', path: '/fuelstation/profile', icon: 'fa-id-card' },
]

const pageTitles = [
  ['/fuelstation/dashboard', ['Fuel Station Dashboard', 'Live sales, fuel rates, and pump overview']],
  ['/fuelstation/dispense', ['Dispense Fuel POS', 'Quick truck refueling counter and receipt generation']],
  ['/fuelstation/pumps', ['Pumps & Fuel Rates', 'Manage pumps, set PKR per liter rates and tank levels']],
  ['/fuelstation/history', ['Dispense History', 'Complete log of vehicle refueling transactions']],
  ['/fuelstation/profile', ['Station Profile', 'Update pump details, OGRA license, and contact info']],
]

function getUser() {
  try { return JSON.parse(sessionStorage.getItem('user') || '{}') } catch { return {} }
}

async function logout() {
  try {
    const csrf = sessionStorage.getItem('csrf_token') || ''
    await fetch('/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      credentials: 'include',
    })
  } catch {
    // Local presentation data cleared
  }
  clearAuthPresentation()
  window.location.replace('/login')
}

export default function FuelStationLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [user, setUser] = useState(getUser)
  const displayName = user.name || user.full_name || user.station_name || 'Fuel Station Manager'
  const page = pageTitles.find(([path]) => location.pathname === path)?.[1]
    || ['Fuel Station Portal', 'Smart Fleet Refueling System']

  useEffect(() => {
    const handleUserUpdate = event => setUser(event.detail || getUser())
    window.addEventListener('dtx:user-updated', handleUserUpdate)
    return () => window.removeEventListener('dtx:user-updated', handleUserUpdate)
  }, [])

  return (
    <div className="fuel-shell">
      {menuOpen && <button className="fuel-backdrop" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <aside className={`fuel-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <div className="fuel-brand" onClick={() => navigate('/fuelstation/dashboard')} role="button" tabIndex={0}>
          <span className="fuel-brand__mark"><i className="fa-solid fa-gas-pump" /></span>
          <span className="fuel-brand__copy">
            <strong>DigiTransX</strong>
            <small>Fuel Station</small>
          </span>
        </div>

        <nav className="fuel-nav" aria-label="Fuel Station navigation">
          <p>STATION MANAGEMENT</p>
          {navigation.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `fuel-nav__item ${isActive ? 'active' : ''}`}
            >
              <span className="fuel-nav__icon"><i className={`fa-solid ${item.icon}`} /></span>
              <span className="fuel-nav__label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="fuel-sidebar__footer">
          <button onClick={logout}>
            <i className="fa-solid fa-arrow-right-from-bracket" />
            <span>Log out</span>
          </button>
        </div>
      </aside>

      <div className="fuel-workspace">
        <header className="fuel-topbar">
          <div className="fuel-topbar__title">
            <button className="fuel-menu-button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <i className="fa-solid fa-bars" />
            </button>
            <div>
              <h1>{page[0]}</h1>
              <p>{page[1]}</p>
            </div>
          </div>

          <div
            className="fuel-profile"
            onClick={() => navigate('/fuelstation/profile')}
            role="button"
            tabIndex={0}
            aria-label="Open Station Profile"
            title="Open Station Profile"
          >
            <span className="fuel-profile__avatar">⛽</span>
            <span className="fuel-profile__copy">
              <strong>{displayName}</strong>
              <small>Fuel Station Manager</small>
            </span>
            <button onClick={(e) => { e.stopPropagation(); logout() }} title="Log out" aria-label="Log out">
              <i className="fa-solid fa-arrow-right-from-bracket" />
            </button>
          </div>
        </header>

        <main className="fuel-main">
          {children}
        </main>
      </div>
    </div>
  )
}
