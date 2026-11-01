import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const PAKISTAN_CENTER = [30.3753, 69.3451]
const EMPTY_LOCATION = Object.freeze({ location: '', lat: null, lng: null })
function coordinates(lat, lng) {
  return Number.isFinite(lat) && lat >= -90 && lat <= 90 && Number.isFinite(lng) && lng >= -180 && lng <= 180
}

export default function LocationPicker({ label, value, onChange, required = false, placeholder }) {
  const val = value || EMPTY_LOCATION
  const [showMap, setShowMap] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const mapDivRef = useRef(null), mapRef = useRef(null), markerRef = useRef(null)
  const valRef = useRef(val), onChangeRef = useRef(onChange), placeMarkerRef = useRef(null)
  const operationRef = useRef(0), abortRef = useRef(null), mountedRef = useRef(false)
  useLayoutEffect(() => { valRef.current = val; onChangeRef.current = onChange }, [val, onChange])
  const hasCoordinates = coordinates(val.lat, val.lng)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false; abortRef.current?.abort() }
  }, [])

  function cancelGeocode() {
    ++operationRef.current
    abortRef.current?.abort()
    abortRef.current = null
    setBusy(false)
  }
  function operation() {
    ++operationRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    return { id: operationRef.current, controller }
  }
  function current(attempt) {
    return mountedRef.current && operationRef.current === attempt.id && !attempt.controller.signal.aborted
  }
  function editAddress(location) {
    cancelGeocode()
    markerRef.current?.remove()
    markerRef.current = null
    setNote(location ? 'Locate this address or select a new pin on the map.' : '')
    const next = { ...valRef.current, location, lat: null, lng: null }
    valRef.current = next
    onChangeRef.current(next)
  }
  async function reverseGeocode(lat, lng) {
    const attempt = operation()
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`, {
        headers: { Accept: 'application/json' }, signal: attempt.controller.signal,
      })
      if (!response.ok) return
      const data = await response.json()
      if (current(attempt) && valRef.current.lat === lat && valRef.current.lng === lng && typeof data.display_name === 'string') {
        const next = { ...valRef.current, location: data.display_name, lat, lng }
        valRef.current = next
        onChangeRef.current(next)
      }
    } catch { /* The manually selected pin remains valid if reverse lookup fails. */ }
  }

  useEffect(() => {
    if (!showMap || !mapDivRef.current || mapRef.current) return undefined
    const selected = coordinates(valRef.current.lat, valRef.current.lng)
    const map = L.map(mapDivRef.current).setView(selected ? [valRef.current.lat, valRef.current.lng] : PAKISTAN_CENTER, selected ? 14 : 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap',
    }).addTo(map)
    const icon = L.divIcon({
      html: '<i class="fas fa-map-marker-alt" style="font-size:34px;color:#2563eb;text-shadow:0 2px 4px rgba(0,0,0,.35)"></i>',
      className: 'lp-pin', iconSize: [34, 34], iconAnchor: [17, 32],
    })
    function commit(lat, lng) {
      const la = Number(Number(lat).toFixed(6))
      const lo = Number((((Number(lng) + 180) % 360 + 360) % 360 - 180).toFixed(6))
      if (!coordinates(la, lo)) return
      cancelGeocode()
      const next = { ...valRef.current, lat: la, lng: lo }
      valRef.current = next
      onChangeRef.current(next)
      placeMarker(la, lo)
      void reverseGeocode(la, lo)
    }
    function placeMarker(lat, lng) {
      if (!markerRef.current) {
        markerRef.current = L.marker([lat, lng], { draggable: true, icon }).addTo(map)
        markerRef.current.on('dragend', () => {
          const position = markerRef.current.getLatLng()
          commit(position.lat, position.lng)
        })
      } else markerRef.current.setLatLng([lat, lng])
    }
    map.on('click', event => commit(event.latlng.lat, event.latlng.lng))
    mapRef.current = map
    placeMarkerRef.current = placeMarker
    if (selected) placeMarker(valRef.current.lat, valRef.current.lng)
    const timer = window.setTimeout(() => map.invalidateSize(), 120)
    return () => {
      window.clearTimeout(timer)
      map.remove()
      mapRef.current = null
      markerRef.current = null
      placeMarkerRef.current = null
    }
    // Map listeners read the current controlled value and callback through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMap])

  async function locateOnMap() {
    setNote('')
    if (!showMap) setShowMap(true)
    const query = (valRef.current.location || '').trim()
    if (!query) {
      setNote('Type an address first, or click on the map to drop a pin.')
      return
    }
    const original = { ...valRef.current }, attempt = operation()
    setBusy(true)
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&countrycodes=pk&limit=1&q=${encodeURIComponent(query)}`, {
        headers: { Accept: 'application/json' }, signal: attempt.controller.signal,
      })
      if (!response.ok) throw new Error('Geocoder unavailable')
      const results = await response.json()
      if (!current(attempt) || valRef.current.location !== original.location
          || valRef.current.lat !== original.lat || valRef.current.lng !== original.lng) return
      const lat = Number(results?.[0]?.lat), lng = Number(results?.[0]?.lon)
      if (coordinates(lat, lng)) {
        const next = { ...valRef.current, lat: Number(lat.toFixed(6)), lng: Number(lng.toFixed(6)) }
        valRef.current = next
        onChangeRef.current(next)
        mapRef.current?.setView([lat, lng], 15)
        placeMarkerRef.current?.(next.lat, next.lng)
        setNote('Pin placed. Drag it or click the map to adjust.')
      } else setNote('Location not found on map. Click on the map to place the pin manually.')
    } catch {
      if (current(attempt)) setNote('Could not search the map right now. You can still place the pin manually.')
    } finally { if (current(attempt)) setBusy(false) }
  }

  return (
    <div className="lp-field">
      <label className="lp-label">{label}{required ? ' *' : ''}</label>
      <div className="lp-input-row">
        <input className="lp-input" value={val.location} onChange={event => editAddress(event.target.value)}
          aria-label={label} placeholder={placeholder || 'House / shop, street, area, city'} required={required} />
        <button type="button" className="lp-map-btn" onClick={locateOnMap} disabled={busy} title="Locate on map" aria-label="Locate on map">
          <i className={`fas ${busy ? 'fa-spinner fa-spin' : 'fa-map-location-dot'}`} aria-hidden="true"></i>
          <span>{showMap ? 'Locate' : 'Map'}</span>
        </button>
      </div>
      {hasCoordinates && <div className="lp-coords">
        <i className="fas fa-location-crosshairs" aria-hidden="true"></i>
        {val.lat.toFixed(5)}, {val.lng.toFixed(5)}
        <button type="button" className="lp-toggle" onClick={() => setShowMap(visible => !visible)}>{showMap ? 'Hide map' : 'Show map'}</button>
      </div>}
      {note && <div className="lp-note">{note}</div>}
      {showMap && <div ref={mapDivRef} className="lp-map" />}
    </div>
  )
}
