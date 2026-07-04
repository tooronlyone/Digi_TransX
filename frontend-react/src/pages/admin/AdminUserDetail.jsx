import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { adminRequest, dateText, money } from './adminApi'

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', padding: 24 },
  label:    { fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  value:    { fontSize: 15, color: '#0f172a', fontWeight: 500 },
  statCard: { background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 },
  textarea: { width: '100%', padding: '12px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', resize: 'vertical', boxSizing: 'border-box' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badge:    (ok) => ({ display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: ok ? '#f0fdf4' : '#fef2f2', color: ok ? '#16a34a' : '#dc2626' }),
  roleBadge:{ display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: '#eff6ff', color: '#2563eb' },
}

export default function AdminUserDetail() {
  const { id } = useParams()
  const [data, setData]   = useState(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  async function load() {
    try {
      const json = await adminRequest(`/api/admin/users/${id}`)
      setData(json)
      setReason(json.user?.block_reason || '')
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [id])

  async function toggleBlock() {
    try {
      await adminRequest(`/api/admin/users/${id}/block`, {
        method: 'PUT',
        body: JSON.stringify({ blocked: !data.user.is_blocked, reason }),
      })
      load()
    } catch (err) { setError(err.message) }
  }

  if (!data) return (
    <div style={{ padding: 40, textAlign: 'center', color: error ? '#dc2626' : '#94a3b8' }}>
      {error ? <><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</> : <><i className="fas fa-circle-notch fa-spin" style={{ marginRight: 8 }} />Loading user...</>}
    </div>
  )

  const { user } = data
  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{
          width: 56, height: 56, borderRadius: '50%',
          background: 'linear-gradient(135deg,#2563eb,#1d4ed8)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 20, flexShrink: 0,
        }}>
          {(user.name || user.email || 'U').slice(0, 2).toUpperCase()}
        </div>
        <div>
          <h1 style={S.heading}>{user.name}</h1>
          <div style={{ marginTop: 6, display: 'flex', gap: 8 }}>
            <span style={S.roleBadge}>{user.role}</span>
            <span style={S.badge(!user.is_blocked)}>{user.is_blocked ? 'Blocked' : 'Active'}</span>
          </div>
        </div>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      {/* Info grid */}
      <div style={{ ...S.card, marginBottom: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 20 }}>
          {[
            ['Email', user.email],
            ['CNIC', user.cnic || '—'],
            ['Phone', user.phone || '—'],
            ['City', user.city || '—'],
            ['Joined', dateText(user.created_at)],
          ].map(([label, val]) => (
            <div key={label}>
              <div style={S.label}>{label}</div>
              <div style={S.value}>{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 16, marginBottom: 20 }}>
        {[
          ['Balance', money(data.wallet?.balance), '#2563eb', '#eff6ff', 'fa-wallet'],
          ['Locked', money(data.wallet?.locked_balance), '#d97706', '#fffbeb', 'fa-lock'],
          ['Trucks', data.truck_count, '#7c3aed', '#f5f3ff', 'fa-truck'],
          ['Orders', data.order_count, '#16a34a', '#f0fdf4', 'fa-box'],
          ['Agreements', data.agreement_count, '#dc2626', '#fef2f2', 'fa-file-contract'],
        ].map(([label, val, color, bg, icon]) => (
          <div key={label} style={S.statCard}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className={`fas ${icon}`} style={{ color, fontSize: 14 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#64748b' }}>{label}</span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Block / Unblock */}
      <div style={{ ...S.card, marginBottom: 20 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 16 }}>
          {user.is_blocked ? 'Unblock User' : 'Block User'}
        </h2>
        <textarea rows={3} style={S.textarea} placeholder="Reason for action" value={reason} onChange={e => setReason(e.target.value)} />
        <button onClick={toggleBlock} style={{
          marginTop: 12, padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer',
          background: user.is_blocked ? 'linear-gradient(135deg,#16a34a,#22c55e)' : '#dc2626',
          color: '#fff', fontWeight: 700, fontSize: 14,
        }}>
          <i className={`fas ${user.is_blocked ? 'fa-unlock' : 'fa-ban'}`} style={{ marginRight: 8 }} />
          {user.is_blocked ? 'Unblock User' : 'Block User'}
        </button>
      </div>

      {/* Trucks */}
      <div style={S.card}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 16 }}>
          <i className="fas fa-truck" style={{ marginRight: 10, color: '#2563eb' }} />Trucks ({data.trucks.length})
        </h2>
        {data.trucks.length === 0 ? (
          <p style={{ color: '#94a3b8', fontSize: 14 }}>No trucks registered.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.trucks.map(truck => (
              <div key={truck.id} style={{ background: '#f8fafc', borderRadius: 10, padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #f1f5f9' }}>
                <div>
                  <span style={{ fontWeight: 700, color: '#0f172a' }}>{truck.truck_number}</span>
                  <span style={{ marginLeft: 10, fontSize: 13, color: '#64748b' }}>{truck.truck_type}</span>
                </div>
                <span style={S.badge(truck.status === 'active')}>{truck.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
