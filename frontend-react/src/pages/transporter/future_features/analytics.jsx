// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useState, useEffect } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const PERIODS = ['week', 'month', 'quarter', 'year']

const EMPTY_DATA = {
  total_jobs: 0, completion_rate: 0, avg_rating: 0, total_distance: 0,
  total_earnings: 0, avg_per_job: 0,
  on_job_trucks: 0, available_trucks: 0, total_trucks: 0, maintenance_trucks: 0,
  efficiency_score: 0, utilization_rate: 0,
}

export default function Analytics() {
  const api = useApi()
  const [period, setPeriod] = useState('month')
  const [data, setData] = useState(EMPTY_DATA)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    setLoading(true)
    api.get(`/api/analytics?period=${period}`)
      .then(d => setData({ ...EMPTY_DATA, ...d }))
      .catch(() => setData(EMPTY_DATA))
      .finally(() => setLoading(false))
  }, [period])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  function fmt(n) { return (parseFloat(n) || 0).toLocaleString() }
  function fmtPct(n) { return `${(parseFloat(n) || 0).toFixed(1)}%` }
  function fmtRating(n) { return `${(parseFloat(n) || 0).toFixed(1)} ★` }
  function fmtKm(n) { return `${fmt(n)} km` }
  function fmtPKR(n) { return `PKR ${fmt(n)}` }

  const util = parseFloat(data.utilization_rate) || 0

  return (
    <TransporterLayout>
      <div className="page-analytics">
        <div className="top-bar">
          <div className="page-title">
            <h1>Analytics Dashboard</h1>
            <p>Track your performance, earnings, and fleet utilization</p>
          </div>
          <div className="period-selector">
            {PERIODS.map(p => (
              <button
                key={p}
                className={`period-btn${period === p ? ' active' : ''}`}
                onClick={() => setPeriod(p)}
                style={{ textTransform: 'capitalize' }}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut"><i className="fas fa-tachometer-alt"></i><span>Dashboard</span></Link>
          <Link to="/transporter/personal-info" className="page-shortcut"><i className="fas fa-id-card"></i><span>Personal Info</span></Link>
          <Link to="/transporter/maintenance" className="page-shortcut"><i className="fas fa-tools"></i><span>Maintenance</span></Link>
          <Link to="/transporter/fuel" className="page-shortcut"><i className="fas fa-gas-pump"></i><span>Fuel</span></Link>
          <Link to="/transporter/analytics" className="page-shortcut active"><i className="fas fa-chart-line"></i><span>Analytics</span></Link>
          <Link to="/transporter/insights" className="page-shortcut"><i className="fas fa-brain"></i><span>Insights</span></Link>
          <Link to="/transporter/bids" className="page-shortcut"><i className="fas fa-shipping-fast"></i><span>My Bids</span></Link>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            <i className="fas fa-spinner fa-spin" style={{ fontSize: 28 }}></i>
            <p style={{ marginTop: 12 }}>Loading analytics...</p>
          </div>
        )}

        {!loading && (
          <>
            <div className="performance-overview">
              <div className="overview-card">
                <div className="overview-icon"><i className="fas fa-briefcase"></i></div>
                <div className="overview-content">
                  <h3>{fmt(data.total_jobs)}</h3>
                  <p>Total Jobs</p>
                </div>
              </div>
              <div className="overview-card">
                <div className="overview-icon"><i className="fas fa-check-circle"></i></div>
                <div className="overview-content">
                  <h3>{fmtPct(data.completion_rate)}</h3>
                  <p>Completion Rate</p>
                </div>
              </div>
              <div className="overview-card">
                <div className="overview-icon"><i className="fas fa-star"></i></div>
                <div className="overview-content">
                  <h3>{fmtRating(data.avg_rating)}</h3>
                  <p>Avg. Rating</p>
                </div>
              </div>
              <div className="overview-card">
                <div className="overview-icon"><i className="fas fa-road"></i></div>
                <div className="overview-content">
                  <h3>{fmtKm(data.total_distance)}</h3>
                  <p>Distance Travelled</p>
                </div>
              </div>
            </div>

            <div className="charts-section">
              <div className="chart-card">
                <div className="chart-header">
                  <h3><i className="fas fa-chart-area"></i> Earnings Trend</h3>
                  <div className="chart-actions">
                    <button className="chart-btn" onClick={() => showToast('Chart export is available in the full report')}>
                      <i className="fas fa-download"></i> Export
                    </button>
                  </div>
                </div>
                <div className="chart-container" style={{ minHeight: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <canvas id="earningsChart"></canvas>
                </div>
                <div className="chart-summary">
                  <div className="summary-item">
                    <span className="label">Total Earnings</span>
                    <span className="value">{fmtPKR(data.total_earnings)}</span>
                  </div>
                  <div className="summary-item">
                    <span className="label">Avg. per Job</span>
                    <span className="value">{fmtPKR(data.avg_per_job)}</span>
                  </div>
                </div>
              </div>

              <div className="chart-card">
                <div className="chart-header">
                  <h3><i className="fas fa-chart-pie"></i> Job Distribution</h3>
                </div>
                <div className="chart-container" style={{ minHeight: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <canvas id="jobDistributionChart"></canvas>
                </div>
                <div className="chart-legend" style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: 14 }}>
                  Data based on {period} period
                </div>
              </div>
            </div>

            <div className="utilization-section">
              <div className="section-header">
                <h3><i className="fas fa-truck"></i> Fleet Utilization</h3>
              </div>
              <div className="utilization-cards">
                <div className="utilization-card">
                  <div className="utilization-header">
                    <span className="utilization-label">Overall Utilization</span>
                    <span className="utilization-value">{fmtPct(util)}</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${Math.min(100, util)}%` }}></div>
                  </div>
                  <div className="utilization-details">
                    <span><i className="fas fa-truck"></i> {fmt(data.on_job_trucks)} on job</span>
                    <span><i className="fas fa-check"></i> {fmt(data.available_trucks)} available</span>
                  </div>
                </div>
                <div className="utilization-card">
                  <div className="utilization-header">
                    <span className="utilization-label">Fleet Overview</span>
                  </div>
                  <div className="fleet-stats">
                    <div className="fleet-stat">
                      <span className="stat-number">{fmt(data.total_trucks)}</span>
                      <span className="stat-label">Total Trucks</span>
                    </div>
                    <div className="fleet-stat">
                      <span className="stat-number">{fmt(data.maintenance_trucks)}</span>
                      <span className="stat-label">In Maintenance</span>
                    </div>
                    <div className="fleet-stat">
                      <span className="stat-number">{fmtPct(data.efficiency_score)}</span>
                      <span className="stat-label">Efficiency Score</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="trends-section">
              <div className="section-header">
                <h3><i className="fas fa-chart-line"></i> Performance Trends</h3>
              </div>
              <div className="trends-container" style={{ minHeight: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <canvas id="performanceChart"></canvas>
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
