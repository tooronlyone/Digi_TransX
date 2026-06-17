// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'

const PART_TYPES = [
  { value: 'Tyre',       label: 'WHEELS / TYRES' },
  { value: 'Engine',     label: 'ENGINE COMPONENTS' },
  { value: 'Nut',        label: 'NUTS / BOLTS' },
  { value: 'Brake',      label: 'BRAKE SYSTEM' },
  { value: 'Electrical', label: 'ELECTRICAL SYSTEM' },
  { value: 'Gear',       label: 'TRANSMISSION / GEAR' },
  { value: 'Suspension', label: 'SUSPENSION' },
  { value: 'Coupling',   label: 'TRAILER / COUPLING' },
  { value: 'Body',       label: 'CABIN / BODY' },
  { value: 'Cooling',    label: 'COOLING' },
  { value: 'Safety',     label: 'SAFETY / OTHERS' },
]

const SUBPARTS = {
  Tyre:       ['Front left tyre', 'Front right tyre', 'Rear left outer tyre', 'Rear left inner tyre', 'Rear right outer tyre', 'Rear right inner tyre', 'Trailer axle tyres', 'Spare tyre'],
  Engine:     ['Engine oil filter', 'Engine air filter', 'Fuel filter', 'Radiator', 'Belts (fan belt, AC belt)', 'Turbocharger', 'Injectors', 'Clutch plate', 'Flywheel', 'Engine mountings'],
  Nut:        ['Wheel nuts (front/rear)', 'Axle nuts', 'Body frame bolts', 'Trailer coupling bolts'],
  Brake:      ['Brake pads (front)', 'Brake pads (rear)', 'Brake discs', 'Brake drums', 'Air brake compressor', 'Air brake hoses/pipes', 'Brake chamber', 'Brake fluid'],
  Electrical: ['Headlights', 'Tail lights', 'Indicator lights', 'Cabin interior lights', 'Battery', 'Alternator', 'Wiring harness', 'Trailer connection cable'],
  Gear:       ['Gearbox oil', 'Gear lever assembly', 'Differential oil', 'Clutch master cylinder', 'Clutch slave cylinder'],
  Suspension: ['Leaf springs', 'Shock absorbers', 'U-bolts', 'Bushes'],
  Coupling:   ['Fifth wheel (coupler)', 'Kingpin', 'Container locks/twist locks', 'Trailer frame bolts', 'Landing gear (support legs)'],
  Body:       ['Mirrors', 'Wipers', 'Cabin mountings', 'Seats', 'Dashboard components'],
  Cooling:    ['Radiator', 'Coolant hoses', 'Water pump', 'Thermostat'],
  Safety:     ['Fire extinguisher', 'Reflectors', 'Jack', 'Tool kit'],
}

const EMPTY_FORM = {
  truck_number: '', part_type: '', part_subtype: '', part_location: '',
  old_part_number: '', new_part_number: '', price: '', datetime: '', comment: ''
}

export default function MaintenancePage() {
  const { get, post } = useApi()
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState({ msg: '', type: 'success' })

  // Filters
  const [search, setSearch] = useState('')
  const [partTypeFilter, setPartTypeFilter] = useState('')
  const [truckFilter, setTruckFilter] = useState('')
  const [dateFilter, setDateFilter] = useState('')

  // Expense summary
  const [expPart, setExpPart] = useState('')
  const [expTruck, setExpTruck] = useState('')
  const [expStart, setExpStart] = useState('')
  const [expEnd, setExpEnd] = useState('')
  const [expResult, setExpResult] = useState(null)

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast({ msg: '', type: 'success' }), 3500)
  }

  function loadRecords() {
    setLoading(true)
    get('/api/maintenance')
      .then(data => { if (data.success) setRecords(data.records || []) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadRecords() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.truck_number || !form.part_type || !form.price || !form.datetime) {
      return showToast('Please fill in all required fields', 'error')
    }
    setSubmitting(true)
    try {
      const res = await post('/api/maintenance', {
        truck_number:    form.truck_number,
        maintenance_type: form.part_type,
        part_subtype:    form.part_subtype,
        part_location:   form.part_location,
        old_part_number: form.old_part_number,
        new_part_number: form.new_part_number,
        cost:            parseFloat(form.price),
        service_date:    form.datetime,
        notes:           form.comment,
        status:          'completed',
      })
      if (res.success) {
        showToast('Maintenance record saved!')
        setForm(EMPTY_FORM)
        loadRecords()
      } else {
        showToast(res.message || 'Failed to save record', 'error')
      }
    } catch (e) { showToast('Failed: ' + e.message, 'error') }
    finally { setSubmitting(false) }
  }

  function calculateExpenses() {
    let filtered = records
    if (expPart) filtered = filtered.filter(r => r.maintenance_type === expPart)
    if (expTruck) filtered = filtered.filter(r => (r.truck_number || '').toLowerCase().includes(expTruck.toLowerCase()))
    if (expStart) filtered = filtered.filter(r => (r.service_date || '') >= expStart)
    if (expEnd) filtered = filtered.filter(r => (r.service_date || '') <= expEnd)
    const total = filtered.reduce((sum, r) => sum + parseFloat(r.cost || 0), 0)
    setExpResult({ total, count: filtered.length, avg: filtered.length ? total / filtered.length : 0 })
  }

  const filteredRecords = useMemo(() => {
    const q = search.toLowerCase()
    return records.filter(r => {
      const matchSearch = !q ||
        (r.truck_number || '').toLowerCase().includes(q) ||
        (r.maintenance_type || '').toLowerCase().includes(q) ||
        (r.notes || '').toLowerCase().includes(q)
      const matchPart = !partTypeFilter || r.maintenance_type === partTypeFilter
      const matchTruck = !truckFilter || (r.truck_number || '').toLowerCase().includes(truckFilter.toLowerCase())
      const matchDate = !dateFilter || (r.service_date || '').startsWith(dateFilter)
      return matchSearch && matchPart && matchTruck && matchDate
    })
  }, [records, search, partTypeFilter, truckFilter, dateFilter])

  function statusBadge(status) {
    const map = { completed: { label: 'Completed', color: '#22c55e' }, scheduled: { label: 'Scheduled', color: '#3b82f6' }, overdue: { label: 'Overdue', color: '#ef4444' } }
    const s = map[(status || 'completed').toLowerCase()] || { label: status || 'Unknown', color: '#94a3b8' }
    return <span style={{ background: s.color + '22', color: s.color, padding: '2px 10px', borderRadius: '20px', fontSize: '0.8rem', fontWeight: '600' }}>{s.label}</span>
  }

  const subparts = form.part_type ? (SUBPARTS[form.part_type] || []) : []

  return (
    <TransporterLayout>
      <div className="page-maintenance">
        {toast.msg && (
          <div style={{
            position: 'fixed', top: '1rem', right: '1rem', zIndex: 9999,
            background: toast.type === 'error' ? '#fee2e2' : '#dcfce7',
            color: toast.type === 'error' ? '#dc2626' : '#16a34a',
            padding: '0.75rem 1.25rem', borderRadius: '8px', fontSize: '0.9rem',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
          }}>{toast.msg}</div>
        )}

        <div className="top-bar">
          <div className="page-title">
            <h1>Truck Maintenance Record System</h1>
            <p>Keep track of all parts changes efficiently</p>
          </div>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut"><i className="fas fa-tachometer-alt"></i><span>Dashboard</span></Link>
          <Link to="/transporter/personal-info" className="page-shortcut"><i className="fas fa-id-card"></i><span>Personal Info</span></Link>
          <Link to="/transporter/maintenance" className="page-shortcut active"><i className="fas fa-tools"></i><span>Maintenance</span></Link>
          <Link to="/transporter/fuel" className="page-shortcut"><i className="fas fa-gas-pump"></i><span>Fuel</span></Link>
          <Link to="/transporter/analytics" className="page-shortcut"><i className="fas fa-chart-line"></i><span>Analytics</span></Link>
          <Link to="/transporter/insights" className="page-shortcut"><i className="fas fa-brain"></i><span>Insights</span></Link>
          <Link to="/transporter/jobs/active" className="page-shortcut"><i className="fas fa-shipping-fast"></i><span>Active Jobs</span></Link>
        </div>

        {/* Add Record Form */}
        <section className="card">
          <h2>Add New Part Change Record</h2>
          <form className="form-grid" onSubmit={handleSubmit}>
            <input
              type="text" placeholder="Truck Number *" required
              value={form.truck_number} onChange={e => setForm(p => ({ ...p, truck_number: e.target.value }))} />

            <select required value={form.part_type}
              onChange={e => setForm(p => ({ ...p, part_type: e.target.value, part_subtype: '' }))}>
              <option value="">Part Type *</option>
              {PART_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
            </select>

            {subparts.length > 0 && (
              <select value={form.part_subtype} onChange={e => setForm(p => ({ ...p, part_subtype: e.target.value }))}>
                <option value="">Select {form.part_type} Part</option>
                {subparts.map(sp => <option key={sp} value={sp}>{sp}</option>)}
              </select>
            )}

            <input type="text" placeholder="Part Location (e.g. Front Left) *" required
              value={form.part_location} onChange={e => setForm(p => ({ ...p, part_location: e.target.value }))} />
            <input type="text" placeholder="Old Part Number *" required
              value={form.old_part_number} onChange={e => setForm(p => ({ ...p, old_part_number: e.target.value }))} />
            <input type="text" placeholder="New Part Number *" required
              value={form.new_part_number} onChange={e => setForm(p => ({ ...p, new_part_number: e.target.value }))} />
            <input type="number" placeholder="Price (PKR) *" required min="0"
              value={form.price} onChange={e => setForm(p => ({ ...p, price: e.target.value }))} />
            <input type="datetime-local" required
              value={form.datetime} onChange={e => setForm(p => ({ ...p, datetime: e.target.value }))} />
            <input type="text" placeholder="Comment (optional)" className="full-width"
              value={form.comment} onChange={e => setForm(p => ({ ...p, comment: e.target.value }))} />

            <button type="submit" className="full-width" disabled={submitting}>
              {submitting ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-save"></i> Save Record</>}
            </button>
          </form>
        </section>

        {/* Expense Summary */}
        <section className="card wide-card">
          <h2>Expense Summary</h2>
          <div className="expense-summary">
            <h3>Calculate Total Expenses</h3>
            <div className="expense-filters">
              <select value={expPart} onChange={e => setExpPart(e.target.value)}>
                <option value="">All Part Types</option>
                {PART_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
              </select>
              <input type="text" placeholder="Truck Number (optional)" value={expTruck} onChange={e => setExpTruck(e.target.value)} />
              <div className="date-range-selector">
                <input type="date" value={expStart} onChange={e => setExpStart(e.target.value)} placeholder="Start Date" />
                <span>to</span>
                <input type="date" value={expEnd} onChange={e => setExpEnd(e.target.value)} placeholder="End Date" />
              </div>
              <button className="filter-btn" type="button" onClick={calculateExpenses}>Calculate</button>
              <button className="filter-btn reset-btn" type="button"
                onClick={() => { setExpPart(''); setExpTruck(''); setExpStart(''); setExpEnd(''); setExpResult(null) }}>
                Reset
              </button>
            </div>
            {expResult && (
              <div className="expense-results">
                <div className="expense-card"><h4>Total Expenses</h4><p style={{ fontSize: '1.5rem', fontWeight: '700', color: '#1e293b' }}>Rs. {expResult.total.toLocaleString()}</p></div>
                <div className="expense-card"><h4>Number of Records</h4><p style={{ fontSize: '1.5rem', fontWeight: '700', color: '#1e293b' }}>{expResult.count}</p></div>
                <div className="expense-card"><h4>Average Cost</h4><p style={{ fontSize: '1.5rem', fontWeight: '700', color: '#1e293b' }}>Rs. {expResult.avg.toFixed(0)}</p></div>
              </div>
            )}
          </div>
        </section>

        {/* Records Table */}
        <section className="card wide-card">
          <h2>Maintenance Records</h2>
          <div className="filter-controls">
            <div className="search-bar" style={{ flexGrow: 1 }}>
              <input type="text" placeholder="Search anything..." value={search} onChange={e => setSearch(e.target.value)} />
              <i className="fas fa-search"></i>
            </div>
            <select value={partTypeFilter} onChange={e => setPartTypeFilter(e.target.value)}>
              <option value="">All Part Types</option>
              {PART_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
            </select>
            <input type="text" placeholder="Truck Number" value={truckFilter} onChange={e => setTruckFilter(e.target.value)} />
            <input type="date" value={dateFilter} onChange={e => setDateFilter(e.target.value)} />
            <button className="filter-btn" type="button" onClick={loadRecords}><i className="fas fa-sync-alt"></i> Refresh</button>
            <button className="filter-btn reset-btn" type="button"
              onClick={() => { setSearch(''); setPartTypeFilter(''); setTruckFilter(''); setDateFilter('') }}>
              Reset
            </button>
            <button className="filter-btn print-btn" type="button" onClick={() => window.print()}>
              <i className="fas fa-print"></i> Print
            </button>
          </div>

          <div className="table-responsive" style={{ marginTop: '1rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th><th>Truck No.</th><th>Part Type</th><th>Sub-Part</th>
                  <th>Location</th><th>Price (PKR)</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="7" style={{ textAlign: 'center', padding: '40px' }}><i className="fas fa-spinner fa-spin"></i></td></tr>
                ) : filteredRecords.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '40px' }}>
                      <i className="fas fa-tools" style={{ fontSize: '2rem', color: '#cbd5e1', marginBottom: '10px', display: 'block' }}></i>
                      <p style={{ color: '#94a3b8' }}>No maintenance records found.</p>
                    </td>
                  </tr>
                ) : filteredRecords.map(r => (
                  <tr key={r.id}>
                    <td style={{ fontSize: '0.85rem', color: '#64748b' }}>{(r.service_date || r.created_at || '').slice(0, 10)}</td>
                    <td><strong>{r.truck_number || '—'}</strong></td>
                    <td>{r.maintenance_type || '—'}</td>
                    <td style={{ fontSize: '0.85rem', color: '#64748b' }}>{r.part_subtype || '—'}</td>
                    <td style={{ fontSize: '0.85rem' }}>{r.part_location || '—'}</td>
                    <td style={{ fontWeight: '600' }}>Rs. {parseFloat(r.cost || 0).toLocaleString()}</td>
                    <td>{statusBadge(r.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

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
