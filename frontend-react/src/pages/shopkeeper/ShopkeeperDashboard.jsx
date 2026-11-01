import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-PK', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch { return iso }
}

export default function ShopkeeperDashboard() {
  const navigate = useNavigate()
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
      <main className="max-w-5xl mx-auto px-4 py-8">
        <section className="shopkeeper-welcome">
          <div>
            <span className="shopkeeper-welcome__eyebrow">TODAY AT A GLANCE</span>
            <h2>Ready to serve your next customer?</h2>
            <p>Start a new sale, update your stock, or review your recent performance.</p>
          </div>
          <button onClick={() => navigate('/shopkeeper/pos')}>
            <i className="fa-solid fa-plus" /> Start New Sale
          </button>
          <span className="shopkeeper-welcome__art"><i className="fa-solid fa-store" /></span>
        </section>

        {/* Shop Tools nav cards */}
        <div className="mb-8">
          <div className="shopkeeper-section-heading">
            <div><h2>Quick Actions</h2><p>Choose what you want to do</p></div>
          </div>
          <div className="shopkeeper-action-grid">
            {[
              { label: 'New Sale', icon: 'fa-cash-register', tone: 'blue', path: '/shopkeeper/pos', desc: 'Create a bill and print a receipt' },
              { label: 'Inventory', icon: 'fa-boxes-stacked', tone: 'orange', path: '/shopkeeper/inventory', desc: 'Manage products, prices and stock' },
              { label: 'Sales & Reports', icon: 'fa-chart-line', tone: 'green', path: '/shopkeeper/sales-analytics', desc: 'See revenue and top products' },
              { label: 'Truck Parts Hub', icon: 'fa-truck-fast', tone: 'purple', path: '/shopkeeper/parts-hub', desc: 'Handle orders and price requests' },
            ].map(tool => (
              <button key={tool.path}
                onClick={() => navigate(tool.path)}
                className="shopkeeper-action-card">
                <span className={`shopkeeper-action-card__icon ${tool.tone}`}><i className={`fa-solid ${tool.icon}`} /></span>
                <span className="shopkeeper-action-card__copy"><strong>{tool.label}</strong><small>{tool.desc}</small></span>
                <i className="fa-solid fa-chevron-right shopkeeper-action-card__arrow" />
              </button>
            ))}
          </div>
        </div>

        {/* Page title row */}
        <div className="shopkeeper-section-heading shopkeeper-section-heading--records">
          <div>
            <h2>Product Records</h2>
            <p>Custom lists for products you want to track separately</p>
          </div>
          <button
            onClick={() => navigate('/shopkeeper/create-table')}
            className="shopkeeper-secondary-action">
            <i className="fa-solid fa-plus" /> New Product List
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="shopkeeper-friendly-notice">
            <i className="fa-solid fa-circle-info" />
            <span><strong>Product records are unavailable right now.</strong><small>Please use Inventory for your regular products and stock.</small></span>
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
            <div className="text-5xl mb-4">📋</div>
            <h2 className="text-xl font-semibold text-gray-700 mb-2">No product lists yet</h2>
            <p className="text-gray-500 text-sm mb-6 max-w-sm mx-auto">
              Create a custom list when you need to track additional product information.
            </p>
            <button
              onClick={() => navigate('/shopkeeper/create-table')}
              className="px-6 py-2.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg transition-colors">
              Create First List
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
              <span className="text-sm text-gray-500 font-medium">New Product List</span>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
