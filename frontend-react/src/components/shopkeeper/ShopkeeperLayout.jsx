import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { clearAuthPresentation } from '../../auth/presentation'
import '../../styles/pages/shopkeeper.css'

const navigation = [
  { label: 'Dashboard', path: '/shopkeeper/dashboard', icon: 'fa-house' },
  { label: 'New Sale', path: '/shopkeeper/pos', icon: 'fa-cash-register' },
  { label: 'Inventory', path: '/shopkeeper/inventory', icon: 'fa-boxes-stacked' },
  { label: 'Sales & Reports', path: '/shopkeeper/sales-analytics', icon: 'fa-chart-column' },
  { label: 'Truck Parts Hub', path: '/shopkeeper/parts-hub', icon: 'fa-truck-fast' },
]

const pageTitles = [
  ['/shopkeeper/create-table', ['Create Product Table', 'Set up a simple custom product list']],
  ['/analysis', ['Table Analysis', 'Review your product table data']],
  ['/shopkeeper/table/', ['Product Table', 'View and update your product records']],
  ['/shopkeeper/inventory', ['Inventory', 'Manage products, prices and stock']],
  ['/shopkeeper/pos', ['New Sale', 'Create a sale and print a receipt']],
  ['/shopkeeper/sales-analytics', ['Sales & Reports', 'Track sales and top-performing products']],
  ['/shopkeeper/parts-hub', ['Truck Parts Hub', 'Manage orders, parts and price requests']],
  ['/shopkeeper/profile', ['My Profile', 'Manage your personal and shop information']],
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
    // Local presentation data still needs to be cleared if the server is unavailable.
  }
  clearAuthPresentation()
  window.location.replace('/login')
}

export default function ShopkeeperLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [user, setUser] = useState(getUser)
  const displayName = user.first_name
    ? `${user.first_name} ${user.last_name || ''}`.trim()
    : user.company_name || user.username || 'Shopkeeper'
  const page = pageTitles.find(([path]) => location.pathname.includes(path))?.[1]
    || ['Shop Dashboard', 'Everything you need to run your shop']

  useEffect(() => {
    const handleUserUpdate = event => setUser(event.detail || getUser())
    window.addEventListener('dtx:user-updated', handleUserUpdate)
    return () => window.removeEventListener('dtx:user-updated', handleUserUpdate)
  }, [])

  return (
    <div className="shopkeeper-shell">
      {menuOpen && <button className="shopkeeper-backdrop" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <aside className={`shopkeeper-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <div className="shopkeeper-brand" onClick={() => navigate('/shopkeeper/dashboard')} role="button" tabIndex={0}>
          <span className="shopkeeper-brand__mark"><i className="fa-solid fa-store" /></span>
          <span className="shopkeeper-brand__copy"><strong>DigiTransX</strong><small>Shop Manager</small></span>
        </div>
        <nav className="shopkeeper-nav" aria-label="Shop navigation">
          <p>MAIN MENU</p>
          {navigation.map(item => (
            <NavLink key={item.path} to={item.path} onClick={() => setMenuOpen(false)} className={({ isActive }) => `shopkeeper-nav__item ${isActive ? 'active' : ''}`}>
              <span className="shopkeeper-nav__icon"><i className={`fa-solid ${item.icon}`} /></span>
              <span className="shopkeeper-nav__label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="shopkeeper-sidebar__footer">
          <button onClick={logout}><i className="fa-solid fa-arrow-right-from-bracket" /> <span>Log out</span></button>
        </div>
      </aside>

      <div className="shopkeeper-workspace">
        <header className="shopkeeper-topbar">
          <div className="shopkeeper-topbar__title">
            <button className="shopkeeper-menu-button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <i className="fa-solid fa-bars" />
            </button>
            <div><h1>{page[0]}</h1><p>{page[1]}</p></div>
          </div>
          <div className="shopkeeper-profile" onClick={() => navigate('/shopkeeper/profile')}
            onKeyDown={event => {
              if (event.key === 'Enter' || event.key === ' ') navigate('/shopkeeper/profile')
            }} role="button" tabIndex={0} aria-label="Open My Profile" title="Open My Profile">
            <span className="shopkeeper-profile__avatar">{displayName.charAt(0).toUpperCase()}</span>
            <span className="shopkeeper-profile__copy"><strong>{displayName}</strong><small>Shopkeeper</small></span>
            <button onClick={(event) => { event.stopPropagation(); logout() }} title="Log out" aria-label="Log out"><i className="fa-solid fa-arrow-right-from-bracket" /></button>
          </div>
        </header>

        <main className="shopkeeper-content">{children}</main>
      </div>
    </div>
  )
}
