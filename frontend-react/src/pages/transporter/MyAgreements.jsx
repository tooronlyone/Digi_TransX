import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AgreementTripMap from '../../components/AgreementTripMap'
import { hasTruckPhoto, truckPhotoBackgroundStyle } from '../../lib/truckPhotos'
import { PrimaryButton, SecondaryButton, StateMessage, StatusBadge, apiGet, apiSend, formatMoney, formatNumber } from '../client/clientUtils'
import '../../styles/pages/my-agreements.css'

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Browser geolocation is not available.'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position.coords),
      () => reject(new Error('Unable to read GPS coordinates.')),
      { enableHighAccuracy: true, timeout: 15000 },
    )
  })
}

export default function MyAgreements() {
  const [agreements, setAgreements] = useState([])
  const [trips, setTrips] = useState({})
  const [descriptions, setDescriptions] = useState({})
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const json = await apiGet('/api/agreements/my')
      setAgreements(json.agreements || [])
      const tripEntries = await Promise.all((json.agreements || []).map(async (agreement) => {
        try {
          const tripJson = await apiGet(`/api/agreements/${agreement.id}/trips`)
          return [agreement.id, tripJson.trips || []]
        } catch (_) {
          return [agreement.id, []]
        }
      }))
      setTrips(Object.fromEntries(tripEntries))
    } catch (loadError) {
      setError(loadError.message || 'Unable to load agreements.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const activeTripByTruck = useMemo(() => {
    const map = {}
    Object.values(trips).flat().forEach((trip) => {
      if (trip.status === 'in_progress') map[`${trip.agreement_id}:${trip.truck_id}`] = trip
    })
    return map
  }, [trips])

  async function startTrip(agreement, truck) {
    const key = `${agreement.id}:${truck.truck_id}`
    const pickup_description = (descriptions[key] || '').trim()
    if (!pickup_description) {
      setError('Trip description is required.')
      return
    }
    setWorking(`start:${key}`)
    setError('')
    setNotice('')
    try {
      const coords = await getPosition()
      await apiSend(`/api/agreements/${agreement.id}/trips`, {
        truck_id: truck.truck_id,
        pickup_description,
        gps_start_lat: coords.latitude,
        gps_start_lng: coords.longitude,
      })
      setNotice(`${truck.truck_number} - TRIP IN PROGRESS: ${pickup_description}. Tap End Trip when truck returns to base.`)
      await loadData()
    } catch (startError) {
      setError(startError.message || 'Unable to start trip.')
    } finally {
      setWorking('')
    }
  }

  async function endTrip(agreement, truck, trip) {
    const key = `${agreement.id}:${truck.truck_id}`
    setWorking(`end:${key}`)
    setError('')
    setNotice('')
    try {
      const coords = await getPosition()
      const json = await apiSend(`/api/agreements/${agreement.id}/trips/${trip.id}/end`, {
        gps_end_lat: coords.latitude,
        gps_end_lng: coords.longitude,
      }, 'PUT')
      const earned = Number(json.distance_km || 0) * Number(truck.per_km_rate || 0)
      const src = json.distance_source ? ` (${json.distance_source})` : ''
      setNotice(`Trip complete! Distance: ${formatNumber(json.distance_km)} km${src} | Earned: ${formatMoney(earned)}`)
      await loadData()
    } catch (endError) {
      setError(endError.message || 'Unable to end trip.')
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="myagreements-page">
      <div className="myagreements-page-title">
        <div>
          <h1>My Agreements</h1>
          <p>Manage trips and monthly earnings for assigned agreement trucks.</p>
        </div>
        <Link to="/transporter/agreement-bids" className="myagreements-primary-btn">
          <i className="fas fa-file-signature" aria-hidden="true"></i>
            Agreement Bids
        </Link>
      </div>

      {loading && <StateMessage type="loading">Loading agreements...</StateMessage>}
      {error && <StateMessage type="error">{error}</StateMessage>}
      {notice && <StateMessage type="success">{notice}</StateMessage>}
      {!loading && !error && agreements.length === 0 && (
        <div className="myagreements-empty-state">
          <i className="fas fa-file-contract" aria-hidden="true"></i>
          <p>No active transporter agreements yet.</p>
          <Link to="/transporter/agreement-bids">Browse Agreement Bids</Link>
        </div>
      )}

      <div className="myagreements-grid">
        {agreements.map((agreement) => (
          <article key={agreement.id} className="myagreements-card">
            <div className="myagreements-card-header">
              <div>
                <h2>Agreement #{agreement.id} with {agreement.client_name}</h2>
                <p>{agreement.cargo_type} | {agreement.duration_months} months</p>
              </div>
              <StatusBadge status={agreement.status} />
            </div>
            <div className="myagreements-summary">
              This month: {formatNumber(agreement.current_month_km)} km | Projected payment {formatMoney(agreement.current_month_earnings)}
            </div>
            <div className="myagreements-truck-list">
              {(agreement.trucks || []).map((truck) => {
                const key = `${agreement.id}:${truck.truck_id}`
                const activeTrip = activeTripByTruck[key]
                return (
                  <div
                    key={truck.id}
                    className={`myagreements-truck-card${hasTruckPhoto(truck) ? ' myagreements-truck-card--has-photo' : ''}`}
                    style={truckPhotoBackgroundStyle(truck)}
                  >
                    {activeTrip && (
                      <div className="myagreements-trip-alert">
                        {truck.truck_number} - TRIP IN PROGRESS: {activeTrip.pickup_description}
                      </div>
                    )}
                    {activeTrip && (
                      <div className="myagreements-map-wrap">
                        <AgreementTripMap tripId={activeTrip.id} isActive={true} />
                      </div>
                    )}
                    <div className="myagreements-truck-row">
                      <div className="myagreements-truck-info">
                        <div>{truck.truck_number} - {truck.truck_type_name}</div>
                        <div>{formatMoney(truck.per_km_rate)} per km | Minimum {formatMoney(truck.minimum_monthly_guarantee)}</div>
                      </div>
                      {!activeTrip ? (
                        <div className="myagreements-trip-actions">
                          <input className="myagreements-trip-input" placeholder="Trip description" value={descriptions[key] || ''} onChange={(event) => setDescriptions((current) => ({ ...current, [key]: event.target.value }))} />
                          <PrimaryButton type="button" className="myagreements-action-btn" onClick={() => startTrip(agreement, truck)} disabled={working === `start:${key}`}>
                            <i className={`fas ${working === `start:${key}` ? 'fa-spinner fa-spin' : 'fa-play'}`} aria-hidden="true"></i>
                            Trip Start
                          </PrimaryButton>
                        </div>
                      ) : (
                        <SecondaryButton type="button" className="myagreements-action-btn" onClick={() => endTrip(agreement, truck, activeTrip)} disabled={working === `end:${key}`}>
                          <i className={`fas ${working === `end:${key}` ? 'fa-spinner fa-spin' : 'fa-stop'}`} aria-hidden="true"></i>
                          End Trip
                        </SecondaryButton>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
