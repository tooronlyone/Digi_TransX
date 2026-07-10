/* eslint-disable no-empty, react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import '../../styles/global.css'
import '../../styles/pages/transporter-dashboard.css'

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

function formatWalletBalance(value) {
  const amount = Number(value || 0)
  return amount.toLocaleString('en-PK', {
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
    minimumFractionDigits: 0,
  })
}

export default function TransporterDashboard() {
  const { get } = useApi()

  const [stats, setStats] = useState({ total: 0, active: 0, available: 0, onJob: 0, maintenance: 0 })
  const [trucks, setTrucks] = useState([])
  const [jobs, setJobs] = useState([])
  const [bids, setBids] = useState([])
  const [wallet, setWallet] = useState(null)
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
      get('/api/wallet'),
    ]).then(([statsRes, trucksRes, jobsRes, bidsRes, walletRes]) => {
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
      if (walletRes.status === 'fulfilled' && walletRes.value.success) {
        setWallet(walletRes.value.wallet || null)
      }
    }).finally(() => setLoading(false))
  }, [])

  const userName = user ? ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || user.username : ''
  const recentTrucks = trucks.slice(0, 4)
  const emptyValue = '\u2014'

  return (
    <>
      <div className="dashboard-page-title">
        <h1>Transporter Dashboard</h1>
        <p>Welcome back{userName ? ', ' + userName : ''}! Manage your trucks, bids, and available bids here.</p>
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
              <div className="dashboard-card-value">{loading ? <i className="fas fa-spinner fa-spin"></i> : 0}</div>
              <div className="dashboard-card-title">Messages</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--available"><i className="fas fa-comments"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>0 unread</span>
            <Link to="/transporter/messages" className="dashboard-action-small">Open</Link>
          </div>
        </article>

        <article className="dashboard-stat-card">
          <div className="dashboard-stat-card__header">
            <div>
              <div className="dashboard-card-value dashboard-card-value--money">
                {loading ? (
                  <i className="fas fa-spinner fa-spin"></i>
                ) : (
                  <>
                    <span className="dashboard-money-prefix">Rs</span>
                    <span className="dashboard-money-amount">{formatWalletBalance(wallet?.available_balance ?? wallet?.balance ?? 0)}</span>
                  </>
                )}
              </div>
              <div className="dashboard-card-title">Wallet</div>
            </div>
            <div className="dashboard-card-icon dashboard-card-icon--active"><i className="fas fa-wallet"></i></div>
          </div>
          <div className="dashboard-card-footer">
            <span>Available balance</span>
            <Link to="/transporter/wallet" className="dashboard-action-small">Open</Link>
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
          <Link to="/transporter/available-bids" className="dashboard-action-tile">
            <i className="fas fa-clipboard-list"></i>
            <span>Available Bids</span>
            <div>Browse available bids</div>
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
    </>
  )
}
