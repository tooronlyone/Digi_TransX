import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminRequest, dateText, qs } from './adminApi'

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({ search: '', role: '' })
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')

  async function load() {
    try {
      const json = await adminRequest(`/api/admin/users${qs(filters)}`)
      setUsers(json.users || [])
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [])

  async function createAdmin(event) {
    event.preventDefault()
    try {
      await adminRequest('/api/admin/users', { method: 'POST', body: JSON.stringify(form) })
      setModal(false)
      setForm({ name: '', email: '', password: '' })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-white">Users</h1>
        <button onClick={() => setModal(true)} className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950">Create Admin</button>
      </div>
      <div className="flex flex-wrap gap-3">
        <input className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" placeholder="Search name, email, CNIC" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
        <select className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm" value={filters.role} onChange={(e) => setFilters({ ...filters, role: e.target.value })}>
          <option value="">All roles</option>
          <option value="platform_admin">Platform admin</option>
          <option value="service_seeker">Service seeker</option>
          <option value="logistics_provider">Logistics provider</option>
          <option value="shopkeeper">Shopkeeper</option>
        </select>
        <button onClick={load} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold">Apply</button>
      </div>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
          <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">Name</th><th>Email</th><th>Role</th><th>City</th><th>Joined</th><th>Status</th><th></th></tr></thead>
          <tbody className="divide-y divide-slate-800">
            {users.map((user) => (
              <tr key={user.id}><td className="px-4 py-3 text-white">{user.name}</td><td>{user.email}</td><td>{user.role}</td><td>{user.city || '-'}</td><td>{dateText(user.created_at)}</td><td>{user.is_blocked ? 'Blocked' : 'Active'}</td><td><Link className="font-semibold text-cyan-300" to={`/admin/users/${user.id}`}>View</Link></td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 px-4">
          <form onSubmit={createAdmin} className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-5">
            <h2 className="text-lg font-bold text-white">Create Admin</h2>
            <input className="mt-4 w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <input className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <div className="mt-5 flex justify-end gap-3"><button type="button" onClick={() => setModal(false)} className="rounded-lg border border-slate-700 px-4 py-2">Cancel</button><button className="rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950">Create</button></div>
          </form>
        </div>
      )}
    </div>
  )
}

