import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import TripOperationalActions from '../../components/business/TripOperationalActions'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import { apiGet, apiSend } from '../client/clientUtils'

export default function DriverActiveTrip() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <OwnedDriverActiveTrip key={String(user.id)} />
}

function OwnedDriverActiveTrip() {
  const [activeAssignment, setActiveAssignment] = useState(null)
  const [tracking, setTracking] = useState(false)
  const [lastCoords, setLastCoords] = useState(null)
  const [pingsCount, setPingsCount] = useState(0)
  const [error, setError] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const watchIdRef = useRef(null)
  const streamRef = useRef(0)
  const mountedRef = useRef(false)
  const pingAbortRef = useRef(null)

  useEffect(() => {
    mountedRef.current = true
    let current = true
    const controller = new AbortController()
    apiGet('/api/driver/me', { signal: controller.signal }).then(result => {
      if (current) setActiveAssignment((result.recent_trips || []).find(trip => ['accepted', 'in_progress'].includes(trip.status)) || null)
    }).catch(failure => { if (current) setError(failure.message || 'Unable to load your active assignment.') })
    return () => {
      current = false
      mountedRef.current = false
      controller.abort()
      pingAbortRef.current?.abort()
      if (watchIdRef.current !== null) navigator.geolocation?.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
  }, [])

  function haltTracking() {
    ++streamRef.current
    pingAbortRef.current?.abort()
    if (watchIdRef.current !== null) navigator.geolocation.clearWatch(watchIdRef.current)
    watchIdRef.current = null
  }
  async function sendPing(position, stream) {
    if (!mountedRef.current || stream !== streamRef.current) return
    const lat = position.coords.latitude, lng = position.coords.longitude
    const speed = position.coords.speed ? Number((position.coords.speed * 3.6).toFixed(1)) : 0
    const heading = position.coords.heading || 0, altitude = position.coords.altitude ?? null
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lng) || lng < -180 || lng > 180) {
      setError('The device returned invalid coordinates. Wait for a new GPS fix.')
      return
    }
    setLastCoords({ lat, lng, speed, heading, time: new Date().toLocaleTimeString() })
    const controller = new AbortController()
    pingAbortRef.current?.abort()
    pingAbortRef.current = controller
    try {
      await apiSend('/api/driver/gps/ping', {
        assignment_id: activeAssignment.id, lat, lng, speed_kmh: speed, heading, altitude,
      }, 'POST', (url, options) => fetch(url, { ...options, signal: controller.signal }))
      if (!mountedRef.current || stream !== streamRef.current || controller.signal.aborted) return
      setPingsCount(count => count + 1)
      setStatusMsg('Live location recorded for your accepted trip.')
    } catch (failure) {
      if (!mountedRef.current || stream !== streamRef.current || controller.signal.aborted) return
      if ([401, 403, 404, 409].includes(failure.status)) {
        haltTracking()
        setTracking(false)
        setActiveAssignment(null)
        setStatusMsg('')
        setError(failure.message || 'Your assignment is no longer active. Accept a current trip before tracking.')
      } else setError(failure.message || 'Location could not be recorded. Please retry.')
    }
  }
  function startStreaming() {
    if (!activeAssignment) { setError('Accept an active trip invitation before broadcasting GPS.'); return }
    if (!navigator.geolocation) { setError('Geolocation is not supported by your browser/device.'); return }
    if (watchIdRef.current !== null) return
    const stream = ++streamRef.current
    const success = position => { void sendPing(position, stream) }
    const failure = problem => {
      if (!mountedRef.current || stream !== streamRef.current) return
      haltTracking(); setTracking(false); setStatusMsg('')
      setError(`GPS Error: ${problem.message}`)
    }
    setError(''); setStatusMsg('Acquiring GPS fix...'); setTracking(true)
    navigator.geolocation.getCurrentPosition(success, failure)
    watchIdRef.current = navigator.geolocation.watchPosition(success, failure, {
      enableHighAccuracy: true, timeout: 10000, maximumAge: 0,
    })
  }
  function stopStreaming() {
    haltTracking(); setTracking(false); setStatusMsg('GPS streaming paused.')
  }

  return (
    <div>
      <TripOperationalActions key={`safety:${activeAssignment?.id || 'none'}`} assignment={activeAssignment} />
      <div className="driver-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Live GPS Trip Console</h1>
            <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
              Stream your smartphone's real-time GPS location directly to the Transporter &amp; Customer tracking map.
            </p>
          </div>

          <div>
            {tracking ? (
              <button
                type="button"
                onClick={stopStreaming}
                style={{
                  background: '#ef4444',
                  color: 'white',
                  border: 'none',
                  padding: '12px 24px',
                  borderRadius: '8px',
                  fontWeight: 700,
                  fontSize: '1rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <i className="fas fa-pause"></i> Stop GPS Streaming
              </button>
            ) : (
              <button
                type="button"
                onClick={startStreaming}
                disabled={!activeAssignment}
                style={{
                  background: '#16a34a',
                  color: 'white',
                  border: 'none',
                  padding: '12px 24px',
                  borderRadius: '8px',
                  fontWeight: 700,
                  fontSize: '1rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <i className="fas fa-satellite-dish"></i> Start Live GPS Broadcast
              </button>
            )}
          </div>
        </div>

        {!activeAssignment && <p className="mt-4 text-sm text-slate-600">Accept an active trip invitation in <Link to="/driver/trips" className="font-semibold text-indigo-700">Trip Requests</Link> before broadcasting GPS.</p>}
        {activeAssignment && <p className="mt-4 text-sm text-slate-600">Accepted assignment #{activeAssignment.id} · Truck {activeAssignment.truck_number}</p>}
        {error && (
          <div style={{ marginTop: '16px', padding: '12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#b91c1c' }}>
            {error}
          </div>
        )}

        <div style={{ marginTop: '24px', padding: '20px', background: tracking ? '#f0fdf4' : '#f8fafc', border: `1px solid ${tracking ? '#bbf7d0' : '#e2e8f0'}`, borderRadius: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="gps-live-indicator">
              <span className="gps-pulse-dot" style={{ background: tracking ? '#16a34a' : '#94a3b8' }}></span>
              <span>{tracking ? 'GPS BROADCAST ACTIVE' : 'BROADCAST STANDBY'}</span>
            </div>
            <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Total Pings Sent: <strong>{pingsCount}</strong></span>
          </div>

          {lastCoords ? (
            <div style={{ marginTop: '16px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
              <div style={{ background: 'white', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>LATITUDE</span>
                <p style={{ margin: '2px 0 0 0', fontWeight: 700 }}>{lastCoords.lat.toFixed(6)}</p>
              </div>
              <div style={{ background: 'white', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>LONGITUDE</span>
                <p style={{ margin: '2px 0 0 0', fontWeight: 700 }}>{lastCoords.lng.toFixed(6)}</p>
              </div>
              <div style={{ background: 'white', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>SPEED</span>
                <p style={{ margin: '2px 0 0 0', fontWeight: 700 }}>{lastCoords.speed} km/h</p>
              </div>
              <div style={{ background: 'white', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>LAST SYNC</span>
                <p style={{ margin: '2px 0 0 0', fontWeight: 700 }}>{lastCoords.time}</p>
              </div>
            </div>
          ) : (
            <p style={{ marginTop: '12px', color: '#64748b', fontSize: '0.9rem' }}>
              Press &quot;Start Live GPS Broadcast&quot; when beginning your journey. Ensure your phone allows location access.
            </p>
          )}

          {statusMsg && (
            <p style={{ margin: '14px 0 0 0', fontSize: '0.85rem', color: '#16a34a', fontWeight: 600 }}>
              <i className="fas fa-check-circle"></i> {statusMsg}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
