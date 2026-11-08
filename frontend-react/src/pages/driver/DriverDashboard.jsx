import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, formatMoney } from '../client/clientUtils'

function statusClass(status = '') {
  return `driver-status driver-status--${String(status).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
}

export default function DriverDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => res.success ? setData(res) : setError(res.message || 'Failed to load driver profile.'))
      .catch((err) => setError(err.message || 'Error loading dashboard.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="driver-page" aria-busy="true"><div className="driver-skeleton driver-skeleton--hero" /><div className="driver-skeleton-grid"><div className="driver-skeleton" /><div className="driver-skeleton" /><div className="driver-skeleton" /></div></div>
  }

  if (error || !data) {
    return <div className="driver-state driver-state--error" role="alert"><i className="fas fa-circle-exclamation" /><h2>Dashboard unavailable</h2><p>{error || 'Unable to load your driver profile.'}</p><button type="button" className="driver-btn driver-btn--primary" onClick={() => window.location.reload()}>Try again</button></div>
  }

  const { driver, recent_trips = [], incidents = [] } = data
  const ratingCount = Number(driver.rating_count || 0)
  const ratingValue = Number(driver.rating)
  const hasRating = ratingCount > 0 && Number.isFinite(ratingValue)
  const activeTrip = recent_trips.find((trip) => ['accepted', 'in_progress'].includes(trip.status))
  const routeStart = activeTrip?.pickup_city || driver.city || 'Driver base'
  const routeEnd = activeTrip?.dropoff_city || 'Awaiting assignment'

  return (
    <div className="driver-page driver-dashboard-page">
      <section className="driver-welcome-panel">
        <div className="driver-welcome-copy">
          <div className="driver-welcome-meta">
            <span className="driver-id-badge"><i className="fas fa-id-card" aria-hidden="true" /> {driver.unique_driver_id}</span>
            <span className={activeTrip ? 'driver-live-label' : 'driver-standby-label'}><span aria-hidden="true" /> {activeTrip ? 'Trip assigned' : 'Ready for dispatch'}</span>
          </div>
          <h2>Welcome back, {driver.full_name}</h2>
          <p>Review your next assignment, keep location updates running during an active trip, and stay on top of earnings and records.</p>
          <div className="driver-welcome-facts">
            <span><i className="fas fa-location-dot" aria-hidden="true" /> {driver.city || 'Base city not set'}</span>
            <span><i className="fas fa-address-card" aria-hidden="true" /> Licence {driver.license_number || 'not available'}</span>
          </div>
          <div className="driver-welcome-actions">
            <Link to="/driver/active-trip" className="driver-btn driver-btn--primary"><i className="fas fa-location-arrow" aria-hidden="true" /> Open trip console</Link>
            <Link to="/driver/trips" className="driver-btn driver-btn--secondary">View requests <i className="fas fa-arrow-right" aria-hidden="true" /></Link>
          </div>
        </div>
        <div className="driver-welcome-route" aria-label={`Route from ${routeStart} to ${routeEnd}`}>
          <span className="driver-route-pin driver-route-pin--start"><i className="fas fa-truck" aria-hidden="true" /><small>Start</small><strong>{routeStart}</strong></span>
          <span className="driver-route-line"><span /></span>
          <span className="driver-route-pin driver-route-pin--end"><i className="fas fa-flag-checkered" aria-hidden="true" /><small>{activeTrip ? 'Destination' : 'Next stop'}</small><strong>{routeEnd}</strong></span>
        </div>
      </section>

      <section className="driver-metric-strip" aria-label="Driver overview">
        <article className="driver-metric driver-metric--priority"><span className="driver-metric-icon"><i className={`fas ${activeTrip ? 'fa-route' : 'fa-tower-broadcast'}`} /></span><div><p>Current assignment</p><strong className="driver-metric-text">{activeTrip ? `${routeStart} → ${routeEnd}` : 'Ready for dispatch'}</strong><small>{activeTrip ? `${activeTrip.truck_number || 'Assigned truck'} · ${String(activeTrip.status).replaceAll('_', ' ')}` : driver.truck_number ? `Truck ${driver.truck_number} available` : 'Waiting for a transporter request'}</small></div></article>
        <article className="driver-metric"><span className="driver-metric-icon"><i className="fas fa-circle-check" /></span><div><p>Completed trips</p><strong>{driver.total_trips || 0}</strong><small>Verified deliveries</small></div></article>
        <article className="driver-metric driver-metric--rating"><span className="driver-metric-icon"><i className="fas fa-star" /></span><div><p>Trust score</p><strong>{hasRating ? ratingValue.toFixed(1) : '—'}</strong><small>{hasRating ? `${ratingCount} verified review${ratingCount === 1 ? '' : 's'}` : 'Awaiting first review'}</small></div></article>
        <article className={`driver-metric ${incidents.length ? 'driver-metric--danger' : 'driver-metric--safe'}`}><span className="driver-metric-icon"><i className={`fas ${incidents.length ? 'fa-triangle-exclamation' : 'fa-shield-halved'}`} /></span><div><p>Integrity record</p><strong>{incidents.length}</strong><small>{incidents.length ? 'Record needs review' : 'Clean record'}</small></div></article>
      </section>

      <div className="driver-dashboard-grid">
        <section className="driver-card driver-card--flush">
          <div className="driver-section-heading"><div><h2>Dispatch board</h2><p>Recent requests and assignments</p></div><Link to="/driver/trips" className="driver-text-link">View all <i className="fas fa-arrow-right" /></Link></div>
          {recent_trips.length === 0 ? (
            <div className="driver-empty-state"><span><i className="fas fa-route" /></span><div><h3>No trip requests yet</h3><p>Fleet owners can find you with driver ID <strong>{driver.unique_driver_id}</strong>.</p></div></div>
          ) : (
            <div className="driver-dispatch-list">
              {recent_trips.slice(0, 5).map((trip) => (
                <article className="driver-dispatch-row" key={trip.id}>
                  <span className="driver-dispatch-icon"><i className="fas fa-truck-moving" /></span>
                  <div className="driver-dispatch-main"><strong>{trip.truck_number} <span>{trip.truck_model}</span></strong><p>{trip.transporter_name}{trip.transporter_phone ? ` · ${trip.transporter_phone}` : ''}</p></div>
                  <div className="driver-dispatch-value"><strong>{formatMoney(trip.offer_amount || 0)}</strong><span className={statusClass(trip.status)}>{String(trip.status || 'pending').replaceAll('_', ' ')}</span></div>
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="driver-quick-panel">
          <div className="driver-section-heading"><div><h2>Quick access</h2><p>Common driver tasks</p></div></div>
          <Link to="/driver/fuel-logs"><span><i className="fas fa-gas-pump" /></span><div><strong>Record a refuel</strong><small>Save fuel, rate and mileage</small></div><i className="fas fa-chevron-right" /></Link>
          <Link to="/driver/wallet"><span><i className="fas fa-wallet" /></span><div><strong>Open wallet</strong><small>Balance, reserves and payouts</small></div><i className="fas fa-chevron-right" /></Link>
          <Link to="/driver/profile"><span><i className="fas fa-id-card" /></span><div><strong>Driver credential</strong><small>Review your driver details</small></div><i className="fas fa-chevron-right" /></Link>
        </aside>
      </div>
    </div>
  )
}
