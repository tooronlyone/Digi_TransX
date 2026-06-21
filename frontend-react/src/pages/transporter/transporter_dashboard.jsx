/* eslint-disable no-empty, react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'
import './Dashboard.css'

function statusBadge(status) {
  const map = {
    active: { label: 'Active', className: 'available' },
    available: { label: 'Available', className: 'available' },
    on_job: { label: 'On Job', className: 'on_job' },
    maintenance: { label: 'Maintenance', className: 'maintenance' },
    inactive: { label: 'Inactive', className: 'inactive' },
  }
  const s = map[status] || { label: status || 'Unknown', className: 'inactive' }
  return <span className={`dashboard-status-pill dashboard-status-pill--${s.className}`}>{s.label}</span>
}

export default function TransporterDashboard() {
  const { get } = useApi()

  const [stats, setStats] = useState({ total: 0, active: 0, available: 0, onJob: 0, maintenance: 0 })
  const [trucks, setTrucks] = useState([])
  const [jobs, setJobs] = useState([])
  const [bids, setBids] = useState([])
  const [loading, setLoading] = useState(true)
  const [user, setUser] = useState(null)

  useEffect(() => {
    const cached = sessionStorage.getItem('user')
    if (cached) { try { setUser(JSON.parse(cached)) } catch {} }

    Promise.allSettled([
      get('/api/trucks/stats'),
      get('/api/trucks'),
      get('/api/orders/available'),
      get('/api/orders/my-bids'),
    ]).then(([statsRes, trucksRes, jobsRes, bidsRes]) => {
      if (statsRes.status === 'fulfilled' && statsRes.value.success) {
        setStats(statsRes.value.stats)
      }
      if (trucksRes.status === 'fulfilled' && trucksRes.value.success) {
        setTrucks(trucksRes.value.trucks || [])
      }
      if (jobsRes.status === 'fulfilled' && jobsRes.value.success) {
        setJobs(jobsRes.value.orders || [])
      }
      if (bidsRes.status === 'fulfilled' && bidsRes.value.success) {
        setBids(bidsRes.value.bids || [])
      }
    }).finally(() => setLoading(false))
  }, [])

  const userName = user ? ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || user.username : ''
  const recentTrucks = trucks.slice(0, 4)
  const emptyValue = '\u2014'

  return (
    <TransporterLayout>
      <div className="dashboard-page-title">
        <h1>Transporter Dashboard</h1>
        <p>Welcome back{userName ? ', ' + userName : ''}! Manage your trucks, bids, and matching jobs here.</p>
      </div>

      <div className="dashboard-kpi-grid">
        <article className="dashboard-stat-card">
          <div className="dashboard-stat-card__header">
            <div>
              <div className="dashboard-card-value">{loading ? <i className="fas fa-spinner fa-spin"></i> : stats.total}</div>
              <div className="dashboard-card-title">My Trucks</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--trucks"><i className="fas fa-truck"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>{stats.available} available</span>
            <Link to="/transporter/trucks" className="dashboard-action-small">View All</Link>
          </div>
        </article>

        <article className="dashboard-stat-card">
          <div className="dashboard-stat-card__header">
            <div>
              <div className="dashboard-card-value">{loading ? <i className="fas fa-spinner fa-spin"></i> : jobs.length}</div>
              <div className="dashboard-card-title">Matching Jobs</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--available"><i className="fas fa-clipboard-list"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>{stats.onJob} on job</span>
            <Link to="/transporter/jobs" className="dashboard-action-small">Browse</Link>
          </div>
        </article>

        <article className="dashboard-stat-card">
          <div className="dashboard-stat-card__header">
            <div>
              <div className="dashboard-card-value">{loading ? <i className="fas fa-spinner fa-spin"></i> : bids.filter((bid) => bid.status === 'pending').length}</div>
              <div className="dashboard-card-title">Pending Bids</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--active"><i className="fas fa-gavel"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>{bids.filter((bid) => bid.status === 'accepted').length} accepted</span>
            <Link to="/transporter/bids" className="dashboard-action-small">Details</Link>
          </div>
        </article>

        <article className="dashboard-stat-card">
          <div className="dashboard-stat-card__header">
            <div>
              <div className="dashboard-card-value">{loading ? <i className="fas fa-spinner fa-spin"></i> : stats.maintenance}</div>
              <div className="dashboard-card-title">In Maintenance</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--maintenance"><i className="fas fa-tools"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>{stats.inactive || 0} inactive</span>
            <Link to="/transporter/trucks" className="dashboard-action-small">View</Link>
          </div>
        </article>
      </div>

      <section className="dashboard-section">
        <h2 className="dashboard-section-title">Quick Actions</h2>
        <div className="dashboard-actions-grid">
          <Link to="/transporter/trucks/add" className="dashboard-action-tile">
            <i className="fas fa-truck"></i>
            <span>Add New Truck</span>
            <div>Register a new vehicle</div>
          </Link>
          <Link to="/transporter/jobs" className="dashboard-action-tile">
            <i className="fas fa-clipboard-list"></i>
            <span>Find Jobs</span>
            <div>Browse available shipments</div>
          </Link>
          <Link to="/transporter/bids" className="dashboard-action-tile">
            <i className="fas fa-gavel"></i>
            <span>My Bids</span>
            <div>Track accepted and pending proposals</div>
          </Link>
          <Link to="/transporter/earnings" className="dashboard-action-tile">
            <i className="fas fa-wallet"></i>
            <span>Earnings</span>
            <div>View your earnings</div>
          </Link>
          <Link to="/transporter/trucks" className="dashboard-action-tile">
            <i className="fas fa-tools"></i>
            <span>Fleet Status</span>
            <div>Review available and maintenance trucks</div>
          </Link>
          <Link to="/transporter/help" className="dashboard-action-tile">
            <i className="fas fa-headset"></i>
            <span>24/7 Support</span>
            <div>Get help anytime</div>
          </Link>
        </div>
      </section>

      <section className="dashboard-section">
        <h2 className="dashboard-section-title">Recent Trucks</h2>
        {loading ? (
          <p className="dashboard-loading"><i className="fas fa-spinner fa-spin"></i> Loading trucks...</p>
        ) : recentTrucks.length === 0 ? (
          <div className="dashboard-empty-state">
            <i className="fas fa-truck"></i>
            <p>No trucks found. <Link to="/transporter/trucks/add">Add your first truck</Link></p>
          </div>
        ) : (
          <div className="dashboard-truck-grid">
            {recentTrucks.map(truck => (
              <article key={truck.id} className="dashboard-truck-card">
                <div className="dashboard-truck-card__top">
                  <div>
                    <strong>{truck.truck_number || truck.registration_number || emptyValue}</strong>
                    <p>{truck.truck_type || emptyValue} &middot; Driver: {truck.driver_name || emptyValue}</p>
                  </div>
                  {statusBadge(truck.status)}
                </div>
                <div className="dashboard-truck-card__meta">
                  <span><i className="fas fa-route"></i>{truck.location || 'Karachi Depot'}</span>
                  <Link to={`/transporter/trucks/${truck.id}`} className="dashboard-action-small">Track</Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </TransporterLayout>
  )
}
