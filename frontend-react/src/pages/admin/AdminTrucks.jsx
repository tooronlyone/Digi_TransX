import { useEffect, useState } from 'react'
import { adminRequest, dateText, qs } from './adminApi'

export default function AdminTrucks() {
  const [filters, setFilters] = useState({ search: '', status: '' })
  const [trucks, setTrucks] = useState([])
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      const json = await adminRequest(`/api/admin/trucks${qs(filters)}`)
      setTrucks(json.trucks || [])
    } catch (err) {
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Trucks</h1>
      <div className="flex flex-wrap gap-3">
        <input className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" placeholder="Truck or chassis" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
        <select className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All status</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
        <button onClick={load} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold">Apply</button>
      </div>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
          <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">Truck Number</th><th>Type</th><th>Owner</th><th>Status</th><th>GPS</th><th>Created</th><th></th></tr></thead>
          <tbody className="divide-y divide-slate-800">{trucks.map((truck) => <tr key={truck.id}><td className="px-4 py-3 text-white">{truck.truck_number}</td><td>{truck.truck_type}</td><td>{truck.owner_name}<div className="text-xs text-slate-500">{truck.owner_email}</div></td><td>{truck.status}</td><td>{truck.gps_enabled ? 'Yes' : 'No'}</td><td>{dateText(truck.created_at)}</td><td><button onClick={() => setSelected(truck)} className="font-semibold text-cyan-300">View</button></td></tr>)}</tbody>
        </table>
      </div>
      {selected && <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 px-4"><div className="w-full max-w-xl rounded-lg border border-slate-700 bg-slate-900 p-5"><h2 className="text-lg font-bold">{selected.truck_number}</h2><pre className="mt-4 max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-300">{JSON.stringify(selected, null, 2)}</pre><button onClick={() => setSelected(null)} className="mt-4 rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950">Close</button></div></div>}
    </div>
  )
}

