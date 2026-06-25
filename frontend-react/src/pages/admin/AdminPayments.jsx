import { useEffect, useState } from 'react'
import { adminRequest, dateText, money, qs } from './adminApi'

export default function AdminPayments() {
  const [filters, setFilters] = useState({ status: '', month_year: '' })
  const [items, setItems] = useState([])
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  async function load(nextFilters = filters) {
    try {
      const json = await adminRequest(`/api/admin/payments${qs(nextFilters)}`)
      setItems(json.payments || [])
    } catch (err) {
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [])

  async function run(action) {
    const label = action === 'process' ? 'process payments' : 'apply penalties'
    if (!window.confirm(`Confirm ${label}?`)) return
    try {
      const json = await adminRequest(`/api/admin/payments/${action === 'process' ? 'process' : 'apply-penalties'}`, { method: 'POST', body: JSON.stringify({}) })
      setNotice(action === 'process' ? `Processed ${json.processed}, failed ${json.failed}` : `Penalties applied: ${json.penalties_applied}`)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-white">Payments</h1>
        <div className="flex flex-wrap gap-2"><button onClick={() => run('process')} className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950">Process Payments</button><button onClick={() => run('penalties')} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-bold">Apply Penalties</button></div>
      </div>
      <div className="flex flex-wrap gap-3">
        <select className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All status</option><option value="pending">Pending</option><option value="paid">Paid</option><option value="failed">Failed</option></select>
        <input className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" placeholder="YYYY-MM" value={filters.month_year} onChange={(e) => setFilters({ ...filters, month_year: e.target.value })} />
        <button onClick={() => load()} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold">Apply</button>
      </div>
      {notice && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{notice}</div>}
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800"><table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
        <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">Agreement</th><th>Client</th><th>Transporter</th><th>Truck</th><th>Month</th><th>KM</th><th>Amount</th><th>Status</th><th>Due Date</th></tr></thead>
        <tbody className="divide-y divide-slate-800">{items.map((item) => <tr key={item.id}><td className="px-4 py-3 text-white">#{item.agreement_id}</td><td>{item.client_name}</td><td>{item.transporter_name}</td><td>{item.truck_number}</td><td>{item.month_year}</td><td>{item.total_km}</td><td>{money(item.final_amount)}</td><td>{item.status}</td><td>{dateText(item.payment_due_date)}</td></tr>)}</tbody>
      </table></div>
    </div>
  )
}

