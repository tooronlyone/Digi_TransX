import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

const PIE_COLORS = ['#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444', '#f59e0b', '#06b6d4', '#84cc16']

function statOf(values, fn) {
  const nums = values.map(Number).filter(n => !isNaN(n))
  if (!nums.length) return '—'
  if (fn === 'sum') return nums.reduce((a, b) => a + b, 0).toLocaleString('en-PK', { maximumFractionDigits: 2 })
  if (fn === 'avg') return (nums.reduce((a, b) => a + b, 0) / nums.length).toLocaleString('en-PK', { maximumFractionDigits: 2 })
  if (fn === 'min') return Math.min(...nums).toLocaleString('en-PK', { maximumFractionDigits: 2 })
  if (fn === 'max') return Math.max(...nums).toLocaleString('en-PK', { maximumFractionDigits: 2 })
  return '—'
}

function useTableData(tableId) {
  const [tableData, setTableData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`/api/shopkeeper/tables/${tableId}`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setTableData(data.data)
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
        } else {
          setError(data.message || 'Failed to load table.')
        }
      })
      .catch(() => setError('Network error. Please refresh.'))
      .finally(() => setLoading(false))
  }, [tableId])

  return { tableData, loading, error }
}

export default function AnalysisView() {
  const { tableId } = useParams()
  const navigate = useNavigate()
  const { tableData, loading, error } = useTableData(tableId)

  const [barCol, setBarCol]         = useState('')
  const [pieCol, setPieCol]         = useState('')
  const [filterCol, setFilterCol]   = useState('')
  const [filterVal, setFilterVal]   = useState('')
  const [dateCol, setDateCol]       = useState('')
  const [dateFrom, setDateFrom]     = useState('')
  const [dateTo, setDateTo]         = useState('')

  const columns    = tableData?.columns || []
  const allRows    = tableData?.rows    || []

  const numberCols  = columns.filter(c => c.type === 'number')
  const textCols    = columns.filter(c => c.type === 'text' || c.type === 'dropdown')
  const dateCols    = columns.filter(c => c.type === 'date')

  // filtered rows (by column value + date range)
  const filteredRows = useMemo(() => {
    let result = allRows
    if (filterCol && filterVal.trim()) {
      const val = filterVal.trim().toLowerCase()
      result = result.filter(r => String(r.values[filterCol] ?? '').toLowerCase().includes(val))
    }
    if (dateCol && dateFrom) {
      result = result.filter(r => {
        const d = String(r.values[dateCol] ?? '')
        return d >= dateFrom
      })
    }
    if (dateCol && dateTo) {
      result = result.filter(r => {
        const d = String(r.values[dateCol] ?? '')
        return d <= dateTo
      })
    }
    return result
  }, [allRows, filterCol, filterVal, dateCol, dateFrom, dateTo])

  // bar chart data: each row as a bar with its barCol value
  const barData = useMemo(() => {
    if (!barCol) return []
    return filteredRows
      .map((row, i) => {
        const label = textCols.length > 0
          ? String(row.values[textCols[0].name] ?? `Row ${i + 1}`)
          : `Row ${i + 1}`
        const value = parseFloat(row.values[barCol]) || 0
        return { name: label.slice(0, 16), value }
      })
      .slice(0, 30)
  }, [barCol, filteredRows, textCols])

  // pie chart data: group by pieCol value, count occurrences
  const pieData = useMemo(() => {
    if (!pieCol) return []
    const counts = {}
    filteredRows.forEach(row => {
      const key = String(row.values[pieCol] ?? '(empty)')
      counts[key] = (counts[key] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([name, value]) => ({ name, value }))
  }, [pieCol, filteredRows])

  // summary stats for all number columns
  const summaryStats = useMemo(() => {
    return numberCols.map(col => {
      const vals = filteredRows.map(r => r.values[col.name]).filter(v => v !== '' && v !== null && v !== undefined)
      return {
        col: col.name,
        sum: statOf(vals, 'sum'),
        avg: statOf(vals, 'avg'),
        min: statOf(vals, 'min'),
        max: statOf(vals, 'max'),
        count: vals.length,
      }
    })
  }, [numberCols, filteredRows])

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (error) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <p className="text-red-600 font-semibold">{error}</p>
        <button onClick={() => navigate('/shopkeeper/dashboard')}
          className="mt-4 text-sm text-blue-500 hover:underline">← Back to Dashboard</button>
      </div>
    </div>
  )

  const hasFilters = !!(filterVal.trim() || (dateCol && (dateFrom || dateTo)))

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(`/shopkeeper/table/${tableId}`)}
            className="text-gray-400 hover:text-gray-700 transition-colors text-sm">
            ← Table
          </button>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-blue-600 truncate max-w-[160px]">
            Analysis — {tableData?.name}
          </span>
        </div>
        <button
          onClick={() => window.open(`/api/shopkeeper/tables/${tableId}/export`, '_blank')}
          className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 text-gray-600 text-xs font-semibold rounded-lg hover:bg-gray-50 transition-colors">
          ↓ Export CSV
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Filter toolbar */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Filter Data</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Column filter */}
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Filter by column</label>
              <select value={filterCol} onChange={e => { setFilterCol(e.target.value); setFilterVal('') }}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 text-gray-700">
                <option value="">— All columns —</option>
                {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Search value</label>
              <input value={filterVal} onChange={e => setFilterVal(e.target.value)}
                disabled={!filterCol}
                placeholder={filterCol ? `Search in ${filterCol}...` : 'Select column first'}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>
            {/* Date filter */}
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Date column</label>
              <select value={dateCol} onChange={e => setDateCol(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 text-gray-700">
                <option value="">— None —</option>
                {dateCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">From</label>
                <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                  disabled={!dateCol}
                  className="w-full px-2 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 disabled:bg-gray-50" />
              </div>
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">To</label>
                <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                  disabled={!dateCol}
                  className="w-full px-2 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 disabled:bg-gray-50" />
              </div>
            </div>
          </div>
          {hasFilters && (
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-orange-600 font-medium bg-orange-50 px-2 py-1 rounded-full border border-orange-200">
                Showing {filteredRows.length} of {allRows.length} rows
              </span>
              <button onClick={() => { setFilterCol(''); setFilterVal(''); setDateCol(''); setDateFrom(''); setDateTo('') }}
                className="text-xs text-gray-500 hover:text-red-500 transition-colors">
                Clear filters
              </button>
            </div>
          )}
        </div>

        {/* Summary stats */}
        {summaryStats.length > 0 && (
          <div>
            <h2 className="text-sm font-bold text-gray-700 mb-3">Number Column Summary</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {summaryStats.map(stat => (
                <div key={stat.col} className="bg-white rounded-xl border border-gray-200 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-8 h-8 bg-orange-100 rounded-lg flex items-center justify-center text-base">🔢</div>
                    <h3 className="font-bold text-gray-800 text-sm">{stat.col}</h3>
                    <span className="ml-auto text-xs text-gray-400">{stat.count} values</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: 'Sum', value: stat.sum, color: 'text-blue-600' },
                      { label: 'Average', value: stat.avg, color: 'text-green-600' },
                      { label: 'Min', value: stat.min, color: 'text-gray-600' },
                      { label: 'Max', value: stat.max, color: 'text-orange-600' },
                    ].map(s => (
                      <div key={s.label} className="bg-gray-50 rounded-lg p-2.5">
                        <p className="text-xs text-gray-500">{s.label}</p>
                        <p className={`text-base font-bold ${s.color} truncate`}>{s.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bar chart */}
        {numberCols.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-gray-700">Bar Chart</h2>
              <select value={barCol} onChange={e => setBarCol(e.target.value)}
                className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 text-gray-700">
                <option value="">Select column...</option>
                {numberCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            {barCol && barData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={barData} margin={{ top: 5, right: 10, left: 0, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7280' }} angle={-35} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }} />
                  <Bar dataKey="value" fill="#f97316" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
                {barCol ? 'No data to display.' : 'Select a number column above.'}
              </div>
            )}
          </div>
        )}

        {/* Pie chart */}
        {textCols.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-gray-700">Pie Chart (by category)</h2>
              <select value={pieCol} onChange={e => setPieCol(e.target.value)}
                className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 text-gray-700">
                <option value="">Select column...</option>
                {textCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            {pieCol && pieData.length > 0 ? (
              <div className="flex flex-col sm:flex-row items-center gap-4">
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      labelLine={false}>
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }} />
                    <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
                {pieCol ? 'No data to display.' : 'Select a text or dropdown column above.'}
              </div>
            )}
          </div>
        )}

        {/* No columns available hint */}
        {numberCols.length === 0 && textCols.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
            <p className="text-sm">This table has no Number or Text columns — add some to enable charts.</p>
          </div>
        )}
      </main>
    </div>
  )
}
