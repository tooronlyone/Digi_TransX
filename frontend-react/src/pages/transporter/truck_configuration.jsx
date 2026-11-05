/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import LocationPicker from '../../components/common/LocationPicker'
import Notification from '../../components/common/Notification'
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
  extractHybridStateFromTruck,
} from '../../lib/hybridTruckModel'
import '../../styles/pages/truck-configuration.css'

const MAX_RADIUS_KM = 150

const EMPTY_FORM = {
  truck_number: '',
  truck_company: '',
  truck_model: '',
  truck_type: '',
  max_capacity: '',
  chassis_number: '',
  operating_provinces: [],
  catalog_type_key: '',
  body_style: '',
  payload_min_tons: '0',
  payload_max_tons: '',
  volume_min_cbm: '0',
  volume_max_cbm: '',
  catalog_specs_json: '',
  bed_length_ft: '',
  bed_width_ft: '',
  bed_height_ft: '',
  current_city: '',
  current_lat: '',
  current_lng: '',
  service_radius_km: 100,
  refrigeration_supported: false,
  hazardous_supported: false,
  fragile_supported: true,
  photo: '',
  insurance_photo: '',
  rc_book_photo: '',
  status: 'inactive',
  status_reason_code: '',
  status_reason: '',
}

const REQUIRED = [
  'truck_number',
  'truck_company',
  'truck_model',
  'body_style',
  'payload_max_tons',
  'chassis_number',
  'operating_provinces',
  'current_city',
]

const PROVINCES = [
  'Punjab',
  'Sindh',
  'Khyber Pakhtunkhwa',
  'Balochistan',
  'Islamabad Capital Territory',
  'Gilgit-Baltistan',
  'Azad Jammu and Kashmir',
]

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'on_job', label: 'On Job' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'blocked', label: 'Blocked' },
]

const STATUS_REASONS = [
  { value: 'assigned_job', label: 'On job / assigned to job' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'driver_unavailable', label: 'Driver unavailable' },
  { value: 'route_hold', label: 'Route hold' },
  { value: 'documents_pending', label: 'Documents pending' },
  { value: 'owner_hold', label: 'Owner hold' },
  { value: 'fuel_or_loading', label: 'Fuel/loading wait' },
  { value: 'repair', label: 'Repair required' },
  { value: 'weather_delay', label: 'Weather delay' },
  { value: 'blocked_by_admin', label: 'Blocked by admin' },
]

export default function TruckConfiguration() {
  const { id } = useParams()
  const api = useApi()
  const [form, setForm] = useState(EMPTY_FORM)
  const [sizeClass, setSizeClass] = useState('')
  const [tankerUse, setTankerUse] = useState('')
  const [temperatureRange, setTemperatureRange] = useState('Both')
  const [allowedCommodities, setAllowedCommodities] = useState([])
  const [livestockTypes, setLivestockTypes] = useState([...LIVESTOCK_ANIMAL_OPTIONS])
  const [capacityUnit, setCapacityUnit] = useState('tons')
  const [tankLiters, setTankLiters] = useState('')
  const [capacityWarning, setCapacityWarning] = useState('')
  const [truckPhoto, setTruckPhoto] = useState(null)
  const [insurancePhoto, setInsurancePhoto] = useState(null)
  const [loading, setLoading] = useState(() => Boolean(id))
  const [saving, setSaving] = useState(false)
  const [statusSaving, setStatusSaving] = useState(false)
  const [statusForm, setStatusForm] = useState({ status: 'inactive', reason_code: '' })
  const [toast, setToast] = useState(null)

  function normalizeConfig(raw) {
    const cfg = raw || {}
    const catalogSpecs = cfg.catalog_specs_json
    const hybrid = extractHybridStateFromTruck(cfg)
    return {
      nextForm: {
        ...EMPTY_FORM,
        ...cfg,
        body_style: hybrid.bodyType || cfg.body_style || '',
        payload_max_tons: hybrid.capacityTons || (cfg.payload_max_tons !== undefined && cfg.payload_max_tons !== null ? String(cfg.payload_max_tons) : ''),
        max_capacity: hybrid.capacityTons || (cfg.max_capacity !== undefined && cfg.max_capacity !== null ? String(cfg.max_capacity) : ''),
        operating_provinces: Array.isArray(cfg.operating_provinces)
          ? cfg.operating_provinces
          : typeof cfg.operating_provinces === 'string'
            ? cfg.operating_provinces.split(',').map((s) => s.trim()).filter(Boolean)
            : [],
        catalog_specs_json:
          catalogSpecs && typeof catalogSpecs === 'object'
            ? JSON.stringify(catalogSpecs)
            : catalogSpecs || '',
        photo: cfg.photo || cfg.truck_photo_path || '',
        insurance_photo: cfg.insurance_photo || cfg.insurance_photo_path || '',
        rc_book_photo: cfg.rc_book_photo || cfg.rc_book_photo_path || '',
      },
      hybrid,
    }
  }

  function loadConfig() {
    if (!id) {
      setLoading(false)
      return
    }
    setLoading(true)
    api
      .get(`/api/trucks/${id}/configuration`)
      .then((d) => {
        const cfg = d.configuration || d.truck || d
        applySavedTruck(cfg)
      })
      .catch(() => {
        api
          .get(`/api/trucks/${id}`)
          .then((d) => {
            const t = d.truck || d
            applySavedTruck(t)
          })
          .catch(() => undefined)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!id) return
    let active = true
    api
      .get(`/api/trucks/${id}/configuration`)
      .then((d) => {
        if (!active) return
        const cfg = d.configuration || d.truck || d
        applySavedTruck(cfg)
      })
      .catch(() => {
        api
          .get(`/api/trucks/${id}`)
          .then((d) => {
            if (!active) return
            const t = d.truck || d
            applySavedTruck(t)
          })
          .catch(() => undefined)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [id])

  useEffect(() => {
    document.title = 'Truck Configuration - Digi_TransX'
  }, [])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
  }

  function applySavedTruck(truck) {
    if (truck) {
      const { nextForm, hybrid } = normalizeConfig(truck)
      setForm(nextForm)
      setSizeClass(hybrid.sizeClass)
      setTankerUse(hybrid.tankerUse)
      setTemperatureRange(hybrid.temperatureRange)
      setAllowedCommodities(hybrid.allowedCommodities)
      setLivestockTypes(hybrid.livestockTypes)
      setTankLiters(hybrid.tankLiters)
      setCapacityUnit(hybrid.capacityUnit || 'tons')
      setCapacityWarning('')
      setStatusForm({
        status: nextForm.status || 'inactive',
        reason_code: nextForm.status_reason_code || '',
      })
    }
    setTruckPhoto(null)
    setInsurancePhoto(null)
  }

  function syncCapacityFromTons(tonsVal) {
    const num = Number(tonsVal)
    const str = String(tonsVal)
    setForm((f) => ({ ...f, payload_max_tons: str, max_capacity: str }))
    if (Number.isFinite(num) && num > 0) {
      setTankLiters(String(Math.round(num * 1000)))
    } else {
      setTankLiters('')
    }
  }

  function handleBodyTypeChange(nextBody) {
    setCapacityWarning('')
    setCapacityUnit('tons')
    const presets = SIZE_CLASS_PRESETS[nextBody] || []
    let defaultTons = form.payload_max_tons || '10'
    if (presets.length > 0) {
      const firstPreset = presets[0]
      setSizeClass(firstPreset.key)
      defaultTons = String(firstPreset.default_tons)
    } else {
      setSizeClass('')
    }

    if (nextBody === 'Tanker') {
      const firstTanker = TANKER_USE_OPTIONS[0]
      setTankerUse(firstTanker.key)
      defaultTons = String(firstTanker.default_tons || 12)
      setAllowedCommodities([...firstTanker.allowed_commodities])
    } else if (nextBody === 'Refrigerated') {
      setTemperatureRange('Both')
      const bothOpt = REEFER_TEMPERATURE_OPTIONS.find((t) => t.value === 'Both')
      setAllowedCommodities(
        bothOpt ? [...bothOpt.allowed_commodities] : ['frozen_food', 'fruits_vegetables', 'pharmaceuticals'],
      )
    } else if (nextBody === 'Dumper') {
      defaultTons = '18'
      setAllowedCommodities((CARGO_USE_OPTIONS_BY_BODY.Dumper || []).map((o) => o.key))
    } else if (nextBody === 'Livestock') {
      defaultTons = '10'
      setLivestockTypes([...LIVESTOCK_ANIMAL_OPTIONS])
      setAllowedCommodities(['livestock'])
    } else {
      const cargoOpts = CARGO_USE_OPTIONS_BY_BODY[nextBody] || []
      setAllowedCommodities(cargoOpts.map((o) => o.key))
    }

    setForm((f) => ({
      ...f,
      body_style: nextBody,
      truck_type: nextBody || f.truck_type,
      payload_max_tons: defaultTons,
      max_capacity: defaultTons,
    }))
    setTankLiters(String(Math.round(Number(defaultTons) * 1000)))
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

  const selectedTankerOpt = TANKER_USE_OPTIONS.find((o) => o.key === tankerUse)
  const supportsLiters = form.body_style === 'Tanker' && selectedTankerOpt?.capacity_mode === 'liters'
  const activeCapacityUnit = supportsLiters ? capacityUnit : 'tons'

  function handleCapacityUnitChange(nextUnit) {
    if (nextUnit === capacityUnit) return
    setCapacityUnit(nextUnit)
    setCapacityWarning('')
    if (nextUnit === 'liters') {
      const tonsNum = Number(form.payload_max_tons)
      if (Number.isFinite(tonsNum) && tonsNum > 0) {
        setTankLiters(String(Math.round(tonsNum * 1000)))
      }
    } else {
      const litersNum = Number(tankLiters)
      if (Number.isFinite(litersNum) && litersNum > 0) {
        const tonsStr = String(Number((litersNum / 1000).toFixed(2)))
        setForm((f) => ({ ...f, payload_max_tons: tonsStr, max_capacity: tonsStr }))
      }
    }
  }

  function handleCapacityTonsInput(e) {
    const raw = e.target.value
    if (raw === '') {
      setForm((f) => ({ ...f, payload_max_tons: '', max_capacity: '' }))
      setTankLiters('')
      setCapacityWarning('')
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_CAPACITY_TONS) {
      const clamped = String(MAX_CAPACITY_TONS)
      setForm((f) => ({ ...f, payload_max_tons: clamped, max_capacity: clamped }))
      setTankLiters(String(MAX_CAPACITY_LITERS))
      setCapacityWarning(
        supportsLiters
          ? `Maximum allowed weight is ${MAX_CAPACITY_TONS} Tons. If you want to enter Liters (e.g. 12,000 L), switch the unit to Liters.`
          : `Maximum allowed weight is ${MAX_CAPACITY_TONS} Tons (please enter weight in Tons, not kg).`,
      )
      return
    }
    setCapacityWarning('')
    setForm((f) => ({ ...f, payload_max_tons: raw, max_capacity: raw }))
    if (Number.isFinite(num) && num > 0) {
      setTankLiters(String(Math.round(num * 1000)))
    }
  }

  function handleTankLitersInput(e) {
    const raw = e.target.value
    if (raw === '') {
      setTankLiters('')
      setForm((f) => ({ ...f, payload_max_tons: '', max_capacity: '' }))
      setCapacityWarning('')
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_CAPACITY_LITERS) {
      setTankLiters(String(MAX_CAPACITY_LITERS))
      const clampedTons = String(MAX_CAPACITY_TONS)
      setForm((f) => ({ ...f, payload_max_tons: clampedTons, max_capacity: clampedTons }))
      setCapacityWarning(`Maximum allowed capacity is ${MAX_CAPACITY_LITERS.toLocaleString()} Liters (${MAX_CAPACITY_TONS} Tons).`)
      return
    }
    setCapacityWarning('')
    setTankLiters(raw)
    if (Number.isFinite(num) && num > 0) {
      const tonsStr = String(Number((num / 1000).toFixed(2)))
      setForm((f) => ({ ...f, payload_max_tons: tonsStr, max_capacity: tonsStr }))
    }
  }

  function setField(e) {
    const { name, value } = e.target
    setForm((f) => ({ ...f, [name]: value }))
  }

  function fileName(path) {
    const text = String(path || '')
    return text.split('/').filter(Boolean).pop() || text
  }

  function toggleProvince(province) {
    setForm((f) => {
      const list = f.operating_provinces || []
      return {
        ...f,
        operating_provinces: list.includes(province)
          ? list.filter((p) => p !== province)
          : [...list, province],
      }
    })
  }

  function calcCompleteness() {
    let filled = 0
    for (const key of REQUIRED) {
      const val = form[key]
      if (Array.isArray(val) ? val.length > 0 : val && String(val).trim() !== '') filled++
    }
    return Math.round((filled / REQUIRED.length) * 100)
  }

  function getMissing() {
    return REQUIRED.filter((key) => {
      const val = form[key]
      return Array.isArray(val) ? val.length === 0 : !val || String(val).trim() === ''
    })
  }

  async function handleStatusUpdate() {
    const nextStatus = statusForm.status || 'inactive'
    const missing = getMissing()
    if (nextStatus === 'active' && missing.length > 0) {
      showToast(
        `Complete and save required fields first: ${missing.map((k) => k.replace(/_/g, ' ')).join(', ')}`,
        'error',
      )
      return
    }
    if (nextStatus !== 'active' && !statusForm.reason_code) {
      showToast('Please select a reason before changing status.', 'error')
      return
    }
    setStatusSaving(true)
    try {
      const saved = await api.put(`/api/trucks/${id}/status`, {
        status: nextStatus,
        reason_code: nextStatus === 'active' ? '' : statusForm.reason_code,
      })
      applySavedTruck(saved.truck)
      showToast('Truck status updated successfully')
    } catch (err) {
      showToast(err.message || 'Failed to update status', 'error')
    } finally {
      setStatusSaving(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const missing = getMissing()
    if (missing.length > 0) {
      showToast(`Please fill: ${missing.map((k) => k.replace(/_/g, ' ')).join(', ')}`, 'error')
      return
    }
    const radiusNum = Number(form.service_radius_km)
    if (!Number.isFinite(radiusNum) || radiusNum <= 0 || radiusNum > MAX_RADIUS_KM) {
      showToast(`Service radius must be between 1 and ${MAX_RADIUS_KM} km.`, 'error')
      return
    }
    if ((form.current_lat === '') !== (form.current_lng === '')) {
      showToast('Operating location needs both latitude and longitude, or neither.', 'error')
      return
    }

    const computed = computeHybridTruckPayload({
      bodyStyle: form.body_style,
      sizeClass,
      tankerUse,
      temperatureRange,
      allowedCommodities,
      livestockTypes,
      capacityTons: form.payload_max_tons,
      tankLiters,
      capacityUnit: activeCapacityUnit,
    })

    if (computed.error) {
      showToast(computed.error, 'error')
      return
    }

    setSaving(true)
    try {
      const fd = new FormData()
      const payload = {
        ...form,
        ...computed.fields,
        operating_provinces: form.operating_provinces,
      }
      Object.entries(payload).forEach(([k, v]) => {
        if (Array.isArray(v)) fd.append(k, v.join(','))
        else if (typeof v === 'boolean') fd.append(k, v ? '1' : '0')
        else if (v && typeof v === 'object') fd.append(k, JSON.stringify(v))
        else fd.append(k, v ?? '')
      })
      if (truckPhoto) fd.append('truck_photo', truckPhoto)
      if (insurancePhoto) fd.append('insurance_photo', insurancePhoto)
      const saved = await api.request(`/api/trucks/${id}/configuration`, { method: 'PUT', body: fd })
      applySavedTruck(saved.truck || saved.configuration)
      showToast('Configuration saved successfully')
    } catch (err) {
      showToast(err.message || 'Failed to save configuration', 'error')
    } finally {
      setSaving(false)
    }
  }

  const completeness = calcCompleteness()
  const missing = getMissing()
  const statusLabel = STATUS_OPTIONS.find((item) => item.value === form.status)?.label || form.status || 'Inactive'
  const statusIsActive = form.status === 'active'
  const sizePresets = SIZE_CLASS_PRESETS[form.body_style] || []
  const cargoOptions = CARGO_USE_OPTIONS_BY_BODY[form.body_style] || []
  const preview = form.body_style
    ? computeHybridTruckPayload({
        bodyStyle: form.body_style,
        sizeClass,
        tankerUse,
        temperatureRange,
        allowedCommodities,
        livestockTypes,
        capacityTons: form.payload_max_tons,
        tankLiters,
        capacityUnit: activeCapacityUnit,
      })
    : null

  return (
    <div className="truck-config-page">
      <div className="truck-config-shell">
        <Link
          to="/transporter/trucks"
          className="inline-flex items-center gap-2 text-sm font-semibold text-[#6B7280] hover:text-[#4F46E5]"
        >
          <i className="fas fa-arrow-left" aria-hidden="true"></i>
          Back To My Trucks
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#111827]">Truck Configuration</h1>
            <p className="mt-1 text-sm text-[#6B7280]">
              Configure your truck&apos;s hybrid cargo profile, route permits (operating provinces), location, and status.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="grid min-h-80 place-items-center rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
            <div className="text-center">
              <i className="fas fa-spinner fa-spin text-3xl text-[#4F46E5]" aria-hidden="true"></i>
              <p className="mt-3 text-sm text-[#6B7280]">Loading configuration...</p>
            </div>
          </div>
        ) : (
          <>
            <div className="truck-config-summary-grid">
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <div className="flex items-center gap-4">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-green-50 text-[#10B981]">
                    <i className="fas fa-power-off" aria-hidden="true"></i>
                  </span>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-gray-400">Current Status</div>
                    <span
                      className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
                        statusIsActive ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {statusLabel}
                    </span>
                  </div>
                </div>
              </section>

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <div className="flex items-center gap-4">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-50 text-[#4F46E5]">
                    <i className="fas fa-sliders" aria-hidden="true"></i>
                  </span>
                  <div className="flex-1">
                    <div className="text-xs font-bold uppercase tracking-wide text-gray-400">Configuration</div>
                    <span className="mt-2 inline-flex rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                      {completeness}% Complete
                    </span>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#F3F4F6]">
                      <div className="h-full rounded-full bg-[#4F46E5]" style={{ width: `${completeness}%` }}></div>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            {missing.length > 0 && (
              <div className="rounded-lg border-l-4 border-blue-500 bg-[#EFF6FF] p-4 text-sm text-[#1E40AF]">
                <strong>Required before activating:</strong> {missing.map((k) => k.replace(/_/g, ' ')).join(', ')}
              </div>
            )}

            <form className="truck-config-form" onSubmit={handleSubmit} noValidate>
              {/* SECTION 1: Truck Status */}
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">1. Truck Status</h2>
                <p className="mt-1 text-sm text-[#6B7280]">
                  A truck cannot be set to Active until all required details (including Operating Provinces and Location) are saved.
                </p>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Status</span>
                    <select
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      value={statusForm.status}
                      onChange={(e) =>
                        setStatusForm((s) => ({
                          ...s,
                          status: e.target.value,
                          reason_code: e.target.value === 'active' ? '' : s.reason_code,
                        }))
                      }
                    >
                      {STATUS_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {statusForm.status !== 'active' && (
                    <label className="block">
                      <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Reason</span>
                      <select
                        className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                        value={statusForm.reason_code}
                        onChange={(e) => setStatusForm((s) => ({ ...s, reason_code: e.target.value }))}
                      >
                        <option value="">Select reason</option>
                        {STATUS_REASONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
                {form.status_reason && (
                  <p className="mt-3 text-sm text-[#6B7280]">
                    Last reason: <strong>{form.status_reason}</strong>
                  </p>
                )}
                <div className="mt-5">
                  <button
                    type="button"
                    onClick={handleStatusUpdate}
                    disabled={statusSaving}
                    className="inline-flex items-center gap-2 rounded-lg bg-[#4F46E5] px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    <i className={`fas ${statusSaving ? 'fa-spinner fa-spin' : 'fa-toggle-on'}`}></i>
                    {statusSaving ? 'Updating...' : 'Update Status'}
                  </button>
                </div>
              </section>

              {/* SECTION 2: Truck Identity & Hybrid Smart Matching Setup */}
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">2. Truck Identity &amp; Smart Matching Setup</h2>
                <p className="mt-1 text-sm text-[#6B7280]">
                  Same 3-step hybrid setup as Add Truck — vehicle class, bed dimensions, and CBM volume are configured automatically.
                </p>

                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Number *</span>
                    <input
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      type="text"
                      name="truck_number"
                      value={form.truck_number}
                      onChange={setField}
                      placeholder="Example: LE-1234, ABC 12345"
                      required
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Company *</span>
                    <input
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      type="text"
                      name="truck_company"
                      value={form.truck_company}
                      onChange={setField}
                      placeholder="Example: Hino, ISUZU"
                      required
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Model *</span>
                    <input
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      type="text"
                      name="truck_model"
                      value={form.truck_model}
                      onChange={setField}
                      placeholder="Example: Hino 500, Shehzore, Mazda T3500"
                      required
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Chassis Number *</span>
                    <input
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      type="text"
                      name="chassis_number"
                      value={form.chassis_number}
                      onChange={setField}
                      placeholder="11 to 17 letters/numbers"
                      pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}"
                      required
                    />
                    <span className="mt-1 block text-xs italic text-gray-400">
                      11-17 characters, letters and numbers only (I, O, Q not allowed)
                    </span>
                  </label>

                  <label className="block md:col-span-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Body Type *</span>
                    <select
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      name="body_style"
                      value={form.body_style}
                      onChange={(e) => handleBodyTypeChange(e.target.value)}
                      required
                    >
                      <option value="">Select Body Type</option>
                      {HYBRID_BODY_TYPES.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label} — {option.subtitle}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {/* Preset Cards for Open Body / Box Body / Trailer / Refrigerated */}
                {sizePresets.length > 0 && (
                  <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                    <div className="text-xs font-bold uppercase tracking-wide text-indigo-900">
                      Truck Size / Class Preset *
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      Select your truck&apos;s size class — cargo bed length and volume are configured automatically.
                    </p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {sizePresets.map((preset) => {
                        const active = sizeClass === preset.key
                        return (
                          <button
                            key={preset.key}
                            type="button"
                            onClick={() => handleSizeClassSelect(preset)}
                            className={`flex flex-col items-start justify-between gap-1.5 rounded-xl border p-3.5 text-left transition ${
                              active
                                ? 'border-indigo-600 bg-white ring-2 ring-indigo-500/20'
                                : 'border-gray-200 bg-white hover:border-indigo-300'
                            }`}
                          >
                            <div className="flex w-full items-start justify-between gap-2">
                              <span className="text-sm font-bold text-gray-900">{preset.title}</span>
                              <i
                                className={`fas ${
                                  active ? 'fa-circle-check text-indigo-600' : 'fa-circle text-gray-300'
                                }`}
                              ></i>
                            </div>
                            <span className="text-xs text-gray-500">{preset.specLabel}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Dedicated Tanker Use (Safety-Locked) */}
                {form.body_style === 'Tanker' && (
                  <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                    <div className="text-xs font-bold uppercase tracking-wide text-indigo-900">
                      Dedicated Tanker Use (Safety-Locked) *
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      For hygiene and hazard safety, a tanker is locked to one dedicated cargo category.
                    </p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {TANKER_USE_OPTIONS.map((opt) => {
                        const active = tankerUse === opt.key
                        return (
                          <button
                            key={opt.key}
                            type="button"
                            onClick={() => handleTankerUseSelect(opt)}
                            className={`flex flex-col items-start justify-between gap-2 rounded-xl border p-3.5 text-left transition ${
                              active
                                ? 'border-indigo-600 bg-white ring-2 ring-indigo-500/20'
                                : 'border-gray-200 bg-white hover:border-indigo-300'
                            }`}
                          >
                            <div className="flex w-full items-start justify-between gap-2">
                              <span className="text-sm font-bold text-gray-900">{opt.label}</span>
                              <i
                                className={`fas ${
                                  active ? 'fa-circle-check text-indigo-600' : 'fa-circle text-gray-300'
                                }`}
                              ></i>
                            </div>
                            <span
                              className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                                opt.hazardous ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {opt.badge}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Cooling / Temperature Capability for Refrigerated */}
                {form.body_style === 'Refrigerated' && (
                  <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                    <div className="text-xs font-bold uppercase tracking-wide text-indigo-900">
                      Cooling / Temperature Capability *
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      Chilled-only trucks are protected from deep-frozen (-18°C) meat/ice-cream orders.
                    </p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-3">
                      {REEFER_TEMPERATURE_OPTIONS.map((opt) => {
                        const active = temperatureRange === opt.value
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => handleTemperatureSelect(opt)}
                            className={`flex flex-col items-start justify-between gap-1.5 rounded-xl border p-3.5 text-left transition ${
                              active
                                ? 'border-indigo-600 bg-white ring-2 ring-indigo-500/20'
                                : 'border-gray-200 bg-white hover:border-indigo-300'
                            }`}
                          >
                            <div className="flex w-full items-start justify-between gap-2">
                              <span className="text-sm font-bold text-gray-900">{opt.label}</span>
                              <i
                                className={`fas ${
                                  active ? 'fa-circle-check text-indigo-600' : 'fa-circle text-gray-300'
                                }`}
                              ></i>
                            </div>
                            <span className="text-xs text-gray-500">{opt.subtitle}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Cargo Use Checkboxes for Open Body / Box Body / Trailer / Dumper */}
                {cargoOptions.length > 0 && (
                  <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-bold uppercase tracking-wide text-indigo-900">
                        Truck Use (What cargo does this truck carry?) *
                      </span>
                      <div className="inline-flex gap-2">
                        <button
                          type="button"
                          onClick={() => setAllowedCommodities(cargoOptions.map((o) => o.key))}
                          className="rounded-md border border-indigo-200 bg-white px-2.5 py-1 text-xs font-bold text-indigo-600 hover:bg-indigo-50"
                        >
                          Select All
                        </button>
                        <button
                          type="button"
                          onClick={() => setAllowedCommodities([])}
                          className="rounded-md border border-indigo-200 bg-white px-2.5 py-1 text-xs font-bold text-indigo-600 hover:bg-indigo-50"
                        >
                          Clear
                        </button>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      You will receive client orders matching the cargo uses ticked below.
                    </p>
                    <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                      {cargoOptions.map((opt) => {
                        const checked = allowedCommodities.includes(opt.key)
                        return (
                          <label
                            key={opt.key}
                            className={`flex cursor-pointer items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm font-semibold transition ${
                              checked
                                ? 'border-indigo-600 bg-white text-gray-900'
                                : 'border-gray-200 bg-white text-gray-600'
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-indigo-600"
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

                {/* Livestock Checkboxes */}
                {form.body_style === 'Livestock' && (
                  <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                    <div className="text-xs font-bold uppercase tracking-wide text-indigo-900">Livestock Use *</div>
                    <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
                      {LIVESTOCK_ANIMAL_OPTIONS.map((animal) => {
                        const checked = livestockTypes.includes(animal)
                        return (
                          <label
                            key={animal}
                            className={`flex cursor-pointer items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm font-semibold transition ${
                              checked
                                ? 'border-indigo-600 bg-white text-gray-900'
                                : 'border-gray-200 bg-white text-gray-600'
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-indigo-600"
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

                {/* Dynamic Capacity Input */}
                <div className="mt-5 max-w-lg">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label
                      htmlFor={activeCapacityUnit === 'liters' ? 'configTankLiters' : 'configCapacityTons'}
                      className="text-xs font-bold uppercase tracking-wide text-gray-400"
                    >
                      {activeCapacityUnit === 'liters'
                        ? 'Tank Capacity (Liters) *'
                        : 'Max Weight Capacity (Tons) *'}
                    </label>
                    {supportsLiters && (
                      <div className="inline-flex rounded-lg border border-gray-200 bg-gray-100 p-0.5 text-xs font-bold">
                        <button
                          type="button"
                          onClick={() => handleCapacityUnitChange('tons')}
                          className={`rounded-md px-2.5 py-1 transition ${
                            activeCapacityUnit === 'tons' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500'
                          }`}
                        >
                          Tons (Default)
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCapacityUnitChange('liters')}
                          className={`rounded-md px-2.5 py-1 transition ${
                            activeCapacityUnit === 'liters' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500'
                          }`}
                        >
                          Liters
                        </button>
                      </div>
                    )}
                  </div>

                  {activeCapacityUnit === 'liters' ? (
                    <div className="truck-config-weight-input">
                      <input
                        id="configTankLiters"
                        className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                        type="number"
                        min={MIN_CAPACITY_LITERS}
                        max={MAX_CAPACITY_LITERS}
                        step="100"
                        value={tankLiters}
                        onChange={handleTankLitersInput}
                        placeholder="Example: 12000 (Max 100,000)"
                        required
                      />
                      <span>Liters</span>
                    </div>
                  ) : (
                    <div className="truck-config-weight-input">
                      <input
                        id="configCapacityTons"
                        className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                        type="number"
                        name="payload_max_tons"
                        min={MIN_CAPACITY_TONS}
                        max={MAX_CAPACITY_TONS}
                        step="0.1"
                        value={form.payload_max_tons}
                        onChange={handleCapacityTonsInput}
                        placeholder={`Example: 12 (Max ${MAX_CAPACITY_TONS} Tons)`}
                        required
                      />
                      <span>Tons</span>
                    </div>
                  )}

                  <span className="mt-1.5 block text-xs text-gray-400">
                    {supportsLiters
                      ? `Allowed range: ${MIN_CAPACITY_TONS} – ${MAX_CAPACITY_TONS} Tons (500 – 100,000 Liters).`
                      : `Allowed range: ${MIN_CAPACITY_TONS} – ${MAX_CAPACITY_TONS} Tons.`}
                  </span>

                  {capacityWarning && (
                    <div
                      className="mt-2 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
                      role="alert"
                    >
                      <i className="fas fa-triangle-exclamation"></i>
                      <span>{capacityWarning}</span>
                    </div>
                  )}
                </div>

                {/* Auto-Configured Matching Profile Ready Banner */}
                {preview && !preview.error && (
                  <div className="mt-5 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-100 text-emerald-700">
                      <i className="fas fa-wand-magic-sparkles"></i>
                    </span>
                    <div>
                      <div className="text-xs font-extrabold uppercase tracking-wide text-emerald-900">
                        Matched Vehicle Class (Auto-Set)
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-bold text-emerald-800">
                          <i className="fas fa-tag"></i> {preview.fields.mainUse}
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-bold text-emerald-800">
                          <i className="fas fa-weight-hanging"></i> Up to {preview.fields.payload_max_tons} Tons
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-bold text-emerald-800">
                          <i className="fas fa-cube"></i> {preview.fields.volume_max_cbm} CBM
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-bold text-emerald-800">
                          <i className="fas fa-ruler-horizontal"></i> {preview.fields.bed_length_ft} ft Deck
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </section>

              {/* SECTION 3: Operating Provinces (Route Permit) */}
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-bold text-[#111827]">3. Operating Provinces (Route Permit) *</h2>
                    <p className="mt-1 text-xs text-gray-500">
                      Select the provinces where this truck is legally permitted to operate. Client orders will only match when both pickup and dropoff are within your permitted provinces.
                    </p>
                  </div>
                  <div className="inline-flex gap-2">
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, operating_provinces: [...PROVINCES] }))}
                      className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-bold text-indigo-700 hover:bg-indigo-100"
                    >
                      Select All Provinces
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, operating_provinces: [] }))}
                      className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-bold text-gray-600 hover:bg-gray-50"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {PROVINCES.map((p) => (
                    <label
                      key={p}
                      className="flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border border-[#E5E7EB] bg-white px-4 py-3 text-sm font-semibold text-[#111827] transition hover:border-indigo-200 hover:bg-indigo-50/50"
                    >
                      <input
                        className="h-4 w-4 accent-indigo-600 focus:ring-2 focus:ring-indigo-500"
                        type="checkbox"
                        checked={form.operating_provinces.includes(p)}
                        onChange={() => toggleProvince(p)}
                      />
                      <span>{p}</span>
                    </label>
                  ))}
                </div>
              </section>

              {/* SECTION 4: Operating Location */}
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">4. Operating Location *</h2>
                <p className="mt-1 text-xs text-gray-500">
                  Where this truck is based now. You will only see orders whose pickup is within the service radius of this location.
                </p>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <LocationPicker
                      label="Current location of this truck"
                      value={{
                        location: form.current_city || '',
                        lat: form.current_lat === '' || form.current_lat == null ? null : Number(form.current_lat),
                        lng: form.current_lng === '' || form.current_lng == null ? null : Number(form.current_lng),
                      }}
                      onChange={(next) =>
                        setForm((f) => ({
                          ...f,
                          current_city: next.location || '',
                          current_lat: next.lat == null ? '' : next.lat,
                          current_lng: next.lng == null ? '' : next.lng,
                        }))
                      }
                      placeholder="City / area where the truck is currently parked"
                    />
                  </div>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Service radius (km)</span>
                    <input
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] px-4 py-3 text-sm text-[#111827] outline-none placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-500"
                      type="number"
                      name="service_radius_km"
                      min="1"
                      max={MAX_RADIUS_KM}
                      step="1"
                      value={form.service_radius_km}
                      onChange={setField}
                      placeholder="Default 100"
                    />
                    <span className="mt-1 block text-xs text-gray-400">
                      Default 100 km, maximum {MAX_RADIUS_KM} km.
                    </span>
                  </label>
                </div>
              </section>

              {/* SECTION 5: Documents (Optional) */}
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">5. Documents (Optional)</h2>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <div>
                    <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-5 py-8 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40">
                      <i className="fas fa-cloud-arrow-up text-4xl text-gray-300" aria-hidden="true"></i>
                      <span className="mt-3 font-bold text-[#111827]">Truck Pic</span>
                      <span className="mt-1 text-sm font-semibold text-[#4F46E5]">Choose File</span>
                      <span className="mt-1 text-sm text-gray-400">
                        {truckPhoto ? truckPhoto.name : form.photo ? `Saved: ${fileName(form.photo)}` : 'No file chosen'}
                      </span>
                      <input
                        className="hidden"
                        type="file"
                        accept=".jpg,.jpeg,.png,.webp"
                        onChange={(e) => setTruckPhoto(e.target.files[0] || null)}
                      />
                    </label>
                    <p className="mt-2 text-xs text-gray-400">
                      {truckPhoto ? truckPhoto.name : form.photo ? `Saved truck photo: ${fileName(form.photo)}` : 'No truck photo selected.'}
                    </p>
                    {form.photo && !truckPhoto && (
                      <a
                        href={form.photo}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex text-xs font-semibold text-[#4F46E5]"
                      >
                        View saved truck pic
                      </a>
                    )}
                  </div>
                  <div>
                    <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-5 py-8 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40">
                      <i className="fas fa-file-arrow-up text-4xl text-gray-300" aria-hidden="true"></i>
                      <span className="mt-3 font-bold text-[#111827]">Insurance Paper</span>
                      <span className="mt-1 text-sm font-semibold text-[#4F46E5]">Choose File</span>
                      <span className="mt-1 text-sm text-gray-400">
                        {insurancePhoto
                          ? insurancePhoto.name
                          : form.insurance_photo
                            ? `Saved: ${fileName(form.insurance_photo)}`
                            : 'No file chosen'}
                      </span>
                      <input
                        className="hidden"
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png,.webp"
                        onChange={(e) => setInsurancePhoto(e.target.files[0] || null)}
                      />
                    </label>
                    <p className="mt-2 text-xs text-gray-400">
                      {insurancePhoto
                        ? insurancePhoto.name
                        : form.insurance_photo
                          ? `Saved insurance paper: ${fileName(form.insurance_photo)}`
                          : 'No insurance document selected.'}
                    </p>
                    {form.insurance_photo && !insurancePhoto && (
                      <a
                        href={form.insurance_photo}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex text-xs font-semibold text-[#4F46E5]"
                      >
                        View saved insurance paper
                      </a>
                    )}
                  </div>
                </div>
              </section>

              <div className="truck-config-actions">
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-60"
                  onClick={loadConfig}
                  disabled={loading}
                >
                  <i className="fas fa-sync-alt" aria-hidden="true"></i>
                  Reload
                </button>
                <button
                  type="submit"
                  className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-[#4F46E5] px-5 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60"
                  disabled={saving}
                >
                  <i className="fas fa-save" aria-hidden="true"></i>
                  {saving ? 'Saving...' : 'Save Configuration'}
                </button>
              </div>
            </form>
          </>
        )}

        <Notification type={toast?.type || 'info'} message={toast?.msg} onClose={() => setToast(null)} />
      </div>
    </div>
  )
}
