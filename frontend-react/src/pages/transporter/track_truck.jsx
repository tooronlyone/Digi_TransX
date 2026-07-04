import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiGet } from '../client/clientUtils'

function statusLabel(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'on_job') return 'On Job'
  if (!s) return 'Inactive'
  return s.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function isActiveStatus(status) {
  const s = String(status || '').toLowerCase()
  return s === 'active' || s === 'available' || s === 'on_job'
}

function LiveMap({ truckId }) {
  const [state, setState] = useState({ loading: true, gpsAvailable: false, lat: null, lon: null, speed: null, timestamp: null, message: '', reason: '', lastUpdated: null })

  async function fetchLocation() {
    try {
      const data = await apiGet(`/api/trucks/${truckId}/live-location`)
      if (data.gps_available) {
        setState({ loading: false, gpsAvailable: true, lat: Number(data.lat), lon: Number(data.lon), speed: data.speed, timestamp: data.timestamp, message: '', reason: '', lastUpdated: new Date().toLocaleTimeString() })
      } else {
        setState(s => ({ ...s, loading: false, gpsAvailable: false, message: data.message || 'Location unavailable.', reason: data.reason || '', lastUpdated: new Date().toLocaleTimeString() }))
      }
    } catch (err) {
      setState(s => ({ ...s, loading: false, gpsAvailable: false, message: `Error: ${err.message || 'Failed to fetch GPS data.'}`, reason: 'fetch_error', lastUpdated: new Date().toLocaleTimeString() }))
    }
  }

  useEffect(() => {
    if (!truckId) return
    fetchLocation()
    const iv = setInterval(fetchLocation, 30000)
    return () => clearInterval(iv)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [truckId])

  if (state.loading) {
    return (
      <div style={{ minHeight: 320, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F9FAFB', borderRadius: 12 }}>
        <div style={{ textAlign: 'center' }}>
          <i className="fas fa-satellite-dish fa-spin" style={{ fontSize: 36, color: '#4F46E5' }}></i>
          <p style={{ marginTop: 12, color: '#6B7280', fontSize: 14 }}>Fetching live location...</p>
        </div>
      </div>
    )
  }

  if (state.gpsAvailable && state.lat && state.lon) {
    const { lat, lon, speed } = state
    const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${lon - 0.01},${lat - 0.01},${lon + 0.01},${lat + 0.01}&layer=mapnik&marker=${lat},${lon}`
    return (
      <div>
        <iframe
          title="Live truck location"
          src={mapUrl}
          style={{ width: '100%', height: 360, border: 'none', borderRadius: 12 }}
        />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 12 }}>
          <span style={{ fontSize: 13, color: '#6B7280' }}>
            <i className="fas fa-location-dot" style={{ color: '#4F46E5', marginRight: 5 }}></i>
            {lat.toFixed(5)}, {lon.toFixed(5)}
          </span>
          {speed != null && (
            <span style={{ fontSize: 13, color: '#6B7280' }}>
              <i className="fas fa-gauge-high" style={{ color: '#10B981', marginRight: 5 }}></i>
              {speed} km/h
            </span>
          )}
          {state.lastUpdated && (
            <span style={{ fontSize: 13, color: '#9CA3AF' }}>
              <i className="fas fa-clock" style={{ marginRight: 5 }}></i>
              Updated {state.lastUpdated}
            </span>
          )}
        </div>
      </div>
    )
  }

  const reasonIcon = {
    no_device: 'fa-microchip',
    provider_not_configured: 'fa-plug-circle-xmark',
    no_data: 'fa-satellite',
    fetch_error: 'fa-triangle-exclamation',
  }[state.reason] || 'fa-location-dot'

  const reasonColor = state.reason === 'fetch_error' ? '#EF4444' : '#F59E0B'

  return (
    <div style={{ minHeight: 320, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#F9FAFB', borderRadius: 12, padding: '36px 24px', textAlign: 'center', border: '2px dashed #E5E7EB' }}>
      <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#FEF3C7', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
        <i className={`fas ${reasonIcon}`} style={{ fontSize: 28, color: reasonColor }}></i>
      </div>
      <p style={{ fontWeight: 700, color: '#111827', fontSize: 15, margin: '0 0 8px' }}>Live Location Unavailable</p>
      <p style={{ color: '#6B7280', fontSize: 13, maxWidth: 360, margin: '0 auto' }}>{state.message}</p>
      {state.lastUpdated && (
        <p style={{ marginTop: 12, fontSize: 12, color: '#9CA3AF' }}>Last checked: {state.lastUpdated}</p>
      )}
      <button
        type="button"
        onClick={fetchLocation}
        style={{ marginTop: 16, background: '#4F46E5', color: '#fff', border: 'none', padding: '8px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
      >
        <i className="fas fa-rotate-right" style={{ marginRight: 6 }}></i>
        Retry
      </button>
    </div>
  )
}

export default function TrackTruck() {
  const { id } = useParams()
  const [truck, setTruck] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) { setLoading(false); return }
    setLoading(true)
    apiGet(`/api/trucks/${id}`)
      .then(json => setTruck(json.truck || json))
      .catch(err => setError(err.message || 'Failed to load truck.'))
      .finally(() => setLoading(false))
  }, [id])

  const truckNumber = truck?.truck_number || '—'
  const truckType = truck?.truck_type || '—'
  const currentStatus = truck?.status || 'inactive'
  const activeStatus = isActiveStatus(currentStatus)

  if (loading) return (
    <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <i className="fas fa-spinner fa-spin" style={{ fontSize: 36, color: '#4F46E5' }}></i>
        <p style={{ marginTop: 12, color: '#6B7280' }}>Loading truck...</p>
      </div>
    </div>
  )

  if (error) return (
    <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', background: '#FEE2E2', border: '1px solid #FECACA', borderRadius: 12, padding: '32px 40px' }}>
        <i className="fas fa-triangle-exclamation" style={{ fontSize: 36, color: '#EF4444' }}></i>
        <p style={{ marginTop: 12, color: '#991B1B', fontWeight: 600 }}>{error}</p>
      </div>
    </div>
  )

  return (
    <div style={{ background: '#F9FAFB', minHeight: '100vh', padding: '28px 24px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' }}>
              {truckNumber} — Truck Tracking
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 14, color: '#6B7280' }}>Live location — always active, regardless of trip status.</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {id && (
              <Link to={`/transporter/trucks/${id}`}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: '#F9FAFB', border: '1px solid #E5E7EB', color: '#374151', padding: '9px 16px', borderRadius: 8, textDecoration: 'none', fontWeight: 600, fontSize: 13 }}>
                <i className="fas fa-circle-info"></i> Truck Details
              </Link>
            )}
          </div>
        </div>

        {/* Stats Row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          {[
            {
              label: 'Truck Status',
              content: (
                <span style={{ display: 'inline-block', padding: '4px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600, background: activeStatus ? '#D1FAE5' : '#F3F4F6', color: activeStatus ? '#065F46' : '#6B7280' }}>
                  {statusLabel(currentStatus)}
                </span>
              ),
            },
            { label: 'Truck Number', value: truckNumber },
            { label: 'Truck Type', value: truckType },
            { label: 'GPS Device', value: truck?.tracking_id || '—', muted: !truck?.tracking_id },
          ].map(({ label, value, content, muted }) => (
            <div key={label} style={{ background: '#fff', borderRadius: 14, padding: '16px 20px', boxShadow: '0 1px 3px rgba(0,0,0,0.07)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{label}</div>
              {content || <div style={{ fontSize: 15, fontWeight: 700, color: muted ? '#9CA3AF' : '#111827' }}>{value}</div>}
            </div>
          ))}
        </div>

        {/* Live Map Card */}
        <div style={{ background: '#fff', borderRadius: 16, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#111827' }}>Live GPS Location</h2>
              <p style={{ margin: '3px 0 0', fontSize: 13, color: '#6B7280' }}>Real-time position from GPS device. Auto-refreshes every 30 seconds.</p>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: '#EEF2FF', color: '#4F46E5', padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600 }}>
              <i className="fas fa-circle" style={{ fontSize: 8 }}></i> LIVE
            </span>
          </div>
          {id ? <LiveMap truckId={id} /> : (
            <p style={{ color: '#6B7280', fontSize: 14 }}>No truck selected.</p>
          )}
        </div>

      </div>
    </div>
  )
}
