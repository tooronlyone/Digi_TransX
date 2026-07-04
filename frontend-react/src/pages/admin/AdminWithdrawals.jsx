import { useEffect, useState } from 'react'
import { adminRequest, dateText, money, qs } from './adminApi'

const S = {
  heading:    { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:        { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:       { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  select:     { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', cursor: 'pointer' },
  th:         { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:         { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:      { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badgeStatus: (s) => {
    const map = { pending: ['#fffbeb','#d97706'], approved: ['#f0fdf4','#16a34a'], rejected: ['#fef2f2','#dc2626'] }
    const [bg, color] = map[s] || ['#f1f5f9','#475569']
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: bg, color }
  },
  btnGreen:   { padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', background: '#f0fdf4', color: '#16a34a', fontWeight: 600, fontSize: 13 },
  btnRed:     { padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', background: '#fef2f2', color: '#dc2626', fontWeight: 600, fontSize: 13 },
}

export default function AdminWithdrawals() {
  const [status, setStatus] = useState('pending')
  const [items, setItems]   = useState([])
  const [error, setError]   = useState('')

  async function load(nextStatus = status) {
    try {
      const json = await adminRequest(`/api/admin/wallet/withdrawals${qs({ status: nextStatus })}`)
      setItems(json.withdrawals || [])
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  async function act(id, action) {
    if (action === 'approve' && !window.confirm('Approve this withdrawal?')) return
    try {
      await adminRequest(`/api/admin/wallet/withdrawals/${id}/${action}`, { method: 'POST', body: JSON.stringify({}) })
      load()
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={S.heading}>Wallet Withdrawals</h1>
          <p style={S.sub}>Review and process pending withdrawal requests.</p>
        </div>
        <select style={S.select} value={status} onChange={e => { setStatus(e.target.value); load(e.target.value) }}>
          <option value="">All status</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['User','Amount','Requested At','Status','Locked Balance',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={S.td}>
                  <div style={{ fontWeight: 600, color: '#0f172a' }}>{item.user_name}</div>
                  <div style={{ fontSize: 12, color: '#94a3b8' }}>{item.email}</div>
                </td>
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>{money(item.amount)}</td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.requested_at)}</td>
                <td style={S.td}><span style={S.badgeStatus(item.status)}>{item.status}</span></td>
                <td style={S.td}>{money(item.current_locked_balance)}</td>
                <td style={S.td}>
                  {item.status === 'pending' && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => act(item.id, 'approve')} style={S.btnGreen}>
                        <i className="fas fa-check" style={{ marginRight: 6 }} />Approve
                      </button>
                      <button onClick={() => act(item.id, 'reject')} style={S.btnRed}>
                        <i className="fas fa-times" style={{ marginRight: 6 }} />Reject
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={6} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No withdrawal requests found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
