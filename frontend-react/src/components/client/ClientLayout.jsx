import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { apiGet, getCsrfToken } from '../../pages/client/clientUtils'

const NAV_ITEMS = [
  { label: 'Dashboard', icon: 'fa-home', path: '/client/dashboard' },
  { label: 'Post Order', icon: 'fa-shipping-fast', path: '/client/post-order', badge: 'New' },
  { label: 'My Orders', icon: 'fa-clipboard-list', path: '/client/orders' },
  { label: 'Messages', icon: 'fa-comments', path: '/client/messages' },
  { label: 'Your Wallet', icon: 'fa-wallet', path: '/client/wallet', match: ['/client/balance'] },
  { label: 'Cargo Insurance', icon: 'fa-shield-alt', path: '/client/insurance.html', legacy: true },
  { label: 'Documents', icon: 'fa-file-alt', path: '/client/documents.html', legacy: true },
  { label: 'Agreements', icon: 'fa-file-contract', path: '/client/agreements' },
  { label: 'About Us', icon: 'fa-info-circle', path: '/client/about.html', legacy: true },
  { label: 'Contact Us', icon: 'fa-address-book', path: '/client/contact.html', legacy: true },
  { label: 'Your Account', icon: 'fa-user-circle', path: '/client/account' },
]

export default function ClientLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [user, setUser] = useState({
    name: 'Client',
    role: 'Service Seeker',
  })
  const [unreadTotal, setUnreadTotal] = useState(0)

  useEffect(() => {
    const stored = sessionStorage.getItem('user')
    if (!stored) return
    try {
      const parsed = JSON.parse(stored)
      const name = [parsed.first_name, parsed.last_name].filter(Boolean).join(' ').trim()
      setUser({
        name: name || parsed.username || parsed.email || 'Client',
        role: parsed.organization_role_label || 'Service Seeker',
      })
    } catch (_) {}
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
    } catch (_) {}
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  function isActive(item) {
    if (location.pathname === item.path) return true
    if (item.match?.some((prefix) => location.pathname.startsWith(prefix))) return true
    return location.pathname.startsWith(`${item.path}/`)
  }

  const sidebar = (
    <nav className="flex h-full flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-4">
        <Link to="/client/dashboard" className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-blue-600 text-white">
            <i className="fas fa-truck" aria-hidden="true"></i>
          </span>
          <span className="text-lg font-extrabold tracking-normal text-slate-900">
            Digi_Trans<span className="text-blue-600">X</span>
          </span>
        </Link>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {navItems.map((item) => {
          const active = isActive(item)
          const classes = `flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
            active
              ? 'bg-blue-50 text-blue-700'
              : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
          }`
          const content = (
            <>
              <i className={`fas ${item.icon} w-5 text-center`} aria-hidden="true"></i>
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                  {item.badge}
                </span>
              )}
            </>
          )
          return (
            <li key={item.path}>
              {item.legacy ? (
                <a href={item.path} className={classes} onClick={() => setMenuOpen(false)}>
                  {content}
                </a>
              ) : (
                <Link to={item.path} className={classes} onClick={() => setMenuOpen(false)}>
                  {content}
                </Link>
              )}
            </li>
          )
        })}
      </ul>
    </nav>
  )

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
        <div className="flex min-h-16 items-center justify-between gap-3 px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-300 text-slate-700 lg:hidden"
              onClick={() => setMenuOpen((open) => !open)}
              aria-label="Toggle navigation"
            >
              <i className={`fas ${menuOpen ? 'fa-times' : 'fa-bars'}`} aria-hidden="true"></i>
            </button>
            <Link to="/main" className="hidden text-sm font-semibold text-slate-600 hover:text-blue-700 sm:inline-flex">
              Home
            </Link>
            <a href="/client/about.html" className="hidden text-sm font-semibold text-slate-600 hover:text-blue-700 sm:inline-flex">
              About
            </a>
            <a href="/client/contact.html" className="hidden text-sm font-semibold text-slate-600 hover:text-blue-700 sm:inline-flex">
              Contact
            </a>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-semibold text-slate-900">{user.name}</div>
              <div className="text-xs text-slate-500">{user.role}</div>
            </div>
            <div className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-sm font-bold text-white">
              {initials}
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-300 text-slate-700 transition hover:bg-slate-100"
              title="Logout"
            >
              <i className="fas fa-sign-out-alt" aria-hidden="true"></i>
            </button>
          </div>
        </div>
      </header>

      <div className="flex">
        <aside className="fixed inset-y-16 left-0 z-20 hidden w-72 lg:block">
          {sidebar}
        </aside>
        {menuOpen && (
          <div className="fixed inset-0 z-20 bg-slate-900/30 lg:hidden" onClick={() => setMenuOpen(false)}>
            <aside className="h-full w-72" onClick={(event) => event.stopPropagation()}>
              {sidebar}
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-6 lg:ml-72 lg:px-8">
          <div className="mx-auto max-w-7xl space-y-6">{children}</div>
          <footer className="mx-auto mt-10 max-w-7xl border-t border-slate-200 py-6 text-sm text-slate-500">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p>(c) 2026 Digi_TransX Transport Services. All rights reserved.</p>
              <div className="flex flex-wrap gap-4">
                <a className="hover:text-blue-700" href="/client/about.html">About Us</a>
                <a className="hover:text-blue-700" href="/client/contact.html">Contact</a>
                <a className="hover:text-blue-700" href="/client/terms-details.html">Terms</a>
                <a className="hover:text-blue-700" href="/client/privacy.html">Privacy</a>
                <a className="hover:text-blue-700" href="/client/help.html">Help</a>
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}
