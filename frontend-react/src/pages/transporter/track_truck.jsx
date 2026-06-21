import { useEffect, useState } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

export default function TrackTruck() {
  const { id } = useParams()
  const api = useApi()
  const [truck, setTruck] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  function showToast(message) {
    setToast(message)
    setTimeout(() => setToast(null), 2500)
  }

  function load() {
    setLoading(true)

    const truckReq = id ? api.get(`/api/trucks/${id}`) : Promise.resolve(null)
    const jobsReq = api.get('/api/jobs/active')

    Promise.allSettled([truckReq, jobsReq]).then(([truckRes, jobsRes]) => {
      let currentTruck = null

      if (truckRes.status === 'fulfilled' && truckRes.value) {
        currentTruck = truckRes.value.truck || truckRes.value
        setTruck(currentTruck)
      }

      if (jobsRes.status === 'fulfilled') {
        const jobs = jobsRes.value.jobs || jobsRes.value.active_jobs || []
        const job = id
          ? jobs.find((item) => item.truck_id === id || item.truck === currentTruck?.truck_number)
          : jobs[0]
        setActiveJob(job || null)
      }
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [id])

  function refresh() {
    load()
    showToast('Tracking data refreshed')
  }

  const truckStatus = truck?.status || 'inactive'
  const statusColor = {
    active: '#22c55e',
    available: '#22c55e',
    on_job: '#3b82f6',
    maintenance: '#f59e0b',
    inactive: '#94a3b8',
  }
  const color = statusColor[truckStatus.toLowerCase()] || '#94a3b8'

  const progress = activeJob ? activeJob.progress || 0 : 0
  const checkpoints = activeJob?.checkpoints || []

  return (
    <TransporterLayout>
      <div className="page-track-truck">
        <main className="page">
          <section className="hero">
            <div>
              <h2>{id && truck ? `${truck.truck_number} - ` : ''}Truck Tracking</h2>
              <p>{truck?.truck_type || ''} - {truck?.current_location || 'Location not available'}</p>
            </div>
            <div className="hero-actions">
              <button className="btn" type="button" onClick={refresh} disabled={loading}>
                <i className={`fas fa-rotate-right${loading ? ' fa-spin' : ''}`}></i> Refresh
              </button>
              {activeJob && (
                <Link className="btn-secondary" to="/transporter/bids">
                  <i className="fas fa-briefcase"></i> Open Active Job
                </Link>
              )}
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
            <div className="truck-state-card">
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 28 }}></i>
              <p style={{ marginTop: 12, color: 'var(--text-secondary)' }}>Loading tracking data...</p>
            </div>
          ) : (
            <>
              <section className="cards">
                <div className="card">
                  <div className="metric-label">Live Status</div>
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
                      {truckStatus.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="metric-note">Derived from current active assignment.</div>
                </div>
                <div className="card">
                  <div className="metric-label">Current Location</div>
                  <div className="metric-value">{truck?.current_location || '-'}</div>
                  <div className="metric-note">Latest synced position.</div>
                </div>
                <div className="card">
                  <div className="metric-label">Trip Progress</div>
                  <div className="metric-value">{progress}%</div>
                  <div className="progress-shell">
                    <div className="progress-fill" style={{ width: `${progress}%`, background: color }}></div>
                  </div>
                  <div className="metric-note">{activeJob ? `Job #${activeJob.id}` : 'No active job'}</div>
                </div>
                <div className="card">
                  <div className="metric-label">Last Updated</div>
                  <div className="metric-value">{truck?.updated_at ? new Date(truck.updated_at).toLocaleString() : '-'}</div>
                  <div className="metric-note">Last time this truck record changed.</div>
                </div>
              </section>

              {activeJob ? (
                <section className="section-grid">
                  <section className="section">
                    <h3>Route Summary</h3>
                    <div className="route-stack">
                      <div className="route-node">
                        <div className="route-dot route-dot-start"></div>
                        <div>
                          <div className="route-label">Pickup</div>
                          <div className="route-value">{activeJob.pickup_location || '-'}</div>
                        </div>
                      </div>
                      <div className="route-divider">
                        {activeJob.distance ? `${activeJob.distance} km` : 'Distance TBD'}
                      </div>
                      <div className="route-node">
                        <div className="route-dot route-dot-end"></div>
                        <div>
                          <div className="route-label">Destination</div>
                          <div className="route-value">{activeJob.drop_location || '-'}</div>
                        </div>
                      </div>
                      <div className="route-meta">
                        <strong>Cargo:</strong> {activeJob.cargo_type || activeJob.cargo || '-'} {' '}
                        <strong>Fare:</strong> PKR {parseFloat(activeJob.total_fare || activeJob.fare || 0).toLocaleString()}
                      </div>
                    </div>
                  </section>

                  <section className="section">
                    <h3>Checkpoint Timeline</h3>
                    <div className="timeline">
                      {checkpoints.length === 0 ? (
                        <p className="empty-copy">No checkpoints recorded yet.</p>
                      ) : checkpoints.map((checkpoint, index) => (
                        <div key={index} className="timeline-item">
                          <div className="timeline-dot"></div>
                          <div>
                            <div className="timeline-title">{checkpoint.label || checkpoint.location}</div>
                            <div className="timeline-copy">{checkpoint.time || checkpoint.timestamp}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                </section>
              ) : (
                <section className="section truck-empty-section">
                  <i className="fas fa-location-dot truck-empty-icon"></i>
                  <h3>No Active Trip</h3>
                  <p className="empty-copy">This truck is not currently assigned to any job.</p>
                  <Link to="/transporter/jobs" className="action-btn" style={{ marginTop: 16 }}>
                    Browse Available Jobs
                  </Link>
                </section>
              )}
            </>
          )}
        </main>

        {toast && <div className="truck-toast">{toast}</div>}
      </div>
    </TransporterLayout>
  )
}
