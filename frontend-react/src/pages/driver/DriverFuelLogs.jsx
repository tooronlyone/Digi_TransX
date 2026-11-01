import { useEffect, useState } from 'react'
import { apiGet, apiSend, formatMoney } from '../client/clientUtils'

const POPULAR_BRANDS = ['PSO', 'Shell', 'TotalParco', 'Attock Petroleum', 'Hascol', 'Gas & Go', 'Other']

export default function DriverFuelLogs() {
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  // Form State
  const [pumpName, setPumpName] = useState('')
  const [pumpBrand, setPumpBrand] = useState('PSO')
  const [city, setCity] = useState('')
  const [areaLandmark, setAreaLandmark] = useState('')
  const [fuelType, setFuelType] = useState('diesel')
  const [liters, setLiters] = useState('')
  const [pricePerLiter, setPricePerLiter] = useState('285')
  const [paymentMode, setPaymentMode] = useState('cash')
  const [selectedAssignmentId, setSelectedAssignmentId] = useState('')
  const [tripDistanceKm, setTripDistanceKm] = useState('')
  const [odometerKm, setOdometerKm] = useState('')
  const [fuelDate, setFuelDate] = useState(() => new Date().toISOString().split('T')[0])
  const [notes, setNotes] = useState('')

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    Promise.all([
      apiGet('/api/driver/fuel-logs'),
      apiGet('/api/driver/trips-for-fuel'),
    ])
      .then(([logsRes, tripsRes]) => {
        if (ignore) return
        if (logsRes.success) {
          setLogs(logsRes.logs || [])
          setStats(logsRes.stats || null)
        }
        if (tripsRes.success) {
          setTrips(tripsRes.trips || [])
        }
      })
      .catch((err) => {
        if (!ignore) setError(err.message || 'Failed to load fuel records.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [reloadKey])

  function handleTripSelect(e) {
    const asgnId = e.target.value
    setSelectedAssignmentId(asgnId)
    if (!asgnId) {
      setTripDistanceKm('')
      return
    }
    const chosen = trips.find((t) => String(t.assignment_id) === String(asgnId))
    if (chosen && chosen.actual_distance_km) {
      setTripDistanceKm(String(chosen.actual_distance_km))
    }
  }

  // Auto-calculated fields
  const calculatedTotal = Number(liters || 0) * Number(pricePerLiter || 0)
  const calculatedAvg = Number(tripDistanceKm) > 0 && Number(liters) > 0
    ? (Number(tripDistanceKm) / Number(liters)).toFixed(2)
    : null

  async function handleSubmit(e) {
    e.preventDefault()
    if (!pumpName.trim() || !city.trim() || Number(liters) <= 0 || Number(pricePerLiter) <= 0) {
      setError('Please fill in pump name, city, liters, and price.')
      return
    }

    setSubmitting(true)
    setError('')
    setMsg('')

    try {
      const payload = {
        pump_name: pumpName.trim(),
        pump_brand: pumpBrand,
        city: city.trim(),
        area_landmark: areaLandmark.trim(),
        fuel_type: fuelType,
        liters: Number(liters),
        price_per_liter: Number(pricePerLiter),
        payment_mode: paymentMode,
        assignment_id: selectedAssignmentId ? Number(selectedAssignmentId) : null,
        trip_distance_km: tripDistanceKm ? Number(tripDistanceKm) : null,
        odometer_km: odometerKm ? Number(odometerKm) : null,
        fuel_date: fuelDate,
        notes: notes.trim(),
      }

      const res = await apiSend('/api/driver/fuel-logs', payload)
      if (res.success) {
        setMsg(res.message || 'Fuel record added successfully!')
        setShowAddModal(false)
        // Reset form
        setPumpName('')
        setAreaLandmark('')
        setLiters('')
        setNotes('')
        setReloadKey((k) => k + 1)
      } else {
        setError(res.message || 'Failed to add log.')
      }
    } catch (err) {
      setError(err.message || 'Network error.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="driver-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Fuel &amp; Diesel Consumption Log</h1>
            <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
              Track every cash or card refuel with exact pump station name, city, area location, and trip fuel average.
            </p>
          </div>

          <button
            type="button"
            onClick={() => { setShowAddModal(true); setError(''); setMsg(''); }}
            style={{
              background: '#2563eb',
              color: 'white',
              border: 'none',
              padding: '12px 20px',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '0.95rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <i className="fas fa-gas-pump"></i> Record New Refuel
          </button>
        </div>

        {/* Stats Overview */}
        {stats && (
          <div className="driver-stat-grid" style={{ marginTop: '20px' }}>
            <div className="driver-stat-box">
              <p>Total Fuel Expense</p>
              <h3 style={{ color: '#0f172a' }}>{formatMoney(stats.total_fuel_spent)}</h3>
              <small style={{ color: '#64748b' }}>Across all trips</small>
            </div>
            <div className="driver-stat-box">
              <p>Total Diesel / Fuel</p>
              <h3 style={{ color: '#2563eb' }}>{stats.total_liters} Liters</h3>
              <small style={{ color: '#64748b' }}>{stats.total_refuels} Refuel visits</small>
            </div>
            <div className="driver-stat-box">
              <p>Average Mileage</p>
              <h3 style={{ color: Number(stats.avg_km_per_liter) >= 4.0 ? '#16a34a' : '#ea580c' }}>
                {stats.avg_km_per_liter > 0 ? `${stats.avg_km_per_liter} km/L` : '—'}
              </h3>
              <small style={{ color: '#64748b' }}>Trip distance &divide; consumed liters</small>
            </div>
          </div>
        )}

        {msg && (
          <div style={{ marginTop: '16px', padding: '12px', background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0', borderRadius: '8px' }}>
            <i className="fas fa-check-circle" style={{ marginRight: '6px' }}></i> {msg}
          </div>
        )}
      </div>

      {/* Fuel Logs Table / Cards */}
      <div className="driver-card">
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 16px 0' }}>Refuel History &amp; Consumption Records</h2>

        {loading ? (
          <p>Loading fuel records...</p>
        ) : logs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: '#64748b', background: '#f8fafc', borderRadius: '8px', border: '1px dashed #cbd5e1' }}>
            <i className="fas fa-gas-pump" style={{ fontSize: '2.5rem', color: '#94a3b8', marginBottom: '8px' }}></i>
            <p style={{ margin: 0, fontWeight: 700 }}>No fuel entries recorded yet.</p>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>Click &quot;Record New Refuel&quot; whenever you fill diesel or petrol during your journey.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e2e8f0', color: '#475569' }}>
                  <th style={{ padding: '10px 12px' }}>Date</th>
                  <th style={{ padding: '10px 12px' }}>Pump &amp; Exact Location</th>
                  <th style={{ padding: '10px 12px' }}>Trip / Route</th>
                  <th style={{ padding: '10px 12px' }}>Fuel Type &amp; Liters</th>
                  <th style={{ padding: '10px 12px' }}>Rate &amp; Total Paid</th>
                  <th style={{ padding: '10px 12px' }}>Trip Avg (km/L)</th>
                  <th style={{ padding: '10px 12px' }}>Payment</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px', whiteSpace: 'nowrap', fontWeight: 600 }}>{log.fuel_date}</td>
                    <td style={{ padding: '12px' }}>
                      <div style={{ fontWeight: 700, color: '#0f172a' }}>
                        {log.pump_brand ? `[${log.pump_brand}] ` : ''}{log.pump_name}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                        <i className="fas fa-location-dot" style={{ color: '#ef4444' }}></i>
                        {log.area_landmark ? `${log.area_landmark}, ` : ''}{log.city}
                      </div>
                    </td>
                    <td style={{ padding: '12px' }}>
                      {log.pickup_city && log.dropoff_city ? (
                        <div>
                          <span style={{ fontWeight: 600, color: '#1e293b' }}>{log.pickup_city} &rarr; {log.dropoff_city}</span>
                          {log.trip_distance_km && (
                            <span style={{ display: 'block', fontSize: '0.75rem', color: '#64748b' }}>
                              Dist: {log.trip_distance_km} km
                            </span>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>General / Standby</span>
                      )}
                    </td>
                    <td style={{ padding: '12px' }}>
                      <strong style={{ textTransform: 'capitalize' }}>{log.fuel_type}</strong>
                      <div style={{ color: '#2563eb', fontWeight: 700 }}>{log.liters} Liters</div>
                    </td>
                    <td style={{ padding: '12px' }}>
                      <div style={{ fontWeight: 800, color: '#0f172a' }}>{formatMoney(log.total_amount)}</div>
                      <small style={{ color: '#64748b' }}>@{formatMoney(log.price_per_liter)}/L</small>
                    </td>
                    <td style={{ padding: '12px' }}>
                      {log.fuel_average_km_per_liter ? (
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '0.8rem',
                          fontWeight: 700,
                          background: Number(log.fuel_average_km_per_liter) >= 4.0 ? '#dcfce7' : '#ffedd5',
                          color: Number(log.fuel_average_km_per_liter) >= 4.0 ? '#166534' : '#9a3412',
                        }}>
                          {log.fuel_average_km_per_liter} km/L
                        </span>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        textTransform: 'uppercase',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        background: '#f1f5f9',
                        padding: '3px 8px',
                        borderRadius: '4px',
                        color: '#475569',
                      }}>
                        {log.payment_mode}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Fuel Modal */}
      {showAddModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div style={{
            background: 'white',
            borderRadius: '12px',
            maxWidth: '650px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <i className="fas fa-gas-pump" style={{ fontSize: '1.25rem', color: '#2563eb' }}></i>
                <h2 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 800 }}>Record Fuel Refuel</h2>
              </div>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer', color: '#64748b' }}
              >
                &times;
              </button>
            </div>

            {error && (
              <div style={{ marginTop: '12px', padding: '10px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#b91c1c', fontSize: '0.85rem' }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Trip Selection */}
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                  Select Related Trip (For Distance &amp; Mileage Calculation)
                </label>
                <select
                  value={selectedAssignmentId}
                  onChange={handleTripSelect}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                >
                  <option value="">No specific trip (General fleet / Standby refill)</option>
                  {trips.map((t) => (
                    <option key={t.assignment_id} value={t.assignment_id}>
                      Truck {t.truck_number}: {t.pickup_city || 'City'} &rarr; {t.dropoff_city || 'City'} {t.actual_distance_km ? `(${t.actual_distance_km} km)` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Pump Details */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Brand
                  </label>
                  <select
                    value={pumpBrand}
                    onChange={(e) => setPumpBrand(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  >
                    {POPULAR_BRANDS.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Pump / Station Name *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. PSO Al-Rehman Petroleum"
                    value={pumpName}
                    onChange={(e) => setPumpName(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
              </div>

              {/* Exact Location & Area */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    City *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Faisalabad, Lahore"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Area / Landmark / Location
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. D-Ground, Canal Road, Bypass"
                    value={areaLandmark}
                    onChange={(e) => setAreaLandmark(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
              </div>

              {/* Fuel, Liters & Rate */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Fuel Type
                  </label>
                  <select
                    value={fuelType}
                    onChange={(e) => setFuelType(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  >
                    <option value="diesel">Diesel</option>
                    <option value="petrol">Petrol</option>
                    <option value="cng">CNG</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Liters *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    required
                    placeholder="e.g. 50"
                    value={liters}
                    onChange={(e) => setLiters(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Price / Liter (PKR) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    required
                    placeholder="285"
                    value={pricePerLiter}
                    onChange={(e) => setPricePerLiter(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
              </div>

              {/* Calculation Summary Box */}
              <div style={{ padding: '12px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>TOTAL CALCULATED CASH:</span>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>
                    {formatMoney(calculatedTotal)}
                  </div>
                </div>
                {calculatedAvg && (
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>ESTIMATED AVERAGE:</span>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#16a34a' }}>
                      {calculatedAvg} km / Liter
                    </div>
                  </div>
                )}
              </div>

              {/* Payment Mode & Distance */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Payment Mode
                  </label>
                  <select
                    value={paymentMode}
                    onChange={(e) => setPaymentMode(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  >
                    <option value="cash">Cash (Driver Paid)</option>
                    <option value="driver_wallet">Driver App Wallet</option>
                    <option value="transporter_account">Transporter Fleet Account</option>
                    <option value="company_card">Fuel Station Fleet Card</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Trip Distance (km)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    placeholder="e.g. 150"
                    value={tripDistanceKm}
                    onChange={(e) => setTripDistanceKm(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
              </div>

              {/* Refuel Date & Notes */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Refuel Date
                  </label>
                  <input
                    type="date"
                    required
                    value={fuelDate}
                    onChange={(e) => setFuelDate(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Odometer (km reading)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    placeholder="e.g. 84210"
                    value={odometerKm}
                    onChange={(e) => setOdometerKm(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                  Notes / Receipt Remark
                </label>
                <input
                  type="text"
                  placeholder="e.g. Tank full before motorway entry"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={{ padding: '10px 18px', background: '#f1f5f9', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{ padding: '10px 22px', background: '#2563eb', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
                >
                  {submitting ? 'Saving...' : 'Save Fuel Log'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
