import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import FuelStationLayout from '../../components/fuelstation/FuelStationLayout'

export default function FuelStationDashboard() {
  const api = useApi()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false
    api.get('/api/fuelstation/dashboard')
      .then(res => {
        if (ignore) return
        if (res.success) {
          setData(res)
        } else {
          setError(res.message || 'Failed to load dashboard data.')
        }
      })
      .catch(err => {
        if (!ignore) setError(err.message || 'Unable to connect to server.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [api])

  const metrics = data?.metrics || {
    today_liters: 0,
    today_revenue: 0,
    today_transactions: 0,
    active_pumps: 0,
    total_liters: 0,
    total_revenue: 0,
  }

  const recent = data?.recent_dispenses || []
  const pumps = data?.pumps || []

  return (
    <FuelStationLayout>
      {error && (
        <div style={{ background: '#fff0f0', border: '1px solid #ffcaca', color: '#a93737', padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>
          <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 8 }} />
          {error}
        </div>
      )}

      {/* KPI Cards */}
      <div className="fuel-kpi-grid">
        <div className="fuel-kpi-card">
          <div className="fuel-kpi-card__icon fuel-kpi-card__icon--amber">
            <i className="fa-solid fa-gas-pump" />
          </div>
          <div className="fuel-kpi-card__info">
            <p>Today's Fuel Dispensed</p>
            <h3>{loading ? '...' : `${metrics.today_liters.toLocaleString()} L`}</h3>
          </div>
        </div>

        <div className="fuel-kpi-card">
          <div className="fuel-kpi-card__icon fuel-kpi-card__icon--green">
            <i className="fa-solid fa-coins" />
          </div>
          <div className="fuel-kpi-card__info">
            <p>Today's Revenue (PKR)</p>
            <h3>{loading ? '...' : `Rs. ${metrics.today_revenue.toLocaleString()}`}</h3>
          </div>
        </div>

        <div className="fuel-kpi-card">
          <div className="fuel-kpi-card__icon fuel-kpi-card__icon--blue">
            <i className="fa-solid fa-truck" />
          </div>
          <div className="fuel-kpi-card__info">
            <p>Today's Refuelings</p>
            <h3>{loading ? '...' : metrics.today_transactions}</h3>
          </div>
        </div>

        <div className="fuel-kpi-card">
          <div className="fuel-kpi-card__icon fuel-kpi-card__icon--purple">
            <i className="fa-solid fa-sliders" />
          </div>
          <div className="fuel-kpi-card__info">
            <p>Active Dispensers</p>
            <h3>{loading ? '...' : `${metrics.active_pumps} / ${data?.metrics?.total_pumps || metrics.active_pumps}`}</h3>
          </div>
        </div>
      </div>

      {/* Live Rates & Quick POS Action */}
      <div className="fuel-rates-bar">
        <div className="fuel-rates-bar__title">
          <i className="fa-solid fa-bolt" />
          <span>Live Fuel Rates:</span>
        </div>
        <div className="fuel-rates-chips">
          {pumps.map(p => (
            <div key={p.id} className="fuel-rate-chip">
              <span>{p.pump_number} ({p.fuel_type_label}):</span>
              <strong>Rs. {p.price_per_liter.toFixed(2)} / L</strong>
            </div>
          ))}
          {pumps.length === 0 && <span style={{ color: '#94a3b8' }}>No pumps configured.</span>}
        </div>
        <button
          className="fuel-btn fuel-btn--primary"
          onClick={() => navigate('/fuelstation/dispense')}
        >
          <i className="fa-solid fa-gas-pump" /> New Fueling POS
        </button>
      </div>

      {/* Recent Dispenses Table */}
      <div className="fuel-card">
        <div className="fuel-card__header">
          <h2>Recent Dispenses & Refuelings</h2>
          <Link to="/fuelstation/history" style={{ color: '#f59e0b', fontSize: 13, textDecoration: 'none', fontWeight: 600 }}>
            View All History &rarr;
          </Link>
        </div>

        <div className="fuel-table-wrapper">
          <table className="fuel-table">
            <thead>
              <tr>
                <th>Receipt #</th>
                <th>Time</th>
                <th>Vehicle Plate</th>
                <th>Driver</th>
                <th>Fuel Type</th>
                <th>Liters</th>
                <th>Rate (PKR)</th>
                <th>Total (PKR)</th>
                <th>Payment</th>
              </tr>
            </thead>
            <tbody>
              {recent.map(r => (
                <tr key={r.id}>
                  <td><strong>#{r.id}</strong></td>
                  <td>{r.created_at ? new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'N/A'}</td>
                  <td><span style={{ background: '#eaf1ff', color: '#2459d3', padding: '3px 8px', borderRadius: 4, fontWeight: 700 }}>{r.vehicle_plate}</span></td>
                  <td>{r.driver_name}</td>
                  <td>{r.fuel_type_label}</td>
                  <td><strong>{r.liters.toFixed(2)} L</strong></td>
                  <td>Rs. {r.price_per_liter.toFixed(2)}</td>
                  <td><span style={{ color: '#22c55e', fontWeight: 700 }}>Rs. {r.total_pkr.toLocaleString()}</span></td>
                  <td><span className="fuel-badge fuel-badge--active">{r.payment_method}</span></td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr>
                  <td colSpan="9" style={{ textAlign: 'center', padding: '32px', color: '#94a3b8' }}>
                    No fuel dispensed yet today. Click "New Fueling POS" to log a refuel.
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
