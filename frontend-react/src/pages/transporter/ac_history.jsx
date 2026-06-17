import { useState, useEffect, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const TX_FILTERS = ['all', 'credits', 'debits', 'thisMonth']

export default function AcHistory() {
  const api = useApi()
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [appliedStart, setAppliedStart] = useState('')
  const [appliedEnd, setAppliedEnd] = useState('')
  const [toast, setToast] = useState(null)

  useEffect(() => {
    setLoading(true)
    api.get('/api/history/account')
      .then(d => setTransactions(d.transactions || d.history || []))
      .catch(() => setTransactions([]))
      .finally(() => setLoading(false))
  }, [])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  function applyFilters() {
    setAppliedStart(startDate)
    setAppliedEnd(endDate)
    showToast('Filters applied')
  }

  const now = new Date()
  const cm = now.getMonth(), cy = now.getFullYear()

  const filtered = useMemo(() => {
    let list = transactions
    if (filter === 'credits') list = list.filter(t => (t.type || '').toLowerCase() === 'credit' || parseFloat(t.amount || 0) > 0)
    else if (filter === 'debits') list = list.filter(t => (t.type || '').toLowerCase() === 'debit' || parseFloat(t.amount || 0) < 0)
    else if (filter === 'thisMonth') list = list.filter(t => {
      const d = new Date(t.date || t.created_at)
      return d.getMonth() === cm && d.getFullYear() === cy
    })
    if (appliedStart) list = list.filter(t => new Date(t.date || t.created_at) >= new Date(appliedStart))
    if (appliedEnd) list = list.filter(t => new Date(t.date || t.created_at) <= new Date(appliedEnd + 'T23:59:59'))
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(t =>
        (t.description || '').toLowerCase().includes(q) ||
        (t.reference || '').toLowerCase().includes(q) ||
        String(t.id || '').includes(q)
      )
    }
    return list
  }, [transactions, filter, search, appliedStart, appliedEnd, cm, cy])

  const stats = useMemo(() => {
    const credits = transactions.filter(t => (t.type || '').toLowerCase() === 'credit' || parseFloat(t.amount || 0) > 0)
    const debits = transactions.filter(t => (t.type || '').toLowerCase() === 'debit' || parseFloat(t.amount || 0) < 0)
    const totalCredits = credits.reduce((s, t) => s + Math.abs(parseFloat(t.amount || 0)), 0)
    const totalDebits = debits.reduce((s, t) => s + Math.abs(parseFloat(t.amount || 0)), 0)
    return {
      total: transactions.length,
      credits: totalCredits,
      debits: totalDebits,
      net: totalCredits - totalDebits,
    }
  }, [transactions])

  function exportCSV() {
    if (!filtered.length) { showToast('No data to export', 'error'); return }
    const headers = ['Date', 'Description', 'Type', 'Amount', 'Reference', 'Status']
    const rows = filtered.map(t => [
      t.date || t.created_at || '',
      (t.description || '').replace(/,/g, ' '),
      t.type || '',
      t.amount || 0,
      t.reference || '',
      t.status || '',
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = 'account_history.csv'
    a.click()
    showToast('Excel export downloaded')
  }

  function exportPDF() {
    window.print()
    showToast('Opening print dialog for PDF')
  }

  function amountColor(t) {
    const isCredit = (t.type || '').toLowerCase() === 'credit' || parseFloat(t.amount || 0) > 0
    return isCredit ? '#27ae60' : '#e74c3c'
  }

  function amountDisplay(t) {
    const amt = parseFloat(t.amount || 0)
    const isCredit = (t.type || '').toLowerCase() === 'credit' || amt > 0
    return `${isCredit ? '+' : '-'} PKR ${Math.abs(amt).toLocaleString()}`
  }

  function statusBadge(status) {
    const colors = { completed: '#27ae60', pending: '#f39c12', failed: '#e74c3c', success: '#27ae60' }
    return (
      <span style={{
        background: colors[(status || '').toLowerCase()] || '#95a5a6',
        color: '#fff', padding: '3px 10px', borderRadius: 20, fontSize: 12,
        fontWeight: 600, textTransform: 'capitalize',
      }}>{status || 'unknown'}</span>
    )
  }

  return (
    <TransporterLayout>
      <div className="page-account-history">
        <div className="page-title">
          <h1>Account History</h1>
          <p>View your complete account activity and transaction history</p>
        </div>

        <div className="filters-section">
          <div className="filter-controls">
            <div className="search-box">
              <i className="fas fa-search"></i>
              <input
                type="text"
                placeholder="Search transactions..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="date-filters">
              <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
              <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
              <button className="filter-btn" onClick={applyFilters}>Apply Filters</button>
            </div>
          </div>
          <div className="export-options">
            <button className="export-btn" onClick={exportPDF}>
              <i className="fas fa-file-pdf"></i> Export PDF
            </button>
            <button className="export-btn" onClick={exportCSV}>
              <i className="fas fa-file-excel"></i> Export Excel
            </button>
          </div>
        </div>

        <div className="summary-cards">
          <div className="summary-card">
            <div className="summary-icon"><i className="fas fa-calendar-alt"></i></div>
            <div className="summary-content">
              <div className="summary-value">{stats.total}</div>
              <div className="summary-label">Total Transactions</div>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-icon"><i className="fas fa-arrow-up"></i></div>
            <div className="summary-content">
              <div className="summary-value" style={{ color: '#27ae60' }}>PKR {stats.credits.toLocaleString()}</div>
              <div className="summary-label">Total Credits</div>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-icon"><i className="fas fa-arrow-down"></i></div>
            <div className="summary-content">
              <div className="summary-value" style={{ color: '#e74c3c' }}>PKR {stats.debits.toLocaleString()}</div>
              <div className="summary-label">Total Debits</div>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-icon"><i className="fas fa-balance-scale"></i></div>
            <div className="summary-content">
              <div className="summary-value" style={{ color: stats.net >= 0 ? '#27ae60' : '#e74c3c' }}>
                PKR {stats.net.toLocaleString()}
              </div>
              <div className="summary-label">Net Balance</div>
            </div>
          </div>
        </div>

        <div className="history-table-container">
          <div className="table-header">
            <h2 className="section-title">Transaction History</h2>
            <div className="table-actions">
              {TX_FILTERS.map(f => (
                <button
                  key={f}
                  className={`filter-btn${filter === f ? ' active' : ''}`}
                  onClick={() => setFilter(f)}
                >
                  {f === 'all' ? 'All' : f === 'thisMonth' ? 'This Month' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Date &amp; Time</th><th>Description</th><th>Type</th>
                  <th>Amount</th><th>Reference</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 24 }}>Loading...</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 24 }}>No transactions found</td></tr>
                ) : filtered.map((t, i) => (
                  <tr key={t.id || i}>
                    <td>{t.date || t.created_at || '-'}</td>
                    <td>{t.description || '-'}</td>
                    <td style={{ textTransform: 'capitalize' }}>{t.type || '-'}</td>
                    <td style={{ fontWeight: 600, color: amountColor(t) }}>{amountDisplay(t)}</td>
                    <td>{t.reference || '-'}</td>
                    <td>{statusBadge(t.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="recommendations-section">
          <h2 className="section-title">Financial Insights</h2>
          <div className="recommendations-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginTop: 16 }}>
            {stats.net < 0 && (
              <div style={{ background: '#fff3cd', borderRadius: 10, padding: 16, border: '1px solid #ffc107' }}>
                <i className="fas fa-exclamation-triangle" style={{ color: '#f39c12', marginBottom: 8 }}></i>
                <p style={{ margin: 0, fontWeight: 600 }}>Negative balance alert</p>
                <p style={{ margin: '4px 0 0', fontSize: 13 }}>Your debits exceed credits. Review your expenses.</p>
              </div>
            )}
            {stats.total > 0 && (
              <div style={{ background: '#d4edda', borderRadius: 10, padding: 16, border: '1px solid #28a745' }}>
                <i className="fas fa-chart-line" style={{ color: '#27ae60', marginBottom: 8 }}></i>
                <p style={{ margin: 0, fontWeight: 600 }}>Activity summary</p>
                <p style={{ margin: '4px 0 0', fontSize: 13 }}>{stats.total} transactions recorded in your account.</p>
              </div>
            )}
          </div>
        </div>

        <div className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/transporter/about">About Us</Link>
            <Link to="/transporter/contact">Contact</Link>
            <Link to="/transporter/terms">Terms &amp; Conditions</Link>
            <Link to="/transporter/privacy">Privacy Policy</Link>
            <Link to="/transporter/help">Help Center</Link>
            <Link to="/transporter/partner">Partner With Us</Link>
          </div>
        </div>
      </div>

      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
          background: toast.type === 'error' ? '#e74c3c' : '#27ae60',
          color: '#fff', padding: '12px 20px', borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        }}>
          {toast.msg}
        </div>
      )}
    </TransporterLayout>
  )
}
