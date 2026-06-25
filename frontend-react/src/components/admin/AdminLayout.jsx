import { NavLink, useNavigate } from 'react-router-dom'
import { adminRequest, adminUser } from '../../pages/admin/adminApi'

const navItems = [
  ['Dashboard', '/admin/dashboard'],
  ['Users', '/admin/users'],
  ['Trucks', '/admin/trucks'],
  ['Wallet Withdrawals', '/admin/withdrawals'],
  ['Agreements', '/admin/agreements'],
  ['Disputes', '/admin/disputes'],
  ['Payments', '/admin/payments'],
]

export default function AdminLayout({ children }) {
  const navigate = useNavigate()
  const user = adminUser()

  async function logout() {
    try {
      await adminRequest('/auth/logout', { method: 'POST', body: JSON.stringify({}) })
    } catch (_) {}
    sessionStorage.clear()
    navigate('/admin/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-slate-800 bg-slate-950 px-5 py-6 lg:block">
        <div className="text-xl font-bold tracking-wide text-white">Digi_TransX Admin</div>
        <nav className="mt-8 space-y-1">
          {navItems.map(([label, href]) => (
            <NavLink
              key={href}
              to={href}
              className={({ isActive }) =>
                `block rounded-lg px-4 py-3 text-sm font-semibold transition ${
                  isActive ? 'bg-cyan-500 text-slate-950' : 'text-slate-300 hover:bg-slate-900 hover:text-white'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="lg:pl-72">
        <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/95 px-4 py-4 backdrop-blur sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2 lg:hidden">
              {navItems.map(([label, href]) => (
                <NavLink key={href} to={href} className="rounded-md border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200">
                  {label}
                </NavLink>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-3">
              <span className="text-sm text-slate-300">{user?.full_name || user?.email || 'Admin'}</span>
              <button type="button" onClick={logout} className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-white">
                Logout
              </button>
            </div>
          </div>
        </header>
        <main className="px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  )
}

