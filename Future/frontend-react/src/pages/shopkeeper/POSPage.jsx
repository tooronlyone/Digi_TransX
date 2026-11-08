import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCsrf, getUser, fmtCurrency, fmtDateTime, unitLabel, unitAllowsDecimals } from './posUtils'
import { printReceipt } from './receiptPrinting'
import { quotePosCart, posLineMinor } from './posAmounts'

export default function POSPage() {
  const navigate = useNavigate()
  const user = getUser()
  const shopName = user.company_name || `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username || 'My Shop'
  const city = ''

  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cart, setCart] = useState([]) // [{ product, quantity }]
  const [purchaserName, setPurchaserName] = useState('')
  const [amountPaid, setAmountPaid] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submissionPending = useRef(false)
  const [saleError, setSaleError] = useState('')
  const [completedSale, setCompletedSale] = useState(null)
  const [search, setSearch] = useState('')

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
        setError('We could not load your products right now. Please try again.')
      }
    } catch {
      setError('We could not connect to the shop service. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  function addToCart(product) {
    const stock = unitAllowsDecimals(product.unit) ? Number(product.stock_quantity) : Math.floor(Number(product.stock_quantity))
    if (!Number.isFinite(stock) || stock <= 0) return
    setCart(prev => {
      const existing = prev.find(c => c.product.id === product.id)
      if (existing) {
        if (Number(existing.quantity) >= stock) return prev
        return prev.map(c => c.product.id === product.id ? { ...c, quantity: Math.min(Number((Number(c.quantity) + 1).toFixed(3)), stock) } : c)
      }
      return [...prev, { product, quantity: Math.min(1, stock) }]
    })
  }

  function updateQty(productId, qty) {
    if (typeof qty === 'number' && qty <= 0) { removeFromCart(productId); return }
    setCart(prev => prev.map(c => {
      if (c.product.id !== productId) return c
      if (qty === '') return { ...c, quantity: '' }
      const value = Number(qty)
      if (!Number.isFinite(value) || value < 0 || (!unitAllowsDecimals(c.product.unit) && !Number.isInteger(value))) return c
      const stock = unitAllowsDecimals(c.product.unit) ? Number(c.product.stock_quantity) : Math.floor(Number(c.product.stock_quantity))
      return { ...c, quantity: value > stock ? stock : qty }
    }))
  }

  function removeFromCart(productId) {
    setCart(prev => prev.filter(c => c.product.id !== productId))
  }

  const { total, paid, change, canConfirm } = quotePosCart(cart, amountPaid)

  async function handleConfirm() {
    if (!canConfirm || completedSale || submissionPending.current) return
    submissionPending.current = true
    setSaleError('')
    setSubmitting(true)
    try {
      const csrf = await getCsrf()
      const res = await fetch('/api/shopkeeper/sales', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
        body: JSON.stringify({
          purchaser_name: purchaserName.trim(),
          amount_paid: paid,
          items: cart.map(c => ({ product_id: c.product.id, quantity: Number(c.quantity) })),
        }),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (!res.ok || !data.success) {
        setSaleError(res.status === 404
          ? 'Sales processing is not available yet. Please try again later.'
          : 'The sale could not be completed. Please check the details and try again.')
        return
      }

      // The POST returns the committed receipt. A later read must never turn
      // that successful sale back into a retryable checkout.
      setCompletedSale(data.data)
      setCart([])
      setPurchaserName('')
      setAmountPaid('')
      await loadProducts()
    } catch {
      setSaleError('We could not connect to the shop service. Please try again.')
    } finally {
      submissionPending.current = false
      setSubmitting(false)
    }
  }

  function resetSale() {
    setCart([])
    setPurchaserName('')
    setAmountPaid('')
    setSaleError('')
    setCompletedSale(null)
  }

  const filtered = products.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    (p.category || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-orange-600">New Sale (POS)</span>
        </div>
        <button onClick={() => navigate('/shopkeeper/dashboard')}
          className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors">
          ← Dashboard
        </button>
      </header>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="shopkeeper-state-card shopkeeper-state-card--error">
          <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-triangle-exclamation" /></span>
          <h2>Products could not be loaded</h2>
          <p>{error}</p>
          <button onClick={loadProducts}><i className="fa-solid fa-rotate-right" /> Try Again</button>
        </div>
      ) : (
        <div className="max-w-6xl mx-auto px-4 py-6 flex flex-col lg:flex-row gap-6">

          {/* Product grid */}
          <div className="flex-1 min-w-0">
            <div className="mb-4">
              <input value={search} onChange={e => setSearch(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                placeholder="Search products..." />
            </div>
            {products.length === 0 ? (
              <div className="shopkeeper-state-card">
                <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-box-open" /></span>
                <h2>No products available yet</h2>
                <p>Add products to your inventory before creating your first sale.</p>
                <button onClick={() => navigate('/shopkeeper/inventory')}
                  className="shopkeeper-state-card__primary">
                  <i className="fa-solid fa-plus" /> Add Your First Product
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {filtered.map(p => {
                  const inCart = cart.find(c => c.product.id === p.id)
                  const outOfStock = p.stock_quantity === 0
                  return (
                    <div key={p.id}
                      onClick={() => addToCart(p)}
                      className={`bg-white rounded-xl border p-3 cursor-pointer transition-all select-none
                        ${outOfStock ? 'opacity-50 cursor-not-allowed border-gray-200' :
                          inCart ? 'border-orange-400 shadow-md ring-2 ring-orange-200' :
                          'border-gray-200 hover:shadow-md hover:border-orange-300'}`}>
                      <div className="text-xs text-gray-400 mb-1 truncate">{p.category || 'General'}</div>
                      <div className="font-semibold text-gray-800 text-sm truncate mb-1">{p.name}</div>
                      <div className="text-orange-600 font-bold text-sm">PKR {fmtCurrency(p.price)} <small className="text-[10px] font-medium text-gray-400">/ {unitLabel(p.unit, true)}</small></div>
                      <div className="mt-1.5 flex items-center justify-between">
                        <span className={`text-xs ${p.stock_quantity <= 5 ? 'text-yellow-600' : 'text-gray-400'}`}>
                          Stock: {p.stock_quantity} {unitLabel(p.unit, true)}
                        </span>
                        {outOfStock ? (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full">Out</span>
                        ) : inCart ? (
                          <span className="text-xs bg-orange-100 text-orange-600 px-1.5 py-0.5 rounded-full">
                            {inCart.quantity} {unitLabel(p.unit, true)}
                          </span>
                        ) : (
                          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">+ Add</span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Cart panel */}
          <div className="w-full lg:w-80 flex-shrink-0">
            <div className="bg-white rounded-xl border border-gray-200 p-4 sticky top-4">
              <h2 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
                <span>🧾</span> Cart
                {cart.length > 0 && (
                  <span className="ml-auto text-xs bg-orange-100 text-orange-600 px-2 py-0.5 rounded-full">
                    {cart.length} item{cart.length !== 1 ? 's' : ''}
                  </span>
                )}
              </h2>

              {cart.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">Click a product to add it</p>
              ) : (
                <div className="space-y-2 mb-4 max-h-56 overflow-y-auto">
                  {cart.map(({ product, quantity }) => (
                    <div key={product.id} className="flex items-center gap-2 py-1.5 border-b border-gray-100">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-800 truncate">{product.name}</div>
                        <div className="text-xs text-gray-500">PKR {fmtCurrency(product.price)} per {unitLabel(product.unit)}</div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={() => updateQty(product.id, Number((Number(quantity) - 1).toFixed(3)))}
                          className="w-6 h-6 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-bold text-sm leading-none">
                          −
                        </button>
                        <input type="number" aria-label={`Quantity for ${product.name}`}
                          min={unitAllowsDecimals(product.unit) ? '0.001' : '1'}
                          step={unitAllowsDecimals(product.unit) ? '0.001' : '1'}
                          max={product.stock_quantity} value={quantity}
                          onChange={event => updateQty(product.id, event.target.value)}
                          className="w-16 rounded border border-gray-300 text-center text-sm font-semibold text-gray-800" />
                        <small className="text-[10px] text-gray-400">{unitLabel(product.unit, true)}</small>
                        <button onClick={() => updateQty(product.id, Number((Number(quantity) + 1).toFixed(3)))}
                          className="w-6 h-6 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-bold text-sm leading-none">
                          +
                        </button>
                      </div>
                      <div className="text-xs font-semibold text-gray-800 w-16 text-right">
                        PKR {fmtCurrency(Number(posLineMinor(product.price, quantity) ?? 0n) / 100)}
                      </div>
                      <button onClick={() => removeFromCart(product.id)}
                        className="text-red-400 hover:text-red-600 text-xs ml-1">✕</button>
                    </div>
                  ))}
                </div>
              )}

              {/* Totals */}
              <div className="border-t border-gray-200 pt-3 mb-4">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-bold text-gray-800">Total</span>
                  <span className="text-base font-bold text-gray-900">PKR {fmtCurrency(total)}</span>
                </div>
              </div>

              {/* Purchaser name */}
              <div className="mb-3">
                <label className="block text-xs font-medium text-gray-600 mb-1">Purchaser Name</label>
                <input value={purchaserName} onChange={e => setPurchaserName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                  placeholder="Optional" />
              </div>

              {/* Amount paid */}
              <div className="mb-3">
                <label className="block text-xs font-medium text-gray-600 mb-1">Amount Paid (PKR) *</label>
                <input type="number" min="0" step="0.01" value={amountPaid}
                  onChange={e => setAmountPaid(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                  placeholder="0" />
              </div>

              {/* Change display */}
              {amountPaid !== '' && cart.length > 0 && (
                <div className={`rounded-lg px-3 py-2 mb-3 text-sm font-semibold flex justify-between
                  ${change >= 0 ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'}`}>
                  <span>Change</span>
                  <span>PKR {fmtCurrency(Math.abs(change))}{change < 0 ? ' short' : ''}</span>
                </div>
              )}

              {saleError && (
                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{saleError}</p>
              )}

              <button onClick={handleConfirm} disabled={!canConfirm || submitting || Boolean(completedSale)}
                className="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white font-bold rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm">
                {submitting ? 'Processing...' : 'Confirm Sale & Generate Receipt'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Receipt Modal */}
      {completedSale && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-screen overflow-y-auto">
            {/* Receipt preview */}
            <div className="p-6 font-mono text-sm">
              {/* Header */}
              <div className="flex justify-between items-start mb-4">
                <div>
                  <div className="text-xl font-black text-blue-600 tracking-tight">DigiTransX</div>
                  <div className="text-xs text-gray-400">Point of Sale</div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-gray-800 text-sm">{shopName}</div>
                </div>
              </div>
              <hr className="border-dashed border-gray-300 mb-3" />
              <div className="text-xs text-gray-600 space-y-0.5 mb-3">
                <div>Receipt: <span className="font-semibold text-gray-800">{completedSale.receipt_number}</span></div>
                <div>Date: <span className="font-semibold text-gray-800">{fmtDateTime(completedSale.created_at)}</span></div>
                <div>Purchaser: <span className="font-semibold text-gray-800">{completedSale.purchaser_name || '—'}</span></div>
              </div>
              <hr className="border-dashed border-gray-300 mb-3" />
              {/* Items */}
              <table className="w-full text-xs mb-3">
                <thead>
                  <tr className="border-b border-gray-300">
                    <th className="text-left py-1">Product</th>
                    <th className="text-center py-1">Qty</th>
                    <th className="text-right py-1">Unit</th>
                    <th className="text-right py-1">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(completedSale.items || []).map((item, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-1">{item.product_name}</td>
                      <td className="py-1 text-center">{item.quantity}</td>
                      <td className="py-1 text-right">PKR {fmtCurrency(item.unit_price)}</td>
                      <td className="py-1 text-right">PKR {fmtCurrency(item.subtotal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <hr className="border-dashed border-gray-300 mb-2" />
              <div className="text-xs space-y-1">
                <div className="flex justify-between font-black text-sm border-t border-gray-800 pt-1">
                  <span>Total</span><span>PKR {fmtCurrency(completedSale.total_amount)}</span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span>Amount Paid</span><span>PKR {fmtCurrency(completedSale.amount_paid)}</span>
                </div>
                <div className="flex justify-between font-bold text-green-700">
                  <span>Change</span><span>PKR {fmtCurrency(completedSale.change_amount)}</span>
                </div>
              </div>
              <hr className="border-dashed border-gray-300 mt-3 mb-3" />
              <div className="text-center text-xs text-gray-400">
                — Thank you for your purchase! —<br />
                Powered by DigiTransX
              </div>
            </div>

            {/* Action buttons */}
            <div className="px-6 pb-6 flex gap-3">
              <button
                onClick={() => printReceipt(completedSale, shopName, city)}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl text-sm transition-colors">
                🖨️ Print Receipt
              </button>
              <button onClick={resetSale}
                className="flex-1 py-2.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-xl text-sm transition-colors">
                New Sale
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
