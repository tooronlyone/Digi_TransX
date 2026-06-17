/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'

function getStatusMeta(status) {
  const normalized = (status || '').toLowerCase()
  if (['pickup_pending', 'assigned', 'pending', 'awaiting_pickup'].includes(normalized)) {
    return { label: 'Awaiting Pickup', className: 'pickup' }
  }
  if (['completed', 'delivered'].includes(normalized)) {
    return { label: 'Delivered', className: 'delivered' }
  }
  return { label: 'In Transit', className: 'transit' }
}

function statusBadge(status) {
  const meta = getStatusMeta(status)
  return (
    <span className={`job-status-pill job-status-pill--${meta.className}`}>
      {meta.className === 'transit' && <span className="job-status-dot" />}
      {meta.label}
    </span>
  )
}

function sourceBadge(job) {
  // TODO: backend should send a canonical job_type/source field for one-time orders vs agreement shipments.
  const raw = (job.job_type || job.source || job.flow_type || job.order_type || '').toLowerCase()
  const isAgreement = raw.includes('agreement') || raw.includes('contract')
  return (
    <span className={`job-source-badge job-source-badge--${isAgreement ? 'agreement' : 'one-time'}`}>
      {isAgreement ? 'AGREEMENT' : 'ONE-TIME'}
    </span>
  )
}

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount) || amount <= 0) return 'PKR \u2014'
  return `PKR ${amount.toLocaleString()}`
}

function cargoLabel(job) {
  const weight = job.cargo_weight || job.weight || job.load_weight || ''
  const cargo = job.cargo_type || job.goods_type || job.material || job.description || 'Cargo'
  return weight ? `${weight} ${cargo}` : cargo
}

export default function ActiveJob() {
  const { get } = useApi()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    get('/api/jobs/active')
      .then(data => {
        if (data.success) setJobs(data.jobs || data.active_jobs || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <TransporterLayout>
      <div className="page-active-jobs">
        <div className="job-page-title">
          <h1>Active Jobs</h1>
          <p>Live shipments in transit. Tap a job to view route, driver, and shipper.</p>
        </div>

        <section className="job-section">
          <h2 className="job-section-title">In progress ({jobs.length})</h2>

          {loading ? (
            <div className="job-loading">
              <i className="fas fa-spinner fa-spin"></i>
              <p>Loading active jobs...</p>
            </div>
          ) : jobs.length === 0 ? (
            <div className="job-empty-state">
              <i className="fas fa-shipping-fast"></i>
              <p>No active jobs right now. Browse <Link to="/transporter/jobs">available jobs</Link>.</p>
            </div>
          ) : (
            <div className="job-list">
              {jobs.map(job => {
                const origin = job.pickup_location || job.origin || job.from_location || '\u2014'
                const destination = job.drop_location || job.destination || job.to_location || '\u2014'
                const pickupMeta = job.pickup_time || job.picked_up_at || job.pickup_date
                  ? `Picked up · ${job.pickup_time || job.picked_up_at || job.pickup_date}`
                  : 'Pickup in progress'
                const eta = job.eta || job.estimated_delivery || job.delivery_eta || job.delivery_date || 'ETA pending'

                return (
                  <article key={job.id || job.job_id} className="job-card">
                    <div className="job-route">
                      <div className="job-pin-column">
                        <i className="fas fa-circle job-origin-pin"></i>
                        <span className="job-route-line"></span>
                        <i className="fas fa-map-marker-alt job-destination-pin"></i>
                      </div>

                      <div className="job-route-copy">
                        {sourceBadge(job)}
                        <span className="job-id">{job.job_id || `#${job.id}`}</span>
                        <b>{origin}</b>
                        <span>{pickupMeta}</span>
                        <div className="job-route-spacer" />
                        <b>{destination}</b>
                        <span>{eta}</span>
                      </div>
                    </div>

                    <div className="job-meta-grid">
                      <div>
                        <span>Cargo</span>
                        <b>{cargoLabel(job)}</b>
                      </div>
                      <div>
                        <span>Truck</span>
                        <b>{job.truck_number || job.registration_number || job.truck_type || '\u2014'}</b>
                      </div>
                      <div>
                        <span>Driver</span>
                        <b>{job.driver_name || job.driver || '\u2014'}</b>
                      </div>
                      <div>
                        <span>Earnings</span>
                        <b className="job-earnings">{formatMoney(job.total_fare || job.fare || job.amount)}</b>
                      </div>
                    </div>

                    <div className="job-actions">
                      {statusBadge(job.status)}
                      <Link to={`/transporter/jobs/${job.id}/track`} className="job-action-small">Track Live</Link>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </TransporterLayout>
  )
}
