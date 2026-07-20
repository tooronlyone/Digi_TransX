import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

/*
 * LocationPicker
 * One detailed address input + a map button. Typing an address and pressing
 * "Locate" geocodes it (OpenStreetMap / Nominatim) and drops a pin. If the map
 * gets it wrong, the user can click anywhere on the map or drag the pin to the
 * exact spot - the address text and coordinates update to match.
 *
 * Uses the installed Leaflet package with OpenStreetMap tiles (no API key).
 *
 * value:    { location: string, lat: number|null, lng: number|null }
 * onChange: (nextValue) => void
 */

const PAKISTAN_CENTER = [30.3753, 69.3451]

export default function LocationPicker({ label, value, onChange, required = false, placeholder }) {
  const val = value || { location: '', lat: null, lng: null }
  const [showMap, setShowMap] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  const mapDivRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const valRef = useRef(val)
  valRef.current = val


  // Initialise / tear down the map when it becomes visible.
  useEffect(() => {
    if (!showMap || !mapDivRef.current || mapRef.current) return
    const start = valRef.current.lat != null ? [valRef.current.lat, valRef.current.lng] : PAKISTAN_CENTER
    const zoom = valRef.current.lat != null ? 14 : 5
    const map = L.map(mapDivRef.current).setView(start, zoom)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map)

    const icon = L.divIcon({
      html: '<i class="fas fa-map-marker-alt" style="font-size:34px;color:#2563eb;text-shadow:0 2px 4px rgba(0,0,0,.35)"></i>',
      className: 'lp-pin',
      iconSize: [34, 34],
      iconAnchor: [17, 32],
    })

    function placeMarker(lat, lng, reverse) {
      if (!markerRef.current) {
        markerRef.current = L.marker([lat, lng], { draggable: true, icon }).addTo(map)
        markerRef.current.on('dragend', () => {
          const p = markerRef.current.getLatLng()
          commit(p.lat, p.lng, true)
        })
      } else {
        markerRef.current.setLatLng([lat, lng])
      }
      if (reverse) reverseGeocode(lat, lng)
    }

    function commit(lat, lng, reverse) {
      onChange({ ...valRef.current, lat: Number(lat.toFixed(6)), lng: Number(lng.toFixed(6)) })
      placeMarker(lat, lng, reverse)
    }

    map.on('click', (e) => commit(e.latlng.lat, e.latlng.lng, true))
    mapRef.current = map
    if (valRef.current.lat != null) placeMarker(valRef.current.lat, valRef.current.lng, false)
    setTimeout(() => map.invalidateSize(), 120)

    return () => {
      map.remove()
      mapRef.current = null
      markerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMap])

  async function reverseGeocode(lat, lng) {
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`, {
        headers: { Accept: 'application/json' },
      })
      const data = await res.json()
      if (data && data.display_name) {
        onChange({ ...valRef.current, location: data.display_name, lat: Number(lat.toFixed(6)), lng: Number(lng.toFixed(6)) })
      }
    } catch (_) { /* keep typed text */ }
  }

  async function locateOnMap() {
    setNote('')
    if (!showMap) setShowMap(true)
    const query = (valRef.current.location || '').trim()
    if (!query) {
      setNote('Type an address first, or click on the map to drop a pin.')
      return
    }
    setBusy(true)
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&countrycodes=pk&limit=1&q=${encodeURIComponent(query)}`,
        { headers: { Accept: 'application/json' } },
      )
      const results = await res.json()
      if (results && results.length) {
        const { lat, lon } = results[0]
        const la = Number(lat), lo = Number(lon)
        onChange({ ...valRef.current, lat: Number(la.toFixed(6)), lng: Number(lo.toFixed(6)) })
        const map = mapRef.current
        if (map) {
          map.setView([la, lo], 15)
          if (markerRef.current) markerRef.current.setLatLng([la, lo])
          else map.fire('click', { latlng: { lat: la, lng: lo } })
        }
        setNote('Pin placed. Drag it or click the map to adjust.')
      } else {
        setNote('Location not found on map. Click on the map to place the pin manually.')
      }
    } catch (_) {
      setNote('Could not search the map right now. You can still place the pin manually.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lp-field">
      <label className="lp-label">
        {label}{required ? ' *' : ''}
      </label>
      <div className="lp-input-row">
        <input
          className="lp-input"
          value={val.location}
          onChange={(e) => onChange({ ...val, location: e.target.value })}
          placeholder={placeholder || 'House / shop, street, area, city'}
          required={required}
        />
        <button type="button" className="lp-map-btn" onClick={locateOnMap} disabled={busy} title="Locate on map">
          <i className={`fas ${busy ? 'fa-spinner fa-spin' : 'fa-map-location-dot'}`} aria-hidden="true"></i>
          <span>{showMap ? 'Locate' : 'Map'}</span>
        </button>
      </div>

      {val.lat != null && (
        <div className="lp-coords">
          <i className="fas fa-location-crosshairs" aria-hidden="true"></i>
          {val.lat.toFixed(5)}, {val.lng.toFixed(5)}
          <button type="button" className="lp-toggle" onClick={() => setShowMap((s) => !s)}>
            {showMap ? 'Hide map' : 'Show map'}
          </button>
        </div>
      )}

      {note && <div className="lp-note">{note}</div>}
      {showMap && <div ref={mapDivRef} className="lp-map" />}
    </div>
  )
}
