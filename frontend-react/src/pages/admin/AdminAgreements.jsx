import { useEffect, useState } from 'react'
import { adminRequest, dateText, qs } from './adminApi'

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:      { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  select:   { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', cursor: 'pointer' },
  th:       { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:       { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badgeStatus: (s) => {
    const map = { active: ['#f0fdf4','#16a34a'], completed: ['#eff6ff','#2563eb'], cancelled: ['#fef2f2','#dc2626'] }
    const [bg, color] = map[s] || ['#f1f5f9','#475569']
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: bg, color }
  },
}

export default function AdminAgreements() {
  const [status, setStatus] = useState('')
  const [items, setItems]   = useState([])
  const [detail, setDetail] = useState(null)
  const [error, setError]   = useState('')

  async function load(nextStatus = status) {
    try {
      const json = await adminRequest(`/api/admin/agreements${qs({ status: nextStatus })}`)
      setItems(json.agreements || [])
    } catch (err) { setError(err.message) }
  }

  async function view(id) {
    try { setDetail(await adminRequest(`/api/admin/agreements/${id}`)) }
    catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={S.heading}>Agreements</h1>
          <p style={S.sub}>Long-term truck rental agreements between clients and transporters.</p>
        </div>
        <select style={S.select} value={status} onChange={e => { setStatus(e.target.value); load(e.target.value) }}>
          <option value="">All status</option>
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['ID','Client','Trucks','Duration','Status','Created',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>#{item.id}</td>
                <td style={S.td}>{item.client_name}</td>
                <td style={S.td}>{item.truck_count}</td>
                <td style={S.td}>{item.duration_months} months</td>
                <td style={S.td}><span style={S.badgeStatus(item.status)}>{item.status}</span></td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.created_at)}</td>
                <td style={S.td}>
                  <button onClick={() => view(item.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontWeight: 600, fontSize: 13 }}>View →</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No agreements found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {detail && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 8px 32px rgba(0,0,0,0.12)', padding: 28, width: '100%', maxWidth: 700, maxHeight: '85vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>Agreement #{detail.agreement?.id}</h2>
              <button onClick={() => setDetail(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20 }}>
                <i className="fas fa-times" />
              </button>
            </div>
            <pre style={{ background: '#f8fafc', borderRadius: 10, padding: 16, fontSize: 12, color: '#374151', overflow: 'auto', border: '1px solid #e2e8f0' }}>
              {JSON.stringify(detail, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
