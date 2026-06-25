import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminRequest, dateText, money } from './adminApi'

const cards = [
  ['Total Users', 'total_users', '/admin/users'],
  ['Active Agreements', 'active_agreements', '/admin/agreements'],
  ['Pending Disputes', 'pending_disputes', '/admin/disputes'],
  ['Pending Withdrawals', 'pending_withdrawals', '/admin/withdrawals'],
  ['Failed Payments', 'failed_payments', '/admin/payments'],
]

export default function AdminDashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    adminRequest('/api/admin/dashboard').then(setData).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Dashboard</h1>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {cards.map(([label, key, href]) => (
          <button key={key} onClick={() => navigate(href)} className="rounded-lg border border-slate-800 bg-slate-900 p-5 text-left hover:border-cyan-400">
            <div className="text-sm text-slate-400">{label}</div>
            <div className="mt-3 text-3xl font-bold text-white">{data?.stats?.[key] ?? '-'}</div>
          </button>
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
          <h2 className="font-bold text-white">Recent Disputes</h2>
          <div className="mt-4 space-y-3">
            {(data?.recent_disputes || []).map((item) => (
              <div key={item.id} className="rounded-lg bg-slate-950 p-3 text-sm text-slate-300">
                Trip #{item.id} · {item.truck_number || 'Truck'} · {item.distance_km} km · {dateText(item.created_at)}
              </div>
            ))}
            {data && data.recent_disputes.length === 0 && <p className="text-sm text-slate-400">No pending disputes.</p>}
          </div>
        </section>
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
          <h2 className="font-bold text-white">Failed Payments</h2>
          <div className="mt-4 space-y-3">
            {(data?.recent_failed_payments || []).map((item) => (
              <div key={item.id} className="rounded-lg bg-slate-950 p-3 text-sm text-slate-300">
                Agreement #{item.agreement_id} · {item.month_year} · {money(item.final_amount)} · {item.client_name}
              </div>
            ))}
            {data && data.recent_failed_payments.length === 0 && <p className="text-sm text-slate-400">No failed payments.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}

