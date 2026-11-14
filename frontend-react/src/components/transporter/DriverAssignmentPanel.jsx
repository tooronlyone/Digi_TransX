import { useCallback, useEffect, useRef, useState } from 'react'
import TripOperationalActions from '../business/TripOperationalActions'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'
import { apiGet, apiSend } from '../../pages/client/clientUtils'

export default function DriverAssignmentPanel({ tripId = null, defaultOpen = false }) {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !['transporter', 'logistics_provider'].includes(user?.role)
      || !tripId) return null
  return <TripDriverPanel key={`${user.id}:${tripId}`} tripId={tripId} defaultOpen={defaultOpen} />
}

function TripDriverPanel({ tripId, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen)
  return <section className="my-4 rounded-xl border border-slate-200 bg-white p-4">
    <button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)} className="font-semibold text-indigo-700">
      Driver invitation &amp; review
    </button>
    <p className="mt-1 text-sm text-slate-600">The driver must accept this trip invitation before their profile and smartphone GPS are linked. Reviews are available after the trip is completed.</p>
    {open && <AssignmentDetails tripId={tripId} />}
  </section>
}

function AssignmentDetails({ tripId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  const [driverId, setDriverId] = useState('')
  const [offer, setOffer] = useState('0.00')
  const [notes, setNotes] = useState('')
  const mounted = useRef(false), request = useRef(0), abort = useRef(null)
  const readBusy = useRef(false)
  const sourceKey = 'trip_id'
  const sourceId = tripId
  const load = useCallback(async ({ replace = false } = {}) => {
    if (readBusy.current && !replace) return
    readBusy.current = true
    const id = ++request.current
    abort.current?.abort()
    const controller = new AbortController()
    abort.current = controller
    try {
      const result = await apiGet(`/api/transporter/driver-assignments?${sourceKey}=${encodeURIComponent(sourceId)}`, { signal: controller.signal })
      if (!Array.isArray(result.assignments) || !result.truck_id) throw new Error('Driver request data is unavailable. Refresh and try again.')
      if (mounted.current && id === request.current && !controller.signal.aborted) { setData(result); setError('') }
    } catch (failure) {
      if (mounted.current && id === request.current && !controller.signal.aborted) setError(failure.message || 'Unable to load driver invitations.')
    } finally {
      if (id === request.current) readBusy.current = false
    }
  }, [sourceId, sourceKey])
  useEffect(() => {
    mounted.current = true
    // Start a guarded remote read for this keyed trip, not a derived-state update.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load({ replace: true })
    return () => { mounted.current = false; abort.current?.abort() }
  }, [load])
  useEffect(() => {
    if (!data?.assignments?.some(item => ['requested', 'accepted', 'in_progress'].includes(item.status))) return undefined
    const timer = window.setInterval(() => { void load() }, 10000)
    return () => window.clearInterval(timer)
  }, [data, load])
  async function invite(event) {
    event.preventDefault()
    if (!data?.can_dispatch || working) return
    setWorking(true); setError(''); setNotice('')
    try {
      const result = await apiSend('/api/transporter/dispatch-driver', {
        unique_driver_id: driverId.trim().toUpperCase(), truck_id: data.truck_id,
        [sourceKey]: sourceId, offer_amount: offer, notes: notes.trim(),
      })
      if (!mounted.current) return
      setNotice(result.message || 'Invitation sent. The driver must accept from Trip Requests.')
      setDriverId(''); setNotes('')
      await load({ replace: true })
    } catch (failure) {
      if (mounted.current) setError(failure.message || 'Unable to invite this driver.')
    } finally { if (mounted.current) setWorking(false) }
  }
  async function driveMyself() {
    if (!data?.can_dispatch || working) return
    setWorking(true); setError(''); setNotice('')
    try {
      const result = await apiSend('/api/transporter/drive-myself', { [sourceKey]: sourceId, truck_id: data.truck_id })
      if (!mounted.current) return
      setNotice(result.message || 'Owner-Operator assigned after credential and allocation checks.')
      await load({ replace: true })
    } catch (failure) { if (mounted.current) setError(failure.message || 'Verified driving credentials are required before self-assignment.') }
    finally { if (mounted.current) setWorking(false) }
  }
  async function review(assignment, values) {
    if (working) return false
    setWorking(true); setError(''); setNotice('')
    try {
      const result = await apiSend('/api/driver/rate', {
        assignment_id: assignment.id, driver_user_id: assignment.driver_user_id, ...values,
      })
      if (!mounted.current) return false
      setNotice(result.incident_status === 'investigating'
        ? 'Review recorded. The incident is investigating and has not been confirmed.'
        : result.message || 'Review recorded.')
      await load({ replace: true })
      return true
    } catch (failure) {
      if (mounted.current) setError(failure.message || 'Unable to record this review.')
      return false
    } finally { if (mounted.current) setWorking(false) }
  }
  return <div className="mt-3 space-y-3">
    <button type="button" onClick={() => { void load({ replace: true }) }} className="text-sm font-semibold text-indigo-700">Refresh driver requests</button>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    {!data && !error && <p className="text-sm text-slate-500">Loading driver requests...</p>}
    {data && <>
      {!data.assignments.length && <p className="text-sm text-slate-500">No driver invitation has been sent for this trip.</p>}
      {data.assignments.map(assignment => <article key={assignment.id} className="rounded-lg border border-slate-200 p-3">
        <p className="font-semibold">{assignment.driver_name} <span className="text-sm font-normal">({assignment.unique_driver_id})</span></p>
        <p className="text-sm text-slate-600">Status: {String(assignment.status).replaceAll('_', ' ')}{assignment.reviewed ? ' · Review already recorded' : ''}</p>
        {assignment.status === 'requested' && <p className="text-sm text-slate-500">Waiting for the driver to accept or decline in their Trip Requests.</p>}
        <TripOperationalActions key={`operations:${assignment.id}`} assignment={assignment} transporter />
        {assignment.can_review && <DriverReviewForm assignment={assignment} disabled={working} onSubmit={review} />}
      </article>)}
      {data.can_dispatch && <div className="rounded border border-indigo-200 p-3"><button type="button" disabled={working} onClick={driveMyself} className="rounded border border-indigo-600 p-2 font-semibold text-indigo-700 disabled:opacity-50">Drive Myself (Owner-Operator)</button><p className="mt-2 text-xs text-slate-600">Requires verified driving credentials, operating authority for this truck, and no conflicting active assignment. Your Transporter role remains unchanged.</p></div>}
      {data.can_dispatch && <form onSubmit={invite} className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">Driver ID
          <input required maxLength={32} value={driverId} onChange={event => setDriverId(event.target.value)} placeholder="DRV-12345" className="rounded border border-slate-300 p-2" />
        </label>
        <label className="grid gap-1 text-sm">Trip offer (PKR)
          <input required type="number" min="0" step="0.01" max="9999999999.99" value={offer} onChange={event => setOffer(event.target.value)} className="rounded border border-slate-300 p-2" />
        </label>
        <label className="grid gap-1 text-sm sm:col-span-2">Invitation notes
          <textarea maxLength={4000} value={notes} onChange={event => setNotes(event.target.value)} className="rounded border border-slate-300 p-2" />
        </label>
        <button type="submit" disabled={working} className="rounded bg-indigo-600 px-4 py-2 font-semibold text-white disabled:opacity-50">{working ? 'Sending...' : 'Send trip invitation'}</button>
      </form>}
    </>}
  </div>
}

function DriverReviewForm({ assignment, disabled, onSubmit }) {
  const [rating, setRating] = useState('5'), [comment, setComment] = useState('')
  const [incidentType, setIncidentType] = useState(''), [description, setDescription] = useState('')
  return <form className="mt-3 grid gap-2" onSubmit={event => {
    event.preventDefault()
    void onSubmit(assignment, { rating: Number(rating), comment: comment.trim(), incident_type: incidentType,
      incident_description: incidentType ? description.trim() : '' })
  }}>
    <label className="grid gap-1 text-sm">Driver rating
      <select value={rating} onChange={event => setRating(event.target.value)} className="rounded border p-2">
        {[5, 4, 3, 2, 1].map(value => <option key={value} value={value}>{value} / 5</option>)}
      </select>
    </label>
    <label className="grid gap-1 text-sm">Review comment
      <textarea value={comment} maxLength={2000} onChange={event => setComment(event.target.value)} className="rounded border p-2" />
    </label>
    <label className="grid gap-1 text-sm">Report an incident (optional)
      <select value={incidentType} onChange={event => setIncidentType(event.target.value)} className="rounded border p-2">
        <option value="">No incident</option>
        {['theft', 'damage', 'misconduct', 'delay', 'other'].map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </label>
    {incidentType && <label className="grid gap-1 text-sm">Incident details
      <textarea required aria-label="Incident details" value={description} maxLength={4000} onChange={event => setDescription(event.target.value)} className="rounded border p-2" />
      <span className="text-xs text-slate-500">Reports start as investigating. An allegation does not confirm an incident.</span>
    </label>}
    <button type="submit" disabled={disabled} className="rounded border border-indigo-600 px-3 py-2 font-semibold text-indigo-700 disabled:opacity-50">Submit trip review</button>
  </form>
}
