import { useEffect, useState } from 'react'
import { adminRequest, dateText, qs } from './adminApi'

export default function AdminAgreements() {
  const [status, setStatus] = useState('')
  const [items, setItems] = useState([])
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  async function load(nextStatus = status) {
    try {
      const json = await adminRequest(`/api/admin/agreements${qs({ status: nextStatus })}`)
      setItems(json.agreements || [])
    } catch (err) {
      setError(err.message)
    }
  }

  async function view(id) {
    try {
      setDetail(await adminRequest(`/api/admin/agreements/${id}`))
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Agreements</h1>
      <select className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" value={status} onChange={(e) => { setStatus(e.target.value); load(e.target.value) }}>
        <option value="">All status</option><option value="active">Active</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option>
      </select>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
          <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">ID</th><th>Client</th><th>Trucks</th><th>Duration</th><th>Status</th><th>Created</th><th></th></tr></thead>
          <tbody className="divide-y divide-slate-800">{items.map((item) => <tr key={item.id}><td className="px-4 py-3 text-white">#{item.id}</td><td>{item.client_name}</td><td>{item.truck_count}</td><td>{item.duration_months} months</td><td>{item.status}</td><td>{dateText(item.created_at)}</td><td><button onClick={() => view(item.id)} className="font-semibold text-cyan-300">View</button></td></tr>)}</tbody>
        </table>
      </div>
      {detail && <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 px-4"><div className="max-h-[85vh] w-full max-w-4xl overflow-auto rounded-lg border border-slate-700 bg-slate-900 p-5"><h2 className="text-lg font-bold">Agreement #{detail.agreement.id}</h2><pre className="mt-4 rounded-lg bg-slate-950 p-4 text-xs text-slate-300">{JSON.stringify(detail, null, 2)}</pre><button onClick={() => setDetail(null)} className="mt-4 rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950">Close</button></div></div>}
    </div>
  )
}

