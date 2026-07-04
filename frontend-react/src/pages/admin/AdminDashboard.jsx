import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminRequest, dateText, money } from './adminApi'

const STAT_CARDS = [
  { key: 'total_users',         label: 'Total Users',          icon: 'fa-users',                  color: '#2563eb', bg: '#eff6ff' },
  { key: 'active_agreements',   label: 'Active Agreements',    icon: 'fa-file-contract',           color: '#16a34a', bg: '#f0fdf4' },
  { key: 'pending_disputes',    label: 'Pending Disputes',     icon: 'fa-triangle-exclamation',    color: '#dc2626', bg: '#fef2f2' },
  { key: 'pending_withdrawals', label: 'Pending Withdrawals',  icon: 'fa-money-bill-transfer',     color: '#d97706', bg: '#fffbeb' },
  { key: 'failed_payments',     label: 'Failed Payments',      icon: 'fa-credit-card',             color: '#7c3aed', bg: '#f5f3ff' },
]

const LINKS = [
  ['/admin/users', 'total_users'],
  ['/admin/agreements', 'active_agreements'],
  ['/admin/disputes', 'pending_disputes'],
  ['/admin/withdrawals', 'pending_withdrawals'],
  ['/admin/payments', 'failed_payments'],
]

const card = {
  background: '#ffffff', borderRadius: 14,
  border: '1px solid #e2e8f0', padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
}

export default function AdminDashboard() {
  const navigate = useNavigate()
  const [data, setData]   = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    adminRequest('/api/admin/dashboard').then(setData).catch(err => setError(err.message))
  }, [])

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 }}>Dashboard</h1>
        <p style={{ color: '#64748b', fontSize: 14, marginTop: 4 }}>Platform overview — users, agreements, disputes, and payments.</p>
      </div>

      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 20 }}>
          <i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 16, marginBottom: 28 }}>
        {STAT_CARDS.map((s, i) => (
          <button key={s.key} onClick={() => navigate(LINKS[i][0])} style={{
            ...card, textAlign: 'left', cursor: 'pointer', border: '1px solid #e2e8f0',
            transition: 'box-shadow 0.2s, border-color 0.2s',
          }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(37,99,235,0.1)'; e.currentTarget.style.borderColor = '#bfdbfe' }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)'; e.currentTarget.style.borderColor = '#e2e8f0' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#64748b' }}>{s.label}</span>
              <div style={{ width: 38, height: 38, borderRadius: 10, background: s.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className={`fas ${s.icon}`} style={{ color: s.color, fontSize: 16 }} />
              </div>
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#0f172a' }}>
              {data?.stats?.[s.key] ?? <i className="fas fa-circle-notch fa-spin" style={{ fontSize: 18, color: '#94a3b8' }} />}
            </div>
          </button>
        ))}
      </div>

      {/* Recent sections */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <section style={card}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fas fa-triangle-exclamation" style={{ color: '#dc2626' }} />
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', margin: 0 }}>Recent Disputes</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(data?.recent_disputes || []).map(item => (
              <div key={item.id} style={{ background: '#f8fafc', borderRadius: 10, padding: '12px 14px', fontSize: 13, color: '#475569', border: '1px solid #f1f5f9' }}>
                <strong style={{ color: '#1e293b' }}>Trip #{item.id}</strong> · {item.truck_number || 'Truck'} · {item.distance_km} km · {dateText(item.created_at)}
              </div>
            ))}
            {data && data.recent_disputes.length === 0 && (
              <div style={{ textAlign: 'center', padding: '24px 0', color: '#94a3b8', fontSize: 13 }}>
                <i className="fas fa-circle-check" style={{ fontSize: 24, color: '#86efac', marginBottom: 8, display: 'block' }} />
                No pending disputes.
              </div>
            )}
          </div>
        </section>

        <section style={card}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: '#f5f3ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fas fa-credit-card" style={{ color: '#7c3aed' }} />
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', margin: 0 }}>Failed Payments</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(data?.recent_failed_payments || []).map(item => (
              <div key={item.id} style={{ background: '#f8fafc', borderRadius: 10, padding: '12px 14px', fontSize: 13, color: '#475569', border: '1px solid #f1f5f9' }}>
                <strong style={{ color: '#1e293b' }}>Agreement #{item.agreement_id}</strong> · {item.month_year} · {money(item.final_amount)} · {item.client_name}
              </div>
            ))}
            {data && data.recent_failed_payments.length === 0 && (
              <div style={{ textAlign: 'center', padding: '24px 0', color: '#94a3b8', fontSize: 13 }}>
                <i className="fas fa-circle-check" style={{ fontSize: 24, color: '#86efac', marginBottom: 8, display: 'block' }} />
                No failed payments.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
