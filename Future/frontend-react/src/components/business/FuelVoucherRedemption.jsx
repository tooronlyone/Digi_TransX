import { useRef, useState, useEffect } from 'react'
import { apiSend } from '../../pages/client/clientUtils'
import { moneyText } from './BusinessRules'

export default function FuelVoucherRedemption({ pumps, onDispensed }) {
  const [otp, setOtp] = useState(''), [pumpId, setPumpId] = useState(''), [liters, setLiters] = useState('')
  const [authorization, setAuthorization] = useState(null), [receipt, setReceipt] = useState(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const alive = useRef(true), mutationRequest = useRef(null)
  useEffect(() => { alive.current = true; return () => { alive.current = false; mutationRequest.current?.abort() } }, [])
  const send = (url, payload) => apiSend(url, payload, 'POST', (target, options) => {
    if (!alive.current) throw new DOMException('The account changed.', 'AbortError')
    const controller = new AbortController()
    mutationRequest.current = controller
    return fetch(target, { ...options, signal: controller.signal })
  })
  async function verify(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setReceipt(null)
    try {
      const result = await send('/api/fuelstation/vouchers/verify', { otp: otp.trim(), pump_id: pumpId })
      if (alive.current) { setAuthorization({ ...result, pumpId }); setOtp('') }
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  async function finalize(event) {
    event.preventDefault()
    if (busy || !authorization) return
    setBusy(true); setError('')
    try {
      const result = await send(`/api/fuelstation/vouchers/${authorization.voucher.id}/dispense`, {
        redemption_token: authorization.redemption_token, pump_id: authorization.pumpId,
        actual_liters: liters, truck_plate: authorization.voucher.truck_plate, fuel_type: authorization.voucher.fuel_type,
      })
      if (!alive.current) return
      setReceipt(result.receipt || result.voucher || result); setAuthorization(null); setLiters(''); onDispensed?.()
    } catch (failure) { if (alive.current) setError(failure.message) }
    finally { if (alive.current) setBusy(false) }
  }
  const voucher = authorization?.voucher
  return <section aria-label="Fuel voucher redemption" className="fuel-card" style={{ marginBottom: 24 }}>
    <h2 className="font-semibold">Redeem Digi_TransX Fuel Voucher</h2>
    <p className="mt-2 text-sm">Verify the OTP and reserved funding before dispensing. The station receives the full verified value with 0% platform commission.</p>
    {!authorization && <form onSubmit={verify} className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1 text-sm">Fuel Voucher OTP<input required autoComplete="off" maxLength={128} value={otp} onChange={event => setOtp(event.target.value)} className="fuel-form-input" /></label>
      <label className="grid gap-1 text-sm">Dispense pump<select required value={pumpId} onChange={event => setPumpId(event.target.value)} className="fuel-form-select"><option value="">Select matching pump</option>{pumps.map(pump => <option key={pump.id} value={pump.id}>{pump.pump_name || pump.name || `Pump ${pump.id}`} · {pump.fuel_type}</option>)}</select></label>
      <button disabled={busy} type="submit" className="fuel-btn fuel-btn--primary">{busy ? 'Verifying...' : 'Verify OTP & reserved funding'}</button>
    </form>}
    {voucher && <div className="mt-4 rounded-lg border p-4">
      <h3 className="font-semibold">Authorized digital dispense slip</h3>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">{[
        ['Truck plate', voucher.truck_plate], ['Fuel type', voucher.fuel_type], ['Authorized maximum', moneyText(voucher.max_amount)],
        ['Authorized quantity', voucher.max_liters == null ? 'Monetary cap applies' : `${voucher.max_liters} liters`],
        ['Fuel Station', voucher.redeemed_station_id || voucher.restricted_station_id || 'Station identity unavailable'], ['Trip reference', voucher.trip_id || voucher.agreement_trip_id],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="font-semibold">{value}</dd></div>)}</dl>
      <form onSubmit={finalize} className="mt-3 flex flex-wrap items-end gap-3"><label className="grid gap-1 text-sm">Actual dispensed liters<input required type="number" min="0.01" step="0.01" value={liters} onChange={event => setLiters(event.target.value)} className="fuel-form-input" /></label><button type="submit" disabled={busy} className="fuel-btn fuel-btn--success">{busy ? 'Finalizing...' : 'Finalize dispense & credit station wallet'}</button></form>
      <p className="mt-2 text-xs">The server calculates the charge from the verified pump rate, enforces authorization limits, and returns unused funding.</p>
    </div>}
    {receipt && <div role="status" className="mt-3 rounded border border-emerald-300 p-3"><p className="font-semibold">Dispense finalized. Fuel Station credited.</p><p>Truck: {receipt.truck_plate || receipt.vehicle_plate}. Quantity: {receipt.actual_liters || receipt.liters}. Actual amount: {moneyText(receipt.actual_amount || receipt.total_pkr)}.</p><button type="button" className="fuel-btn" onClick={() => window.print()}>Print verified slip</button></div>}
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
  </section>
}
