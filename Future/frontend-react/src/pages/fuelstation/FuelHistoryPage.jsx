import { useEffect, useState, useMemo } from 'react'
import { useApi } from '../../hooks/useApi'
import FuelStationLayout from '../../components/fuelstation/FuelStationLayout'

export default function FuelHistoryPage() {
  const api = useApi()
  const [dispenses, setDispenses] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [fuelFilter, setFuelFilter] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false
    api.get('/api/fuelstation/dispenses')
      .then(res => {
        if (!ignore && res.success) setDispenses(res.dispenses || [])
      })
      .catch(() => {
        if (!ignore) setError('Failed to load transaction history.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [api])

  const filtered = useMemo(() => {
    return dispenses.filter(d => {
      const matchFuel = !fuelFilter || d.fuel_type === fuelFilter
      const q = search.trim().toLowerCase()
      const matchSearch = !q ||
        d.vehicle_plate.toLowerCase().includes(q) ||
        (d.driver_name || '').toLowerCase().includes(q) ||
        (d.driver_phone || '').includes(q) ||
        String(d.id).includes(q)
      return matchFuel && matchSearch
    })
  }, [dispenses, fuelFilter, search])

  const totalLiters = filtered.reduce((sum, d) => sum + (d.liters || 0), 0)
  const totalRevenue = filtered.reduce((sum, d) => sum + (d.total_pkr || 0), 0)

  function exportCSV() {
    if (!filtered.length) return
    const headers = ['Receipt #', 'Date', 'Vehicle Plate', 'Driver Name', 'Driver Phone', 'Fuel Type', 'Liters', 'Price Per Liter', 'Total PKR', 'Payment Mode', 'Notes']
    const rows = filtered.map(d => [
      d.id,
      d.created_at || '',
      d.vehicle_plate,
      `"${d.driver_name || ''}"`,
      d.driver_phone || '',
      d.fuel_type_label,
      d.liters,
      d.price_per_liter,
      d.total_pkr,
      d.payment_method,
      `"${(d.notes || '').replace(/"/g, '""')}"`,
    ])

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `fuel_dispenses_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <FuelStationLayout>
      <div className="fuel-card">
        <div className="fuel-card__header">
          <div>
            <h2>Vehicle Refueling History &amp; Dispense Logs</h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#94a3b8' }}>
              Complete record of all trucks serviced, liters dispensed, and payments received.
            </p>
          </div>
          <button
            className="fuel-btn fuel-btn--success"
            onClick={exportCSV}
            disabled={filtered.length === 0}
          >
            <i className="fa-solid fa-file-csv" /> Export CSV / Excel
          </button>
        </div>

        {error && (
          <div className="fuel-alert fuel-alert--danger" style={{ marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16, marginBottom: 20 }}>
          <div className="fuel-form-group" style={{ margin: 0 }}>
            <input
              type="text"
              placeholder="Search by truck plate (e.g. LES-4921) or driver name..."
              className="fuel-form-input"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="fuel-form-group" style={{ margin: 0 }}>
            <select
              className="fuel-form-select"
              value={fuelFilter}
              onChange={e => setFuelFilter(e.target.value)}
            >
              <option value="">All Fuel Types</option>
              <option value="diesel">High Speed Diesel (HSD)</option>
              <option value="petrol">Super Petrol</option>
              <option value="hi_octane">Hi-Octane 97</option>
              <option value="cng">CNG</option>
              <option value="adblue">AdBlue / DEF</option>
            </select>
          </div>
        </div>

        {/* Summary Totals */}
        <div style={{ display: 'flex', gap: 24, padding: '12px 18px', background: '#f5f8fc', borderRadius: 8, marginBottom: 20, border: '1px solid #dce5ee' }}>
          <div>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>Filtered Transactions:</span>
            <strong style={{ display: 'block', fontSize: 16, color: '#243b53' }}>{filtered.length}</strong>
          </div>
          <div>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>Total Quantity:</span>
            <strong style={{ display: 'block', fontSize: 16, color: '#f59e0b' }}>{totalLiters.toFixed(2)} Liters</strong>
          </div>
          <div>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>Total Value (PKR):</span>
            <strong style={{ display: 'block', fontSize: 16, color: '#22c55e' }}>Rs. {totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
          </div>
        </div>

        <div className="fuel-table-wrapper">
          <table className="fuel-table">
            <thead>
              <tr>
                <th>Receipt #</th>
                <th>Date / Time</th>
                <th>Vehicle Plate</th>
                <th>Driver</th>
                <th>Dispenser / Bay</th>
                <th>Fuel Grade</th>
                <th>Liters</th>
                <th>Rate (PKR)</th>
                <th>Total Paid (PKR)</th>
                <th>Payment Mode</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(d => (
                <tr key={d.id}>
                  <td><strong>#{d.id}</strong></td>
                  <td>{d.created_at ? new Date(d.created_at).toLocaleString() : 'N/A'}</td>
                  <td><span style={{ background: '#eaf1ff', color: '#2459d3', padding: '3px 8px', borderRadius: 4, fontWeight: 700 }}>{d.vehicle_plate}</span></td>
                  <td>
                    {d.driver_name}
                    {d.driver_phone && <small style={{ display: 'block', color: '#94a3b8' }}>{d.driver_phone}</small>}
                  </td>
                  <td>{d.pump_number}</td>
                  <td>{d.fuel_type_label}</td>
                  <td><strong>{d.liters.toFixed(2)} L</strong></td>
                  <td>Rs. {d.price_per_liter.toFixed(2)}</td>
                  <td><span style={{ color: '#22c55e', fontWeight: 700 }}>Rs. {d.total_pkr.toLocaleString()}</span></td>
                  <td><span className="fuel-badge fuel-badge--active">{d.payment_method}</span></td>
                </tr>
              ))}
              {filtered.length === 0 && !loading && (
                <tr>
                  <td colSpan="10" style={{ textAlign: 'center', padding: '32px', color: '#94a3b8' }}>
                    No matching refueling records found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </FuelStationLayout>
  )
}
