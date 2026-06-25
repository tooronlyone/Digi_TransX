import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { adminRequest, dateText, money } from './adminApi'

export default function AdminUserDetail() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  async function load() {
    try {
      const json = await adminRequest(`/api/admin/users/${id}`)
      setData(json)
      setReason(json.user?.block_reason || '')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [id])

  async function toggleBlock() {
    try {
      await adminRequest(`/api/admin/users/${id}/block`, {
        method: 'PUT',
        body: JSON.stringify({ blocked: !data.user.is_blocked, reason }),
      })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!data) return <div className="text-slate-300">{error || 'Loading user...'}</div>
  const { user } = data
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">{user.name}</h1>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <section className="grid gap-4 rounded-lg border border-slate-800 bg-slate-900 p-5 sm:grid-cols-2 xl:grid-cols-4">
        <div><div className="text-xs text-slate-400">Email</div><div className="mt-1 text-white">{user.email}</div></div>
        <div><div className="text-xs text-slate-400">Role</div><div className="mt-1 text-white">{user.role}</div></div>
        <div><div className="text-xs text-slate-400">City</div><div className="mt-1 text-white">{user.city || '-'}</div></div>
        <div><div className="text-xs text-slate-400">Joined</div><div className="mt-1 text-white">{dateText(user.created_at)}</div></div>
      </section>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-sm text-slate-400">Balance</div><div className="mt-2 text-xl font-bold">{money(data.wallet.balance)}</div></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-sm text-slate-400">Locked</div><div className="mt-2 text-xl font-bold">{money(data.wallet.locked_balance)}</div></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-sm text-slate-400">Trucks</div><div className="mt-2 text-xl font-bold">{data.truck_count}</div></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-sm text-slate-400">Orders</div><div className="mt-2 text-xl font-bold">{data.order_count}</div></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-sm text-slate-400">Agreements</div><div className="mt-2 text-xl font-bold">{data.agreement_count}</div></div>
      </section>
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <h2 className="font-bold text-white">{user.is_blocked ? 'Unblock User' : 'Block User'}</h2>
        <textarea className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm" rows="3" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button onClick={toggleBlock} className="mt-3 rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950">{user.is_blocked ? 'Unblock User' : 'Block User'}</button>
      </section>
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <h2 className="font-bold text-white">Trucks</h2>
        <div className="mt-3 grid gap-3">
          {data.trucks.map((truck) => <div key={truck.id} className="rounded-lg bg-slate-950 p-3 text-sm">{truck.truck_number} · {truck.truck_type} · {truck.status}</div>)}
          {data.trucks.length === 0 && <p className="text-sm text-slate-400">No trucks.</p>}
        </div>
      </section>
    </div>
  )
}

