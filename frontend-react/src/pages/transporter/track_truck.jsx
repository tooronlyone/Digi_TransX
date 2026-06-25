import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AgreementTripMap from '../../components/AgreementTripMap'
import { StateMessage, apiGet, formatDateTime } from '../client/clientUtils'

function statusColor(status) {
  const colors = {
    active: '#22c55e',
    available: '#22c55e',
    on_job: '#3b82f6',
    maintenance: '#f59e0b',
    inactive: '#94a3b8',
  }
  return colors[(status || '').toLowerCase()] || '#94a3b8'
}

function truckFromAgreementTrip(agreements, trip) {
  if (!trip) return null
  for (const agreement of agreements) {
    const truck = (agreement.trucks || []).find((item) => Number(item.truck_id) === Number(trip.truck_id))
    if (truck) return truck
  }
  return null
}

export default function TrackTruck() {
  const { id } = useParams()
  const [truck, setTruck] = useState(null)
  const [agreements, setAgreements] = useState([])
  const [activeTrip, setActiveTrip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  async function loadTruck() {
    if (!id) {
      setTruck(null)
      return
    }
    const json = await apiGet(`/api/trucks/${id}`)
    setTruck(json.truck || json)
  }

  async function loadTrips({ initial = false } = {}) {
    if (initial) setLoading(true)
    else setRefreshing(true)
    setError('')

    try {
      const agreementsJson = await apiGet('/api/agreements/my')
      const nextAgreements = agreementsJson.agreements || []
      const tripEntries = await Promise.all(nextAgreements.map(async (agreement) => {
        try {
          const tripJson = await apiGet(`/api/agreements/${agreement.id}/trips`)
          return tripJson.trips || []
        } catch (_) {
          return []
        }
      }))
      const inProgressTrips = tripEntries.flat().filter((trip) => trip.status === 'in_progress')
      const matchedTrip = id
        ? inProgressTrips.find((trip) => Number(trip.truck_id) === Number(id))
        : inProgressTrips[0]

      setAgreements(nextAgreements)
      setActiveTrip(matchedTrip || null)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load tracking data.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadInitialData() {
      setLoading(true)
      try {
        await Promise.all([loadTruck(), loadTrips({ initial: true })])
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || 'Unable to load tracking data.')
          setLoading(false)
        }
      }
    }

    loadInitialData()
    const intervalId = window.setInterval(() => {
      if (!cancelled) loadTrips()
    }, 30000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [id])

  const agreementTruck = useMemo(() => truckFromAgreementTrip(agreements, activeTrip), [agreements, activeTrip])
  const displayTruck = truck || agreementTruck || {}
  const currentStatus = displayTruck.status || (activeTrip ? 'on_job' : 'inactive')
  const color = statusColor(currentStatus)
  const truckNumber = displayTruck.truck_number || activeTrip?.truck_number || 'No truck selected'
  const truckType = displayTruck.truck_type || displayTruck.truck_type_name || '-'

  return (
    <div className="page-track-truck">
      <main className="page">
        <section className="hero">
          <div>
            <h2>{truckNumber} - Truck Tracking</h2>
            <p>{truckType}</p>
          </div>
          <div className="hero-actions">
            <button className="btn" type="button" onClick={() => loadTrips()} disabled={refreshing || loading}>
              <i className={`fas fa-rotate-right${refreshing || loading ? ' fa-spin' : ''}`}></i> Refresh
            </button>
            {id && (
              <>
                <Link className="btn-secondary" to={`/transporter/trucks/${id}`}>
                  <i className="fas fa-circle-info"></i> Truck Details
                </Link>
                <Link className="btn-secondary" to={`/transporter/trucks/${id}/service`}>
                  <i className="fas fa-wrench"></i> Service History
                </Link>
              </>
            )}
          </div>
        </section>

        {loading ? (
          <StateMessage type="loading">Loading tracking data...</StateMessage>
        ) : error ? (
          <StateMessage type="error">{error}</StateMessage>
        ) : (
          <>
            <section className="cards">
              <div className="card">
                <div className="metric-label">Truck Status</div>
                <div className="metric-value">
                  <span
                    style={{
                      background: `${color}22`,
                      color,
                      padding: '3px 12px',
                      borderRadius: 20,
                      fontSize: 14,
                      fontWeight: 600,
                      textTransform: 'capitalize',
                    }}
                  >
                    {currentStatus.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="metric-note">Current truck operational status.</div>
              </div>
              <div className="card">
                <div className="metric-label">Truck Number</div>
                <div className="metric-value">{truckNumber}</div>
                <div className="metric-note">Registered fleet identity.</div>
              </div>
              <div className="card">
                <div className="metric-label">Truck Type</div>
                <div className="metric-value">{truckType}</div>
                <div className="metric-note">Configured vehicle category.</div>
              </div>
              <div className="card">
                <div className="metric-label">Active Trip</div>
                <div className="metric-value">{activeTrip ? `#${activeTrip.id}` : '-'}</div>
                <div className="metric-note">{activeTrip?.started_at ? `Started ${formatDateTime(activeTrip.started_at)}` : 'No active trip found.'}</div>
              </div>
            </section>

            {activeTrip ? (
              <section className="section">
                <h3>Live GPS Location</h3>
                <AgreementTripMap tripId={activeTrip.id} isActive={true} />
                <div className="route-meta" style={{ marginTop: 12 }}>
                  <strong>Trip:</strong> {activeTrip.pickup_description || '-'} {' '}
                  <strong>Status:</strong> {activeTrip.status.replace(/_/g, ' ')}
                </div>
              </section>
            ) : (
              <section className="section truck-empty-section">
                <i className="fas fa-location-dot truck-empty-icon"></i>
                <h3>No active trip</h3>
                <p className="empty-copy">This truck does not currently have an in-progress agreement trip.</p>
                <Link to="/transporter/my-agreements" className="action-btn" style={{ marginTop: 16 }}>
                  Open My Agreements
                </Link>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  )
}
