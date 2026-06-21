// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useState, useEffect, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const EMPTY_INSIGHTS = {
  overall_score: 0,
  industry_comparison: '',
  score_trend: '',
  perf_score: 0,
  earn_score: 0,
  fleet_score: 0,
  cust_score: 0,
  proj_7: 0, proj_7_conf: '',
  proj_15: 0, proj_15_conf: '',
  proj_30: 0, proj_30_conf: '',
  proj_90: 0, proj_90_conf: '',
  recommendations: [],
  maintenance_predictions: [],
  maintenance_cost: 0,
  maintenance_downtime: 0,
}

export default function PredInsights() {
  const api = useApi()
  const [insights, setInsights] = useState(EMPTY_INSIGHTS)
  const [loading, setLoading] = useState(true)
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [toast, setToast] = useState(null)

  function loadInsights() {
    setLoading(true)
    api.get('/api/insights/predictions')
      .then(d => setInsights({ ...EMPTY_INSIGHTS, ...d }))
      .catch(() => setInsights(EMPTY_INSIGHTS))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadInsights() }, [])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  function refresh() {
    loadInsights()
    showToast('Insights refreshed')
  }

  const recommendations = useMemo(() => {
    const recs = insights.recommendations || []
    if (priorityFilter === 'all') return recs
    return recs.filter(r => (r.priority || '').toLowerCase() === priorityFilter)
  }, [insights.recommendations, priorityFilter])

  function fmt(n) { return `PKR ${(parseFloat(n) || 0).toLocaleString()}` }
  function fmtScore(n) { return (parseFloat(n) || 0).toFixed(0) }

  const score = parseFloat(insights.overall_score) || 0
  const circumference = 2 * Math.PI * 45
  const strokeDasharray = `${(score / 100) * circumference} ${circumference}`

  return (
    <TransporterLayout>
      <div className="page-predictive-insights">
        <div className="top-bar">
          <div className="page-title">
            <h1>Predictive Insights</h1>
            <p>AI-powered forecasts and recommendations for your transport business</p>
          </div>
          <button className="refresh-btn" onClick={refresh} disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', background: 'none', border: '1px solid var(--border-color)', borderRadius: 8, padding: '8px 16px', color: 'var(--text-primary)' }}>
            <i className={`fas fa-sync-alt${loading ? ' fa-spin' : ''}`}></i> Refresh Insights
          </button>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut"><i className="fas fa-tachometer-alt"></i><span>Dashboard</span></Link>
          <Link to="/transporter/personal-info" className="page-shortcut"><i className="fas fa-id-card"></i><span>Personal Info</span></Link>
          <Link to="/transporter/maintenance" className="page-shortcut"><i className="fas fa-tools"></i><span>Maintenance</span></Link>
          <Link to="/transporter/fuel" className="page-shortcut"><i className="fas fa-gas-pump"></i><span>Fuel</span></Link>
          <Link to="/transporter/analytics" className="page-shortcut"><i className="fas fa-chart-line"></i><span>Analytics</span></Link>
          <Link to="/transporter/insights" className="page-shortcut active"><i className="fas fa-brain"></i><span>Insights</span></Link>
          <Link to="/transporter/bids" className="page-shortcut"><i className="fas fa-shipping-fast"></i><span>My Bids</span></Link>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <i className="fas fa-brain fa-spin" style={{ fontSize: 36, color: 'var(--primary)' }}></i>
            <p style={{ marginTop: 12, color: 'var(--text-secondary)' }}>Generating AI predictions...</p>
          </div>
        )}

        {!loading && (
          <>
            <div className="score-card">
              <div className="score-main">
                <div className="score-circle">
                  <svg viewBox="0 0 100 100">
                    <circle className="score-bg" cx="50" cy="50" r="45" fill="none" stroke="var(--border-color)" strokeWidth="8" />
                    <circle
                      className="score-progress"
                      cx="50" cy="50" r="45"
                      fill="none" stroke="var(--primary)" strokeWidth="8"
                      strokeDasharray={strokeDasharray}
                      strokeLinecap="round"
                      transform="rotate(-90 50 50)"
                    />
                  </svg>
                  <div className="score-value">
                    <span style={{ fontSize: 28, fontWeight: 700 }}>{fmtScore(score)}</span>
                    <span className="score-label">Score</span>
                  </div>
                </div>
                <div className="score-info">
                  <h2>Business Health Score</h2>
                  <p>{insights.industry_comparison || 'Score based on performance data'}</p>
                  {insights.score_trend && (
                    <span className="score-trend up">{insights.score_trend}</span>
                  )}
                </div>
              </div>
              <div className="score-breakdown">
                {[
                  { label: 'Performance', value: insights.perf_score },
                  { label: 'Earnings', value: insights.earn_score },
                  { label: 'Fleet', value: insights.fleet_score },
                  { label: 'Customer', value: insights.cust_score },
                ].map(item => (
                  <div className="breakdown-item" key={item.label}>
                    <span className="breakdown-label">{item.label}</span>
                    <span className="breakdown-value">{fmtScore(item.value)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="projections-section">
              <div className="section-header">
                <h3><i className="fas fa-chart-line"></i> Earnings Projections</h3>
              </div>
              <div className="projections-grid">
                {[
                  { label: 'Next 7 Days', icon: 'fa-calendar-week', value: insights.proj_7, conf: insights.proj_7_conf },
                  { label: 'Next 15 Days', icon: 'fa-calendar-alt', value: insights.proj_15, conf: insights.proj_15_conf },
                  { label: 'Next 30 Days', icon: 'fa-calendar', value: insights.proj_30, conf: insights.proj_30_conf },
                  { label: 'Next 90 Days', icon: 'fa-calendar-check', value: insights.proj_90, conf: insights.proj_90_conf },
                ].map(p => (
                  <div className="projection-card" key={p.label}>
                    <div className="projection-header">
                      <span className="projection-period">{p.label}</span>
                      <span className="projection-icon"><i className={`fas ${p.icon}`}></i></span>
                    </div>
                    <div className="projection-value">{fmt(p.value)}</div>
                    <div className="projection-meta">
                      <span className="confidence">{p.conf || 'Confidence: N/A'}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="recommendations-section">
              <div className="section-header">
                <h3><i className="fas fa-lightbulb"></i> Smart Recommendations</h3>
                <div className="priority-filter">
                  {['all', 'high', 'medium'].map(p => (
                    <button
                      key={p}
                      className={`filter-btn${priorityFilter === p ? ' active' : ''}`}
                      onClick={() => setPriorityFilter(p)}
                      style={{ textTransform: 'capitalize' }}
                    >
                      {p === 'all' ? 'All' : p.charAt(0).toUpperCase() + p.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="recommendations-list">
                {recommendations.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)', padding: 16 }}>No recommendations for this filter.</p>
                ) : recommendations.map((rec, i) => (
                  <div key={i} style={{
                    padding: '16px 20px', borderRadius: 10, marginBottom: 12,
                    background: 'var(--card-bg)', border: '1px solid var(--border-color)',
                    borderLeft: `4px solid ${rec.priority === 'high' ? '#e74c3c' : '#f39c12'}`,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontWeight: 600, margin: '0 0 6px' }}>{rec.title || rec.message || 'Recommendation'}</p>
                        {rec.description && <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: 14 }}>{rec.description}</p>}
                      </div>
                      <span style={{
                        background: rec.priority === 'high' ? '#e74c3c' : '#f39c12',
                        color: '#fff', padding: '3px 10px', borderRadius: 20,
                        fontSize: 12, fontWeight: 600, marginLeft: 12, flexShrink: 0, textTransform: 'capitalize',
                      }}>{rec.priority || 'medium'}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="maintenance-section">
              <div className="section-header">
                <h3><i className="fas fa-tools"></i> Maintenance Predictions</h3>
              </div>
              <div className="maintenance-list">
                {(insights.maintenance_predictions || []).length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)', padding: 16 }}>No upcoming maintenance predicted.</p>
                ) : (insights.maintenance_predictions || []).map((m, i) => (
                  <div key={i} style={{
                    padding: '14px 18px', borderRadius: 10, marginBottom: 10,
                    background: 'var(--card-bg)', border: '1px solid var(--border-color)',
                  }}>
                    <strong>{m.truck || 'Truck'}</strong> — {m.issue || 'Maintenance required'}
                    {m.due_date && <span style={{ marginLeft: 12, color: 'var(--text-secondary)', fontSize: 13 }}>Due: {m.due_date}</span>}
                    {m.cost && <span style={{ marginLeft: 12, color: '#e74c3c', fontSize: 13 }}>Est. PKR {parseFloat(m.cost).toLocaleString()}</span>}
                  </div>
                ))}
              </div>
              <div className="maintenance-summary">
                <div className="summary-item">
                  <span className="label">Total Estimated Cost</span>
                  <span className="value">{fmt(insights.maintenance_cost)}</span>
                </div>
                <div className="summary-item">
                  <span className="label">Total Downtime</span>
                  <span className="value">{insights.maintenance_downtime ? `${insights.maintenance_downtime} hrs` : 'N/A'}</span>
                </div>
              </div>
            </div>
          </>
        )}

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

      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
          background: '#27ae60', color: '#fff',
          padding: '12px 20px', borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        }}>
          {toast}
        </div>
      )}
    </TransporterLayout>
  )
}
