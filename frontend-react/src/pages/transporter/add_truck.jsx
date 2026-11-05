import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LocationPicker from '../../components/common/LocationPicker'
import { getCsrfToken } from '../client/clientUtils'
import {
  HYBRID_BODY_TYPES,
  SIZE_CLASS_PRESETS,
  TANKER_USE_OPTIONS,
  REEFER_TEMPERATURE_OPTIONS,
  CARGO_USE_OPTIONS_BY_BODY,
  LIVESTOCK_ANIMAL_OPTIONS,
  MIN_CAPACITY_TONS,
  MAX_CAPACITY_TONS,
  MIN_CAPACITY_LITERS,
  MAX_CAPACITY_LITERS,
  computeHybridTruckPayload,
} from '../../lib/hybridTruckModel'
import '../../styles/pages/add-truck.css'

const EMPTY_LOCATION = { location: '', lat: null, lng: null }
const DEFAULT_RADIUS_KM = 100
const MAX_RADIUS_KM = 150

export default function AddTruck() {
  const navigate = useNavigate()
  const [bodyType, setBodyType] = useState('')
  const [sizeClass, setSizeClass] = useState('')
  const [tankerUse, setTankerUse] = useState('')
  const [temperatureRange, setTemperatureRange] = useState('Both')
  const [allowedCommodities, setAllowedCommodities] = useState([])
  const [livestockTypes, setLivestockTypes] = useState([...LIVESTOCK_ANIMAL_OPTIONS])
  const [capacityUnit, setCapacityUnit] = useState('tons')
  const [capacityTons, setCapacityTons] = useState('')
  const [tankLiters, setTankLiters] = useState('')
  const [capacityWarning, setCapacityWarning] = useState('')
  const [location, setLocation] = useState(EMPTY_LOCATION)
  const [radius, setRadius] = useState(String(DEFAULT_RADIUS_KM))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  function syncCapacityFromTons(tonsVal) {
    const num = Number(tonsVal)
    setCapacityTons(String(tonsVal))
    if (Number.isFinite(num) && num > 0) {
      setTankLiters(String(Math.round(num * 1000)))
    } else {
      setTankLiters('')
    }
  }

  function handleBodyTypeChange(nextBody) {
    setBodyType(nextBody)
    setError('')
    setCapacityWarning('')
    setCapacityUnit('tons')

    const presets = SIZE_CLASS_PRESETS[nextBody] || []
    if (presets.length > 0) {
      const firstPreset = presets[0]
      setSizeClass(firstPreset.key)
      syncCapacityFromTons(firstPreset.default_tons)
    } else {
      setSizeClass('')
    }

    if (nextBody === 'Tanker') {
      const firstTanker = TANKER_USE_OPTIONS[0]
      setTankerUse(firstTanker.key)
      const defTons = firstTanker.default_tons || (firstTanker.default_liters || 12000) / 1000
      syncCapacityFromTons(defTons)
      setAllowedCommodities([...firstTanker.allowed_commodities])
    } else if (nextBody === 'Refrigerated') {
      setTemperatureRange('Both')
      const bothOpt = REEFER_TEMPERATURE_OPTIONS.find((t) => t.value === 'Both')
      setAllowedCommodities(bothOpt ? [...bothOpt.allowed_commodities] : ['frozen_food', 'fruits_vegetables', 'pharmaceuticals'])
    } else if (nextBody === 'Dumper') {
      syncCapacityFromTons(18)
      setAllowedCommodities((CARGO_USE_OPTIONS_BY_BODY.Dumper || []).map((o) => o.key))
    } else if (nextBody === 'Livestock') {
      syncCapacityFromTons(10)
      setLivestockTypes([...LIVESTOCK_ANIMAL_OPTIONS])
      setAllowedCommodities(['livestock'])
    } else {
      const cargoOpts = CARGO_USE_OPTIONS_BY_BODY[nextBody] || []
      setAllowedCommodities(cargoOpts.map((o) => o.key))
    }
  }

  function handleSizeClassSelect(preset) {
    setSizeClass(preset.key)
    setCapacityWarning('')
    syncCapacityFromTons(preset.default_tons)
  }

  function handleTankerUseSelect(option) {
    setTankerUse(option.key)
    setCapacityWarning('')
    if (option.capacity_mode !== 'liters') {
      setCapacityUnit('tons')
    }
    setAllowedCommodities([...option.allowed_commodities])
    const defTons = option.default_tons || (option.default_liters || 15000) / 1000
    syncCapacityFromTons(defTons)
  }

  function handleCapacityUnitChange(nextUnit) {
    if (nextUnit === capacityUnit) return
    setCapacityUnit(nextUnit)
    setCapacityWarning('')
    if (nextUnit === 'liters') {
      const tonsNum = Number(capacityTons)
      if (Number.isFinite(tonsNum) && tonsNum > 0) {
        setTankLiters(String(Math.round(tonsNum * 1000)))
      }
    } else {
      const litersNum = Number(tankLiters)
      if (Number.isFinite(litersNum) && litersNum > 0) {
        setCapacityTons(String(Number((litersNum / 1000).toFixed(2))))
      }
    }
  }

  const selectedTankerOpt = TANKER_USE_OPTIONS.find((o) => o.key === tankerUse)
  const supportsLiters = bodyType === 'Tanker' && selectedTankerOpt?.capacity_mode === 'liters'
  const activeCapacityUnit = supportsLiters ? capacityUnit : 'tons'

  function handleCapacityTonsInput(e) {
    const raw = e.target.value
    if (raw === '') {
      setCapacityTons('')
      setTankLiters('')
      setCapacityWarning('')
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_CAPACITY_TONS) {
      setCapacityTons(String(MAX_CAPACITY_TONS))
      setTankLiters(String(MAX_CAPACITY_LITERS))
      setCapacityWarning(
        supportsLiters
          ? `Maximum allowed weight is ${MAX_CAPACITY_TONS} Tons. If you want to enter Liters (e.g. 12,000 L), switch the unit to Liters.`
          : `Maximum allowed weight is ${MAX_CAPACITY_TONS} Tons (please enter weight in Tons, not kg).`,
      )
      return
    }
    setCapacityWarning('')
    setCapacityTons(raw)
    if (Number.isFinite(num) && num > 0) {
      setTankLiters(String(Math.round(num * 1000)))
    }
  }

  function handleTankLitersInput(e) {
    const raw = e.target.value
    if (raw === '') {
      setTankLiters('')
      setCapacityTons('')
      setCapacityWarning('')
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_CAPACITY_LITERS) {
      setTankLiters(String(MAX_CAPACITY_LITERS))
      setCapacityTons(String(MAX_CAPACITY_TONS))
      setCapacityWarning(`Maximum allowed capacity is ${MAX_CAPACITY_LITERS.toLocaleString()} Liters (${MAX_CAPACITY_TONS} Tons).`)
      return
    }
    setCapacityWarning('')
    setTankLiters(raw)
    if (Number.isFinite(num) && num > 0) {
      setCapacityTons(String(Number((num / 1000).toFixed(2))))
    }
  }

  function handleTemperatureSelect(opt) {
    setTemperatureRange(opt.value)
    setAllowedCommodities([...opt.allowed_commodities])
  }

  function toggleCommodity(key) {
    setAllowedCommodities((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    )
  }

  function toggleLivestock(animal) {
    setLivestockTypes((prev) =>
      prev.includes(animal) ? prev.filter((a) => a !== animal) : [...prev, animal],
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess('')

    const form = e.target
    const data = new FormData(form)

    const hasLat = location.lat != null && location.lng != null
    const radiusNum = Number(radius)
    if (!Number.isFinite(radiusNum) || radiusNum <= 0 || radiusNum > MAX_RADIUS_KM) {
      setError(`Service radius must be between 1 and ${MAX_RADIUS_KM} km.`)
      return
    }
    data.set('current_city', location.location || '')
    data.set('current_lat', hasLat ? String(location.lat) : '')
    data.set('current_lng', hasLat ? String(location.lng) : '')
    data.set('service_radius_km', String(radiusNum))

    const computed = computeHybridTruckPayload({
      bodyStyle: bodyType,
      sizeClass,
      tankerUse,
      temperatureRange,
      allowedCommodities,
      livestockTypes,
      capacityTons,
      tankLiters,
      capacityUnit: activeCapacityUnit,
    })

    if (computed.error) {
      setError(computed.error)
      return
    }

    Object.entries(computed.fields).forEach(([k, v]) => {
      data.set(k, v)
    })

    setSubmitting(true)

    try {
      const csrf = await getCsrfToken()
      const res = await fetch('/api/trucks', {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': csrf },
        body: data,
      })
      const result = await res.json()

      if (result.success) {
        setSuccess(result.message || 'Truck registered. Invite a driver from an assigned trip; the driver must accept.')
        form.reset()
        setBodyType('')
        setSizeClass('')
        setTankerUse('')
        setAllowedCommodities([])
        setCapacityUnit('tons')
        setCapacityTons('')
        setTankLiters('')
        setCapacityWarning('')
        setLocation(EMPTY_LOCATION)
        setRadius(String(DEFAULT_RADIUS_KM))
        setTimeout(() => navigate('/transporter/trucks'), 1500)
      } else {
        setError(result.message || 'Failed to register truck. Please check your details.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const sizePresets = SIZE_CLASS_PRESETS[bodyType] || []
  const cargoOptions = CARGO_USE_OPTIONS_BY_BODY[bodyType] || []
  const preview = bodyType
    ? computeHybridTruckPayload({
        bodyStyle: bodyType,
        sizeClass,
        tankerUse,
        temperatureRange,
        allowedCommodities,
        livestockTypes,
        capacityTons,
        tankLiters,
        capacityUnit: activeCapacityUnit,
      })
    : null

  return (
    <div className="page-add-truck">
      <div className="page-title">
        <div>
          <h1>Register <span>New Truck</span></h1>
          <p>Select your truck&apos;s body type, size preset, and cargo use for automatic order matching</p>
        </div>
      </div>

      {error && (
        <div className="addtruck-alert addtruck-alert--error" role="alert">
          <i className="fas fa-exclamation-circle"></i> {error}
        </div>
      )}
      {success && (
        <div className="addtruck-alert addtruck-alert--success" role="status">
          <i className="fas fa-check-circle"></i> {success}
        </div>
      )}

      <form id="truckForm" onSubmit={handleSubmit}>
        <div className="form-card">
          <div className="card-header">
            <div className="card-icon"><i className="fas fa-truck"></i></div>
            <div>
              <h2 className="card-title">Truck Identity &amp; Smart Matching Setup</h2>
              <p className="card-subtitle">Basic registration details and what this truck transports</p>
            </div>
          </div>

          <div className="fields-grid">
            <div className="form-group">
              <label htmlFor="truckNumber" className="required">Truck Number</label>
              <input
                type="text"
                id="truckNumber"
                name="truckNumber"
                required
                placeholder="Example: LE-1234, ABC 12345"
              />
            </div>

            <div className="form-group">
              <label htmlFor="truckCompany" className="required">Truck Company</label>
              <input
                type="text"
                id="truckCompany"
                name="truckCompany"
                required
                placeholder="Example: Hino, ISUZU, Master"
              />
            </div>

            <div className="form-group">
              <label htmlFor="truckModel" className="required">Truck Model</label>
              <input
                type="text"
                id="truckModel"
                name="truckModel"
                required
                placeholder="Example: Hino 500, Shehzore, Mazda T3500"
              />
            </div>

            <div className="form-group">
              <label htmlFor="chassisNumber" className="required">Chassis Number</label>
              <input
                type="text"
                id="chassisNumber"
                name="chassisNumber"
                required
                pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}"
                placeholder="11 to 17 letters/numbers from vehicle documents"
              />
              <small>11-17 characters, letters and numbers only (I, O, Q not allowed)</small>
            </div>

            <div className="form-group full-width">
              <label htmlFor="bodyType" className="required">Body Type</label>
              <select
                id="bodyType"
                name="body_style"
                required
                value={bodyType}
                onChange={(e) => handleBodyTypeChange(e.target.value)}
              >
                <option value="" disabled>Select Body Type</option>
                {HYBRID_BODY_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} — {option.subtitle}
                  </option>
                ))}
              </select>
            </div>

            {sizePresets.length > 0 && (
              <div className="form-group full-width body-detail-panel">
                <label className="required">Truck Size / Class Preset</label>
                <small className="panel-helper-text">
                  Select your truck&apos;s size class — cargo bed length and volume are configured automatically.
                </small>
                <div className="preset-cards-grid">
                  {sizePresets.map((preset) => {
                    const active = sizeClass === preset.key
                    return (
                      <button
                        key={preset.key}
                        type="button"
                        onClick={() => handleSizeClassSelect(preset)}
                        className={`preset-card ${active ? 'preset-card--active' : ''}`}
                      >
                        <div className="preset-card__top">
                          <span className="preset-card__title">{preset.title}</span>
                          <i className={`fas ${active ? 'fa-circle-check' : 'fa-circle'}`}></i>
                        </div>
                        <span className="preset-card__meta">{preset.specLabel}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {bodyType === 'Tanker' && (
              <div className="form-group full-width body-detail-panel">
                <label className="required">Dedicated Tanker Use (Safety-Locked)</label>
                <small className="panel-helper-text">
                  For hygiene and hazard safety, a tanker is locked to one dedicated cargo category.
                </small>
                <div className="preset-cards-grid">
                  {TANKER_USE_OPTIONS.map((opt) => {
                    const active = tankerUse === opt.key
                    return (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => handleTankerUseSelect(opt)}
                        className={`preset-card ${active ? 'preset-card--active' : ''}`}
                      >
                        <div className="preset-card__top">
                          <span className="preset-card__title">{opt.label}</span>
                          <i className={`fas ${active ? 'fa-circle-check' : 'fa-circle'}`}></i>
                        </div>
                        <span className={`preset-card__badge ${opt.hazardous ? 'preset-card__badge--warn' : 'preset-card__badge--safe'}`}>
                          {opt.badge}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {bodyType === 'Refrigerated' && (
              <div className="form-group full-width body-detail-panel">
                <label className="required">Cooling / Temperature Capability</label>
                <small className="panel-helper-text">
                  Chilled-only trucks are protected from deep-frozen (-18°C) meat/ice-cream orders.
                </small>
                <div className="preset-cards-grid">
                  {REEFER_TEMPERATURE_OPTIONS.map((opt) => {
                    const active = temperatureRange === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => handleTemperatureSelect(opt)}
                        className={`preset-card ${active ? 'preset-card--active' : ''}`}
                      >
                        <div className="preset-card__top">
                          <span className="preset-card__title">{opt.label}</span>
                          <i className={`fas ${active ? 'fa-circle-check' : 'fa-circle'}`}></i>
                        </div>
                        <span className="preset-card__meta">{opt.subtitle}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {cargoOptions.length > 0 && (
              <div className="form-group full-width body-detail-panel">
                <div className="panel-header-row">
                  <label className="required">Truck Use (What cargo does this truck carry?)</label>
                  <div className="panel-quick-actions">
                    <button
                      type="button"
                      className="panel-link-btn"
                      onClick={() => setAllowedCommodities(cargoOptions.map((o) => o.key))}
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      className="panel-link-btn"
                      onClick={() => setAllowedCommodities([])}
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <small className="panel-helper-text">
                  You will receive client orders matching the cargo uses ticked below.
                </small>
                <div className="choice-grid">
                  {cargoOptions.map((opt) => {
                    const checked = allowedCommodities.includes(opt.key)
                    return (
                      <label key={opt.key} className={`choice-pill ${checked ? 'choice-pill--checked' : ''}`}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleCommodity(opt.key)}
                        />
                        <span>{opt.label}</span>
                      </label>
                    )
                  })}
                </div>
              </div>
            )}

            {bodyType === 'Livestock' && (
              <div className="form-group full-width body-detail-panel">
                <label className="required">Livestock Use</label>
                <div className="choice-grid">
                  {LIVESTOCK_ANIMAL_OPTIONS.map((animal) => {
                    const checked = livestockTypes.includes(animal)
                    return (
                      <label key={animal} className={`choice-pill ${checked ? 'choice-pill--checked' : ''}`}>
                        <input
                          type="checkbox"
                          name="livestock_type"
                          value={animal}
                          checked={checked}
                          onChange={() => toggleLivestock(animal)}
                        />
                        <span>{animal}</span>
                      </label>
                    )
                  })}
                </div>
              </div>
            )}

            {bodyType && (
              <div className="form-group full-width">
                <div className="single-capacity-box">
                  <div className="capacity-header-row">
                    <label
                      htmlFor={activeCapacityUnit === 'liters' ? 'tankLiters' : 'capacityTons'}
                      className="required"
                    >
                      {activeCapacityUnit === 'liters'
                        ? 'Tank Capacity (Liters)'
                        : 'Max Weight Capacity (Tons)'}
                    </label>
                    {supportsLiters && (
                      <div className="capacity-unit-toggle" role="group" aria-label="Capacity Unit">
                        <button
                          type="button"
                          className={`capacity-unit-btn ${activeCapacityUnit === 'tons' ? 'capacity-unit-btn--active' : ''}`}
                          onClick={() => handleCapacityUnitChange('tons')}
                        >
                          Tons (Default)
                        </button>
                        <button
                          type="button"
                          className={`capacity-unit-btn ${activeCapacityUnit === 'liters' ? 'capacity-unit-btn--active' : ''}`}
                          onClick={() => handleCapacityUnitChange('liters')}
                        >
                          Liters
                        </button>
                      </div>
                    )}
                  </div>

                  {activeCapacityUnit === 'liters' ? (
                    <>
                      <div className="single-capacity-input-wrap">
                        <input
                          id="tankLiters"
                          type="number"
                          min={MIN_CAPACITY_LITERS}
                          max={MAX_CAPACITY_LITERS}
                          step="100"
                          required
                          value={tankLiters}
                          onChange={handleTankLitersInput}
                          placeholder="Example: 12000 (Max 100,000)"
                        />
                        <span className="single-capacity-unit">Liters</span>
                      </div>
                      <small>
                        Allowed range: <strong>{MIN_CAPACITY_LITERS.toLocaleString()} – {MAX_CAPACITY_LITERS.toLocaleString()} Liters</strong>. Auto-converted to{' '}
                        <strong>
                          {Number(tankLiters) > 0
                            ? `${(Number(tankLiters) / 1000).toFixed(1)} Tons (~${(Number(tankLiters) / 1000).toFixed(1)} CBM)`
                            : 'Tons & CBM'}
                        </strong>{' '}
                        for order matching.
                      </small>
                    </>
                  ) : (
                    <>
                      <div className="single-capacity-input-wrap">
                        <input
                          id="capacityTons"
                          type="number"
                          min={MIN_CAPACITY_TONS}
                          max={MAX_CAPACITY_TONS}
                          step="0.1"
                          required
                          value={capacityTons}
                          onChange={handleCapacityTonsInput}
                          placeholder={`Example: 12 (Max ${MAX_CAPACITY_TONS} Tons)`}
                        />
                        <span className="single-capacity-unit">Tons</span>
                      </div>
                      {supportsLiters ? (
                        <small>
                          Allowed range: <strong>{MIN_CAPACITY_TONS} – {MAX_CAPACITY_TONS} Tons</strong>
                          {Number(capacityTons) > 0
                            ? ` (~${Math.round(Number(capacityTons) * 1000).toLocaleString()} Liters)`
                            : ''}
                          . You can also switch to <strong>Liters</strong> above.
                        </small>
                      ) : (
                        <small>
                          Allowed range: <strong>{MIN_CAPACITY_TONS} – {MAX_CAPACITY_TONS} Tons</strong>. Pre-filled from your selected preset — any client order up to this weight will match.
                        </small>
                      )}
                    </>
                  )}

                  {capacityWarning && (
                    <div className="capacity-limit-warning" role="alert">
                      <i className="fas fa-triangle-exclamation"></i>
                      <span>{capacityWarning}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {preview && !preview.error && (
              <div className="form-group full-width">
                <div className="smart-match-summary">
                  <div className="smart-match-summary__icon">
                    <i className="fas fa-wand-magic-sparkles"></i>
                  </div>
                  <div className="smart-match-summary__body">
                    <div className="smart-match-summary__title">
                      Auto-Configured Matching Profile Ready
                    </div>
                    <div className="smart-match-summary__pills">
                      <span className="smart-pill">
                        <i className="fas fa-tag"></i> {preview.fields.mainUse}
                      </span>
                      <span className="smart-pill">
                        <i className="fas fa-weight-hanging"></i> Up to {preview.fields.payload_max_tons} Tons
                      </span>
                      <span className="smart-pill">
                        <i className="fas fa-cube"></i> {preview.fields.volume_max_cbm} CBM
                      </span>
                      <span className="smart-pill">
                        <i className="fas fa-ruler-horizontal"></i> {preview.fields.bed_length_ft} ft Deck
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="form-card">
          <div className="card-header">
            <div className="card-icon card-icon-green"><i className="fas fa-location-dot"></i></div>
            <div>
              <h2 className="card-title">Operating Location</h2>
              <p className="card-subtitle">
                Where this truck is based now. You will only see orders whose pickup is within
                the service radius of this location.
              </p>
            </div>
          </div>

          <div className="fields-grid">
            <div className="form-group full-width">
              <LocationPicker
                label="Current location of this truck"
                value={location}
                onChange={setLocation}
                placeholder="City / area where the truck is currently parked"
              />
            </div>

            <div className="form-group">
              <label htmlFor="service_radius_km">Service radius (km)</label>
              <input
                type="number" id="service_radius_km" min="1" max={MAX_RADIUS_KM} step="1"
                value={radius} onChange={e => setRadius(e.target.value)}
                placeholder={`Default ${DEFAULT_RADIUS_KM}`}
              />
              <small>How far this truck will travel to a pickup. Default {DEFAULT_RADIUS_KM} km, maximum {MAX_RADIUS_KM} km.</small>
            </div>
          </div>
        </div>

        <button type="submit" className="btn btn-block" disabled={submitting}>
          {submitting
            ? <><i className="fas fa-spinner fa-spin"></i> Registering...</>
            : <><i className="fas fa-save"></i> Register Truck</>
          }
        </button>
      </form>
    </div>
  )
}
