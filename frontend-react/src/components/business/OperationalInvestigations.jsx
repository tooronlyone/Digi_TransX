import { useEffect, useRef, useState } from 'react'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'
import { apiGet, apiSend } from '../../pages/client/clientUtils'

function evidenceText(value) {
  if (typeof value !== 'string') return JSON.stringify(value ?? [], null, 2)
  try { return JSON.stringify(JSON.parse(value), null, 2) } catch { return value }
}

export default function OperationalInvestigations() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || user?.role !== 'platform_admin' || !user.id) return null
  return <OwnedOperationalInvestigations key={String(user.id)} ownerId={user.id} />
}

function OwnedOperationalInvestigations({ ownerId }) {
  const [filter, setFilter] = useState('investigating'), [refresh, setRefresh] = useState(0)
  const [items, setItems] = useState([]), [selected, setSelected] = useState(null), [detail, setDetail] = useState(null)
  const [selectionRevision, setSelectionRevision] = useState(0)
  const [loading, setLoading] = useState(true), [detailLoading, setDetailLoading] = useState(false)
  const [notes, setNotes] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const alive = useRef(true), selectedRef = useRef(null), detailVersion = useRef(0), mutation = useRef(null)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; mutation.current?.abort() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    apiGet(`/api/admin/operational-incidents?status=${filter}&limit=50`, { signal: controller.signal })
      .then(data => { if (alive.current && !controller.signal.aborted) setItems(data.incidents || []) })
      .catch(failure => { if (alive.current && !controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (alive.current && !controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [filter, refresh])
  useEffect(() => {
    if (selected == null) return undefined
    const controller = new AbortController(), version = ++detailVersion.current
    apiGet(`/api/operational-incidents/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then(data => {
        if (!alive.current || controller.signal.aborted || version !== detailVersion.current) return
        if (String(data.incident?.id) !== String(selected)) throw new Error('Returned incident evidence did not match the selected investigation.')
        setDetail(data.incident)
      })
      .catch(failure => { if (alive.current && !controller.signal.aborted && version === detailVersion.current) setError(failure.message) })
      .finally(() => { if (alive.current && !controller.signal.aborted && version === detailVersion.current) setDetailLoading(false) })
    return () => controller.abort()
  }, [selected, selectionRevision])
  function select(id) {
    if (busy) return
    detailVersion.current += 1; selectedRef.current = id
    setSelected(id); setSelectionRevision(value => value + 1); setDetail(null); setDetailLoading(id != null); setNotes(''); setError(''); setNotice('')
  }
  function reload(nextFilter = filter) {
    select(null); setItems([]); setLoading(true); setFilter(nextFilter); setRefresh(value => value + 1)
  }
  const matches = detail != null && String(detail.id) === String(selected)
  async function decide(status) {
    if (busy || !matches || detail.status !== 'investigating' || notes.trim().length < 10) return
    const target = selected, version = detailVersion.current
    setBusy(true); setError(''); setNotice('')
    try {
      await apiSend(`/api/admin/operational-incidents/${target}/decision`, { status, decision_evidence: notes.trim() }, 'POST', (url, options) => {
        if (!alive.current || selectedRef.current !== target || detailVersion.current !== version) throw new DOMException('The selected investigation changed.', 'AbortError')
        const controller = new AbortController()
        mutation.current = controller
        return fetch(url, { ...options, signal: controller.signal, headers: { ...options.headers, 'X-DTX-Expected-User-Id': String(ownerId) } })
      })
      if (!alive.current || selectedRef.current !== target || detailVersion.current !== version) return
      selectedRef.current = null; detailVersion.current += 1
      setSelected(null); setDetail(null); setNotes(''); setItems([]); setLoading(true); setRefresh(value => value + 1)
      setNotice(`Investigation #${target} ${status}. The decision was recorded without an automatic financial penalty or reserve deduction.`)
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  return <section aria-label="Operational investigations" className="my-6 rounded-xl border border-slate-200 bg-white p-4">
    <h2 className="text-xl font-semibold">Operational incident investigations</h2>
    <p className="mt-2 text-sm text-slate-700">Review accident, theft, negligence, abandonment and emergency evidence before recording a finding. Allegations do not establish fault. This decision does not automatically impose a penalty, recover funds, or debit a security reserve.</p>
    <div className="mt-3 flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm">Investigation status<select disabled={busy} value={filter} onChange={event => reload(event.target.value)} className="rounded border p-2"><option value="investigating">Investigating</option><option value="confirmed">Confirmed</option><option value="dismissed">Dismissed</option></select></label>
      <button type="button" disabled={busy || loading} onClick={() => reload()} className="rounded border px-3 py-2 text-sm">Refresh investigations</button>
    </div>
    {loading ? <p role="status" className="mt-3">Loading operational investigations...</p> : items.length === 0 ? <p className="mt-3 text-sm">No {filter} operational incidents.</p> : <ul className="mt-3 space-y-2">{items.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded border p-3 text-sm"><div><strong>Incident #{item.id}: {String(item.incident_type || item.type || '').replace(/_/g, ' ')}</strong><p>Assignment #{item.assignment_id} · Driver: {item.driver_name || item.driver_user_id || 'Recorded in assignment'} · Transporter: {item.transporter_name || item.transporter_user_id || 'Recorded in assignment'}</p></div><button type="button" disabled={busy} onClick={() => select(item.id)} className="rounded border px-3 py-2">Review incident #{item.id}</button></li>)}</ul>}
    {detailLoading && <p role="status" className="mt-3">Loading the selected incident evidence...</p>}
    {matches && <article aria-label={`Incident ${detail.id} evidence`} className="mt-4 rounded border border-blue-200 bg-blue-50 p-4 text-sm">
      <h3 className="font-semibold">Incident #{detail.id} evidence</h3>
      <p className="mt-2 whitespace-pre-wrap">{detail.description}</p>
      <p className="mt-2">Assignment #{detail.assignment_id} · Truck #{detail.truck_id || 'Unavailable'} · Trip #{detail.trip_id || 'Unavailable'} · Status: {detail.status}</p>
      <h4 className="mt-3 font-semibold">Submitted evidence references</h4>
      <pre className="mt-1 whitespace-pre-wrap break-words rounded bg-white p-3">{evidenceText(detail.evidence)}</pre>
      <p className="mt-1 text-xs">Evidence references are displayed for authorized review; external content is not opened automatically.</p>
      {detail.status === 'investigating' ? <>
        <label className="mt-3 grid gap-1">Investigation decision evidence and notes<textarea required minLength={10} maxLength={10000} rows={4} disabled={busy} value={notes} onChange={event => setNotes(event.target.value)} className="rounded border p-2" /></label>
        <div className="mt-3 flex flex-wrap gap-3"><button type="button" disabled={busy || notes.trim().length < 10} onClick={() => decide('confirmed')} className="rounded bg-blue-700 px-3 py-2 font-semibold text-white disabled:opacity-50">Confirm verified incident</button><button type="button" disabled={busy || notes.trim().length < 10} onClick={() => decide('dismissed')} className="rounded border px-3 py-2 font-semibold disabled:opacity-50">Dismiss unsubstantiated incident</button></div>
      </> : <p className="mt-3 whitespace-pre-wrap">Recorded decision: {detail.decision_evidence || 'No decision notes available.'}</p>}
    </article>}
    {notice && <p role="status" className="mt-3 text-emerald-800">{notice}</p>}
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
  </section>
}
