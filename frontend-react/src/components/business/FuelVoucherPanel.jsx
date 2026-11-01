import { useRef, useState, useEffect } from 'react'
import { useStepUp } from '../security/StepUpProvider'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'
import { getCsrfToken } from '../../pages/client/clientUtils'
import { moneyText } from './BusinessRules'

export default function FuelVoucherPanel(props) {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !['transporter', 'logistics_provider'].includes(user?.role)) return null
  return <OwnedFuelVoucherPanel key={`${user.id}:${props.tripId || ''}:${props.agreementTripId || ''}:${props.truckId}`} {...props} ownerId={user.id} />
}

function OwnedFuelVoucherPanel({ tripId, agreementTripId, truckId, ownerId }) {
  const { protectedFetch } = useStepUp()
  const [mode, setMode] = useState('amount'), [fuelType, setFuelType] = useState('diesel')
  const [amount, setAmount] = useState(''), [liters, setLiters] = useState(''), [station, setStation] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [result, setResult] = useState(null), [notice, setNotice] = useState('')
  const idempotency = useRef(null), alive = useRef(true), activeRequest = useRef(null)
  useEffect(() => { alive.current = true; return () => { alive.current = false; activeRequest.current?.abort() } }, [])
  const pendingAuthorization = Boolean(result?.voucher?.id && ['authorized', 'verified'].includes(result.voucher.status || 'authorized'))
  async function create(event) {
    event.preventDefault()
    if (busy || pendingAuthorization) return
    setBusy(true); setError(''); setNotice(''); setResult(null)
    try {
      if (!idempotency.current) idempotency.current = crypto.randomUUID()
      const csrf = await getCsrfToken()
      if (!alive.current) return
      const controller = new AbortController()
      activeRequest.current = controller
      const response = await protectedFetch('/api/fuel/vouchers', {
        signal: controller.signal,
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json', 'Idempotency-Key': idempotency.current, 'X-DTX-Expected-User-Id': String(ownerId) },
        body: JSON.stringify({ ...(tripId ? { trip_id: tripId } : { agreement_trip_id: agreementTripId }), truck_id: truckId,
          request_mode: mode, fuel_type: fuelType, max_amount: amount, ...(liters ? { max_liters: liters } : {}), ...(station ? { station_id: station } : {}) }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data.success === false) throw new Error(data.message || 'Fuel authorization failed.')
      if (!alive.current) return
      setResult(data); idempotency.current = null
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  async function cancel() {
    if (busy || !pendingAuthorization) return
    const voucherId = result.voucher.id
    setBusy(true); setError(''); setNotice(''); setResult(previous => ({ ...previous, otp: null }))
    try {
      const csrf = await getCsrfToken()
      if (!alive.current) return
      const controller = new AbortController()
      activeRequest.current = controller
      const response = await fetch(`/api/fuel/vouchers/${voucherId}/cancel`, {
        signal: controller.signal, method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json', 'X-DTX-Expected-User-Id': String(ownerId) },
        body: JSON.stringify({}),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data.success === false) throw new Error(data.message || 'Fuel authorization cancellation failed. Retry to confirm the outcome.')
      if (!alive.current) return
      setResult({ ...data, otp: null }); idempotency.current = null
      setNotice(['cancelled', 'expired'].includes(data.voucher?.status)
        ? 'Unused funding released. You can create a new voucher to receive a new single-use code.'
        : 'This voucher has already been finalized. Its valid Fuel Station payment remains recorded.')
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  if (!truckId || Boolean(tripId) === Boolean(agreementTripId)) return null
  return <section aria-label="Trip fuel voucher" className="my-4 rounded-xl border border-slate-200 bg-white p-4">
    <h2 className="font-semibold">Authorize trip fuel</h2>
    <p className="mt-1 text-sm text-slate-600">Fuel uses your available wallet and eligible platform fuel credit. Client escrow and security reserves stay isolated. Fuel Station commission: 0%.</p>
    <p className="mt-1 text-sm text-slate-600">Authorized platform fuel credit is recovered from your payable earnings. If a trip is cancelled, unpaid credit carries forward to future eligible earnings and blocks new platform credit until repaid.</p>
    <form onSubmit={create} className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1 text-sm">Request type<select value={mode} onChange={event => { setMode(event.target.value); idempotency.current = null }} className="rounded border p-2"><option value="amount">Specified monetary amount</option><option value="liters">Specified liters</option><option value="tank_full">Tank Full</option></select></label>
      <label className="grid gap-1 text-sm">Fuel type<input required maxLength={40} value={fuelType} onChange={event => { setFuelType(event.target.value); idempotency.current = null }} className="rounded border p-2" /></label>
      <label className="grid gap-1 text-sm">Maximum authorized amount (PKR)<input required type="number" min="0.01" step="0.01" value={amount} onChange={event => { setAmount(event.target.value); idempotency.current = null }} className="rounded border p-2" /></label>
      <label className="grid gap-1 text-sm">Maximum liters {mode === 'liters' ? '(required)' : '(optional)'}<input required={mode === 'liters'} type="number" min="0.01" step="0.01" value={liters} onChange={event => { setLiters(event.target.value); idempotency.current = null }} className="rounded border p-2" /></label>
      <label className="grid gap-1 text-sm">Restrict to Fuel Station ID (optional)<input type="number" min="1" step="1" value={station} onChange={event => { setStation(event.target.value); idempotency.current = null }} className="rounded border p-2" /></label>
      <button type="submit" disabled={busy || pendingAuthorization} className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50">{busy && !pendingAuthorization ? 'Authorizing...' : 'Reserve funding & create voucher'}</button>
    </form>
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
    {notice && <p role="status" className="mt-3 text-emerald-800">{notice}</p>}
    {result && <div role="status" className="mt-3 rounded border border-emerald-300 p-3"><p>Fuel voucher #{result.voucher?.id}: {pendingAuthorization ? `authorized up to ${moneyText(result.voucher?.max_amount)}` : result.voucher?.status || 'status unavailable'}.</p>{result.voucher?.wallet_authorized != null && result.voucher?.credit_authorized != null && <p>Reserved from your available wallet: {moneyText(result.voucher.wallet_authorized)}. Reserved platform fuel credit: {moneyText(result.voucher.credit_authorized)}. Only credit actually dispensed becomes debt.</p>}{pendingAuthorization && (result.otp ? <p>Single-use Fuel Voucher OTP: <strong className="text-xl tracking-widest">{result.otp}</strong>. Show this code to the authorized Fuel Station. It is shown once.</p> : <p>Authorization already exists. The secret code is not redisplayed on retries. Cancel this unused authorization to release funding, then create a new voucher for a new code.</p>)}{pendingAuthorization && result.voucher?.expires_at && <p>Expires {new Date(result.voucher.expires_at).toLocaleString('en-PK')}.</p>}{pendingAuthorization && <button type="button" disabled={busy} onClick={cancel} className="mt-3 rounded border border-slate-400 px-3 py-2 font-semibold disabled:opacity-50">{busy ? 'Cancelling authorization...' : 'Cancel unused authorization & release funding'}</button>}</div>}
  </section>
}
