// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useState, useEffect, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = { truck: '', date: '', amount: '', cost: '', odometer: '', fuelType: 'diesel', notes: '' }

export default function FuelManagement() {
  const api = useApi()
  const [trucks, setTrucks] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [fuelLog, setFuelLog] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)
  const [modal, setModal] = useState(null)

  useEffect(() => {
    api.get('/api/trucks').then(d => setTrucks(d.trucks || [])).catch(() => {})
    loadFuelLog()
  }, [])

  function loadFuelLog() {
    setLoading(true)
    api.get('/api/fuel')
      .then(d => setFuelLog(d.entries || []))
      .catch(() => setFuelLog([]))
      .finally(() => setLoading(false))
  }

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3200)
  }

  function setField(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function addFuelEntry(e) {
    e.preventDefault()
    if (!form.truck || !form.date || !form.amount || !form.cost) {
      showToast('Please fill Truck, Date, Amount and Cost fields', 'error')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/api/fuel', {
        truck: form.truck,
        date: form.date,
        amount: parseFloat(form.amount),
        cost: parseFloat(form.cost),
        odometer: form.odometer ? parseFloat(form.odometer) : null,
        fuel_type: form.fuelType,
        notes: form.notes,
      })
      showToast('Fuel entry added successfully')
      setForm(EMPTY_FORM)
      loadFuelLog()
    } catch (err) {
      showToast(err.message || 'Failed to add fuel entry', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  function calculateMileage() {
    const liters = parseFloat(form.amount)
    const cost = parseFloat(form.cost)
    if (!liters || liters <= 0) { showToast('Enter fuel amount first', 'error'); return }
    if (!cost || cost <= 0) { showToast('Enter fuel cost first', 'error'); return }
    const costPerL = (cost / liters).toFixed(2)
    const truckEntries = fuelLog.filter(e => e.truck === form.truck && e.odometer)
    let extra = ''
    if (form.odometer && truckEntries.length > 0) {
      const lastOdo = Math.max(...truckEntries.map(e => parseFloat(e.odometer || 0)))
      const dist = parseFloat(form.odometer) - lastOdo
      if (dist > 0) {
        const kmpl = (dist / liters).toFixed(2)
        extra = ` | Mileage: ${kmpl} km/L`
      }
    }
    showToast(`Cost/Liter: PKR ${costPerL}${extra}`)
  }

  const now = new Date()
  const cm = now.getMonth(), cy = now.getFullYear()

  const filtered = useMemo(() => {
    if (filter === 'thisMonth') {
      return fuelLog.filter(e => { const d = new Date(e.date); return d.getMonth() === cm && d.getFullYear() === cy })
    }
    if (filter === 'lastMonth') {
      const lm = cm === 0 ? 11 : cm - 1
      const ly = cm === 0 ? cy - 1 : cy
      return fuelLog.filter(e => { const d = new Date(e.date); return d.getMonth() === lm && d.getFullYear() === ly })
    }
    if (filter === 'highCost') return fuelLog.filter(e => parseFloat(e.cost || 0) > 5000)
    return fuelLog
  }, [fuelLog, filter, cm, cy])

  const monthEntries = fuelLog.filter(e => { const d = new Date(e.date); return d.getMonth() === cm && d.getFullYear() === cy })
  const monthlyCost = monthEntries.reduce((s, e) => s + parseFloat(e.cost || 0), 0)
  const totalLitersMonth = monthEntries.reduce((s, e) => s + parseFloat(e.amount || 0), 0)
  const costPerKm = fuelLog.length > 0 ? (monthlyCost / Math.max(1, totalLitersMonth * 8)).toFixed(2) : '0.00'
  const bestTruck = (() => {
    const map = {}
    fuelLog.forEach(e => {
      if (!e.truck) return
      if (!map[e.truck]) map[e.truck] = { cost: 0, liters: 0 }
      map[e.truck].cost += parseFloat(e.cost || 0)
      map[e.truck].liters += parseFloat(e.amount || 0)
    })
    let best = null, bestEff = Infinity
    for (const t in map) {
      const eff = map[t].liters > 0 ? map[t].cost / map[t].liters : Infinity
      if (eff < bestEff) { bestEff = eff; best = t }
    }
    return best || '-'
  })()

  function exportData() {
    if (!filtered.length) { showToast('No data to export', 'error'); return }
    const headers = ['Date', 'Truck', 'Fuel Type', 'Amount (L)', 'Cost (PKR)', 'Odometer', 'Notes']
    const rows = filtered.map(e => [e.date, e.truck, e.fuel_type || '', e.amount, e.cost, e.odometer || '', (e.notes || '').replace(/,/g, ' ')])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = 'fuel_log.csv'
    a.click()
    showToast('Export downloaded')
  }

  return (
    <TransporterLayout>
      <div className="page-fuel-management">
        <div className="top-bar">
          <div className="page-title">
            <h1>Fuel Management</h1>
            <p>Track fuel consumption, costs, and optimize efficiency</p>
          </div>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut"><i className="fas fa-tachometer-alt"></i><span>Dashboard</span></Link>
          <Link to="/transporter/personal-info" className="page-shortcut"><i className="fas fa-id-card"></i><span>Personal Info</span></Link>
          <Link to="/transporter/maintenance" className="page-shortcut"><i className="fas fa-tools"></i><span>Maintenance</span></Link>
          <Link to="/transporter/fuel" className="page-shortcut active"><i className="fas fa-gas-pump"></i><span>Fuel</span></Link>
          <Link to="/transporter/analytics" className="page-shortcut"><i className="fas fa-chart-line"></i><span>Analytics</span></Link>
          <Link to="/transporter/insights" className="page-shortcut"><i className="fas fa-brain"></i><span>Insights</span></Link>
          <Link to="/transporter/bids" className="page-shortcut"><i className="fas fa-shipping-fast"></i><span>My Bids</span></Link>
        </div>

        <div className="dashboard-cards">
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">PKR {monthlyCost.toLocaleString()}</div>
                <div className="card-title">Monthly Fuel Cost</div>
              </div>
              <div className="card-icon fuel-cost-icon"><i className="fas fa-rupee-sign"></i></div>
            </div>
            <div className="card-footer">
              <span><i className="fas fa-chart-line"></i> Live from fuel records</span>
              <button className="action-btn-small" onClick={() => setFilter('thisMonth')}>Details</button>
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">{totalLitersMonth.toFixed(1)} L</div>
                <div className="card-title">Total Liters This Month</div>
              </div>
              <div className="card-icon mileage-icon"><i className="fas fa-tachometer-alt"></i></div>
            </div>
            <div className="card-footer">
              <span><i className="fas fa-chart-line"></i> Monthly consumption</span>
              <button className="action-btn-small" onClick={() => setFilter('thisMonth')}>Analyze</button>
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">PKR {costPerKm}/km</div>
                <div className="card-title">Est. Cost Per KM</div>
              </div>
              <div className="card-icon fuel-saved-icon"><i className="fas fa-leaf"></i></div>
            </div>
            <div className="card-footer">
              <span><i className="fas fa-chart-line"></i> Efficiency estimate</span>
              <button className="action-btn-small" onClick={() => setFilter('all')}>View</button>
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-value">{bestTruck}</div>
                <div className="card-title">Best Performing Truck</div>
              </div>
              <div className="card-icon fuel-alerts-icon"><i className="fas fa-medal"></i></div>
            </div>
            <div className="card-footer">
              <span><i className="fas fa-chart-line"></i> Lowest cost per liter</span>
              <button className="action-btn-small" onClick={() => setFilter('all')}>Check</button>
            </div>
          </div>
        </div>

        <div className="add-fuel-form">
          <h2 className="section-title">Add Fuel Entry</h2>
          <form onSubmit={addFuelEntry}>
            <div className="form-row">
              <div className="form-group">
                <label><i className="fas fa-truck"></i> Select Truck</label>
                <select name="truck" value={form.truck} onChange={setField} required>
                  <option value="">-- Select Truck --</option>
                  {trucks.map(t => (
                    <option key={t.id} value={t.truck_number || t.id}>{t.truck_number} - {t.truck_type || ''}</option>
                  ))}
                  {trucks.length === 0 && <option disabled>No trucks found</option>}
                </select>
              </div>
              <div className="form-group">
                <label><i className="fas fa-calendar-alt"></i> Date of Refueling</label>
                <input type="date" name="date" value={form.date} onChange={setField} required />
              </div>
              <div className="form-group">
                <label><i className="fas fa-gas-pump"></i> Fuel Amount (Liters)</label>
                <input type="number" name="amount" value={form.amount} onChange={setField} placeholder="Enter liters" min="0.1" step="0.1" required />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label><i className="fas fa-rupee-sign"></i> Total Cost (PKR)</label>
                <input type="number" name="cost" value={form.cost} onChange={setField} placeholder="Enter cost" min="0.01" step="0.01" required />
              </div>
              <div className="form-group">
                <label><i className="fas fa-tachometer-alt"></i> Odometer Reading (km)</label>
                <input type="number" name="odometer" value={form.odometer} onChange={setField} placeholder="Enter km reading" min="0" />
              </div>
              <div className="form-group">
                <label><i className="fas fa-oil-can"></i> Fuel Type</label>
                <select name="fuelType" value={form.fuelType} onChange={setField}>
                  <option value="diesel">Diesel</option>
                  <option value="petrol">Petrol</option>
                  <option value="cng">CNG</option>
                  <option value="electric">Electric Charging</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label><i className="fas fa-sticky-note"></i> Notes (Optional)</label>
              <input type="text" name="notes" value={form.notes} onChange={setField} placeholder="Any additional notes..." />
            </div>
            <div style={{ display: 'flex', gap: 15, marginTop: 25 }}>
              <button type="submit" className="action-btn" disabled={submitting}>
                <i className="fas fa-plus-circle"></i> {submitting ? 'Adding...' : 'Add Fuel Entry'}
              </button>
              <button type="button" className="action-btn" style={{ background: 'var(--gradient-success)' }} onClick={calculateMileage}>
                <i className="fas fa-calculator"></i> Calculate Mileage
              </button>
            </div>
          </form>
        </div>

        <div className="fuel-stats">
          <div className="stat-card">
            <div className="stat-header">
              <div className="stat-title">Fuel Cost per km</div>
              <div className="stat-icon" style={{ background: 'var(--gradient-primary)' }}><i className="fas fa-rupee-sign"></i></div>
            </div>
            <div className="stat-value">PKR {costPerKm}</div>
            <div className="stat-change"><i className="fas fa-chart-line"></i> Estimated from records</div>
          </div>
          <div className="stat-card">
            <div className="stat-header">
              <div className="stat-title">Total Fuel This Month</div>
              <div className="stat-icon" style={{ background: 'var(--gradient-primary)' }}><i className="fas fa-gas-pump"></i></div>
            </div>
            <div className="stat-value">{totalLitersMonth.toFixed(1)} L</div>
            <div className="stat-change"><i className="fas fa-chart-line"></i> Updated from fuel logs</div>
          </div>
          <div className="stat-card">
            <div className="stat-header">
              <div className="stat-title">Best Performing Truck</div>
              <div className="stat-icon" style={{ background: 'var(--gradient-success)' }}><i className="fas fa-medal"></i></div>
            </div>
            <div className="stat-value">{bestTruck}</div>
            <div className="stat-change"><i className="fas fa-tachometer-alt"></i> Lowest cost per liter</div>
          </div>
        </div>

        <div className="fuel-log-section">
          <div className="table-header">
            <h2 className="section-title">Fuel Log</h2>
            <div className="table-actions">
              {['all', 'thisMonth', 'lastMonth', 'highCost'].map(f => (
                <button
                  key={f}
                  className={`filter-btn${filter === f ? ' active' : ''}`}
                  onClick={() => setFilter(f)}
                >
                  {f === 'all' ? 'All' : f === 'thisMonth' ? 'This Month' : f === 'lastMonth' ? 'Last Month' : 'High Cost'}
                </button>
              ))}
              <button className="action-btn" onClick={exportData} style={{ background: 'var(--hover-bg)', color: 'var(--text-secondary)' }}>
                <i className="fas fa-file-export"></i> Export Data
              </button>
            </div>
          </div>
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Date</th><th>Truck</th><th>Fuel Type</th><th>Amount (L)</th>
                  <th>Cost (PKR)</th><th>Odometer</th><th>Notes</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24 }}>Loading...</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24 }}>No fuel entries found</td></tr>
                ) : filtered.map((e, i) => (
                  <tr key={e.id || i}>
                    <td>{e.date}</td>
                    <td>{e.truck}</td>
                    <td>{e.fuel_type || '-'}</td>
                    <td>{e.amount} L</td>
                    <td>PKR {parseFloat(e.cost || 0).toLocaleString()}</td>
                    <td>{e.odometer ? `${e.odometer} km` : '-'}</td>
                    <td>{e.notes || '-'}</td>
                    <td>
                      <button className="action-btn-small" onClick={() => setModal(e)}>
                        <i className="fas fa-eye"></i> View
                      </button>
                    </td>
                  </tr>
                ))}
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
          </div>
        </div>

        {modal && (
          <div className="modal" style={{ display: 'flex', position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9998, alignItems: 'center', justifyContent: 'center' }}>
            <div className="modal-content" style={{ background: 'var(--card-bg)', borderRadius: 12, padding: 28, maxWidth: 480, width: '90%' }}>
              <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2>Fuel Entry Details</h2>
                <button onClick={() => setModal(null)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer' }}>&times;</button>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  {Object.entries(modal).map(([k, v]) => v != null && (
                    <tr key={k} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '8px 4px', fontWeight: 600, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</td>
                      <td style={{ padding: '8px 4px' }}>{String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {toast && (
          <div style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
            background: toast.type === 'error' ? '#e74c3c' : '#27ae60',
            color: '#fff', padding: '12px 20px', borderRadius: 8,
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)', maxWidth: 360,
          }}>
            {toast.msg}
          </div>
        )}
      </div>
    </TransporterLayout>
  )
}
