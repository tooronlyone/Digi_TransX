import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const S = {
  page: { background: '#F9FAFB', minHeight: '100vh', padding: '28px 24px', fontFamily: 'inherit' },
  card: { background: '#FFFFFF', borderRadius: 16, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', padding: '20px 24px' },
  badge: (color, bg) => ({ background: bg, color, padding: '3px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, display: 'inline-block' }),
  label: { fontSize: 11, fontWeight: 600, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 },
  value: { fontSize: 15, fontWeight: 600, color: '#111827' },
  divider: { borderBottom: '1px solid #F3F4F6', margin: 0 },
}

const statusBadge = (status) => {
  const s = (status || '').toLowerCase()
  if (s === 'active' || s === 'available') return S.badge('#065F46', '#D1FAE5')
  if (s === 'on_job') return S.badge('#1D4ED8', '#DBEAFE')
  if (s === 'maintenance') return S.badge('#92400E', '#FEF3C7')
  return S.badge('#374151', '#F3F4F6')
}

export default function TruckDetails() {
  const { id } = useParams()
  const api = useApi()
  const [truck, setTruck] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [fuel, setFuel] = useState([])
  const [loading, setLoading] = useState(true)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [id])

  function load() {
    if (!id) { setLoading(false); return }
    setLoading(true)
    Promise.allSettled([
      api.get(`/api/trucks/${id}`),
      api.get(`/api/trucks/${id}/maintenance`).catch(() => ({ status: 'rejected' })),
      api.get(`/api/trucks/${id}/fuel`).catch(() => ({ status: 'rejected' })),
    ]).then(([truckRes, maintRes, fuelRes]) => {
      if (truckRes.status === 'fulfilled') setTruck(truckRes.value.truck || truckRes.value)
      if (maintRes.status === 'fulfilled') {
        const records = maintRes.value.records || maintRes.value.maintenance || []
        setMaintenance(records.filter(r => !id || r.truck === id || r.truck_id === id).slice(0, 5))
      }
      if (fuelRes.status === 'fulfilled') {
        const entries = fuelRes.value.entries || []
        setFuel(entries.filter(r => !id || r.truck === id).slice(0, 5))
      }
    }).finally(() => setLoading(false))
  }

  function calcCompleteness(t) {
    if (!t) return 0
    const required = ['truck_number', 'truck_type', 'capacity_tons', 'chassis_number']
    const filled = required.filter(k => t[k] && String(t[k]).trim() !== '').length
    return Math.round((filled / required.length) * 100)
  }

  function docStatus(t) {
    return [
      { name: 'Truck Photo', key: 'truck_photo_path', type: 'file' },
      { name: 'Insurance Paper', key: 'insurance_photo_path', type: 'file' },
      { name: 'Chassis Number', key: 'chassis_number', type: 'text' },
    ].map(doc => {
      const raw = String(t?.[doc.key] || '').trim()
      const href = doc.type === 'file' && raw ? (raw.startsWith('/') || /^https?:/.test(raw) ? raw : `/${raw}`) : ''
      return { ...doc, value: raw, href, uploaded: !!raw }
    })
  }

  function viewText(doc) { if (doc?.value) window.alert(`${doc.name}: ${doc.value}`) }

  if (loading) return (
    <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ ...S.card, textAlign: 'center', padding: 48 }}>
        <i className="fas fa-spinner fa-spin" style={{ fontSize: 32, color: '#4F46E5' }}></i>
        <p style={{ marginTop: 12, color: '#6B7280' }}>Loading truck details...</p>
      </div>
    </div>
  )

  if (!truck) return (
    <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ ...S.card, textAlign: 'center', padding: 48 }}>
        <i className="fas fa-exclamation-circle" style={{ fontSize: 40, color: '#EF4444' }}></i>
        <p style={{ marginTop: 12, fontWeight: 600, color: '#111827' }}>Truck not found</p>
        <Link to="/transporter/trucks" style={{ display: 'inline-block', marginTop: 16, background: '#4F46E5', color: '#fff', padding: '8px 20px', borderRadius: 8, textDecoration: 'none', fontWeight: 600, fontSize: 14 }}>
          Back to My Trucks
        </Link>
      </div>
    </div>
  )

  const completeness = calcCompleteness(truck)
  const provinces = truck.operating_provinces
    ? (typeof truck.operating_provinces === 'string' ? truck.operating_provinces.split(',').filter(Boolean) : truck.operating_provinces)
    : []

  const readinessItems = [
    { done: !!truck.truck_number, title: 'Truck Number', desc: 'Plate number registered' },
    { done: !!truck.truck_type, title: 'Truck Type', desc: 'Vehicle category set' },
    { done: !!truck.chassis_number, title: 'Chassis Number', desc: 'Required for identity verification' },
    { done: !!truck.capacity_tons, title: 'Truck Capacity', desc: 'Payload capacity set' },
    { done: provinces.length > 0, title: 'Operating Provinces', desc: 'At least one province selected' },
    { done: !!truck.truck_photo_path, title: 'Truck Photo', desc: 'Vehicle image uploaded' },
  ]

  const docs = docStatus(truck)
  const capabilities = [
    { icon: 'fa-snowflake', label: 'Refrigeration', enabled: !!truck.refrigeration_supported },
    { icon: 'fa-radiation', label: 'Hazardous Materials', enabled: !!truck.hazardous_supported },
    { icon: 'fa-box-open', label: 'Fragile Goods', enabled: !!truck.fragile_supported },
  ]

  const gap = { display: 'flex', flexDirection: 'column', gap: 24 }
  const row = (minW = 220) => ({ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${minW}px, 1fr))`, gap: 16 })

  return (
    <>
    <div style={S.page}>
      <div style={gap}>

        {/* A — Identity Header */}
        <div style={{ ...S.card, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#4F46E5', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
              Vehicle Command View
            </div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' }}>
              {truck.truck_number || 'Truck'} — {truck.truck_type || ''}
            </h1>
            <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <span style={S.badge('#374151', '#F3F4F6')}>
                <i className="fas fa-weight-hanging" style={{ marginRight: 5 }}></i>
                {truck.capacity_tons ? `${truck.capacity_tons} tons` : 'Capacity —'}
              </span>
              <span style={S.badge('#374151', '#F3F4F6')}>
                <i className="fas fa-id-card" style={{ marginRight: 5 }}></i>
                Driver: {truck.driver_name || '—'}
              </span>
            </div>
            <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <span style={S.badge('#065F46', '#D1FAE5')}>
                <i className="fas fa-shield-halved" style={{ marginRight: 5 }}></i>
                Readiness {completeness}%
              </span>
              <span style={S.badge('#3730A3', '#E0E7FF')}>
                <i className="fas fa-file-lines" style={{ marginRight: 5 }}></i>
                Documents
              </span>
              <span style={S.badge('#374151', '#F3F4F6')}>
                <i className="fas fa-route" style={{ marginRight: 5 }}></i>
                Activity
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link to={`/transporter/trucks/config/${id}`}
              style={{ background: '#4F46E5', color: '#fff', padding: '9px 18px', borderRadius: 8, textDecoration: 'none', fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 7 }}>
              <i className="fas fa-pen"></i> Edit Configuration
            </Link>
            <Link to={`/transporter/trucks/${id}/track`}
              style={{ background: '#F9FAFB', color: '#374151', border: '1px solid #E5E7EB', padding: '9px 18px', borderRadius: 8, textDecoration: 'none', fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 7 }}>
              <i className="fas fa-location-crosshairs"></i> Track Truck
            </Link>
          </div>
        </div>

        {/* B — 4-Stat Grid */}
        <div style={row(200)}>
          <div style={S.card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className="fas fa-power-off" style={{ color: '#4F46E5', fontSize: 15 }}></i>
              </div>
              <span style={S.label}>Operating Status</span>
            </div>
            <span style={statusBadge(truck.status)}>{truck.status || 'Inactive'}</span>
            <p style={{ margin: '10px 0 0', fontSize: 12, color: '#6B7280' }}>Live status from fleet records.</p>
          </div>

          <div style={S.card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className="fas fa-sliders" style={{ color: '#4F46E5', fontSize: 15 }}></i>
              </div>
              <span style={S.label}>Configuration</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', marginBottom: 10 }}>{completeness}% Complete</div>
            <div style={{ background: '#F3F4F6', borderRadius: 99, height: 6, overflow: 'hidden' }}>
              <div style={{ background: completeness === 100 ? '#10B981' : '#4F46E5', width: `${completeness}%`, height: '100%', borderRadius: 99, transition: 'width .3s' }}></div>
            </div>
          </div>

          <div style={S.card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: truck.truck_photo_path ? '#D1FAE5' : '#FEF3C7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className={`fas fa-shield-${truck.truck_photo_path ? 'halved' : 'blank'}`} style={{ color: truck.truck_photo_path ? '#065F46' : '#92400E', fontSize: 15 }}></i>
              </div>
              <span style={S.label}>Verification</span>
            </div>
            <span style={truck.truck_photo_path ? S.badge('#065F46', '#D1FAE5') : S.badge('#92400E', '#FEF3C7')}>
              {truck.truck_photo_path ? 'Documents Uploaded' : 'Pending Upload'}
            </span>
            <p style={{ margin: '10px 0 0', fontSize: 12, color: '#6B7280' }}>Document upload readiness.</p>
          </div>

          <div style={S.card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className="fas fa-map-location-dot" style={{ color: '#4F46E5', fontSize: 15 }}></i>
              </div>
              <span style={S.label}>Operating Regions</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', marginBottom: 6 }}>
              {provinces.length} Province{provinces.length !== 1 ? 's' : ''}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: '#6B7280' }}>{provinces.join(', ') || 'None configured'}</p>
          </div>
        </div>

        {/* C & D — Metadata + Readiness */}
        <div style={row(300)}>
          <div style={S.card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#111827' }}>Operational Metadata</h3>
            <p style={{ margin: '0 0 18px', fontSize: 13, color: '#6B7280' }}>Core technical information.</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '16px 20px' }}>
              {[
                { label: 'Truck Type', value: truck.truck_type },
                { label: 'License Plate', value: truck.truck_number },
                { label: 'Capacity', value: truck.capacity_tons ? `${truck.capacity_tons} tons` : null },
                { label: 'Chassis Number', value: truck.chassis_number },
                { label: 'Driver', value: truck.driver_name },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div style={S.label}>{label}</div>
                  <div style={S.value}>{value || '—'}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={S.card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#111827' }}>Readiness Checklist</h3>
            <p style={{ margin: '0 0 14px', fontSize: 13, color: '#6B7280' }}>Complete these items to activate the truck.</p>
            <div>
              {readinessItems.map((item, i) => (
                <div key={item.title}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 0' }}>
                    <i className={`fas ${item.done ? 'fa-circle-check' : 'fa-circle-xmark'}`}
                      style={{ fontSize: 18, color: item.done ? '#10B981' : '#EF4444', flexShrink: 0 }}></i>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: item.done ? '#111827' : '#374151' }}>{item.title}</div>
                      <div style={{ fontSize: 12, color: '#6B7280' }}>{item.desc}</div>
                    </div>
                  </div>
                  {i < readinessItems.length - 1 && <div style={S.divider}></div>}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* E & F — Documents + Capabilities */}
        <div style={row(300)}>
          <div style={S.card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#111827' }}>Document Status</h3>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6B7280' }}>Documents needed for verification and dispatch.</p>
            <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #F3F4F6' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 100px', background: '#F3F4F6', padding: '10px 16px' }}>
                {['DOCUMENT', 'STATUS', 'ACTION'].map(h => (
                  <span key={h} style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', letterSpacing: '0.06em' }}>{h}</span>
                ))}
              </div>
              {docs.map((doc, i) => (
                <div key={doc.name}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 100px', padding: '12px 16px', alignItems: 'center' }}>
                    <span style={{ fontSize: 14, color: '#111827', fontWeight: 500 }}>{doc.name}</span>
                    <span style={doc.uploaded ? S.badge('#065F46', '#D1FAE5') : S.badge('#991B1B', '#FEE2E2')}>
                      {doc.uploaded ? 'Uploaded' : 'Missing'}
                    </span>
                    <span>
                      {doc.uploaded && doc.href ? (
                        <a href={doc.href} target="_blank" rel="noreferrer"
                          style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', color: '#374151', padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>
                          View
                        </a>
                      ) : doc.uploaded ? (
                        <button type="button" onClick={() => viewText(doc)}
                          style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', color: '#374151', padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                          View
                        </button>
                      ) : (
                        <Link to={`/transporter/trucks/config/${id}`}
                          style={{ background: '#4F46E5', color: '#fff', padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>
                          Upload
                        </Link>
                      )}
                    </span>
                  </div>
                  {i < docs.length - 1 && <div style={S.divider}></div>}
                </div>
              ))}
            </div>
          </div>

          <div style={S.card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#111827' }}>Capabilities</h3>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6B7280' }}>Special handling configured for this truck.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {capabilities.map(cap => (
                <div key={cap.label} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 10, background: cap.enabled ? '#F0FDF4' : '#F9FAFB', border: `1px solid ${cap.enabled ? '#BBF7D0' : '#F3F4F6'}` }}>
                  <i className={`fas ${cap.icon}`} style={{ fontSize: 16, color: cap.enabled ? '#10B981' : '#9CA3AF', width: 20, textAlign: 'center' }}></i>
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#111827', flex: 1 }}>{cap.label}</span>
                  <span style={cap.enabled ? S.badge('#065F46', '#D1FAE5') : S.badge('#6B7280', '#F3F4F6')}>
                    {cap.enabled ? '✓ Enabled' : '— Not configured'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

      </div>
    </div>
    <footer style={{ borderTop: '1px solid #E5E7EB', background: '#FFFFFF', padding: '20px 24px', textAlign: 'center' }}>
      <p style={{ margin: '0 0 8px', color: '#9CA3AF', fontSize: 13 }}>© 2026 Digi_TransX Transport Services. All rights reserved.</p>
      <div style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '4px 8px' }}>
        {[['About Us', '/transporter/about'], ['Contact', '/transporter/contact'], ['Terms & Conditions', '/transporter/terms'], ['Privacy Policy', '/transporter/privacy'], ['Help Center', '/transporter/help']].map(([label, to], i, arr) => (
          <span key={label} style={{ color: '#9CA3AF', fontSize: 13 }}>
            <Link to={to} style={{ color: '#9CA3AF', textDecoration: 'none' }}>{label}</Link>
            {i < arr.length - 1 && <span style={{ marginLeft: 8, color: '#E5E7EB' }}>|</span>}
          </span>
        ))}
      </div>
    </footer>
    </>
  )
}
