import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

export default function TruckDetails() {
  const { id } = useParams()
  const api = useApi()
  const [truck, setTruck] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [fuel, setFuel] = useState([])
  const [loading, setLoading] = useState(true)

  function load() {
    if (!id) {
      setLoading(false)
      return
    }

    setLoading(true)
    Promise.allSettled([
      api.get(`/api/trucks/${id}`),
      api.get(`/api/trucks/${id}/maintenance`).catch(() => api.get('/api/maintenance')),
      api.get(`/api/trucks/${id}/fuel`).catch(() => api.get('/api/fuel')),
    ]).then(([truckRes, maintRes, fuelRes]) => {
      if (truckRes.status === 'fulfilled') {
        setTruck(truckRes.value.truck || truckRes.value)
      }

      if (maintRes.status === 'fulfilled') {
        const records = maintRes.value.records || maintRes.value.maintenance || []
        setMaintenance(records.filter((item) => !id || item.truck === id || item.truck_id === id).slice(0, 5))
      }

      if (fuelRes.status === 'fulfilled') {
        const entries = fuelRes.value.entries || []
        setFuel(entries.filter((item) => !id || item.truck === id).slice(0, 5))
      }
    }).finally(() => setLoading(false))
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [id])

  function calcCompleteness(value) {
    if (!value) return 0
    const required = ['truck_number', 'truck_type', 'max_capacity', 'chassis_number', 'per_km_rate', 'waiting_charge_per_hour']
    const filled = required.filter((key) => value[key] && String(value[key]).trim() !== '').length
    return Math.round((filled / required.length) * 100)
  }

  function statusColor(status) {
    const map = {
      active: '#22c55e',
      available: '#22c55e',
      on_job: '#3b82f6',
      maintenance: '#f59e0b',
      inactive: '#94a3b8',
    }
    return map[(status || '').toLowerCase()] || '#94a3b8'
  }

  function docStatus(value) {
    const docs = [
      { name: 'Truck Photo', key: 'truck_photo_path', fallbackKey: 'photo', type: 'file' },
      { name: 'Insurance Paper', key: 'insurance_photo_path', fallbackKey: 'insurance_photo', type: 'file' },
      { name: 'Chassis Number', key: 'chassis_number', type: 'text' },
    ]
    return docs.map((doc) => {
      const rawValue = value?.[doc.key] || (doc.fallbackKey ? value?.[doc.fallbackKey] : '')
      const textValue = String(rawValue || '').trim()
      const href = doc.type === 'file' && textValue
        ? (/^(https?:)?\/\//i.test(textValue) || textValue.startsWith('/') ? textValue : `/${textValue}`)
        : ''
      return { ...doc, value: textValue, href, uploaded: !!textValue }
    })
  }

  function viewTextDocument(doc) {
    if (!doc?.value) return
    window.alert(`${doc.name}: ${doc.value}`)
  }

  const completeness = calcCompleteness(truck)
  const provinces = truck?.operating_provinces
    ? (typeof truck.operating_provinces === 'string'
        ? truck.operating_provinces.split(',').filter(Boolean)
        : truck.operating_provinces)
    : []

  const readinessItems = [
    { done: !!truck?.truck_number, title: 'Truck Number', desc: 'Plate number registered' },
    { done: !!truck?.truck_type, title: 'Truck Type', desc: 'Vehicle category set' },
    { done: !!truck?.chassis_number, title: 'Chassis Number', desc: 'Required for identity verification' },
    { done: !!truck?.per_km_rate, title: 'Per KM Rate', desc: 'Commercial pricing set' },
    { done: provinces.length > 0, title: 'Operating Provinces', desc: 'At least one province selected' },
    { done: !!truck?.truck_photo_path, title: 'Truck Photo', desc: 'Vehicle image uploaded' },
  ]

  if (loading) {
    return (
      <div className="page-truck-details">
        <div className="truck-state-card">
          <i className="fas fa-spinner fa-spin" style={{ fontSize: 36 }}></i>
          <p style={{ marginTop: 12, color: 'var(--text-secondary)' }}>Loading truck details...</p>
        </div>
      </div>
    )
  }

  if (!truck) {
    return (
      <div className="page-truck-details">
        <div className="truck-state-card">
          <i className="fas fa-exclamation-circle" style={{ fontSize: 48, color: '#e74c3c' }}></i>
          <p style={{ marginTop: 12 }}>Truck not found</p>
          <Link to="/transporter/trucks" className="action-btn" style={{ marginTop: 16 }}>
            Back to My Trucks
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page-truck-details">
        <div className="topbar">
          <div>
            <h1>Truck Details</h1>
            <p>Operational profile, readiness, and recent activity for {truck.truck_number || 'this vehicle'}.</p>
          </div>
        </div>

        <div className="hero-section">
          <div className="hero-copy">
            <div className="hero-kicker">Vehicle Command View</div>
            <h2>{truck.truck_number || 'Truck'} - {truck.truck_type || ''}</h2>
            <p>Capacity: {truck.max_capacity ? `${truck.max_capacity} tons` : '-'} - Driver: {truck.driver_name || '-'}</p>
            <div className="hero-tags">
              <span className="hero-tag"><i className="fas fa-shield-halved"></i> Readiness {completeness}%</span>
              <span className="hero-tag"><i className="fas fa-file-lines"></i> Documents</span>
              <span className="hero-tag"><i className="fas fa-route"></i> Activity</span>
            </div>
          </div>
          <div className="hero-actions">
            <Link className="btn" to={`/transporter/trucks/config/${id}`}>
              <i className="fas fa-pen"></i> Edit Configuration
            </Link>
            <Link className="btn-secondary" to={`/transporter/trucks/${id}/track`}>
              <i className="fas fa-location-crosshairs"></i> Track Truck
            </Link>
            <Link className="btn-secondary" to={`/transporter/trucks/${id}/service`}>
              <i className="fas fa-wrench"></i> Service History
            </Link>
          </div>
        </div>

        <div className="cards-grid">
          <div className="metric-card">
            <div className="metric-icon"><i className="fas fa-signal"></i></div>
            <div className="metric-label">Operating Status</div>
            <div className="metric-value">
              <span
                style={{
                  background: `${statusColor(truck.status)}22`,
                  color: statusColor(truck.status),
                  padding: '3px 12px',
                  borderRadius: 20,
                  fontSize: 13,
                  fontWeight: 600,
                  textTransform: 'capitalize',
                }}
              >
                {truck.status || 'Inactive'}
              </span>
            </div>
            <div className="metric-note">Live status from fleet records.</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><i className="fas fa-sliders"></i></div>
            <div className="metric-label">Configuration</div>
            <div className="metric-value">{completeness}% Complete</div>
            <div className="metric-note">Pricing and provinces must be set.</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><i className="fas fa-circle-check"></i></div>
            <div className="metric-label">Verification</div>
            <div className="metric-value">{truck.truck_photo_path ? 'Documents Uploaded' : 'Pending Upload'}</div>
            <div className="metric-note">Document upload readiness.</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><i className="fas fa-map-location-dot"></i></div>
            <div className="metric-label">Operating Regions</div>
            <div className="metric-value">{provinces.length} Province{provinces.length !== 1 ? 's' : ''}</div>
            <div className="metric-note">{provinces.join(', ') || 'None configured'}</div>
          </div>
        </div>

        <div className="section-grid">
          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Operational Metadata</h3>
                <p>Core technical and pricing information for this truck.</p>
              </div>
            </div>
            <div className="meta-grid">
              {[
                { label: 'Truck Type', value: truck.truck_type },
                { label: 'License Plate', value: truck.truck_number },
                { label: 'Capacity', value: truck.max_capacity ? `${truck.max_capacity} tons` : null },
                { label: 'Chassis Number', value: truck.chassis_number },
                { label: 'Per KM Rate', value: truck.per_km_rate ? `PKR ${truck.per_km_rate}` : null },
                { label: 'Waiting Charge', value: truck.waiting_charge_per_hour ? `PKR ${truck.waiting_charge_per_hour}/hr` : null },
                { label: 'Driver', value: truck.driver_name },
              ].map(({ label, value }) => (
                <div className="meta-item" key={label}>
                  <span className="meta-label">{label}</span>
                  <span className="meta-value">{value || '-'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Readiness Checklist</h3>
                <p>Finish these items to keep the truck activation-safe.</p>
              </div>
            </div>
            <div className="list">
              {readinessItems.map((item) => (
                <div key={item.title} className="list-item">
                  <div className="list-icon">
                    <i
                      className={`fas ${item.done ? 'fa-circle-check' : 'fa-circle-xmark'}`}
                      style={{ color: item.done ? '#22c55e' : '#ef4444' }}
                    ></i>
                  </div>
                  <div className="list-content">
                    <div className="list-title">{item.title}</div>
                    <div className="list-desc">{item.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="section-grid">
          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Document Status</h3>
                <p>Documents needed for verification and dispatch.</p>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Document</th><th>Status</th><th>Action</th></tr>
                </thead>
                <tbody>
                  {docStatus(truck).map((doc) => (
                    <tr key={doc.name}>
                      <td>{doc.name}</td>
                      <td>
                        <span style={{ color: doc.uploaded ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                          {doc.uploaded ? 'Uploaded' : 'Missing'}
                        </span>
                      </td>
                      <td>
                        {doc.uploaded && doc.href ? (
                          <a href={doc.href} target="_blank" rel="noreferrer" className="action-btn-small">
                            View
                          </a>
                        ) : doc.uploaded ? (
                          <button type="button" className="action-btn-small" onClick={() => viewTextDocument(doc)}>
                            View
                          </button>
                        ) : (
                          <Link to={`/transporter/trucks/config/${id}`} className="action-btn-small">
                            Upload
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Capabilities</h3>
                <p>Special capabilities configured for this truck.</p>
              </div>
            </div>
            <div className="list">
              {[
                { icon: 'fa-snowflake', label: 'Refrigeration', enabled: !!truck.refrigeration_supported },
                { icon: 'fa-radiation', label: 'Hazardous Materials', enabled: !!truck.hazardous_supported },
                { icon: 'fa-box-open', label: 'Fragile Goods', enabled: !!truck.fragile_supported },
              ].map((capability) => (
                <div key={capability.label} className="list-item">
                  <div className="list-icon">
                    <i
                      className={`fas ${capability.icon}`}
                      style={{ color: capability.enabled ? '#22c55e' : '#94a3b8' }}
                    ></i>
                  </div>
                  <div className="list-content">
                    <div className="list-title">{capability.label}</div>
                    <div
                      className="list-desc"
                      style={{ color: capability.enabled ? '#22c55e' : '#94a3b8' }}
                    >
                      {capability.enabled ? 'Enabled' : 'Not configured'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="section-grid">
          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Recent Maintenance</h3>
                <p>Latest service records for this truck.</p>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Type</th><th>Date</th><th>Cost</th><th>Status</th><th>Notes</th></tr>
                </thead>
                <tbody>
                  {maintenance.length === 0 ? (
                    <tr><td colSpan={5} style={{ textAlign: 'center', padding: 16 }}>No maintenance records</td></tr>
                  ) : maintenance.map((item, index) => (
                    <tr key={item.id || index}>
                      <td>{item.part_type || item.service_type || '-'}</td>
                      <td>{item.date || '-'}</td>
                      <td>PKR {parseFloat(item.cost || 0).toLocaleString()}</td>
                      <td style={{ textTransform: 'capitalize' }}>{item.status || '-'}</td>
                      <td>{item.notes || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="feature-panel">
            <div className="section-head">
              <div>
                <h3>Recent Fuel Activity</h3>
                <p>Fuel records for this truck.</p>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Date</th><th>Amount (L)</th><th>Cost</th><th>Odometer</th></tr>
                </thead>
                <tbody>
                  {fuel.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', padding: 16 }}>No fuel records</td></tr>
                  ) : fuel.map((item, index) => (
                    <tr key={item.id || index}>
                      <td>{item.date || '-'}</td>
                      <td>{item.amount} L</td>
                      <td>PKR {parseFloat(item.cost || 0).toLocaleString()}</td>
                      <td>{item.odometer ? `${item.odometer} km` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
      </div>
  )
}
