import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminRequest, dateText, qs } from './adminApi'

const S = {
  page:   { },
  heading:{ fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:    { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:   { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  input:  { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', minWidth: 220 },
  select: { padding: '10px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', cursor: 'pointer' },
  btnPrimary: { padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 700, fontSize: 14 },
  btnOutline: { padding: '10px 20px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
  th:     { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:     { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:  { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badge:  (ok) => ({ display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: ok ? '#f0fdf4' : '#fef2f2', color: ok ? '#16a34a' : '#dc2626' }),
}

export default function AdminUsers() {
  const [users,   setUsers]   = useState([])
  const [filters, setFilters] = useState({ search: '', role: '' })
  const [modal,   setModal]   = useState(false)
  const [form,    setForm]    = useState({ name: '', email: '', password: '' })
  const [error,   setError]   = useState('')

  async function load() {
    try   { const json = await adminRequest(`/api/admin/users${qs(filters)}`); setUsers(json.users || []) }
    catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  async function createAdmin(e) {
    e.preventDefault()
    try { await adminRequest('/api/admin/users', { method: 'POST', body: JSON.stringify(form) }); setModal(false); setForm({ name: '', email: '', password: '' }); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div style={S.page}>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={S.heading}>Users</h1>
          <p style={S.sub}>All registered users on the platform.</p>
        </div>
        <button onClick={() => setModal(true)} style={S.btnPrimary}><i className="fas fa-plus" style={{ marginRight: 8 }} />Create Admin</button>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <input style={S.input} placeholder="Search name, email, CNIC" value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} />
        <select style={S.select} value={filters.role} onChange={e => setFilters({ ...filters, role: e.target.value })}>
          <option value="">All roles</option>
          <option value="platform_admin">Platform admin</option>
          <option value="service_seeker">Service seeker</option>
          <option value="logistics_provider">Logistics provider</option>
          <option value="shopkeeper">Shopkeeper</option>
        </select>
        <button onClick={load} style={S.btnOutline}><i className="fas fa-magnifying-glass" style={{ marginRight: 8 }} />Apply</button>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Name','Email','Role','City','Joined','Status',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ transition: 'background 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 600, color: '#0f172a' }}>{u.name}</td>
                <td style={S.td}>{u.email}</td>
                <td style={S.td}><span style={S.badge(u.role !== 'platform_admin')}>{u.role}</span></td>
                <td style={S.td}>{u.city || '—'}</td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(u.created_at)}</td>
                <td style={S.td}><span style={S.badge(!u.is_blocked)}>{u.is_blocked ? 'Blocked' : 'Active'}</span></td>
                <td style={S.td}><Link to={`/admin/users/${u.id}`} style={{ color: '#2563eb', fontWeight: 600, textDecoration: 'none', fontSize: 13 }}>View →</Link></td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No users found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {modal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <form onSubmit={createAdmin} style={{ ...S.card, padding: 28, width: '100%', maxWidth: 440 }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', marginBottom: 20 }}>Create Admin Account</h2>
            {['name','email','password'].map(f => (
              <input key={f} style={{ ...S.input, width: '100%', boxSizing: 'border-box', marginBottom: 12 }}
                placeholder={f.charAt(0).toUpperCase() + f.slice(1)}
                type={f === 'password' ? 'password' : 'text'}
                value={form[f]} onChange={e => setForm({ ...form, [f]: e.target.value })} />
            ))}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
              <button type="button" onClick={() => setModal(false)} style={S.btnOutline}>Cancel</button>
              <button type="submit" style={S.btnPrimary}>Create</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
