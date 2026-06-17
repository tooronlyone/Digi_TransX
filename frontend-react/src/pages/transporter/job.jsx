import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'

function statusBadge(status) {
  const map = {
    available: { label: 'Available', color: '#22c55e' },
    open: { label: 'Open', color: '#3b82f6' },
    assigned: { label: 'Assigned', color: '#f59e0b' },
    pending: { label: 'Pending', color: '#8b5cf6' },
    applied: { label: 'Applied', color: '#06b6d4' },
    saved: { label: 'Saved', color: '#64748b' },
  }
  const s = map[(status || '').toLowerCase()] || { label: status || 'Unknown', color: '#94a3b8' }
  return (
    <span
      style={{
        background: s.color + '22',
        color: s.color,
        padding: '2px 10px',
        borderRadius: '20px',
        fontSize: '0.8rem',
        fontWeight: '600',
      }}
    >
      {s.label}
    </span>
  )
}

function formatFare(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) && number > 0 ? number.toLocaleString() : '-'
}

function JobCard({ job, onApply, onSave, onRespond, applying }) {
  const isMarketplaceRequest = job.source_type === 'marketplace_request' || job.source_type === 'canonical_dispatch'
  const actionKey = job.order_id || job.job_id || job.id
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '1.25rem',
        boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.75rem' }}>
        <div>
          <div style={{ fontWeight: '700', color: '#1e293b' }}>{job.job_id || job.order_id || `#${job.id}`}</div>
          <div style={{ color: '#64748b', fontSize: '0.85rem', marginTop: '0.2rem' }}>
            {job.title || job.job_type || (isMarketplaceRequest ? 'One-Time Shipment Request' : 'Shipment Job')}
          </div>
        </div>
        {statusBadge(job.status)}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '0.5rem',
          marginBottom: '0.75rem',
          fontSize: '0.85rem',
        }}
      >
        <div><i className="fas fa-map-marker-alt" style={{ color: '#3b82f6', width: '16px' }}></i> {job.pickup_location || '-'}</div>
        <div><i className="fas fa-flag" style={{ color: '#ef4444', width: '16px' }}></i> {job.drop_location || '-'}</div>
        <div><i className="fas fa-truck" style={{ color: '#f59e0b', width: '16px' }}></i> {job.truck_type || '-'}</div>
        <div><i className="fas fa-rupee-sign" style={{ color: '#22c55e', width: '16px' }}></i> Rs. {formatFare(job.total_fare || job.fare)}</div>
      </div>

      {isMarketplaceRequest && (
        <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '0.75rem' }}>
          Trucks: <strong>{job.truck_number || 'Selected bundle'}</strong>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem' }}>
        {isMarketplaceRequest ? (
          <>
            <button
              className="action-btn-small"
              style={{ flex: 1, background: '#16a34a', color: '#fff', border: 'none', cursor: 'pointer' }}
              onClick={() => onRespond(job, 'accept')}
              disabled={applying === actionKey}
            >
              {applying === actionKey ? <><i className="fas fa-spinner fa-spin"></i> Accepting...</> : <><i className="fas fa-check"></i> Accept</>}
            </button>
            <button
              className="action-btn-small"
              style={{ flex: 1, background: '#fee2e2', color: '#b91c1c', border: 'none', cursor: 'pointer' }}
              onClick={() => onRespond(job, 'reject')}
              disabled={applying === actionKey}
            >
              <i className="fas fa-times"></i> Reject
            </button>
          </>
        ) : (
          <>
            <button
              className="action-btn-small"
              style={{ flex: 1, background: '#3b82f6', color: '#fff', border: 'none', cursor: 'pointer' }}
              onClick={() => onApply(job)}
              disabled={applying === job.id}
            >
              {applying === job.id ? <><i className="fas fa-spinner fa-spin"></i> Applying...</> : <><i className="fas fa-check"></i> Apply</>}
            </button>
            <button
              className="action-btn-small"
              style={{ background: '#f1f5f9', color: '#64748b', border: 'none', cursor: 'pointer' }}
              onClick={() => onSave(job)}
              title="Save job"
            >
              <i className={`fas fa-bookmark${job.saved ? ' text-blue-500' : ''}`}></i>
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function normalizeMarketplaceRequest(order) {
  return {
    ...order,
    id: order.order_id,
    job_id: order.order_id,
    title: 'One-Time Shipment Request',
    source_type: 'marketplace_request',
    status: order.request_status || order.assignment_status || 'pending',
    truck_type: order.required_truck_type || order.truck_type,
    total_fare: order.bundle_total || order.total_fare,
  }
}

function normalizeCanonicalDispatch(order) {
  return {
    ...order,
    id: order.id || order.display_id,
    job_id: order.display_id,
    order_id: order.display_id,
    title: order.accept_mode === 'MANUAL' ? 'Manual Dispatch Window' : 'Auto Dispatch Request',
    source_type: 'canonical_dispatch',
    status: order.response_status || order.status || 'notified',
    truck_type: order.truck_type,
    total_fare: order.total_fare || order.max_price_limit || order.min_total_price,
  }
}

export default function Job() {
  const { get, post } = useApi()
  const [jobs, setJobs] = useState([])
  const [savedJobs, setSavedJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(null)
  const [appTab, setAppTab] = useState('all')
  const [search, setSearch] = useState('')
  const [jobType, setJobType] = useState('all')
  const [truckType, setTruckType] = useState('all')
  const [toast, setToast] = useState('')

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  function load() {
    setLoading(true)
    Promise.allSettled([get('/api/jobs'), get('/api/jobs/saved'), get('/api/client/marketplace/orders/pending'), get('/api/transporter/jobs/incoming')])
      .then(([jobsRes, savedRes, pendingRes, incomingRes]) => {
        const nextJobs = []
        if (jobsRes.status === 'fulfilled' && jobsRes.value.success) {
          nextJobs.push(...(jobsRes.value.jobs || []))
        }
        if (incomingRes.status === 'fulfilled' && incomingRes.value.success) {
          nextJobs.unshift(...((incomingRes.value.jobs || []).map(normalizeCanonicalDispatch)))
        }
        if (pendingRes.status === 'fulfilled' && pendingRes.value.success) {
          nextJobs.unshift(...((pendingRes.value.orders || []).map(normalizeMarketplaceRequest)))
        }
        setJobs(nextJobs)
        if (savedRes.status === 'fulfilled' && savedRes.value.success) {
          setSavedJobs(savedRes.value.savedJobs || [])
        }
      })
      .finally(() => setLoading(false))
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  const savedIds = useMemo(() => new Set(savedJobs.map(j => j.id)), [savedJobs])

  const filtered = useMemo(() => {
    return jobs.filter(j => {
      const q = search.toLowerCase()
      const matchSearch = !q ||
        (j.job_id || '').toLowerCase().includes(q) ||
        (j.order_id || '').toLowerCase().includes(q) ||
        (j.pickup_location || '').toLowerCase().includes(q) ||
        (j.drop_location || '').toLowerCase().includes(q) ||
        (j.title || '').toLowerCase().includes(q)
      const matchType = jobType === 'all' || (j.job_type || '').toLowerCase() === jobType
      const matchTruck = truckType === 'all' || (j.truck_type || '').toLowerCase() === truckType.toLowerCase()
      return matchSearch && matchType && matchTruck
    })
  }, [jobs, search, jobType, truckType])

  async function applyToJob(job) {
    setApplying(job.id)
    try {
      const csrf = sessionStorage.getItem('csrf_token') || ''
      const res = await fetch('/api/jobs/apply', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ job_id: job.id }),
      })
      const data = await res.json()
      if (data.success) {
        showToast('Application submitted!')
        load()
      } else {
        showToast(data.message || 'Failed to apply')
      }
    } catch {
      showToast('Network error')
    } finally {
      setApplying(null)
    }
  }

  async function respondToMarketplace(job, action) {
    const key = job.order_id || job.job_id || job.id
    setApplying(key)
    try {
      if (job.source_type === 'canonical_dispatch') {
        if (action === 'accept') {
          const data = await post(`/api/transporter/jobs/${encodeURIComponent(job.id || job.order_id)}/accept`, {})
          showToast(data.success ? 'Dispatch accepted.' : data.message || 'Failed to accept')
        } else {
          const data = await post(`/api/transporter/jobs/${encodeURIComponent(job.id || job.order_id)}/leave`, {})
          showToast(data.success ? 'Dispatch left.' : data.message || 'Failed to leave')
        }
        load()
        return
      }
      const data = await post(`/api/client/marketplace/orders/${encodeURIComponent(key)}/transporter-response`, { action })
      if (data.success) {
        showToast(action === 'accept' ? 'Request accepted. Trip moved to Active Jobs.' : 'Request rejected.')
        load()
      } else {
        showToast(data.message || 'Failed to update request')
      }
    } catch (error) {
      showToast(error.message || 'Network error')
    } finally {
      setApplying(null)
    }
  }

  async function saveJob(job) {
    try {
      const csrf = sessionStorage.getItem('csrf_token') || ''
      await fetch('/api/jobs/save', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ job_id: job.id }),
      })
      load()
      showToast('Job saved!')
    } catch {
      showToast('Failed to save')
    }
  }

  const displayJobs = appTab === 'saved' ? savedJobs : filtered

  return (
    <TransporterLayout>
      <div className="page-job">
        {toast && (
          <div
            style={{
              position: 'fixed',
              top: '1rem',
              right: '1rem',
              zIndex: 1000,
              background: '#1e293b',
              color: '#fff',
              padding: '0.75rem 1.25rem',
              borderRadius: '8px',
              fontSize: '0.9rem',
              boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            }}
          >
            {toast}
          </div>
        )}

        <div className="top-bar">
          <div className="page-title">
            <h1>Available Jobs</h1>
            <p>Browse and accept new shipment opportunities</p>
          </div>
        </div>

        <div className="jobs-header">
          <div>
            <h2>Available Shipments</h2>
            <p>Showing <strong>{filtered.length}</strong> jobs</p>
          </div>

          <div className="jobs-filter">
            <div className="search-bar">
              <input
                type="text"
                placeholder="Search jobs by route or ID..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              <i className="fas fa-search"></i>
            </div>

            <select className="filter-select" value={jobType} onChange={e => setJobType(e.target.value)}>
              <option value="all">All Job Types</option>
              <option value="full-truck">Full Truck Load</option>
              <option value="part-load">Part Load</option>
              <option value="express">Express Delivery</option>
            </select>

            <select className="filter-select" value={truckType} onChange={e => setTruckType(e.target.value)}>
              <option value="all">All Truck Types</option>
              <option value="Container Carrier">Container Carrier</option>
              <option value="Refrigerated Truck">Refrigerated Truck</option>
              <option value="Dumper Truck">Dumper Truck</option>
              <option value="Cargo Truck">Cargo Truck</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
            <i className="fas fa-spinner fa-spin" style={{ fontSize: '1.5rem' }}></i>
            <p>Loading available jobs...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
            <i className="fas fa-briefcase" style={{ fontSize: '3rem', display: 'block', marginBottom: '1rem' }}></i>
            <p>No jobs match your filters.</p>
            {(search || jobType !== 'all' || truckType !== 'all') && (
              <button
                onClick={() => { setSearch(''); setJobType('all'); setTruckType('all') }}
                style={{ marginTop: '0.5rem', color: '#3b82f6', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <div className="jobs-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {filtered.map(job => (
              <JobCard
                key={job.order_id || job.id}
                job={{ ...job, saved: savedIds.has(job.id) }}
                onApply={applyToJob}
                onSave={saveJob}
                onRespond={respondToMarketplace}
                applying={applying}
              />
            ))}
          </div>
        )}

        <div className="recent-jobs-table" style={{ marginTop: '2rem' }}>
          <div className="table-header">
            <h2 className="section-title">Job Applications</h2>
            <div className="table-actions">
              {['all', 'applied', 'saved'].map(t => (
                <button
                  key={t}
                  className={`filter-btn${appTab === t ? ' active' : ''}`}
                  onClick={() => setAppTab(t)}
                >
                  {t === 'all' ? 'All' : t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {appTab === 'saved' && (
            savedJobs.length === 0 ? (
              <p style={{ color: '#94a3b8', padding: '1rem' }}>No saved jobs yet.</p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem', padding: '1rem 0' }}>
                {savedJobs.map(job => (
                  <JobCard
                    key={job.id}
                    job={{ ...job, saved: true }}
                    onApply={applyToJob}
                    onSave={saveJob}
                    onRespond={respondToMarketplace}
                    applying={applying}
                  />
                ))}
              </div>
            )
          )}

          {appTab === 'all' && (
            <div className="table-responsive">
              <table>
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Route</th>
                    <th>Truck Type</th>
                    <th>Fare</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {displayJobs.slice(0, 20).map(job => {
                  const isMarketplaceRequest = job.source_type === 'marketplace_request' || job.source_type === 'canonical_dispatch'
                    const actionKey = job.order_id || job.job_id || job.id
                    return (
                      <tr key={actionKey}>
                        <td>{job.job_id || job.order_id || `#${job.id}`}</td>
                        <td>{job.pickup_location || '-'}{' to '}{job.drop_location || '-'}</td>
                        <td>{job.truck_type || '-'}</td>
                        <td>Rs. {formatFare(job.total_fare || job.fare)}</td>
                        <td>{statusBadge(job.status)}</td>
                        <td>
                          {isMarketplaceRequest ? (
                            <div style={{ display: 'flex', gap: '0.4rem' }}>
                              <button
                                className="action-btn-small"
                                style={{ background: '#16a34a', color: '#fff', border: 'none', cursor: 'pointer' }}
                                onClick={() => respondToMarketplace(job, 'accept')}
                                disabled={applying === actionKey}
                              >
                                {applying === actionKey ? 'Accepting...' : 'Accept'}
                              </button>
                              <button
                                className="action-btn-small"
                                style={{ background: '#fee2e2', color: '#b91c1c', border: 'none', cursor: 'pointer' }}
                                onClick={() => respondToMarketplace(job, 'reject')}
                                disabled={applying === actionKey}
                              >
                                Reject
                              </button>
                            </div>
                          ) : (
                            <button
                              className="action-btn-small"
                              style={{ background: '#3b82f6', color: '#fff', border: 'none', cursor: 'pointer' }}
                              onClick={() => applyToJob(job)}
                              disabled={applying === job.id}
                            >
                              {applying === job.id ? 'Applying...' : 'Apply'}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/transporter/about">About Us</Link>
            <Link to="/transporter/contact">Contact</Link>
            <Link to="/transporter/terms">Terms &amp; Conditions</Link>
            <Link to="/transporter/privacy">Privacy Policy</Link>
            <Link to="/transporter/help">Help Center</Link>
          </div>
        </div>
      </div>
    </TransporterLayout>
  )
}
