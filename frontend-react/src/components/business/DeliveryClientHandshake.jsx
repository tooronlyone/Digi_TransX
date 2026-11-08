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
  const [code, setCode] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState('')
  const [notice, setNotice] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  if (!trip) return null

  const send = (url, payload) => apiSend(url, payload, 'POST', (target, options) => {
    if (!alive.current) throw new DOMException('The account changed.', 'AbortError')
    return fetch(target, options)
  })

  async function reveal() {
    if (busy) return
    setBusy(true)
    setError('')
    setCode(null)
    setCopied(false)
    try {
      const csrf = await getCsrfToken()
      if (!alive.current) return
      const response = await protectedFetch(`/api/orders/${orderId}/trips/${trip.id}/delivery-otp`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
        body: '{}',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data.success === false) throw new Error(data.message || 'Unable to reveal delivery code.')
      if (alive.current) setCode(data)
    } catch (failure) {
      if (alive.current) setError(failure.message)
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  async function copyOtp() {
    if (!code?.otp) return
    try {
      await navigator.clipboard.writeText(String(code.otp))
      setCopied(true)
      setTimeout(() => { if (alive.current) setCopied(false) }, 2500)
    } catch {
      // ignore clipboard errors
    }
  }

  async function dispute(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await send(`/api/orders/${orderId}/trips/${trip.id}/disputes`, {
        reason: reason.trim(),
        evidence: evidence.split('\n').map(value => value.trim()).filter(Boolean),
      })
      if (!alive.current) return
      setNotice('Dispute submitted for authorized investigation. An allegation does not establish fault or a penalty.')
      setReason('')
      setEvidence('')
      onChanged?.()
    } catch (failure) {
      if (alive.current) setError(failure.message)
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  const awaiting = trip.status === 'awaiting_client_confirmation'
  const completed = Boolean(settlement)
  if (!awaiting && !completed) return null

  return (
    <section aria-label="Secure delivery acceptance" className="my-4 rounded-xl border-2 border-indigo-200 bg-indigo-50/60 p-5 text-sm shadow-sm">
      {awaiting && (
        <div>
          <div className="flex items-center gap-2 text-base font-bold text-indigo-950">
            <i className="fas fa-key text-indigo-600" aria-hidden="true"></i>
            <span>Delivery Handshake Required — Share OTP with Transporter</span>
          </div>
          <p className="mt-1.5 text-slate-700">
            The transporter has marked your cargo delivered and requested your 8-digit Delivery OTP.
            Inspect the cargo first, then click below to reveal the single-use OTP and share it with the transporter to complete the order.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy}
              className="inline-flex min-h-10 items-center justify-center rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={reveal}
            >
              <i className={`fas ${busy ? 'fa-spinner fa-spin' : 'fa-eye'} mr-2`} aria-hidden="true"></i>
              {busy ? 'Processing...' : code ? 'Refresh / Show Delivery OTP' : 'Inspect cargo & reveal delivery OTP'}
            </button>
          </div>
          {code && (
            <div role="status" className="mt-4 rounded-xl border border-indigo-300 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Your 8-Digit Delivery OTP</span>
                  <div className="mt-1 font-mono text-2xl font-extrabold tracking-widest text-indigo-900">
                    {code.otp}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={copyOtp}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                >
                  <i className={`fas ${copied ? 'fa-check text-emerald-600' : 'fa-copy'}`} aria-hidden="true"></i>
                  {copied ? 'Copied!' : 'Copy OTP'}
                </button>
              </div>
              <p className="mt-2 text-xs text-slate-600">
                Expires {new Date(code.expires_at).toLocaleString('en-PK')}. Share this code with the transporter only after accepting delivery.
              </p>
            </div>
          )}
        </div>
      )}

      {completed && (
        <details className="group">
          <summary className="cursor-pointer font-semibold text-slate-800 hover:text-indigo-700">
            <i className="fas fa-shield-halved mr-2 text-indigo-600" aria-hidden="true"></i>
            Have an issue with this delivery? (90-minute dispute window)
          </summary>
          <form className="mt-3 grid gap-2 border-t border-indigo-100 pt-3" onSubmit={dispute}>
            <p className="text-xs text-slate-600">
              Delivery-related disputes must reach the server before 90 minutes after verified completion. Minutes 90–120 are an operational safety buffer; a new dispute during that buffer cannot stop the scheduled release under this policy.
            </p>
            <label className="grid gap-1 font-medium text-slate-700">
              Dispute reason
              <textarea required maxLength={4000} value={reason} onChange={event => setReason(event.target.value)} className="rounded-lg border border-slate-300 bg-white p-2" />
            </label>
            <label className="grid gap-1 font-medium text-slate-700">
              Evidence references (one authenticated record or uploaded evidence reference per line)
              <textarea maxLength={8000} value={evidence} onChange={event => setEvidence(event.target.value)} className="rounded-lg border border-slate-300 bg-white p-2" />
            </label>
            <button type="submit" disabled={busy} className="w-fit rounded-lg border border-red-700 bg-white px-4 py-2 font-semibold text-red-800 hover:bg-red-50">
              Submit delivery dispute
            </button>
          </form>
        </details>
      )}
      {error && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 font-medium text-red-700">{error}</p>}
      {notice && <p role="status" className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 font-medium text-emerald-700">{notice}</p>}
    </section>
  )
}
