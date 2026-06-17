import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-PK', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch (_) { return iso }
}

async function logout() {
  try {
    const csrf = sessionStorage.getItem('csrf_token') || ''
    await fetch('/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      credentials: 'include',
    })
  } catch (_) {}
  sessionStorage.clear()
  window.location.replace('/login')
}

export default function ShopkeeperDashboard() {
  const navigate = useNavigate()
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const user = (() => { try { return JSON.parse(sessionStorage.getItem('user') || '{}') } catch (_) { return {} } })()

  useEffect(() => {
    fetch('/api/shopkeeper/tables', { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setTables(data.data || [])
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
        } else {
          setError(data.message || 'Failed to load tables.')
        }
      })
      .catch(() => setError('Network error. Please refresh.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-orange-600">Shop Dashboard</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600 hidden sm:block">
            {user.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : user.username || 'Shopkeeper'}
          </span>
          <button onClick={logout}
            className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors">
            Logout
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Shop Tools nav cards */}
        <div className="mb-8">
          <h2 className="text-base font-bold text-gray-700 mb-3">Shop Tools</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { label: 'Inventory', icon: '📦', path: '/shopkeeper/inventory', desc: 'Add & manage products and stock' },
              { label: 'New Sale (POS)', icon: '🧾', path: '/shopkeeper/pos', desc: 'Create a sale & print receipt' },
              { label: 'Sales Analytics', icon: '📊', path: '/shopkeeper/sales-analytics', desc: 'Revenue, top products & history' },
            ].map(tool => (
              <div key={tool.path}
                onClick={() => navigate(tool.path)}
                className="bg-white rounded-xl border border-gray-200 p-4 cursor-pointer hover:shadow-md hover:border-orange-300 transition-all">
                <div className="text-2xl mb-2">{tool.icon}</div>
                <div className="font-bold text-gray-800 text-sm">{tool.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{tool.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Page title row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">My Product Tables</h1>
            <p className="text-gray-500 text-sm mt-1">
              Each table is its own product type — like a custom spreadsheet.
            </p>
          </div>
          <button
            onClick={() => navigate('/shopkeeper/create-table')}
            className="flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg transition-colors text-sm shadow-sm">
            <span className="text-lg leading-none">+</span> Create Product Table
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && tables.length === 0 && (
          <div className="text-center py-20 bg-white rounded-xl border-2 border-dashed border-gray-200">
            <div className="text-5xl mb-4">🛒</div>
            <h2 className="text-xl font-semibold text-gray-700 mb-2">No product tables yet</h2>
            <p className="text-gray-500 text-sm mb-6 max-w-sm mx-auto">
              Create your first table to start tracking stock, prices and sales for any product type.
            </p>
            <button
              onClick={() => navigate('/shopkeeper/create-table')}
              className="px-6 py-2.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg transition-colors">
              Create First Table
            </button>
          </div>
        )}

        {/* Table cards grid */}
        {!loading && tables.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {tables.map(table => (
              <div key={table.id}
                onClick={() => navigate(`/shopkeeper/table/${table.id}`)}
                className="bg-white rounded-xl border border-gray-200 p-5 cursor-pointer hover:shadow-md hover:border-orange-300 transition-all group">
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center text-xl">
                    📊
                  </div>
                  <span className="text-xs text-gray-400 bg-gray-50 px-2 py-1 rounded-full">
                    {table.columns?.length || 0} col{table.columns?.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <h3 className="font-bold text-gray-800 text-base mb-1 group-hover:text-orange-600 transition-colors truncate">
                  {table.name}
                </h3>
                <p className="text-sm text-gray-500 mb-4">
                  {table.row_count} row{table.row_count !== 1 ? 's' : ''}
                </p>
                <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                  <span className="text-xs text-gray-400">Updated {formatDate(table.updated_at)}</span>
                  <span className="text-xs text-orange-500 font-medium group-hover:underline">Open →</span>
                </div>
              </div>
            ))}

            {/* Add new card */}
            <div
              onClick={() => navigate('/shopkeeper/create-table')}
              className="bg-white rounded-xl border-2 border-dashed border-gray-200 p-5 cursor-pointer hover:border-orange-400 hover:bg-orange-50 transition-all flex flex-col items-center justify-center min-h-[160px] gap-2">
              <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center text-2xl text-gray-400">
                +
              </div>
              <span className="text-sm text-gray-500 font-medium">New Table</span>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
