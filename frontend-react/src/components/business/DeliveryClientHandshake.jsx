import { useRef, useState, useEffect } from 'react'
import { getCsrfToken, apiSend } from '../../pages/client/clientUtils'
import { useStepUp } from '../security/StepUpProvider'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'

export default function DeliveryClientHandshake(props) {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return null
  return <OwnedHandshake key={`${user.id}:${props.orderId}:${props.trip?.id}`} {...props} />
}

function OwnedHandshake({ orderId, trip, settlement, onChanged }) {
  const { protectedFetch } = useStepUp()
  const [code, setCode] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [reason, setReason] = useState(''), [evidence, setEvidence] = useState(''), [notice, setNotice] = useState('')
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  if (!trip) return null
  const send = (url, payload) => apiSend(url, payload, 'POST', (target, options) => {
    if (!alive.current) throw new DOMException('The account changed.', 'AbortError')
    return fetch(target, options)
  })
  async function reveal() {
    if (busy) return
    setBusy(true); setError(''); setCode(null)
    try {
      const csrf = await getCsrfToken()
      if (!alive.current) return
      const response = await protectedFetch(`/api/orders/${orderId}/trips/${trip.id}/delivery-otp`, {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' }, body: '{}',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data.success === false) throw new Error(data.message || 'Unable to reveal delivery code.')
      if (alive.current) setCode(data)
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  async function dispute(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await send(`/api/orders/${orderId}/trips/${trip.id}/disputes`, {
        reason: reason.trim(), evidence: evidence.split('\n').map(value => value.trim()).filter(Boolean),
      })
      if (!alive.current) return
      setNotice('Dispute submitted for authorized investigation. An allegation does not establish fault or a penalty.')
      setReason(''); setEvidence(''); onChanged?.()
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  const awaiting = trip.status === 'awaiting_client_confirmation'
  const completed = Boolean(settlement)
  return <section aria-label="Secure delivery acceptance" className="my-4 rounded-lg border border-indigo-200 p-4 text-sm">
    {awaiting && <>
      <p>Inspect the cargo before sharing your single-use delivery code with the Transporter. Sharing the code authorizes completion and settlement.</p>
      <button type="button" disabled={busy} className="mt-3 rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50" onClick={reveal}>{busy ? 'Processing...' : 'Inspect cargo & reveal delivery OTP'}</button>
      {code && <p role="status" className="mt-3">Delivery OTP: <strong className="text-xl tracking-widest">{code.otp}</strong>. Expires {new Date(code.expires_at).toLocaleString('en-PK')}. Share only after accepting delivery.</p>}
    </>}
    {completed && <form className="mt-3 grid gap-2" onSubmit={dispute}>
      <p>Delivery-related disputes must reach the server before 90 minutes after verified completion. Minutes 90–120 are an operational safety buffer; a new dispute during that buffer cannot stop the scheduled release under this policy.</p>
      <label className="grid gap-1">Dispute reason<textarea required maxLength={4000} value={reason} onChange={event => setReason(event.target.value)} className="rounded border p-2" /></label>
      <label className="grid gap-1">Evidence references (one authenticated record or uploaded evidence reference per line)<textarea maxLength={8000} value={evidence} onChange={event => setEvidence(event.target.value)} className="rounded border p-2" /></label>
      <button type="submit" disabled={busy} className="rounded border border-red-700 p-2 font-semibold text-red-800">Submit delivery dispute</button>
    </form>}
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
    {notice && <p role="status" className="mt-2 text-emerald-700">{notice}</p>}
  </section>
}
