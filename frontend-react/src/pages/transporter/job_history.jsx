import { useState, useEffect, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const FILTERS = ['all', 'completed', 'cancelled', 'disputed', 'thisMonth']

export default function JobHistory() {
  const api = useApi()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('table')
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [rateModal, setRateModal] = useState(null)
  const [rating, setRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [review, setReview] = useState('')
  const [submittingRating, setSubmittingRating] = useState(false)
  const [ratingMsg, setRatingMsg] = useState('')
  const [toast, setToast] = useState(null)

  useEffect(() => {
    setLoading(true)
    api.get('/api/jobs/history')
      .then(d => setJobs(d.jobs || []))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false))
  }, [])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const now = new Date()
  const cm = now.getMonth(), cy = now.getFullYear()

  const filtered = useMemo(() => {
    let list = jobs
    if (filter === 'completed') list = list.filter(j => j.status === 'completed')
    else if (filter === 'cancelled') list = list.filter(j => j.status === 'cancelled')
    else if (filter === 'disputed') list = list.filter(j => j.status === 'disputed')
    else if (filter === 'thisMonth') list = list.filter(j => {
      const d = new Date(j.date || j.created_at)
      return d.getMonth() === cm && d.getFullYear() === cy
    })
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(j =>
        (j.id && String(j.id).includes(q)) ||
        (j.route && j.route.toLowerCase().includes(q)) ||
        (j.client && j.client.toLowerCase().includes(q)) ||
        (j.truck && j.truck.toLowerCase().includes(q))
      )
    }
    return list
  }, [jobs, filter, search, cm, cy])

  const stats = useMemo(() => {
    const completed = jobs.filter(j => j.status === 'completed')
    const earnings = completed.reduce((s, j) => s + parseFloat(j.earnings || j.amount || 0), 0)
    const distance = completed.reduce((s, j) => s + parseFloat(j.distance || 0), 0)
    const ratings = completed.filter(j => j.rating).map(j => parseFloat(j.rating))
    const avgRating = ratings.length ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1) : '-'
    return { count: completed.length, earnings, distance, avgRating }
  }, [jobs])

  async function submitRating() {
    if (!rating) { setRatingMsg('Please select a star rating'); return }
    setSubmittingRating(true)
    try {
      await api.post(`/api/jobs/${rateModal.id}/rate`, { rating, review })
      setRatingMsg('Rating submitted successfully!')
      setTimeout(() => {
        setRateModal(null)
        setRating(0)
        setReview('')
        setRatingMsg('')
      }, 1500)
      setJobs(prev => prev.map(j => j.id === rateModal.id ? { ...j, client_rated: true } : j))
    } catch (err) {
      setRatingMsg(err.message || 'Failed to submit rating')
    } finally {
      setSubmittingRating(false)
    }
  }

  function statusBadge(status) {
    const colors = { completed: '#27ae60', cancelled: '#e74c3c', disputed: '#f39c12', active: '#3498db', pending: '#95a5a6' }
    return (
      <span style={{
        background: colors[status] || '#95a5a6', color: '#fff',
        padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
        textTransform: 'capitalize',
      }}>{status || 'unknown'}</span>
    )
  }

  return (
    <TransporterLayout>
      <div className="page-job-history">
        <div className="top-bar">
          <div className="page-title">
            <h1>Job History</h1>
            <p>View all your past and completed transportation jobs</p>
          </div>
        </div>

        <div className="stats-cards">
          <div className="stat-card">
            <div className="stat-icon icon-completed"><i className="fas fa-check-circle"></i></div>
            <div className="stat-details"><h3>{stats.count}</h3><p>Jobs Completed</p></div>
          </div>
          <div className="stat-card">
            <div className="stat-icon icon-earnings"><i className="fas fa-rupee-sign"></i></div>
            <div className="stat-details"><h3>PKR {stats.earnings.toLocaleString()}</h3><p>Total Earnings</p></div>
          </div>
          <div className="stat-card">
            <div className="stat-icon icon-distance"><i className="fas fa-road"></i></div>
            <div className="stat-details"><h3>{stats.distance.toLocaleString()} km</h3><p>Total Distance</p></div>
          </div>
          <div className="stat-card">
            <div className="stat-icon icon-rating"><i className="fas fa-star"></i></div>
            <div className="stat-details"><h3>{stats.avgRating}</h3><p>Average Rating</p></div>
          </div>
        </div>

        <div className="view-toggle">
          <button className={`view-btn${view === 'table' ? ' active' : ''}`} onClick={() => setView('table')}>
            <i className="fas fa-table"></i> Table View
          </button>
          <button className={`view-btn${view === 'timeline' ? ' active' : ''}`} onClick={() => setView('timeline')}>
            <i className="fas fa-stream"></i> Timeline View
          </button>
        </div>

        <div className="job-history-section">
          <div className="filter-controls">
            <div className="search-box">
              <i className="fas fa-search"></i>
              <input
                type="text"
                placeholder="Search by Job ID, Route, or Client..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="filter-options">
              {FILTERS.map(f => (
                <button
                  key={f}
                  className={`filter-btn${filter === f ? ' active' : ''}`}
                  onClick={() => setFilter(f)}
                  style={{ textTransform: 'capitalize' }}
                >
                  {f === 'all' ? 'All Jobs' : f === 'thisMonth' ? 'This Month' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {view === 'table' && (
            <div className="table-view">
              <div className="table-responsive">
                <table>
                  <thead>
                    <tr>
                      <th>Job ID</th><th>Date</th><th>Route</th><th>Truck Used</th>
                      <th>Status</th><th>Earnings</th><th>Rating</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24 }}>Loading...</td></tr>
                    ) : filtered.length === 0 ? (
                      <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24 }}>No jobs found</td></tr>
                    ) : filtered.map(j => (
                      <tr key={j.id}>
                        <td>#{j.id}</td>
                        <td>{j.date || j.created_at || '-'}</td>
                        <td>{j.route || `${j.pickup || ''} → ${j.dropoff || ''}`}</td>
                        <td>{j.truck || '-'}</td>
                        <td>{statusBadge(j.status)}</td>
                        <td>PKR {parseFloat(j.earnings || j.amount || 0).toLocaleString()}</td>
                        <td>{j.rating ? `${j.rating} ★` : '-'}</td>
                        <td style={{ display: 'flex', gap: 6 }}>
                          <Link to={`/transporter/jobs/${j.id}`} className="action-btn-small">
                            <i className="fas fa-eye"></i> View
                          </Link>
                          {j.status === 'completed' && !j.client_rated && (
                            <button className="action-btn-small" onClick={() => { setRateModal(j); setRating(0); setReview(''); setRatingMsg('') }}>
                              <i className="fas fa-star"></i> Rate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {view === 'timeline' && (
            <div className="timeline-view" style={{ padding: '16px 0' }}>
              {loading ? (
                <p style={{ textAlign: 'center', padding: 24 }}>Loading...</p>
              ) : filtered.length === 0 ? (
                <p style={{ textAlign: 'center', padding: 24 }}>No jobs found</p>
              ) : filtered.map(j => (
                <div key={j.id} style={{ display: 'flex', gap: 16, padding: '16px 0', borderBottom: '1px solid var(--border-color)' }}>
                  <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0 }}>
                    <i className="fas fa-truck"></i>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>Job #{j.id} — {j.route || `${j.pickup || ''} → ${j.dropoff || ''}`}</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
                      {j.date || j.created_at} · {j.truck || ''} · PKR {parseFloat(j.earnings || j.amount || 0).toLocaleString()}
                    </div>
                    <div style={{ marginTop: 6 }}>{statusBadge(j.status)}</div>
                  </div>
                </div>
              ))}
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
            <Link to="/transporter/partner">Partner With Us</Link>
          </div>
        </div>

        {rateModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9998, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: 'var(--card-bg)', borderRadius: 12, padding: 28, maxWidth: 440, width: '90%' }}>
              <h3 style={{ marginBottom: 8 }}>Rate the Client</h3>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>Job #{rateModal.id}</p>
              <div style={{ display: 'flex', gap: 8, fontSize: 32, marginBottom: 16 }}>
                {[1,2,3,4,5].map(v => (
                  <span
                    key={v}
                    style={{ cursor: 'pointer', color: v <= (hoverRating || rating) ? '#f39c12' : '#ddd' }}
                    onClick={() => setRating(v)}
                    onMouseEnter={() => setHoverRating(v)}
                    onMouseLeave={() => setHoverRating(0)}
                  >★</span>
                ))}
              </div>
              <textarea
                value={review}
                onChange={e => setReview(e.target.value)}
                placeholder="Optional: share your experience..."
                style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid var(--border-color)', minHeight: 80, resize: 'vertical', background: 'var(--input-bg)', color: 'var(--text-primary)' }}
              />
              {ratingMsg && <p style={{ marginTop: 8, color: ratingMsg.includes('success') ? '#27ae60' : '#e74c3c', fontWeight: 500 }}>{ratingMsg}</p>}
              <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                <button className="action-btn" onClick={submitRating} disabled={submittingRating}>
                  {submittingRating ? 'Submitting...' : 'Submit Rating'}
                </button>
                <button className="action-btn" style={{ background: 'var(--hover-bg)', color: 'var(--text-secondary)' }}
                  onClick={() => setRateModal(null)}>Cancel</button>
              </div>
            </div>
          </div>
        )}

        {toast && (
          <div style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
            background: toast.type === 'error' ? '#e74c3c' : '#27ae60',
            color: '#fff', padding: '12px 20px', borderRadius: 8,
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          }}>
            {toast.msg}
          </div>
        )}
      </div>
    </TransporterLayout>
  )
}
