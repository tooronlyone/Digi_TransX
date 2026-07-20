/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { hasTruckPhoto, truckPhotoBackgroundStyle } from '../../lib/truckPhotos'
import '../../styles/pages/my-trucks.css'

function statusBadge(status) {
  const map = {
    active: { label: 'Active', className: 'available' },
    available: { label: 'Available', className: 'available' },
    on_job: { label: 'On Job', className: 'on_job' },
    maintenance: { label: 'Maintenance', className: 'maintenance' },
    inactive: { label: 'Inactive', className: 'inactive' },
  }
  const s = map[status] || { label: status || 'Unknown', className: 'inactive' }
  return <span className={`mytrucks-status-pill mytrucks-status-pill--${s.className}`}>{s.label}</span>
}

export default function MyTruck() {
  const { get } = useApi()

  const [trucks, setTrucks] = useState([])
  const [stats, setStats] = useState({ available: 0, onJob: 0, maintenance: 0, total: 0 })
  const [loading, setLoading] = useState(true)
  const [truckFilter, setTruckFilter] = useState('all')

  function load() {
    setLoading(true)
    Promise.allSettled([get('/api/trucks?page_size=200'), get('/api/trucks/stats')])
      .then(([trucksRes, statsRes]) => {
        if (trucksRes.status === 'fulfilled' && trucksRes.value.success) {
          setTrucks(trucksRes.value.trucks || [])
        }
        if (statsRes.status === 'fulfilled' && statsRes.value.success) {
          setStats(statsRes.value.stats)
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    if (truckFilter === 'all') return trucks
    if (truckFilter === 'active') {
      return trucks.filter(t => t.status === 'active' || t.status === 'available' || t.status === 'on_job')
    }
    if (truckFilter === 'maintenance') {
      return trucks.filter(t => t.status === 'maintenance')
    }
    return trucks
  }, [trucks, truckFilter])

  const emptyValue = '\u2014'
  void stats

  return (
      <div className="page-my-truck">
        <div className="mytrucks-page-title">
          <h1>My Trucks</h1>
          <p>Manage your fleet, monitor status, and add new vehicles.</p>
        </div>

        <div className="mytrucks-table-header">
          <h2 className="mytrucks-section-title">Fleet ({filtered.length})</h2>
          <div className="mytrucks-header-actions">
            {[
              { value: 'all', label: 'All' },
              { value: 'active', label: 'Active' },
              { value: 'maintenance', label: 'Maintenance' },
            ].map(filter => (
              <button
                key={filter.value}
                type="button"
                className={`mytrucks-filter-pill${truckFilter === filter.value ? ' is-active' : ''}`}
                onClick={() => setTruckFilter(filter.value)}
              >
                {filter.label}
              </button>
            ))}
            <Link to="/transporter/trucks/add" className="mytrucks-primary-btn">
              <i className="fas fa-plus"></i>
              Add Truck
            </Link>
          </div>
        </div>

        {loading ? (
          <div className="mytrucks-loading">
            <i className="fas fa-spinner fa-spin"></i>
            <p>Loading your fleet...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="mytrucks-empty-state">
            <i className="fas fa-truck"></i>
            <p>No trucks found.</p>
            <Link to="/transporter/trucks/add">Add your first truck</Link>
          </div>
        ) : (
          <div className="mytrucks-grid">
            {filtered.map(truck => (
              <article
                key={truck.id}
                className={`mytrucks-card${hasTruckPhoto(truck) ? ' mytrucks-card--has-photo' : ''}`}
                style={truckPhotoBackgroundStyle(truck)}
              >
                <div className="mytrucks-card-top">
                  <div>
                    <strong>{truck.truck_number || truck.registration_number || emptyValue}</strong>
                    <p>{truck.truck_type || emptyValue} &middot; Driver: {truck.driver_name || emptyValue}</p>
                  </div>
                  {statusBadge(truck.status)}
                </div>

                <div className="mytrucks-stats-grid">
                  <div>
                    <span>Capacity</span>
                    <b>{truck.capacity_tons ? `${truck.capacity_tons} tons` : emptyValue}</b>
                  </div>
                </div>

                <div className="mytrucks-card-meta">
                  {/* TODO before deployment: implement real GPS location via tracking API */}
                  <span><i className="fas fa-route"></i>{truck.location || '—'}</span>
                  <div>
                    <Link to={`/transporter/trucks/edit/${truck.id}`} className="mytrucks-ghost-btn">Edit</Link>
                    {truck.status === 'active' || truck.status === 'available' || truck.status === 'on_job' ? (
                      <Link to={`/transporter/trucks/${truck.id}`} className="mytrucks-action-small">
                        Track
                      </Link>
                    ) : (
                      <Link to={`/transporter/trucks/config/${truck.id}`} className="mytrucks-action-small mytrucks-activate-btn">
                        Activate
                      </Link>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    
  )
}
