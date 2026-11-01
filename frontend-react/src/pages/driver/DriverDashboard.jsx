import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, formatMoney } from '../client/clientUtils'

export default function DriverDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => {
        if (res.success) {
          setData(res)
        } else {
          setError(res.message || 'Failed to load driver profile.')
        }
      })
      .catch((err) => setError(err.message || 'Error loading dashboard.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="driver-card"><p>Loading driver workspace...</p></div>
  }

  if (error || !data) {
    return <div className="driver-card"><p style={{ color: '#ef4444' }}>{error || 'Unable to load profile.'}</p></div>
  }

  const { driver, recent_trips, incidents } = data
  const ratingCount = Number(driver.rating_count || 0)
  const ratingValue = Number(driver.rating)
  const hasRating = ratingCount > 0 && Number.isFinite(ratingValue)

  return (
    <div>
      <div className="driver-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800 }}>Welcome, {driver.full_name}</h1>
              <span className="driver-id-badge">{driver.unique_driver_id}</span>
            </div>
            <p style={{ margin: '6px 0 0 0', color: '#64748b' }}>
              Base City: <strong>{driver.city || 'Not specified'}</strong> &middot; License: <strong>{driver.license_number}</strong>
            </p>
          </div>

          <Link
            to="/driver/active-trip"
            style={{
              background: '#16a34a',
              color: 'white',
              padding: '10px 18px',
              borderRadius: '8px',
              textDecoration: 'none',
              fontWeight: 700,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <i className="fas fa-location-arrow"></i> Open GPS Trip Console
          </Link>
        </div>

        <div className="driver-stat-grid">
          <div className="driver-stat-box">
            <p>Trust &amp; Rating Score</p>
            <h3 style={{ color: hasRating ? (ratingValue >= 4.0 ? '#16a34a' : '#ea580c') : '#64748b' }}>
              {hasRating ? `⭐ ${ratingValue.toFixed(1)} / 5.0` : 'Not rated yet'}
            </h3>
            <small style={{ color: '#64748b' }}>
              {hasRating ? `Based on ${ratingCount} review${ratingCount === 1 ? '' : 's'}` : 'No customer reviews yet'}
            </small>
          </div>

          <div className="driver-stat-box">
            <p>Total Completed Trips</p>
            <h3>{driver.total_trips || 0}</h3>
            <small style={{ color: '#64748b' }}>Verified deliveries</small>
          </div>

          <div className="driver-stat-box">
            <p>Currently Assigned Truck</p>
            <h3>{driver.truck_number || 'None'}</h3>
            <small style={{ color: '#64748b' }}>{driver.truck_model || 'Standby mode'}</small>
          </div>

          <div className="driver-stat-box">
            <p>Theft &amp; Incident Flags</p>
            <h3 style={{ color: incidents.length === 0 ? '#16a34a' : '#dc2626' }}>
              {incidents.length}
            </h3>
            <small style={{ color: incidents.length === 0 ? '#16a34a' : '#dc2626' }}>
              {incidents.length === 0 ? 'Clean Background' : 'Flagged Record'}
            </small>
          </div>
        </div>
      </div>

      <div className="driver-card">
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 16px 0' }}>Recent Dispatch Requests &amp; Trips</h2>
        {recent_trips.length === 0 ? (
          <p style={{ color: '#64748b' }}>No trip requests assigned yet. Transporters can assign you using your Unique ID <strong>{driver.unique_driver_id}</strong>.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {recent_trips.map((trip) => (
              <div
                key={trip.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '16px',
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                }}
              >
                <div>
                  <strong>Truck: {trip.truck_number} ({trip.truck_model})</strong>
                  <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>
                    Transporter: {trip.transporter_name} ({trip.transporter_phone}) &middot; Offer: {formatMoney(trip.offer_amount || 0)}
                  </p>
                </div>
                <div>
                  <span
                    style={{
                      padding: '4px 10px',
                      borderRadius: '9999px',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      background: trip.status === 'accepted' ? '#dcfce7' : trip.status === 'requested' ? '#fef3c7' : '#e2e8f0',
                      color: trip.status === 'accepted' ? '#166534' : trip.status === 'requested' ? '#92400e' : '#475569',
                    }}
                  >
                    {trip.status.toUpperCase()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
