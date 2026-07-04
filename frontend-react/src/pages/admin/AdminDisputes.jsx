import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminRequest, dateText } from './adminApi'

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:      { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  th:       { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:       { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badgeStatus: (s) => {
    const map = { pending: ['#fffbeb','#d97706'], resolved: ['#f0fdf4','#16a34a'] }
    const [bg, color] = map[s] || ['#f1f5f9','#475569']
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: bg, color }
  },
  textarea: { width: '100%', padding: '12px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', resize: 'vertical', boxSizing: 'border-box' },
  btnPrimary: { padding: '12px 24px', borderRadius: 10, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 700, fontSize: 14 },
  btnOutline: { padding: '10px 18px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
  btnChat:    { padding: '10px 18px', borderRadius: 10, border: '1.5px solid #bfdbfe', cursor: 'pointer', background: '#eff6ff', color: '#2563eb', fontWeight: 600, fontSize: 14 },
}

function DecisionBtn({ value, current, onClick, title, sub }) {
  const active = current === value
  return (
    <button onClick={onClick} style={{
      padding: '14px 16px', borderRadius: 12, textAlign: 'left', cursor: 'pointer',
      border: active ? '2px solid #2563eb' : '2px solid #e2e8f0',
      background: active ? '#eff6ff' : '#fff',
      transition: 'all 0.15s',
    }}>
      <div style={{ fontWeight: 700, color: active ? '#2563eb' : '#0f172a', fontSize: 14 }}>{title}</div>
      <div style={{ fontSize: 12, color: active ? '#3b82f6' : '#64748b', marginTop: 4 }}>{sub}</div>
    </button>
  )
}

export default function AdminDisputes() {
  const navigate = useNavigate()
  const [items, setItems]       = useState([])
  const [selected, setSelected] = useState(null)
  const [decision, setDecision] = useState('km_approved')
  const [adminNote, setAdminNote] = useState('')
  const [error, setError]       = useState('')

  async function load() {
    try {
      const json = await adminRequest('/api/admin/disputes')
      setItems(json.disputes || [])
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  async function openChat() {
    try {
      const json = await adminRequest(`/api/admin/disputes/${selected.id}/group-chat`, { method: 'POST', body: JSON.stringify({}) })
      navigate(`/admin/dispute-chat/${json.thread_id}`)
    } catch (err) { setError(err.message) }
  }

  async function resolve() {
    if (!selected || !window.confirm('Confirm this dispute decision?')) return
    try {
      await adminRequest(`/api/admin/disputes/${selected.id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ decision, admin_note: adminNote }),
      })
      setSelected(null); setAdminNote(''); load()
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={S.heading}>Disputes</h1>
        <p style={S.sub}>Trip KM disputes awaiting admin review and resolution.</p>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Trip','Agreement','Truck','Transporter','Client','Date','KM','Status',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>#{item.id}</td>
                <td style={S.td}>#{item.agreement_id}</td>
                <td style={S.td}>{item.truck_number}</td>
                <td style={S.td}>{item.transporter_name}</td>
                <td style={S.td}>{item.client_name}</td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.trip_date)}</td>
                <td style={S.td}>{item.distance_km || 0}</td>
                <td style={S.td}><span style={S.badgeStatus(item.status)}>{item.status}</span></td>
                <td style={S.td}>
                  <button onClick={() => { setSelected(item); setDecision('km_approved') }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontWeight: 600, fontSize: 13 }}>
                    Resolve →
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No disputes found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 8px 32px rgba(0,0,0,0.12)', padding: 28, width: '100%', maxWidth: 560 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>Trip #{selected.id}</h2>
                <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                  {selected.pickup_description} · {selected.distance_km || 0} km reported
                </p>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20 }}>
                <i className="fas fa-times" />
              </button>
            </div>

            {/* Open Chat */}
            <button onClick={openChat} style={S.btnChat}>
              <i className="fas fa-comments" style={{ marginRight: 8 }} />Open Group Chat
            </button>

            {/* Decision selection */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 20 }}>
              <DecisionBtn
                value="km_approved" current={decision} onClick={() => setDecision('km_approved')}
                title="Approve KM" sub="Rs 5,000 penalty to client"
              />
              <DecisionBtn
                value="km_rejected" current={decision} onClick={() => setDecision('km_rejected')}
                title="Reject KM" sub="Rs 5,000 penalty to transporter"
              />
            </div>

            {/* Note */}
            <textarea rows={4} style={{ ...S.textarea, marginTop: 16 }}
              placeholder="Admin note (optional)" value={adminNote}
              onChange={e => setAdminNote(e.target.value)} />

            {/* Actions */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
              <button onClick={() => setSelected(null)} style={S.btnOutline}>Cancel</button>
              <button onClick={resolve} style={S.btnPrimary}>
                <i className="fas fa-gavel" style={{ marginRight: 8 }} />Confirm Decision
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
