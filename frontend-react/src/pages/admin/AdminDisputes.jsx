import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminRequest, dateText } from './adminApi'

export default function AdminDisputes() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [decision, setDecision] = useState('km_approved')
  const [adminNote, setAdminNote] = useState('')
  const [error, setError] = useState('')

  async function load() {
    try {
      const json = await adminRequest('/api/admin/disputes')
      setItems(json.disputes || [])
    } catch (err) {
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [])

  async function openChat() {
    try {
      const json = await adminRequest(`/api/admin/disputes/${selected.id}/group-chat`, { method: 'POST', body: JSON.stringify({}) })
      navigate(`/admin/dispute-chat/${json.thread_id}`)
    } catch (err) {
      setError(err.message)
    }
  }

  async function resolve() {
    if (!selected || !window.confirm('Confirm this dispute decision?')) return
    try {
      await adminRequest(`/api/admin/disputes/${selected.id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ decision, admin_note: adminNote }),
      })
      setSelected(null)
      setAdminNote('')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Disputes</h1>
      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 bg-slate-900 text-sm">
          <thead className="bg-slate-950 text-left text-xs uppercase text-slate-400"><tr><th className="px-4 py-3">Trip ID</th><th>Agreement</th><th>Truck</th><th>Transporter</th><th>Client</th><th>Date</th><th>KM</th><th>Status</th><th></th></tr></thead>
          <tbody className="divide-y divide-slate-800">{items.map((item) => <tr key={item.id}><td className="px-4 py-3 text-white">#{item.id}</td><td>#{item.agreement_id}</td><td>{item.truck_number}</td><td>{item.transporter_name}</td><td>{item.client_name}</td><td>{dateText(item.trip_date)}</td><td>{item.distance_km || 0}</td><td>{item.status}</td><td><button onClick={() => { setSelected(item); setDecision('km_approved') }} className="font-semibold text-cyan-300">Resolve</button></td></tr>)}</tbody>
        </table>
      </div>
      {selected && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 px-4">
          <div className="w-full max-w-2xl rounded-lg border border-slate-700 bg-slate-900 p-5">
            <div className="flex items-start justify-between gap-4">
              <div><h2 className="text-lg font-bold">Trip #{selected.id}</h2><p className="mt-1 text-sm text-slate-400">{selected.pickup_description} · {selected.distance_km || 0} km</p></div>
              <button onClick={() => setSelected(null)} className="text-sm text-slate-400">Close</button>
            </div>
            <button onClick={openChat} className="mt-4 rounded-lg border border-cyan-400 px-4 py-2 text-sm font-bold text-cyan-300">Open Group Chat</button>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <button onClick={() => setDecision('km_approved')} className={`rounded-lg border px-4 py-3 text-left text-sm ${decision === 'km_approved' ? 'border-cyan-400 bg-cyan-400 text-slate-950' : 'border-slate-700'}`}>Approve KM<br /><span className="text-xs opacity-80">Rs 5,000 penalty to client</span></button>
              <button onClick={() => setDecision('km_rejected')} className={`rounded-lg border px-4 py-3 text-left text-sm ${decision === 'km_rejected' ? 'border-cyan-400 bg-cyan-400 text-slate-950' : 'border-slate-700'}`}>Reject KM<br /><span className="text-xs opacity-80">Rs 5,000 penalty to transporter</span></button>
            </div>
            <textarea rows="4" className="mt-4 w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="Admin note" value={adminNote} onChange={(e) => setAdminNote(e.target.value)} />
            <button onClick={resolve} className="mt-4 rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950">Confirm Decision</button>
          </div>
        </div>
      )}
    </div>
  )
}

