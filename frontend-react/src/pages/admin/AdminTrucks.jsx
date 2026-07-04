import { useEffect, useState } from 'react'
import { adminRequest, dateText, qs } from './adminApi'

const S = {
  heading: { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:     { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:    { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  input:   { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', minWidth: 200 },
  select:  { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', cursor: 'pointer' },
  btnOutline: { padding: '10px 20px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
  th:  { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:  { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error: { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badge: (ok) => ({ display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: ok ? '#f0fdf4' : '#fef2f2', color: ok ? '#16a34a' : '#dc2626' }),
}

export default function AdminTrucks() {
  const [filters,  setFilters]  = useState({ search: '', status: '' })
  const [trucks,   setTrucks]   = useState([])
  const [selected, setSelected] = useState(null)
  const [error,    setError]    = useState('')

  async function load() {
    try   { const json = await adminRequest(`/api/admin/trucks${qs(filters)}`); setTrucks(json.trucks || []) }
    catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={S.heading}>Trucks</h1>
        <p style={S.sub}>All registered trucks across the platform.</p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <input style={S.input} placeholder="Truck or chassis number" value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} />
        <select style={S.select} value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}>
          <option value="">All status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <button onClick={load} style={S.btnOutline}><i className="fas fa-magnifying-glass" style={{ marginRight: 8 }} />Apply</button>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Truck Number','Type','Owner','Status','GPS','Created',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {trucks.map(t => (
              <tr key={t.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>{t.truck_number}</td>
                <td style={S.td}>{t.truck_type}</td>
                <td style={S.td}>
                  <div style={{ fontWeight: 600 }}>{t.owner_name}</div>
                  <div style={{ fontSize: 12, color: '#94a3b8' }}>{t.owner_email}</div>
                </td>
                <td style={S.td}><span style={S.badge(t.status === 'active')}>{t.status}</span></td>
                <td style={S.td}><span style={S.badge(t.gps_enabled)}>{t.gps_enabled ? 'Yes' : 'No'}</span></td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(t.created_at)}</td>
                <td style={S.td}>
                  <button onClick={() => setSelected(t)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontWeight: 600, fontSize: 13 }}>View →</button>
                </td>
              </tr>
            ))}
            {trucks.length === 0 && (
              <tr><td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No trucks found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ ...S.card, padding: 28, width: '100%', maxWidth: 560 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>{selected.truck_number}</h2>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20 }}>
                <i className="fas fa-times" />
              </button>
            </div>
            <pre style={{ background: '#f8fafc', borderRadius: 10, padding: 16, fontSize: 12, color: '#374151', maxHeight: 400, overflow: 'auto', border: '1px solid #e2e8f0' }}>
              {JSON.stringify(selected, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
