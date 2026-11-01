import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { fmtCurrency, fmtDate } from './posUtils'

export default function SalesAnalyticsPage({ view = 'overview' }) {
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
  const [productQuery, setProductQuery] = useState('')

  // The first report load intentionally uses the initial 30-day date range.
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      if (aRes.status === 404 && sRes.status === 404) {
        setAnalytics({ summary: {}, revenue_by_date: [], top_products: [] })
        setSales([])
      } else if ([aRes.status, sRes.status].some(status => status === 401 || status === 403)) {
        setError('Your session has expired. Please sign in again.')
      } else if (aRes.ok && aData.success) {
        setAnalytics(aData.data)
        setSales(sRes.ok && sData.success ? (sData.data || []) : [])
      } else {
        setError('We could not load your sales report right now. Please try again.')
      }
    } catch {
      setError('We could not connect to the shop service. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  const summary = analytics?.summary || {}
  const revenueByDate = analytics?.revenue_by_date || []
  const topProducts = [...(analytics?.top_products || [])].sort((a, b) =>
    topSort === 'qty' ? b.total_qty - a.total_qty : b.total_revenue - a.total_revenue
  )
  const filteredSales = sales.filter(sale => {
    const query = productQuery.trim().toLowerCase()
    if (!query) return true
    return (sale.items || []).some(item => String(item.product_name || '').toLowerCase().includes(query))
  })

  async function exportHistoryPdf() {
    const { jsPDF } = await import('jspdf')
    const pdf = new jsPDF({ unit: 'mm', format: 'a4' })
    const shop = (() => { try { return JSON.parse(sessionStorage.getItem('user') || '{}').shop_name || 'My Shop' } catch { return 'My Shop' } })()
    let y = 17
    const addHeader = () => {
      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(17); pdf.text('DigiTransX Sales History', 14, y)
      y += 7; pdf.setFontSize(10); pdf.text(shop, 14, y)
      y += 5; pdf.setFont('helvetica', 'normal'); pdf.setTextColor(90)
      pdf.text(`Period: ${dateFrom} to ${dateTo}${productQuery.trim() ? `  |  Product: ${productQuery.trim()}` : ''}`, 14, y)
      y += 8; pdf.setTextColor(0); pdf.setDrawColor(210); pdf.line(14, y, 196, y); y += 7
    }
    addHeader()
    if (filteredSales.length === 0) {
      pdf.text('No matching sales found.', 14, y)
    } else {
      for (const sale of filteredSales) {
        if (y > 270) { pdf.addPage(); y = 17; addHeader() }
        pdf.setFont('helvetica', 'bold'); pdf.setFontSize(10)
        pdf.text(`${sale.receipt_number}  |  ${fmtDate(sale.sale_date)}  |  ${sale.purchaser_name || 'Walk-in customer'}`, 14, y)
        pdf.text(`PKR ${fmtCurrency(sale.total_amount)}`, 196, y, { align: 'right' }); y += 6
        pdf.setFont('helvetica', 'normal'); pdf.setFontSize(9); pdf.setTextColor(70)
        for (const item of (sale.items || []).filter(item => !productQuery.trim() || String(item.product_name || '').toLowerCase().includes(productQuery.trim().toLowerCase()))) {
          pdf.text(`${item.product_name}  -  ${item.quantity} x PKR ${fmtCurrency(item.unit_price)}`, 18, y)
          pdf.text(`PKR ${fmtCurrency(item.subtotal)}`, 196, y, { align: 'right' }); y += 5
        }
        pdf.setTextColor(0); pdf.setDrawColor(230); pdf.line(14, y, 196, y); y += 6
      }
    }
    pdf.save(`sales-history-${dateFrom}-to-${dateTo}.pdf`)
  }

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
        {view === 'overview' && (
          <div className="shopkeeper-report-actions">
            <button onClick={() => navigate('/shopkeeper/sales-analytics/charts')}>
              <span className="blue"><i className="fa-solid fa-chart-line" /></span>
              <span><strong>Graphical Analysis</strong><small>View revenue trends and product performance</small></span>
              <i className="fa-solid fa-arrow-right" />
            </button>
            <button onClick={() => navigate('/shopkeeper/sales-analytics/history')}>
              <span className="orange"><i className="fa-solid fa-clock-rotate-left" /></span>
              <span><strong>Sales History</strong><small>Search, filter and export past sales</small></span>
              <i className="fa-solid fa-arrow-right" />
            </button>
          </div>
        )}

        {/* Filters only belong to the dedicated charts/history views. */}
        {view !== 'overview' && <div className="shopkeeper-report-filters">
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
          {view === 'history' && <>
            <div className="shopkeeper-report-filters__search">
              <label className="block text-xs font-medium text-gray-600 mb-1">Product Name</label>
              <div><i className="fa-solid fa-magnifying-glass" /><input value={productQuery} onChange={e => setProductQuery(e.target.value)} placeholder="Search a product..." /></div>
            </div>
            <button onClick={exportHistoryPdf} className="shopkeeper-export-pdf" disabled={filteredSales.length === 0}>
              <i className="fa-solid fa-file-pdf" /> Export PDF
            </button>
          </>}
        </div>}

        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="shopkeeper-state-card shopkeeper-state-card--error">
            <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-triangle-exclamation" /></span>
            <h2>Sales report could not be loaded</h2>
            <p>{error}</p>
            <button onClick={loadAll}><i className="fa-solid fa-rotate-right" /> Try Again</button>
          </div>
        ) : sales.length === 0 ? (
          <div className="shopkeeper-state-card shopkeeper-state-card--sales">
            <span className="shopkeeper-state-card__icon"><i className="fa-solid fa-receipt" /></span>
            <h2>No sales recorded yet</h2>
            <p>Once a customer makes a purchase, sales totals and reports will appear here.</p>
            <button className="shopkeeper-state-card__primary" onClick={() => navigate('/shopkeeper/pos')}>
              <i className="fa-solid fa-plus" /> Create First Sale
            </button>
          </div>
        ) : (
          <>
            {/* Summary cards: last 30 days load automatically on the overview. */}
            {view !== 'history' && <>
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
            </>}

            {/* Revenue bar chart */}
            {view === 'charts' && (
            <div className="shopkeeper-revenue-chart mb-6">
              <div className="shopkeeper-revenue-chart__header">
                <div>
                  <span className="shopkeeper-revenue-chart__eyebrow">REVENUE TREND</span>
                  <h2>Daily Revenue</h2>
                  <p>Sales collected during the selected period</p>
                </div>
                <span className="shopkeeper-revenue-chart__total">
                  <small>Period total</small>
                  <strong>PKR {fmtCurrency(summary.total_revenue || 0)}</strong>
                </span>
              </div>
              {revenueByDate.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-10">No sales in this period.</p>
              ) : (
                <div className="shopkeeper-revenue-chart__plot">
                <ResponsiveContainer width="100%" height={270}>
                  <BarChart data={revenueByDate} margin={{ top: 18, right: 18, left: 8, bottom: 6 }} barCategoryGap="35%">
                    <defs>
                      <linearGradient id="shopRevenueBar" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#3b82f6" />
                        <stop offset="100%" stopColor="#2563eb" />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="4 5" stroke="#e8eef5" />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#829ab1' }} tickMargin={12}
                      tickFormatter={d => new Date(`${d}T00:00:00`).toLocaleDateString('en-PK', { day: '2-digit', month: 'short' })} />
                    <YAxis axisLine={false} tickLine={false} width={64} tick={{ fontSize: 10, fill: '#829ab1' }}
                      tickFormatter={v => v >= 1000 ? `PKR ${(v/1000).toFixed(v % 1000 ? 1 : 0)}k` : `PKR ${v}`} />
                    <Tooltip
                      cursor={{ fill: 'rgba(37, 99, 235, 0.045)', radius: 10 }}
                      formatter={(v) => [`PKR ${fmtCurrency(v)}`, 'Revenue']}
                      labelFormatter={l => new Date(`${l}T00:00:00`).toLocaleDateString('en-PK', { day: '2-digit', month: 'long', year: 'numeric' })}
                      contentStyle={{ border: '1px solid #dbe5f0', borderRadius: 12, boxShadow: '0 12px 28px rgba(15,42,67,.12)', fontSize: 12 }}
                    />
                    <Bar dataKey="revenue" fill="url(#shopRevenueBar)" radius={[8, 8, 3, 3]} maxBarSize={64} />
                  </BarChart>
                </ResponsiveContainer>
                </div>
              )}
            </div>
            )}

            {/* Top products */}
            {view !== 'history' && (
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
            )}

            {/* Sales history */}
            {view === 'history' && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="shopkeeper-history-heading"><div><h2>Sales History</h2><p>Newest sales appear first</p></div><span>{filteredSales.length} result{filteredSales.length !== 1 ? 's' : ''}</span></div>
              {filteredSales.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-10">No sales match the selected filters.</p>
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
                    {filteredSales.map(sale => (
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
                                <span className="text-green-700 font-semibold">Change: PKR {fmtCurrency(sale.change_amount)}</span>
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
            )}
          </>
        )}
      </main>
    </div>
  )
}
