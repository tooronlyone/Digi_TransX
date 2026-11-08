import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiSend } from '../client/clientUtils'
import { productMoney } from '../../lib/exactMoney'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import FuelVoucherRedemption from '../../components/business/FuelVoucherRedemption'
import FuelStationLayout from '../../components/fuelstation/FuelStationLayout'

export default function FuelDispensePOS() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || user?.role !== 'fuel_station_manager' || !user?.id) return <ShellPageSkeleton />
  return <OwnedFuelDispensePOS key={String(user.id)} />
}

function OwnedFuelDispensePOS() {
  const [pumps, setPumps] = useState([])
  const [selectedPumpId, setSelectedPumpId] = useState('')
  const [form, setForm] = useState({
    vehicle_plate: '',
    driver_name: '',
    driver_phone: '',
    liters: '',
    payment_method: 'cash',
    notes: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [receipt, setReceipt] = useState(null)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const alive = useRef(true), pumpRequest = useRef(null), mutationRequest = useRef(null), readGeneration = useRef(0)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; pumpRequest.current?.abort(); mutationRequest.current?.abort() }
  }, [])

  const loadPumps = useCallback(async () => {
    if (!alive.current) return
    const generation = ++readGeneration.current
    pumpRequest.current?.abort()
    const controller = new AbortController()
    pumpRequest.current = controller
    try {
      const result = await apiGet('/api/fuelstation/pumps', { signal: controller.signal })
      if (!alive.current || controller.signal.aborted || generation !== readGeneration.current) return
      const activePumps = (result.pumps || []).filter(pump => pump.status === 'active')
      setPumps(activePumps)
      setSelectedPumpId(current => activePumps.some(pump => String(pump.id) === current) ? current : String(activePumps[0]?.id ?? ''))
    } catch (error) {
      if (!alive.current || controller.signal.aborted || generation !== readGeneration.current) return
      setError(error.message || 'Pump stock could not be refreshed. Please reload before dispensing.')
    }
  }, [])

  useEffect(() => {
    let active = true
    queueMicrotask(() => { if (active) void loadPumps() })
    return () => { active = false }
  }, [loadPumps])

  function handlePumpChange(pumpId) {
    setSelectedPumpId(pumpId)
  }

  const selectedPump = pumps.find(p => String(p.id) === String(selectedPumpId))

  const calculatedTotal = productMoney(selectedPump?.price_per_liter, form.liters)

  async function handleDispense(e) {
    e.preventDefault()
    if (submitting) return
    setError('')
    setSuccessMsg('')
    if (!form.vehicle_plate.trim()) {
      setError('Vehicle plate number is required.')
      return
    }
    if (!selectedPump) {
      setError('Select an active pump before dispensing.')
      return
    }
    const liters = Number(form.liters)
    if (!Number.isFinite(liters) || liters <= 0) {
      setError('Please enter a valid amount of liters.')
      return
    }
    if (liters > Number(selectedPump.current_stock_liters)) {
      setError('The selected pump does not have enough fuel in stock.')
      return
    }

    setSubmitting(true)
    try {
      const res = await apiSend('/api/fuelstation/dispense', {
        pump_id: Number(selectedPump.id),
        vehicle_plate: form.vehicle_plate.trim().toUpperCase(),
        driver_name: form.driver_name.trim(),
        driver_phone: form.driver_phone.trim(),
        liters,
        payment_method: form.payment_method,
        notes: form.notes.trim(),
      }, 'POST', (url, options) => {
        if (!alive.current) throw new DOMException('Station account changed.', 'AbortError')
        const controller = new AbortController()
        mutationRequest.current = controller
        return fetch(url, { ...options, signal: controller.signal })
      })
      if (!alive.current) return

      if (res.success) {
        setReceipt(res.receipt)
        setSuccessMsg('Fuel successfully dispensed and logged!')
        setPumps(current => current.map(pump => pump.id === selectedPump.id
          ? { ...pump, current_stock_liters: Math.max(0, Number(pump.current_stock_liters) - liters) }
          : pump))
        setForm(f => ({
          ...f,
          vehicle_plate: '',
          driver_name: '',
          driver_phone: '',
          liters: '',
          notes: '',
        }))
        await loadPumps()
      } else {
        setError(res.message || 'Dispense failed.')
      }
    } catch (err) {
      if (!alive.current) return
      setError(err.message || 'Server error occurred during dispense.')
    } finally {
      if (alive.current) setSubmitting(false)
    }
  }

  function handlePrint() {
    window.print()
  }

  return (
    <FuelStationLayout>
      <FuelVoucherRedemption pumps={pumps} onDispensed={loadPumps} />
      <div className="fuel-pos-grid">
        {/* Dispense Form */}
        <div className="fuel-card">
          <div className="fuel-card__header">
            <h2><i className="fa-solid fa-gas-pump" style={{ color: '#f59e0b', marginRight: 8 }} /> Truck Refueling Counter</h2>
          </div>

          {error && (
            <div style={{ background: '#fff0f0', border: '1px solid #ffcaca', color: '#a93737', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
              <i className="fa-solid fa-circle-exclamation" style={{ marginRight: 6 }} /> {error}
            </div>
          )}

          {successMsg && (
            <div style={{ background: '#ecf9f4', border: '1px solid #c4eadc', color: '#176b54', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
              <i className="fa-solid fa-circle-check" style={{ marginRight: 6 }} /> {successMsg}
            </div>
          )}

          <form onSubmit={handleDispense}>
            <div className="fuel-form-group">
              <label>Select Dispenser Pump / Fuel Type</label>
              <select
                className="fuel-form-select"
                value={selectedPumpId}
                onChange={e => handlePumpChange(e.target.value)}
                required
                disabled={submitting || !pumps.length}
              >
                {!pumps.length && <option value="">No active pumps available</option>}
                {pumps.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.pump_number} — {p.fuel_type_label} (Rs. {Number(p.price_per_liter).toFixed(2)}/L) [Stock: {Number(p.current_stock_liters ?? 0).toLocaleString()} L]
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="fuel-form-group">
                <label>Liters to Dispense *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={selectedPump?.current_stock_liters ?? 0}
                  className="fuel-form-input"
                  placeholder="e.g. 150"
                  value={form.liters}
                  onChange={e => setForm({ ...form, liters: e.target.value })}
                  required
                />
              </div>

              <div className="fuel-form-group">
                <label>Rate per Liter (PKR)</label>
                <input
                  type="number"
                  step="0.01"
                  className="fuel-form-input"
                  value={selectedPump?.price_per_liter ?? ''}
                  readOnly
                  aria-label="Stored pump rate per liter"
                />
              </div>
            </div>

            <div style={{ background: '#f5f8fc', padding: '12px 16px', borderRadius: 8, marginBottom: 18, border: '1px solid #dce5ee', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#60758a', fontSize: 13, fontWeight: 600 }}>Estimated Total Amount:</span>
              <strong style={{ fontSize: 20, color: '#078969' }}>Rs. {calculatedTotal}</strong>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="fuel-form-group">
                <label>Truck Plate / Registration No *</label>
                <input
                  type="text"
                  className="fuel-form-input"
                  placeholder="e.g. LES-4921, KHI-8832"
                  value={form.vehicle_plate}
                  onChange={e => setForm({ ...form, vehicle_plate: e.target.value })}
                  required
                />
              </div>

              <div className="fuel-form-group">
                <label>Driver Phone Number</label>
                <input
                  type="tel"
                  className="fuel-form-input"
                  placeholder="03XX-XXXXXXX"
                  value={form.driver_phone}
                  onChange={e => setForm({ ...form, driver_phone: e.target.value })}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="fuel-form-group">
                <label>Driver Name</label>
                <input
                  type="text"
                  className="fuel-form-input"
                  placeholder="e.g. Rashid Gujjar"
                  value={form.driver_name}
                  onChange={e => setForm({ ...form, driver_name: e.target.value })}
                />
              </div>

              <div className="fuel-form-group">
                <label>Payment Mode</label>
                <select
                  className="fuel-form-select"
                  value={form.payment_method}
                  onChange={e => setForm({ ...form, payment_method: e.target.value })}
                >
                  <option value="cash">Direct Cash</option>
                  <option value="card">Card at station terminal</option>
                </select>
              </div>
            </div>

            <div className="fuel-form-group">
              <label>Notes / Vehicle Odometer (Optional)</label>
              <input
                type="text"
                className="fuel-form-input"
                placeholder="e.g. Full tank Bedford 10-wheeler, Odometer: 142,500 km"
                value={form.notes}
                onChange={e => setForm({ ...form, notes: e.target.value })}
              />
            </div>

            <button
              type="submit"
              disabled={submitting || !selectedPump || Number(selectedPump.current_stock_liters) <= 0}
              className="fuel-btn fuel-btn--primary"
              style={{ width: '100%', padding: '14px', fontSize: 16 }}
            >
              <i className={`fa-solid ${submitting ? 'fa-spinner fa-spin' : 'fa-gas-pump'}`} />
              {submitting ? 'Processing Dispense...' : 'Dispense Fuel & Print Receipt'}
            </button>
          </form>
        </div>

        {/* Live Receipt Slip Preview */}
        <div>
          {receipt ? (
            <div className="fuel-receipt-box">
              <h3>DIGI_TRANSX FUEL RECEIPT</h3>
              <p className="receipt-sub">Verified Station Dispense Slip</p>

              <div className="fuel-receipt-row">
                <span>Receipt Number:</span>
                <strong>#{receipt.id}</strong>
              </div>
              <div className="fuel-receipt-row">
                <span>Date &amp; Time:</span>
                <span>{receipt.date}</span>
              </div>
              <div className="fuel-receipt-row">
                <span>Vehicle Registration:</span>
                <strong style={{ color: '#f59e0b' }}>{receipt.vehicle_plate}</strong>
              </div>
              <div className="fuel-receipt-row">
                <span>Driver:</span>
                <span>{receipt.driver_name}</span>
              </div>
              <div className="fuel-receipt-row">
                <span>Fuel Grade:</span>
                <span>{receipt.fuel_type_label}</span>
              </div>
              <div className="fuel-receipt-row">
                <span>Quantity Dispensed:</span>
                <strong>{receipt.liters.toFixed(2)} Liters</strong>
              </div>
              <div className="fuel-receipt-row">
                <span>Rate per Liter:</span>
                <span>Rs. {receipt.price_per_liter.toFixed(2)}</span>
              </div>
              <div className="fuel-receipt-row">
                <span>Payment Mode:</span>
                <span style={{ textTransform: 'uppercase' }}>{receipt.payment_method}</span>
              </div>

              <div className="fuel-receipt-total">
                <span>Net Total Paid:</span>
                <span>Rs. {receipt.total_pkr.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>

              <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
                <button
                  type="button"
                  className="fuel-btn fuel-btn--success"
                  style={{ flex: 1 }}
                  onClick={handlePrint}
                >
                  <i className="fa-solid fa-print" /> Print Slip
                </button>
                <button
                  type="button"
                  className="fuel-btn"
                  style={{ background: '#eef2f6', color: '#40566d', border: '1px solid #d9e2ec' }}
                  onClick={() => setReceipt(null)}
                >
                  Close
                </button>
              </div>
            </div>
          ) : (
            <div className="fuel-card" style={{ textAlign: 'center', padding: '48px 24px', color: '#7b8da1' }}>
              <i className="fa-solid fa-receipt" style={{ fontSize: 48, color: '#a9bacb', marginBottom: 16 }} />
              <h3 style={{ color: '#243b53', margin: '0 0 8px' }}>Dispense Slip Preview</h3>
              <p style={{ margin: 0, fontSize: 13 }}>
                When you dispense fuel on the left counter, the official verified customer receipt will appear here for instant printing.
              </p>
            </div>
          )}
        </div>
      </div>
    </FuelStationLayout>
  )
}
