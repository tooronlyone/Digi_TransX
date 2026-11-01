import { useRef, useState, useEffect } from 'react'
import { apiSend } from '../../pages/client/clientUtils'

export default function TripOperationalActions({ assignment, transporter = false }) {
  const [type, setType] = useState('emergency'), [description, setDescription] = useState(''), [evidence, setEvidence] = useState('')
  const [reason, setReason] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  if (!assignment?.id || !['accepted', 'in_progress'].includes(assignment.status)) return null
  const send = (url, payload) => apiSend(url, payload, 'POST', (target, options) => {
    if (!alive.current) throw new DOMException('The assignment or account changed.', 'AbortError')
    return fetch(target, options)
  })
  async function run(action) {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await action()
      if (alive.current) setNotice(result.message || 'Request recorded for authorized operational review.')
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  function ownerLocation() {
    return run(async () => {
      if (!navigator.geolocation) throw new Error('Geolocation is unavailable on this device.')
      const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }))
      const { latitude: lat, longitude: lng, accuracy } = position.coords
      return send('/api/transporter/owner-operator/gps', { assignment_id: assignment.id, lat, lng, accuracy })
    })
  }
  return <section aria-label={`Trip safety and operational actions ${assignment.id}`} className="mt-3 rounded-lg border border-slate-200 p-3 text-sm">
    <details><summary className="cursor-pointer font-semibold text-indigo-700">Safety reporting &amp; operational requests</summary>
      <p className="mt-2">Report emergencies and preserve evidence. A report starts an investigation; it does not establish fault, cancel the trip, or confiscate funds.</p>
      <form onSubmit={event => { event.preventDefault(); void run(() => send('/api/operational-incidents', { assignment_id: assignment.id, incident_type: type, description: description.trim(), evidence: evidence.split('\n').map(value => value.trim()).filter(Boolean) })) }} className="mt-3 grid gap-2">
        <label className="grid gap-1">Incident type<select value={type} onChange={event => setType(event.target.value)} className="rounded border p-2">{['emergency', 'accident', 'theft', 'negligence', 'abandonment', 'other'].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="grid gap-1">Incident description<textarea required maxLength={4000} value={description} onChange={event => setDescription(event.target.value)} className="rounded border p-2" /></label>
        <label className="grid gap-1">Incident evidence references<textarea maxLength={8000} value={evidence} onChange={event => setEvidence(event.target.value)} className="rounded border p-2" /></label>
        <button type="submit" disabled={busy} className="rounded border border-amber-700 p-2 font-semibold text-amber-900">Report incident or emergency</button>
      </form>
      {transporter && <form onSubmit={event => { event.preventDefault(); void run(() => send(`/api/transporter/trips/${assignment.id}/cancellation-request`, { reason: reason.trim() })) }} className="mt-4 grid gap-2">
        <label className="grid gap-1">Transporter cancellation reason<textarea required maxLength={4000} value={reason} onChange={event => setReason(event.target.value)} className="rounded border p-2" /></label>
        <p className="text-xs">Cancellation requests require the applicable cancellation and refund policy review. Outstanding fuel debt remains the Transporter's responsibility and cannot reduce Client escrow.</p>
        <button type="submit" disabled={busy} className="rounded border border-red-700 p-2 font-semibold text-red-800">Request trip cancellation</button>
      </form>}
    </details>
    {transporter && assignment.assignment_mode === 'owner_operator' && <button type="button" disabled={busy} onClick={ownerLocation} className="mt-3 rounded border border-indigo-700 p-2 font-semibold text-indigo-800">Share current Owner-Operator GPS position</button>}
    {notice && <p role="status" className="mt-3 text-emerald-700">{notice}</p>}
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
  </section>
}
