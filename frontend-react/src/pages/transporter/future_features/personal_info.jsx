// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useEffect, useState, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const MAINT_FILTERS = ['all', 'scheduled', 'completed', 'overdue']

const EMPTY_MAINT_FORM = { truck: '', serviceType: '', date: '', cost: '', notes: '' }
const EMPTY_FUEL_FORM = { truck: '', date: '', quantity: '', rate: '', odometer: '', distance: '', station: '' }

export default function PersonalInfo() {
  const api = useApi()
  const navigate = useNavigate()

  const [trucks, setTrucks] = useState([])
  const [truckStats, setTruckStats] = useState({ total: 0, active: 0, available: 0, onJob: 0, maintenance: 0 })
  const [maintenance, setMaintenance] = useState([])
  const [fuel, setFuel] = useState([])
  const [analytics, setAnalytics] = useState({ total_earnings: 0, total_jobs: 0 })
  const [insights, setInsights] = useState({ proj_30: 0 })
  const [loading, setLoading] = useState(true)

  const [maintFilter, setMaintFilter] = useState('all')
  const [showMaintModal, setShowMaintModal] = useState(false)
  const [showFuelModal, setShowFuelModal] = useState(false)
  const [maintForm, setMaintForm] = useState(EMPTY_MAINT_FORM)
  const [fuelForm, setFuelForm] = useState(EMPTY_FUEL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState(null)

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  function load() {
    setLoading(true)
    Promise.allSettled([
      api.get('/api/trucks?page_size=200'),
      api.get('/api/trucks/stats'),
      api.get('/api/maintenance'),
      api.get('/api/fuel'),
      api.get('/api/analytics?period=month'),
      api.get('/api/insights/predictions'),
    ]).then(([trucksR, statsR, maintR, fuelR, analyticsR, insightsR]) => {
      if (trucksR.status === 'fulfilled') setTrucks(trucksR.value.trucks || [])
      if (statsR.status === 'fulfilled') setTruckStats(statsR.value.stats || {})
      if (maintR.status === 'fulfilled') setMaintenance(maintR.value.records || maintR.value.maintenance || [])
      if (fuelR.status === 'fulfilled') setFuel(fuelR.value.entries || [])
      if (analyticsR.status === 'fulfilled') setAnalytics(analyticsR.value || {})
      if (insightsR.status === 'fulfilled') setInsights(insightsR.value || {})
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const now = new Date()
  const cm = now.getMonth(), cy = now.getFullYear()

  const filteredMaint = useMemo(() => {
    if (maintFilter === 'all') return maintenance
    return maintenance.filter(m => (m.status || '').toLowerCase() === maintFilter)
  }, [maintenance, maintFilter])

  const monthFuel = fuel.filter(f => {
    const d = new Date(f.date)
    return d.getMonth() === cm && d.getFullYear() === cy
  })
  const monthFuelCost = monthFuel.reduce((s, f) => s + parseFloat(f.cost || 0), 0)
  const monthFuelLiters = monthFuel.reduce((s, f) => s + parseFloat(f.amount || 0), 0)
  const avgMileage = monthFuelLiters > 0 ? (monthFuelLiters / Math.max(1, monthFuel.length)).toFixed(1) : '0'

  function setMaintField(e) { const { name, value } = e.target; setMaintForm(f => ({ ...f, [name]: value })) }
  function setFuelField(e) { const { name, value } = e.target; setFuelForm(f => ({ ...f, [name]: value })) }

  async function submitMaintenance(e) {
    e.preventDefault()
    if (!maintForm.truck || !maintForm.serviceType || !maintForm.date) {
      showToast('Please fill required fields', 'error'); return
    }
    setSubmitting(true)
    try {
      await api.post('/api/maintenance', {
        truck: maintForm.truck, part_type: maintForm.serviceType,
        date: maintForm.date, cost: parseFloat(maintForm.cost) || 0, notes: maintForm.notes,
      })
      showToast('Maintenance scheduled successfully')
      setShowMaintModal(false)
      setMaintForm(EMPTY_MAINT_FORM)
      load()
    } catch (err) {
      showToast(err.message || 'Failed to schedule maintenance', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  async function submitFuel(e) {
    e.preventDefault()
    if (!fuelForm.truck || !fuelForm.date || !fuelForm.quantity || !fuelForm.rate) {
      showToast('Please fill required fields', 'error'); return
    }
    setSubmitting(true)
    try {
      const cost = parseFloat(fuelForm.quantity) * parseFloat(fuelForm.rate)
      await api.post('/api/fuel', {
        truck: fuelForm.truck, date: fuelForm.date,
        amount: parseFloat(fuelForm.quantity), cost,
        odometer: fuelForm.odometer ? parseFloat(fuelForm.odometer) : null,
        notes: fuelForm.station ? `Station: ${fuelForm.station}` : '',
      })
      showToast('Fuel record added successfully')
      setShowFuelModal(false)
      setFuelForm(EMPTY_FUEL_FORM)
      load()
    } catch (err) {
      showToast(err.message || 'Failed to add fuel record', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  function generateReport() {
    const rows = maintenance.map(m => [m.truck || '', m.part_type || '', m.date || '', m.cost || 0, m.status || ''])
    const csv = [['Truck', 'Service Type', 'Date', 'Cost', 'Status'], ...rows].map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = 'performance_report.csv'
    a.click()
    showToast('Report downloaded')
  }

  function statusBadge(status) {
    const colors = { scheduled: '#3b82f6', completed: '#22c55e', overdue: '#ef4444', pending: '#f59e0b' }
    return (
      <span style={{ background: (colors[status] || '#94a3b8') + '22', color: colors[status] || '#94a3b8', padding: '2px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, textTransform: 'capitalize' }}>
        {status || 'unknown'}
      </span>
    )
  }

  return (
    <TransporterLayout>
      <div className="page-personal-info">
        <div className="top-bar">
          <div className="page-title">
            <h1>Personal Info &amp; Fleet Hub</h1>
            <p>Live overview for trucks, maintenance, fuel activity, earnings, and active jobs</p>
          </div>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut"><i className="fas fa-tachometer-alt"></i><span>Dashboard</span></Link>
          <Link to="/transporter/personal-info" className="page-shortcut active"><i className="fas fa-id-card"></i><span>Personal Info</span></Link>
          <Link to="/transporter/maintenance" className="page-shortcut"><i className="fas fa-tools"></i><span>Maintenance</span></Link>
          <Link to="/transporter/fuel" className="page-shortcut"><i className="fas fa-gas-pump"></i><span>Fuel</span></Link>
          <Link to="/transporter/analytics" className="page-shortcut"><i className="fas fa-chart-line"></i><span>Analytics</span></Link>
          <Link to="/transporter/insights" className="page-shortcut"><i className="fas fa-brain"></i><span>Insights</span></Link>
          <Link to="/transporter/bids" className="page-shortcut"><i className="fas fa-shipping-fast"></i><span>My Bids</span></Link>
        </div>

        <div className="dashboard-cards">
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">{truckStats.total || trucks.length}</div>
                <div className="card-title">My Trucks</div>
              </div>
              <div className="card-icon trucks-icon"><i className="fas fa-truck"></i></div>
            </div>
            <div className="card-footer">
              <span><i className="fas fa-circle" style={{ color: '#22c55e', marginRight: 4 }}></i> {truckStats.active || 0} active</span>
              <Link to="/transporter/trucks" className="action-btn-small">View All</Link>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">{maintenance.filter(m => m.status === 'scheduled').length}</div>
                <div className="card-title">Pending Maintenance</div>
              </div>
              <div className="card-icon maintenance-icon"><i className="fas fa-tools"></i></div>
            </div>
            <div className="card-footer">
              <span>{maintenance.filter(m => m.status === 'overdue').length} overdue</span>
              <button className="action-btn-small" onClick={() => setShowMaintModal(true)}>Schedule</button>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">{analytics.total_jobs || 0}</div>
                <div className="card-title">Active Jobs</div>
              </div>
              <div className="card-icon orders-icon"><i className="fas fa-clipboard-list"></i></div>
            </div>
            <div className="card-footer">
              <span>This month</span>
              <Link to="/transporter/available-bids" className="action-btn-small">Browse</Link>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">PKR {(parseFloat(analytics.total_earnings) || 0).toLocaleString()}</div>
                <div className="card-title">Monthly Earnings</div>
              </div>
              <div className="card-icon earnings-icon"><i className="fas fa-rupee-sign"></i></div>
            </div>
            <div className="card-footer">
              <span>This month</span>
              <Link to="/transporter/earnings" className="action-btn-small">Details</Link>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">PKR {(parseFloat(insights.proj_30) || 0).toLocaleString()}</div>
                <div className="card-title">Next Month Prediction</div>
              </div>
              <div className="card-icon predictive-icon"><i className="fas fa-chart-line"></i></div>
            </div>
            <div className="card-footer">
              <span>AI forecast</span>
              <Link to="/transporter/insights" className="action-btn-small">View</Link>
            </div>
          </div>
        </div>

        <h2 className="section-title">Quick Actions</h2>
        <div className="quick-actions">
          <button className="action-btn" onClick={() => setShowMaintModal(true)}>
            <i className="fas fa-tools"></i>
            <span>Add Maintenance</span>
            <div className="action-desc">Schedule truck service</div>
          </button>
          <Link to="/transporter/account-history" className="action-btn">
            <i className="fas fa-wallet"></i>
            <span>Account History</span>
            <div className="action-desc">Review payments and transactions</div>
          </Link>
          <button className="action-btn" onClick={() => setShowFuelModal(true)}>
            <i className="fas fa-gas-pump"></i>
            <span>Add Fuel Record</span>
            <div className="action-desc">Log fuel consumption</div>
          </button>
          <button className="action-btn" onClick={generateReport}>
            <i className="fas fa-file-invoice"></i>
            <span>Generate Report</span>
            <div className="action-desc">Monthly performance CSV</div>
          </button>
          <Link to="/transporter/insights" className="action-btn">
            <i className="fas fa-brain"></i>
            <span>Predictive Analytics</span>
            <div className="action-desc">Future insights</div>
          </Link>
          <Link to="/transporter/available-bids" className="action-btn">
            <i className="fas fa-clipboard-list"></i>
            <span>Available Bids</span>
            <div className="action-desc">Browse available bids</div>
          </Link>
        </div>

        <div className="maintenance-history">
          <div className="table-header">
            <h2 className="section-title">Maintenance History</h2>
            <div className="table-actions">
              {MAINT_FILTERS.map(f => (
                <button
                  key={f}
                  className={`filter-btn${maintFilter === f ? ' active' : ''}`}
                  onClick={() => setMaintFilter(f)}
                  style={{ textTransform: 'capitalize' }}
                >
                  {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Truck ID</th><th>Service Type</th><th>Date</th>
                  <th>Cost</th><th>Status</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 20 }}>Loading...</td></tr>
                ) : filteredMaint.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 20 }}>No maintenance records found</td></tr>
                ) : filteredMaint.map((m, i) => (
                  <tr key={m.id || i}>
                    <td>{m.truck || '-'}</td>
                    <td>{m.part_type || m.service_type || '-'}</td>
                    <td>{m.date || '-'}</td>
                    <td>PKR {parseFloat(m.cost || 0).toLocaleString()}</td>
                    <td>{statusBadge(m.status)}</td>
                    <td>
                      <Link to="/transporter/maintenance" className="action-btn-small">
                        <i className="fas fa-eye"></i> View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="predictive-insights">
          <h2 className="section-title">Predictive Insights</h2>
          <div className="insights-grid">
            <div className="insight-card">
              <div className="insight-header">
                <div className="insight-icon"><i className="fas fa-tools"></i></div>
                <div className="insight-title">Next Maintenance</div>
              </div>
              <div className="insight-value">
                {maintenance.filter(m => m.status === 'scheduled').length} scheduled
              </div>
              <div className="insight-desc">Expected maintenance cost upcoming</div>
              <div className="insight-progress">
                <div className="progress-fill yellow" style={{ width: `${Math.min(100, maintenance.filter(m => m.status === 'overdue').length * 20)}%` }}></div>
              </div>
            </div>
            <div className="insight-card">
              <div className="insight-header">
                <div className="insight-icon"><i className="fas fa-gas-pump"></i></div>
                <div className="insight-title">Fuel Cost Prediction</div>
              </div>
              <div className="insight-value">PKR {monthFuelCost.toLocaleString()}</div>
              <div className="insight-desc">This month's fuel spend</div>
              <div className="insight-progress">
                <div className="progress-fill red" style={{ width: `${Math.min(100, (monthFuelCost / 50000) * 100)}%` }}></div>
              </div>
            </div>
            <div className="insight-card">
              <div className="insight-header">
                <div className="insight-icon"><i className="fas fa-rupee-sign"></i></div>
                <div className="insight-title">Revenue Forecast</div>
              </div>
              <div className="insight-value">PKR {(parseFloat(insights.proj_30) || 0).toLocaleString()}</div>
              <div className="insight-desc">Projected next 30 days</div>
              <div className="insight-progress">
                <div className="progress-fill green" style={{ width: '65%' }}></div>
              </div>
            </div>
          </div>
        </div>

        <div className="fuel-management">
          <div className="table-header">
            <h2 className="section-title">Fuel Management</h2>
            <button className="btn-primary" onClick={() => setShowFuelModal(true)}>
              <i className="fas fa-plus"></i> Add Fuel Record
            </button>
          </div>
          <div className="fuel-stats">
            <div className="fuel-stat">
              <div className="fuel-stat-value">{avgMileage} km/L</div>
              <div className="fuel-stat-label">Average Mileage</div>
            </div>
            <div className="fuel-stat">
              <div className="fuel-stat-value">PKR {monthFuelCost.toLocaleString()}</div>
              <div className="fuel-stat-label">Monthly Fuel Cost</div>
            </div>
            <div className="fuel-stat">
              <div className="fuel-stat-value">{monthFuelLiters.toFixed(1)} L</div>
              <div className="fuel-stat-label">Monthly Consumption</div>
            </div>
            <div className="fuel-stat">
              <div className="fuel-stat-value">{monthFuel.length > 0 ? `PKR ${(monthFuelCost / monthFuelLiters).toFixed(1)}/L` : '-'}</div>
              <div className="fuel-stat-label">Average Price</div>
            </div>
          </div>
          <div className="table-responsive" style={{ marginTop: 30 }}>
            <table>
              <thead>
                <tr><th>Truck</th><th>Date</th><th>Amount (L)</th><th>Cost (PKR)</th><th>Odometer</th><th>Action</th></tr>
              </thead>
              <tbody>
                {fuel.slice(0, 10).map((f, i) => (
                  <tr key={f.id || i}>
                    <td>{f.truck || '-'}</td>
                    <td>{f.date || '-'}</td>
                    <td>{f.amount} L</td>
                    <td>PKR {parseFloat(f.cost || 0).toLocaleString()}</td>
                    <td>{f.odometer ? `${f.odometer} km` : '-'}</td>
                    <td><Link to="/transporter/fuel" className="action-btn-small"><i className="fas fa-eye"></i> View</Link></td>
                  </tr>
                ))}
                {fuel.length === 0 && !loading && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 20 }}>No fuel records yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
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

        {showMaintModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9998, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="modal-content" style={{ background: 'var(--card-bg)', borderRadius: 12, padding: 28, maxWidth: 480, width: '90%', maxHeight: '90vh', overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 style={{ margin: 0 }}>Schedule Maintenance</h3>
                <button onClick={() => setShowMaintModal(false)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer' }}>&times;</button>
              </div>
              <form onSubmit={submitMaintenance}>
                <div className="form-group">
                  <label className="form-label">Select Truck</label>
                  <select name="truck" value={maintForm.truck} onChange={setMaintField} className="form-control" required>
                    <option value="">Choose Truck</option>
                    {trucks.map(t => <option key={t.id} value={t.truck_number || t.id}>{t.truck_number} - {t.truck_type}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Service Type</label>
                  <select name="serviceType" value={maintForm.serviceType} onChange={setMaintField} className="form-control" required>
                    <option value="">Select Service</option>
                    <option value="oil_change">Oil Change</option>
                    <option value="brake_service">Brake Service</option>
                    <option value="tire_replacement">Tire Replacement</option>
                    <option value="engine_overhaul">Engine Overhaul</option>
                    <option value="battery_check">Battery Check</option>
                    <option value="general_service">General Service</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Service Date</label>
                  <input type="date" name="date" value={maintForm.date} onChange={setMaintField} className="form-control" required />
                </div>
                <div className="form-group">
                  <label className="form-label">Estimated Cost (PKR)</label>
                  <input type="number" name="cost" value={maintForm.cost} onChange={setMaintField} className="form-control" placeholder="Enter estimated cost" />
                </div>
                <div className="form-group">
                  <label className="form-label">Notes</label>
                  <textarea name="notes" value={maintForm.notes} onChange={setMaintField} className="form-control" rows={3} placeholder="Any additional notes..."></textarea>
                </div>
                <button type="submit" className="btn-primary" style={{ width: '100%' }} disabled={submitting}>
                  {submitting ? 'Scheduling...' : 'Schedule Maintenance'}
                </button>
              </form>
            </div>
          </div>
        )}

        {showFuelModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9998, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="modal-content" style={{ background: 'var(--card-bg)', borderRadius: 12, padding: 28, maxWidth: 480, width: '90%', maxHeight: '90vh', overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 style={{ margin: 0 }}>Add Fuel Record</h3>
                <button onClick={() => setShowFuelModal(false)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer' }}>&times;</button>
              </div>
              <form onSubmit={submitFuel}>
                <div className="form-group">
                  <label className="form-label">Select Truck</label>
                  <select name="truck" value={fuelForm.truck} onChange={setFuelField} className="form-control" required>
                    <option value="">Choose Truck</option>
                    {trucks.map(t => <option key={t.id} value={t.truck_number || t.id}>{t.truck_number} - {t.truck_type}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Fueling Date</label>
                  <input type="date" name="date" value={fuelForm.date} onChange={setFuelField} className="form-control" required />
                </div>
                <div className="form-group">
                  <label className="form-label">Quantity (Liters)</label>
                  <input type="number" name="quantity" value={fuelForm.quantity} onChange={setFuelField} className="form-control" placeholder="Enter liters" required />
                </div>
                <div className="form-group">
                  <label className="form-label">Rate per Liter (PKR)</label>
                  <input type="number" step="0.01" name="rate" value={fuelForm.rate} onChange={setFuelField} className="form-control" placeholder="Enter rate per liter" required />
                </div>
                <div className="form-group">
                  <label className="form-label">Odometer Reading (km)</label>
                  <input type="number" name="odometer" value={fuelForm.odometer} onChange={setFuelField} className="form-control" placeholder="Current odometer" />
                </div>
                <div className="form-group">
                  <label className="form-label">Fuel Station</label>
                  <input type="text" name="station" value={fuelForm.station} onChange={setFuelField} className="form-control" placeholder="Name of fuel station" />
                </div>
                {fuelForm.quantity && fuelForm.rate && (
                  <div style={{ background: 'var(--hover-bg)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 14 }}>
                    Total Cost: <strong>PKR {(parseFloat(fuelForm.quantity) * parseFloat(fuelForm.rate)).toFixed(2)}</strong>
                  </div>
                )}
                <button type="submit" className="btn-primary" style={{ width: '100%' }} disabled={submitting}>
                  {submitting ? 'Adding...' : 'Add Fuel Record'}
                </button>
              </form>
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
