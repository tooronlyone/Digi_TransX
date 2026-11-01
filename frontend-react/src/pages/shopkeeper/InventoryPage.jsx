import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCsrf, fmtCurrency, fmtDate, PRODUCT_UNITS, unitAllowsDecimals, unitLabel } from './posUtils'

const EMPTY_FORM = { name: '', category: '', price: '', stock_quantity: '', unit: 'piece' }

export default function InventoryPage() {
  const navigate = useNavigate()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modal, setModal] = useState(null) // null | { mode: 'add'|'edit', product?: obj }
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [deleteId, setDeleteId] = useState(null)

  useEffect(() => { loadProducts() }, [])

  async function loadProducts() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/shopkeeper/products', { credentials: 'include' })
      const data = await res.json()
      if (res.status === 404) {
        setProducts([])
      } else if (res.status === 401 || res.status === 403) {
        setError('Your session has expired. Please sign in again.')
      } else if (res.ok && data.success) {
        setProducts(data.data || [])
        if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      } else {
        setError('We could not load your inventory right now. Please try again.')
      }
    } catch {
      setError('We could not connect to the shop service. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  function openAdd() {
    setForm(EMPTY_FORM)
    setFormError('')
    setModal({ mode: 'add' })
  }

  function openEdit(product) {
    setForm({
      name: product.name,
      category: product.category || '',
      price: String(product.price),
      stock_quantity: String(product.stock_quantity),
      unit: product.unit || 'piece',
    })
    setFormError('')
    setModal({ mode: 'edit', product })
  }

  async function handleSave() {
    const name = form.name.trim()
    if (!name) { setFormError('Product name is required.'); return }
    const price = parseFloat(form.price)
    if (isNaN(price) || price < 0) { setFormError('Enter a valid price (0 or more).'); return }
    const stock = Number(form.stock_quantity)
    if (isNaN(stock) || stock < 0) { setFormError('Enter a valid stock quantity (0 or more).'); return }
    if (!unitAllowsDecimals(form.unit) && !Number.isInteger(stock)) {
      setFormError(`${unitLabel(form.unit)} quantity must be a whole number.`)
      return
    }

    setSaving(true)
    setFormError('')
    try {
      const csrf = await getCsrf()
      const body = { name, category: form.category.trim(), price, stock_quantity: stock, unit: form.unit }
      const isEdit = modal.mode === 'edit'
      const url = isEdit ? `/api/shopkeeper/products/${modal.product.id}` : '/api/shopkeeper/products'
      const method = isEdit ? 'PUT' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (!res.ok || !data.success) {
        setFormError(res.status === 404
          ? 'Inventory setup is not available yet. Please try again later.'
          : 'The product could not be saved. Please check the details and try again.')
        return
      }

      if (isEdit) {
        setProducts(ps => ps.map(p => p.id === modal.product.id ? { ...p, ...body } : p))
      } else {
        await loadProducts()
      }
      setModal(null)
    } catch {
      setFormError('We could not connect to the shop service. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    try {
      const csrf = await getCsrf()
      const res = await fetch(`/api/shopkeeper/products/${id}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': csrf },
        credentials: 'include',
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (data.success) setProducts(ps => ps.filter(p => p.id !== id))
    } catch {
      // Keep the item visible when deletion cannot be confirmed by the server.
    }
    setDeleteId(null)
  }

  const lowStockCount = products.filter(p => p.stock_quantity <= 5).length

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-orange-600">Inventory</span>
        </div>
        <button onClick={() => navigate('/shopkeeper/dashboard')}
          className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors">
          ← Dashboard
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Title + stats */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Product Inventory</h1>
            <p className="text-gray-500 text-sm mt-0.5">
              {products.length} product{products.length !== 1 ? 's' : ''}
              {lowStockCount > 0 && (
                <span className="ml-2 text-yellow-600 font-medium">· {lowStockCount} low stock</span>
              )}
            </p>
          </div>
          <button onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg transition-colors text-sm shadow-sm">
            + Add Product
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="shopkeeper-state-card shopkeeper-state-card--error">
            <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-triangle-exclamation" /></span>
            <h2>Inventory could not be loaded</h2>
            <p>{error}</p>
            <button onClick={loadProducts}><i className="fa-solid fa-rotate-right" /> Try Again</button>
          </div>
        ) : products.length === 0 ? (
          <div className="shopkeeper-state-card">
            <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-box-open" /></span>
            <h2>Your inventory is empty</h2>
            <p>Add your first product to start creating sales and receipts.</p>
            <button onClick={openAdd}
              className="shopkeeper-state-card__primary">
              <i className="fa-solid fa-plus" /> Add Your First Product
            </button>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Product</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600 hidden sm:table-cell">Category</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Price (PKR)</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Stock</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 hidden md:table-cell">Updated</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {products.map(p => (
                  <tr key={p.id}
                    className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${p.stock_quantity <= 5 ? 'bg-yellow-50 hover:bg-yellow-100' : ''}`}>
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {p.name}
                      {p.stock_quantity === 0 && (
                        <span className="ml-2 text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full">Out</span>
                      )}
                      {p.stock_quantity > 0 && p.stock_quantity <= 5 && (
                        <span className="ml-2 text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded-full">Low</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 hidden sm:table-cell">{p.category || '—'}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-800">{fmtCurrency(p.price)}</td>
                    <td className="px-4 py-3 text-right text-gray-800">
                      <span className="font-mono font-semibold">{p.stock_quantity}</span>
                      <span className="ml-1 text-xs text-gray-400">{unitLabel(p.unit, true)}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400 hidden md:table-cell">{fmtDate(p.updated_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => openEdit(p)}
                          className="text-xs px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 rounded-lg transition-colors">
                          Edit
                        </button>
                        <button onClick={() => setDeleteId(p.id)}
                          className="text-xs px-2.5 py-1 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg transition-colors">
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {/* Add/Edit Modal */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-bold text-gray-800 mb-5">
              {modal.mode === 'add' ? 'Add Product' : 'Edit Product'}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Product Name *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                  placeholder="e.g. Engine Oil 1L" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <input value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                  placeholder="e.g. Lubricants, Spare Parts" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Price (PKR) *</label>
                  <input type="number" min="0" step="0.01" value={form.price}
                    onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                    placeholder="0.00" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Stock Quantity *</label>
                  <input type="number" min="0" step={unitAllowsDecimals(form.unit) ? '0.01' : '1'} value={form.stock_quantity}
                    onChange={e => setForm(f => ({ ...f, stock_quantity: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                    placeholder="0" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Measurement Unit *</label>
                <select value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-400">
                  {PRODUCT_UNITS.map(unit => <option key={unit.value} value={unit.value}>{unit.label} ({unit.short})</option>)}
                </select>
                <p className="text-xs text-gray-400 mt-1">Price and stock will be measured per {unitLabel(form.unit).toLowerCase()}.</p>
              </div>
              {formError && (
                <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{formError}</p>
              )}
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setModal(null)} disabled={saving}
                className="flex-1 px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium transition-colors">
                Cancel
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex-1 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-60">
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {deleteId !== null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 text-center">
            <div className="text-4xl mb-3">🗑️</div>
            <h2 className="text-lg font-bold text-gray-800 mb-2">Delete Product?</h2>
            <p className="text-gray-500 text-sm mb-6">This cannot be undone. Existing sales records are kept.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteId(null)}
                className="flex-1 px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium transition-colors">
                Cancel
              </button>
              <button onClick={() => handleDelete(deleteId)}
                className="flex-1 px-4 py-2.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-semibold transition-colors">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
