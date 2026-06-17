import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCsrf, getUser, fmtCurrency, fmtDateTime } from './posUtils'

function buildReceiptHtml(sale, shopName, city) {
  const rows = (sale.items || []).map(item => `
    <tr>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;">${item.product_name}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:center;">${item.quantity}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">PKR ${Number(item.unit_price).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">PKR ${Number(item.subtotal).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</td>
    </tr>
  `).join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Receipt ${sale.receipt_number}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Courier New', monospace; font-size: 13px; color: #111; background: #fff; padding: 24px; max-width: 420px; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
  .logo { font-size: 20px; font-weight: 900; color: #2563eb; letter-spacing: -0.5px; }
  .logo-sub { font-size: 10px; color: #6b7280; margin-top: 2px; }
  .shop-name { text-align: right; font-weight: 700; font-size: 14px; }
  .shop-city { text-align: right; font-size: 10px; color: #6b7280; margin-top: 2px; }
  hr { border: none; border-top: 1px dashed #9ca3af; margin: 10px 0; }
  .meta { font-size: 11px; color: #374151; line-height: 1.8; margin-bottom: 10px; }
  .meta span { font-weight: 700; }
  table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 10px; }
  thead tr { border-bottom: 2px solid #d1d5db; }
  th { padding: 4px 8px; text-align: left; font-weight: 700; color: #374151; }
  th:nth-child(2) { text-align: center; }
  th:nth-child(3), th:nth-child(4) { text-align: right; }
  .totals { font-size: 12px; line-height: 2; }
  .totals .row { display: flex; justify-content: space-between; }
  .totals .grand { font-weight: 900; font-size: 14px; border-top: 2px solid #111; padding-top: 4px; margin-top: 4px; }
  .totals .change { color: #16a34a; font-weight: 900; }
  .footer { text-align: center; font-size: 10px; color: #9ca3af; margin-top: 16px; line-height: 1.6; }
  @media print {
    body { padding: 8px; }
  }
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="logo">DigiTransX</div>
    <div class="logo-sub">Point of Sale</div>
  </div>
  <div>
    <div class="shop-name">${shopName}</div>
    ${city ? `<div class="shop-city">${city}</div>` : ''}
  </div>
</div>
<hr/>
<div class="meta">
  Receipt: <span>${sale.receipt_number}</span><br/>
  Date: <span>${fmtDateTime(sale.created_at)}</span><br/>
  Purchaser: <span>${sale.purchaser_name || '—'}</span>
</div>
<hr/>
<table>
  <thead>
    <tr>
      <th>Product</th>
      <th>Qty</th>
      <th>Unit Price</th>
      <th>Subtotal</th>
    </tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
<hr/>
<div class="totals">
  <div class="row grand"><span>Total</span><span>PKR ${Number(sale.total_amount).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
  <div class="row"><span>Amount Paid</span><span>PKR ${Number(sale.amount_paid).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
  <div class="row change"><span>Change (Wapis)</span><span>PKR ${Number(sale.change_amount).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
</div>
<div class="footer">
  — Thank you for your purchase! —<br/>
  Powered by DigiTransX
</div>
</body>
</html>`
}

function printReceipt(sale, shopName, city) {
  const html = buildReceiptHtml(sale, shopName, city)
  const w = window.open('', '_blank', 'width=520,height=720')
  if (!w) return
  w.document.write(html)
  w.document.close()
  w.focus()
  setTimeout(() => { w.print() }, 400)
}

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
  const [saleError, setSaleError] = useState('')
  const [completedSale, setCompletedSale] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => { loadProducts() }, [])

  async function loadProducts() {
    setLoading(true)
    try {
      const res = await fetch('/api/shopkeeper/products', { credentials: 'include' })
      const data = await res.json()
      if (data.success) {
        setProducts(data.data || [])
        if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      } else {
        setError(data.message || 'Failed to load products.')
      }
    } catch (_) {
      setError('Network error.')
    } finally {
      setLoading(false)
    }
  }

  function addToCart(product) {
    if (product.stock_quantity === 0) return
    setCart(prev => {
      const existing = prev.find(c => c.product.id === product.id)
      if (existing) {
        if (existing.quantity >= product.stock_quantity) return prev
        return prev.map(c => c.product.id === product.id ? { ...c, quantity: c.quantity + 1 } : c)
      }
      return [...prev, { product, quantity: 1 }]
    })
  }

  function updateQty(productId, qty) {
    if (qty <= 0) { removeFromCart(productId); return }
    setCart(prev => prev.map(c => {
      if (c.product.id !== productId) return c
      return { ...c, quantity: Math.min(qty, c.product.stock_quantity) }
    }))
  }

  function removeFromCart(productId) {
    setCart(prev => prev.filter(c => c.product.id !== productId))
  }

  const total = cart.reduce((sum, c) => sum + c.product.price * c.quantity, 0)
  const paid = parseFloat(amountPaid) || 0
  const change = paid - total
  const canConfirm = cart.length > 0 && paid >= total

  async function handleConfirm() {
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
          items: cart.map(c => ({ product_id: c.product.id, quantity: c.quantity })),
        }),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (!data.success) { setSaleError(data.message || 'Sale failed.'); return }

      const saleRes = await fetch(`/api/shopkeeper/sales/${data.data.sale_id}`, { credentials: 'include' })
      const saleData = await saleRes.json()
      if (saleData.csrf_token) sessionStorage.setItem('csrf_token', saleData.csrf_token)
      setCompletedSale(saleData.data || data.data)
      await loadProducts()
    } catch (_) {
      setSaleError('Network error. Please try again.')
    } finally {
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
        <div className="max-w-xl mx-auto mt-12 px-4 py-6 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm text-center">
          {error}
          <button onClick={loadProducts} className="block mx-auto mt-3 text-xs underline">Retry</button>
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
              <div className="text-center py-16 bg-white rounded-xl border-2 border-dashed border-gray-200">
                <div className="text-4xl mb-3">📦</div>
                <p className="text-gray-500 text-sm">No products found.</p>
                <button onClick={() => navigate('/shopkeeper/inventory')}
                  className="mt-3 text-sm text-orange-500 hover:underline">
                  Add products to inventory →
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
                      <div className="text-orange-600 font-bold text-sm">PKR {fmtCurrency(p.price)}</div>
                      <div className="mt-1.5 flex items-center justify-between">
                        <span className={`text-xs ${p.stock_quantity <= 5 ? 'text-yellow-600' : 'text-gray-400'}`}>
                          Stock: {p.stock_quantity}
                        </span>
                        {outOfStock ? (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full">Out</span>
                        ) : inCart ? (
                          <span className="text-xs bg-orange-100 text-orange-600 px-1.5 py-0.5 rounded-full">
                            x{inCart.quantity}
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
                        <div className="text-xs text-gray-500">PKR {fmtCurrency(product.price)} each</div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={() => updateQty(product.id, quantity - 1)}
                          className="w-6 h-6 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-bold text-sm leading-none">
                          −
                        </button>
                        <span className="w-6 text-center text-sm font-semibold text-gray-800">{quantity}</span>
                        <button onClick={() => updateQty(product.id, quantity + 1)}
                          className="w-6 h-6 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-bold text-sm leading-none">
                          +
                        </button>
                      </div>
                      <div className="text-xs font-semibold text-gray-800 w-16 text-right">
                        PKR {fmtCurrency(product.price * quantity)}
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
                <input type="number" min="0" step="1" value={amountPaid}
                  onChange={e => setAmountPaid(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                  placeholder="0" />
              </div>

              {/* Change display */}
              {amountPaid !== '' && cart.length > 0 && (
                <div className={`rounded-lg px-3 py-2 mb-3 text-sm font-semibold flex justify-between
                  ${change >= 0 ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'}`}>
                  <span>Change (Wapis)</span>
                  <span>PKR {fmtCurrency(Math.abs(change))}{change < 0 ? ' short' : ''}</span>
                </div>
              )}

              {saleError && (
                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{saleError}</p>
              )}

              <button onClick={handleConfirm} disabled={!canConfirm || submitting}
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
                  <span>Change (Wapis)</span><span>PKR {fmtCurrency(completedSale.change_amount)}</span>
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
