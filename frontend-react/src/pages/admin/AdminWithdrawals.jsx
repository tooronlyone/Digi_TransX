import { useEffect, useState } from 'react'
import { adminRequest, dateText, money, qs } from './adminApi'

export default function AdminWithdrawals() {
  const [status, setStatus] = useState('pending')
  const [items, setItems] = useState([])
  const [error, setError] = useState('')

  async function load(nextStatus = status) {
    try {
      const json = await adminRequest(`/api/admin/wallet/withdrawals${qs({ status: nextStatus })}`)
      setItems(json.withdrawals || [])
    } catch (err) {
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [])

  async function act(id, action) {
    if (action === 'approve' && !window.confirm('Approve this withdrawal?')) return
    try {
      await adminRequest(`/api/admin/wallet/withdrawals/${id}/${action}`, { method: 'POST', body: JSON.stringify({}) })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Wallet Withdrawals</h1>
      <select className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" value={status} onChange={(e) => { setStatus(e.target.value); load(e.target.value) }}><option value="">All</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800"><table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
        <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">User</th><th>Amount</th><th>Requested At</th><th>Status</th><th>Current Locked Balance</th><th></th></tr></thead>
        <tbody className="divide-y divide-slate-800">{items.map((item) => <tr key={item.id}><td className="px-4 py-3 text-white">{item.user_name}<div className="text-xs text-slate-500">{item.email}</div></td><td>{money(item.amount)}</td><td>{dateText(item.requested_at)}</td><td>{item.status}</td><td>{money(item.current_locked_balance)}</td><td>{item.status === 'pending' && <div className="flex gap-2"><button onClick={() => act(item.id, 'approve')} className="text-cyan-300">Approve</button><button onClick={() => act(item.id, 'reject')} className="text-red-300">Reject</button></div>}</td></tr>)}</tbody>
      </table></div>
    </div>
  )
}

