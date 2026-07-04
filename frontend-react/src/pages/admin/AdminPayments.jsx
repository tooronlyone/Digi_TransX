import { useEffect, useState } from 'react'
import { adminRequest, dateText, money, qs } from './adminApi'

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:      { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  input:    { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b' },
  select:   { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', cursor: 'pointer' },
  btnPrimary:  { padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 700, fontSize: 14 },
  btnOutline:  { padding: '10px 20px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
  btnWarning:  { padding: '10px 20px', borderRadius: 10, border: '1.5px solid #fde68a', cursor: 'pointer', background: '#fffbeb', color: '#d97706', fontWeight: 700, fontSize: 14 },
  th:       { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:       { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  notice:   { background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '12px 16px', color: '#16a34a', fontSize: 13, marginBottom: 16 },
  badgeStatus: (s) => {
    const map = { pending: ['#fffbeb','#d97706'], paid: ['#f0fdf4','#16a34a'], failed: ['#fef2f2','#dc2626'] }
    const [bg, color] = map[s] || ['#f1f5f9','#475569']
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: bg, color }
  },
}

export default function AdminPayments() {
  const [filters, setFilters] = useState({ status: '', month_year: '' })
  const [items, setItems]     = useState([])
  const [notice, setNotice]   = useState('')
  const [error, setError]     = useState('')

  async function load(nextFilters = filters) {
    try {
      const json = await adminRequest(`/api/admin/payments${qs(nextFilters)}`)
      setItems(json.payments || [])
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  async function run(action) {
    const label = action === 'process' ? 'process payments' : 'apply penalties'
    if (!window.confirm(`Confirm ${label}?`)) return
    try {
      const json = await adminRequest(
        `/api/admin/payments/${action === 'process' ? 'process' : 'apply-penalties'}`,
        { method: 'POST', body: JSON.stringify({}) }
      )
      setNotice(action === 'process'
        ? `Processed ${json.processed}, failed ${json.failed}`
        : `Penalties applied: ${json.penalties_applied}`)
      load()
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={S.heading}>Payments</h1>
          <p style={S.sub}>Monthly agreement payments, processing, and penalty records.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button onClick={() => run('process')} style={S.btnPrimary}>
            <i className="fas fa-play" style={{ marginRight: 8 }} />Process Payments
          </button>
          <button onClick={() => run('penalties')} style={S.btnWarning}>
            <i className="fas fa-gavel" style={{ marginRight: 8 }} />Apply Penalties
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <select style={S.select} value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}>
          <option value="">All status</option>
          <option value="pending">Pending</option>
          <option value="paid">Paid</option>
          <option value="failed">Failed</option>
        </select>
        <input style={S.input} placeholder="YYYY-MM" value={filters.month_year} onChange={e => setFilters({ ...filters, month_year: e.target.value })} />
        <button onClick={() => load()} style={S.btnOutline}><i className="fas fa-magnifying-glass" style={{ marginRight: 8 }} />Apply</button>
      </div>

      {notice && <div style={S.notice}><i className="fas fa-circle-check" style={{ marginRight: 8 }} />{notice}</div>}
      {error  && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Agreement','Client','Transporter','Truck','Month','KM','Amount','Status','Due Date'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>#{item.agreement_id}</td>
                <td style={S.td}>{item.client_name}</td>
                <td style={S.td}>{item.transporter_name}</td>
                <td style={S.td}>{item.truck_number}</td>
                <td style={S.td}>{item.month_year}</td>
                <td style={S.td}>{item.total_km}</td>
                <td style={{ ...S.td, fontWeight: 600 }}>{money(item.final_amount)}</td>
                <td style={S.td}><span style={S.badgeStatus(item.status)}>{item.status}</span></td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.payment_due_date)}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No payment records found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
