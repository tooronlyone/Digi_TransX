import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { fmtCurrency, fmtDate, fmtDateTime } from './posUtils'

export default function SalesAnalyticsPage() {
  const navigate = useNavigate()
  const today = new Date().toISOString().slice(0, 10)
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)

  const [analytics, setAnalytics] = useState(null)
  const [sales, setSales] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dateFrom, setDateFrom] = useState(thirtyDaysAgo)
  const [dateTo, setDateTo] = useState(today)
  const [expandedSale, setExpandedSale] = useState(null)
  const [topSort, setTopSort] = useState('revenue') // 'revenue' | 'qty'

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    setLoading(true)
    setError('')
    try {
      const params = `date_from=${dateFrom}&date_to=${dateTo}`
      const [aRes, sRes] = await Promise.all([
        fetch(`/api/shopkeeper/sales/analytics?${params}`, { credentials: 'include' }),
        fetch(`/api/shopkeeper/sales?${params}&limit=100`, { credentials: 'include' }),
      ])
      const [aData, sData] = await Promise.all([aRes.json(), sRes.json()])
      if (aData.csrf_token) sessionStorage.setItem('csrf_token', aData.csrf_token)
      if (aData.success) setAnalytics(aData.data)
      else setError(aData.message || 'Failed to load analytics.')
      if (sData.success) setSales(sData.data || [])
    } catch (_) {
      setError('Network error. Please refresh.')
    } finally {
      setLoading(false)
    }
  }

  const summary = analytics?.summary || {}
  const revenueByDate = analytics?.revenue_by_date || []
  const topProducts = [...(analytics?.top_products || [])].sort((a, b) =>
    topSort === 'qty' ? b.total_qty - a.total_qty : b.total_revenue - a.total_revenue
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-orange-600">Sales Analytics</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate('/shopkeeper/pos')}
            className="text-xs px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors font-medium">
            New Sale
          </button>
          <button onClick={() => navigate('/shopkeeper/dashboard')}
            className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors">
            ← Dashboard
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Date filter */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">From</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">To</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
          <button onClick={loadAll}
            className="px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-lg transition-colors">
            Apply
          </button>
        </div>

        {error && (
          <div className="mb-6 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">{error}</div>
        )}

        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              {[
                { label: 'Total Revenue', value: `PKR ${fmtCurrency(summary.total_revenue || 0)}`, icon: '💰', color: 'text-green-700 bg-green-50' },
                { label: 'Total Sales', value: summary.total_sales || 0, icon: '🧾', color: 'text-blue-700 bg-blue-50' },
                { label: 'Average Sale', value: `PKR ${fmtCurrency(summary.avg_sale_value || 0)}`, icon: '📈', color: 'text-orange-700 bg-orange-50' },
              ].map(card => (
                <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-5">
                  <div className={`inline-flex items-center justify-center w-10 h-10 rounded-xl text-xl mb-3 ${card.color}`}>
                    {card.icon}
                  </div>
                  <div className="text-2xl font-black text-gray-800">{card.value}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{card.label}</div>
                </div>
              ))}
            </div>

            {/* Revenue bar chart */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
              <h2 className="font-bold text-gray-800 mb-4">Daily Revenue</h2>
              {revenueByDate.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-10">No sales in this period.</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={revenueByDate} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
                    <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(v) => [`PKR ${fmtCurrency(v)}`, 'Revenue']}
                      labelFormatter={l => `Date: ${l}`}
                    />
                    <Bar dataKey="revenue" fill="#f97316" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Top products */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-bold text-gray-800">Top Products</h2>
                <div className="flex gap-1">
                  <button
                    onClick={() => setTopSort('revenue')}
                    className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${topSort === 'revenue' ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    By Revenue
                  </button>
                  <button
                    onClick={() => setTopSort('qty')}
                    className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${topSort === 'qty' ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    By Qty
                  </button>
                </div>
              </div>
              {topProducts.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">No data.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 font-semibold text-gray-600">#</th>
                      <th className="text-left py-2 font-semibold text-gray-600">Product</th>
                      <th className="text-right py-2 font-semibold text-gray-600">Qty Sold</th>
                      <th className="text-right py-2 font-semibold text-gray-600">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topProducts.map((p, i) => (
                      <tr key={p.product_name} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 text-gray-400 text-xs">{i + 1}</td>
                        <td className="py-2 font-medium text-gray-800">{p.product_name}</td>
                        <td className="py-2 text-right font-mono text-gray-700">{p.total_qty}</td>
                        <td className="py-2 text-right font-mono text-gray-800 font-semibold">
                          PKR {fmtCurrency(p.total_revenue)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Sales history */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="font-bold text-gray-800 mb-4">Sales History</h2>
              {sales.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">No sales in this period.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 font-semibold text-gray-600">Receipt</th>
                      <th className="text-left py-2 font-semibold text-gray-600 hidden sm:table-cell">Purchaser</th>
                      <th className="text-left py-2 font-semibold text-gray-600 hidden md:table-cell">Date</th>
                      <th className="text-right py-2 font-semibold text-gray-600">Total</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {sales.map(sale => (
                      <>
                        <tr key={sale.id}
                          className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                          onClick={() => setExpandedSale(expandedSale === sale.id ? null : sale.id)}>
                          <td className="py-2 font-mono text-xs text-gray-600">{sale.receipt_number}</td>
                          <td className="py-2 text-gray-700 hidden sm:table-cell">{sale.purchaser_name || '—'}</td>
                          <td className="py-2 text-gray-500 text-xs hidden md:table-cell">{fmtDate(sale.sale_date)}</td>
                          <td className="py-2 text-right font-semibold text-gray-800">PKR {fmtCurrency(sale.total_amount)}</td>
                          <td className="py-2 text-right text-gray-400 text-xs pl-2">
                            {expandedSale === sale.id ? '▲' : '▼'}
                          </td>
                        </tr>
                        {expandedSale === sale.id && (
                          <tr key={`${sale.id}-detail`}>
                            <td colSpan={5} className="px-4 py-3 bg-gray-50">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="text-gray-500">
                                    <th className="text-left pb-1">Product</th>
                                    <th className="text-center pb-1">Qty</th>
                                    <th className="text-right pb-1">Unit Price</th>
                                    <th className="text-right pb-1">Subtotal</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(sale.items || []).map((item, i) => (
                                    <tr key={i} className="border-t border-gray-200">
                                      <td className="py-1">{item.product_name}</td>
                                      <td className="py-1 text-center">{item.quantity}</td>
                                      <td className="py-1 text-right">PKR {fmtCurrency(item.unit_price)}</td>
                                      <td className="py-1 text-right font-medium">PKR {fmtCurrency(item.subtotal)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <div className="mt-2 pt-2 border-t border-gray-200 flex justify-end gap-6 text-xs">
                                <span className="text-gray-500">Paid: PKR {fmtCurrency(sale.amount_paid)}</span>
                                <span className="text-green-700 font-semibold">Wapis: PKR {fmtCurrency(sale.change_amount)}</span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
