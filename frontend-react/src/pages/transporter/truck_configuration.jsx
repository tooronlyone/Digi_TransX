/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import '../../styles/pages/truck-configuration.css'

const EMPTY_FORM = {
  truck_number: '', truck_company: '', truck_model: '', truck_type: '', max_capacity: '', chassis_number: '',
  operating_provinces: [],
  catalog_type_key: '', body_style: '', payload_min_tons: '', payload_max_tons: '',
  volume_min_cbm: '', volume_max_cbm: '', catalog_specs_json: '',
  bed_length_ft: '', bed_width_ft: '', bed_height_ft: '',
  tracking_id: '', driver_name: '', driver_cnic: '',
  refrigeration_supported: true, hazardous_supported: true, fragile_supported: true,
  photo: '', insurance_photo: '', rc_book_photo: '',
  status: 'inactive', status_reason_code: '', status_reason: '',
}

const REQUIRED = ['truck_number', 'truck_company', 'truck_model', 'body_style', 'payload_min_tons', 'payload_max_tons', 'chassis_number', 'operating_provinces']

const PROVINCES = [
  'Punjab', 'Sindh', 'Khyber Pakhtunkhwa', 'Balochistan',
  'Islamabad Capital Territory', 'Gilgit-Baltistan', 'Azad Jammu and Kashmir',
]

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'on_job', label: 'On Job' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'blocked', label: 'Blocked' },
]

const BODY_STYLE_OPTIONS = ['Open Body', 'Box Body', 'Trailer', 'Tanker', 'Refrigerated', 'Dumper', 'Livestock', 'Car Carrier', 'Other']

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

const FALLBACK_TRUCK_TYPES = [
  { type_key: 'mini_pickup', display_name: 'Mini pickup', common_uses: ['Last-mile retail supply', 'Cartons'], payload_min_tons: 0.5, payload_max_tons: 0.7, volume_min_cbm: 2, volume_max_cbm: 3, typical_body_style: 'Low-side deck', class_segment: 'Small urban cargo' },
  { type_key: 'light_truck_2_3_5_ton', display_name: 'Light truck 2-3.5 ton', common_uses: ['Branch replenishment', 'Consumer goods'], payload_min_tons: 2, payload_max_tons: 3.5, volume_min_cbm: 10, volume_max_cbm: 18, typical_body_style: 'Open bed / dry box', class_segment: 'Light rigid truck' },
  { type_key: 'light_truck_3_5_5_ton', display_name: 'Light truck 3.5-5 ton', common_uses: ['Retail distribution', 'Packaging'], payload_min_tons: 3.5, payload_max_tons: 5, volume_min_cbm: 15, volume_max_cbm: 24, typical_body_style: 'Open bed / dry box', class_segment: 'Light rigid truck' },
  { type_key: 'medium_rigid_truck_5_9_ton', display_name: 'Medium rigid truck 5-9 ton', common_uses: ['General cargo', 'Textile'], payload_min_tons: 5, payload_max_tons: 9, volume_min_cbm: 20, volume_max_cbm: 36, typical_body_style: 'Rigid cargo body', class_segment: 'Medium rigid truck' },
  { type_key: 'heavy_rigid_truck_9_15_ton', display_name: 'Heavy rigid truck 9-15 ton', common_uses: ['Long-route cargo', 'Industrial goods'], payload_min_tons: 9, payload_max_tons: 15, volume_min_cbm: 30, volume_max_cbm: 55, typical_body_style: 'Rigid cargo body', class_segment: 'Heavy rigid truck' },
  { type_key: 'heavy_rigid_truck_15_25_ton', display_name: 'Heavy rigid truck 15-25 ton', common_uses: ['Heavy cargo', 'Bulk industrial loads'], payload_min_tons: 15, payload_max_tons: 25, volume_min_cbm: 40, volume_max_cbm: 70, typical_body_style: 'Rigid cargo body', class_segment: 'Heavy rigid truck' },
  { type_key: 'flatbed_trailer_open_semi_trailer', display_name: 'Flatbed trailer / open semi-trailer', common_uses: ['Steel', 'Machinery'], payload_min_tons: 20, payload_max_tons: 45, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Open flatbed', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'container_carrier_skeletal_trailer', display_name: 'Container carrier / skeletal trailer', common_uses: ['Container transport'], payload_min_tons: 20, payload_max_tons: 30, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Skeletal semi-trailer', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'low_bed_low_loader_trailer', display_name: 'Low-bed / low-loader trailer', common_uses: ['Heavy machinery', 'Oversized loads'], payload_min_tons: 25, payload_max_tons: 60, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Low-bed trailer', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'fuel_oil_tanker', display_name: 'Fuel / oil tanker', common_uses: ['Petrol', 'Diesel', 'Furnace oil'], payload_min_tons: 8, payload_max_tons: 35, volume_min_cbm: 10, volume_max_cbm: 45, typical_body_style: 'Tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'milk_tanker', display_name: 'Milk tanker', common_uses: ['Raw milk', 'Dairy liquids'], payload_min_tons: 5, payload_max_tons: 28, volume_min_cbm: 6, volume_max_cbm: 30, typical_body_style: 'Food-grade tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'chemical_tanker', display_name: 'Chemical tanker', common_uses: ['Industrial chemicals'], payload_min_tons: 8, payload_max_tons: 32, volume_min_cbm: 10, volume_max_cbm: 40, typical_body_style: 'Chemical tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'refrigerated_rigid_truck', display_name: 'Refrigerated rigid truck', common_uses: ['Frozen food', 'Pharma', 'Fresh produce'], payload_min_tons: 1, payload_max_tons: 12, volume_min_cbm: 6, volume_max_cbm: 40, typical_body_style: 'Insulated reefer body', class_segment: 'Cold-chain vehicle' },
  { type_key: 'reefer_trailer_reefer_container_carrier', display_name: 'Reefer trailer / reefer container carrier', common_uses: ['Frozen exports', 'Cold-chain bulk'], payload_min_tons: 12, payload_max_tons: 28, volume_min_cbm: 40, volume_max_cbm: 75, typical_body_style: 'Reefer trailer', class_segment: 'Cold-chain vehicle' },
  { type_key: 'insulated_or_dry_box_truck', display_name: 'Insulated or dry box truck', common_uses: ['Sensitive packaged goods', 'Dry groceries'], payload_min_tons: 1, payload_max_tons: 12, volume_min_cbm: 8, volume_max_cbm: 45, typical_body_style: 'Closed box body', class_segment: 'Enclosed cargo' },
  { type_key: 'dump_truck_tipper', display_name: 'Dump truck / tipper', common_uses: ['Sand', 'Gravel', 'Construction materials'], payload_min_tons: 5, payload_max_tons: 25, volume_min_cbm: 4, volume_max_cbm: 16, typical_body_style: 'Tipper body', class_segment: 'Construction and bulk haulage' },
  { type_key: 'bulk_cement_tanker_powder_bulker', display_name: 'Bulk cement tanker / powder bulker', common_uses: ['Bulk cement', 'Fly ash'], payload_min_tons: 15, payload_max_tons: 35, volume_min_cbm: 18, volume_max_cbm: 45, typical_body_style: 'Pneumatic dry bulk tanker', class_segment: 'Construction and bulk haulage' },
  { type_key: 'livestock_carrier', display_name: 'Livestock carrier', common_uses: ['Livestock', 'Poultry'], payload_min_tons: 0, payload_max_tons: 0, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Ventilated body', class_segment: 'Specialized cargo' },
]

export default function TruckConfiguration() {
  const { id } = useParams()
  const api = useApi()
  const [form, setForm] = useState(EMPTY_FORM)
  const [truckTypes, setTruckTypes] = useState([])
  const [catalogFields, setCatalogFields] = useState([])
  const [truckPhoto, setTruckPhoto] = useState(null)
  const [insurancePhoto, setInsurancePhoto] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [statusSaving, setStatusSaving] = useState(false)
  const [statusForm, setStatusForm] = useState({ status: 'inactive', reason_code: '' })
  const [toast, setToast] = useState(null)

  function normalizeConfig(raw) {
    const cfg = raw || {}
    const catalogSpecs = cfg.catalog_specs_json
    return {
      ...EMPTY_FORM,
      ...cfg,
      operating_provinces: Array.isArray(cfg.operating_provinces)
        ? cfg.operating_provinces
        : typeof cfg.operating_provinces === 'string'
          ? cfg.operating_provinces.split(',').map(s => s.trim()).filter(Boolean)
          : [],
      catalog_specs_json: catalogSpecs && typeof catalogSpecs === 'object'
        ? JSON.stringify(catalogSpecs)
        : catalogSpecs || '',
      photo: cfg.photo || cfg.truck_photo_path || '',
      insurance_photo: cfg.insurance_photo || cfg.insurance_photo_path || '',
      rc_book_photo: cfg.rc_book_photo || cfg.rc_book_photo_path || '',
    }
  }

  function loadConfig() {
    if (!id) { setLoading(false); return }
    setLoading(true)
    api.get(`/api/trucks/${id}/configuration`)
      .then(d => {
        const cfg = d.configuration || d.truck || d
        applySavedTruck(cfg)
      })
      .catch(() => {
        api.get(`/api/trucks/${id}`)
          .then(d => {
            const t = d.truck || d
            setForm(f => ({
              ...f,
              truck_number: t.truck_number || '',
              truck_company: t.truck_company || '',
              truck_model: t.truck_model || '',
              truck_type: t.truck_type || '',
          max_capacity: t.max_capacity || '',
          chassis_number: t.chassis_number || '',
        }))
      })
          .catch(() => undefined)
      })
      .finally(() => setLoading(false))
  }

  function loadCatalog() {
    api.get('/api/catalog/truck-types')
      .then(data => {
        const items = data.truck_types || data.items || []
        setTruckTypes(items.length ? items : FALLBACK_TRUCK_TYPES)
      })
      .catch(() => setTruckTypes(FALLBACK_TRUCK_TYPES))
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadConfig() }, [id])
  useEffect(() => { loadCatalog() }, [])

  useEffect(() => {
    let active = true
    if (!form.catalog_type_key) {
      queueMicrotask(() => {
        if (active) setCatalogFields([])
      })
      return () => { active = false }
    }
    api.get(`/api/catalog/truck-types/${encodeURIComponent(form.catalog_type_key)}/fields`)
      .then(data => { if (active) setCatalogFields(data.fields || []) })
      .catch(() => { if (active) setCatalogFields([]) })
    return () => { active = false }
  }, [form.catalog_type_key])

  useEffect(() => {
    document.title = 'Truck Configuration - Digi_TransX'
  }, [])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3200)
  }

  function setField(e) {
    const { name, value, type, checked } = e.target
    if (type === 'checkbox') {
      setForm(f => ({ ...f, [name]: checked }))
    } else if (name === 'payload_max_tons') {
      setForm(f => ({ ...f, payload_max_tons: value, max_capacity: value }))
    } else if (name === 'body_style') {
      setForm(f => ({ ...f, body_style: value, truck_type: value || f.truck_type }))
    } else {
      setForm(f => ({ ...f, [name]: value }))
    }
  }

  function applyCatalogType(typeKey) {
    const catalog = truckTypes.find(item => item.type_key === typeKey)
    setForm(f => ({
      ...f,
      catalog_type_key: typeKey,
      truck_type: catalog?.display_name || f.truck_type,
      max_capacity: catalog?.payload_max_tons ? String(catalog.payload_max_tons) : f.max_capacity,
      body_style: catalog?.typical_body_style || f.body_style,
      payload_min_tons: catalog?.payload_min_tons || f.payload_min_tons,
      payload_max_tons: catalog?.payload_max_tons || f.payload_max_tons,
      volume_min_cbm: catalog?.volume_min_cbm || f.volume_min_cbm,
      volume_max_cbm: catalog?.volume_max_cbm || f.volume_max_cbm,
      catalog_specs_json: catalog ? JSON.stringify({
        class_segment: catalog.class_segment,
        common_local_names: catalog.common_local_names,
        companies_models: catalog.companies_models,
        engine_fuel_notes: catalog.engine_fuel_notes,
        routes_terrain_suitability: catalog.routes_terrain_suitability,
        special_transport_features: catalog.special_transport_features,
      }) : f.catalog_specs_json,
    }))
  }

  function fileName(path) {
    const text = String(path || '')
    return text.split('/').filter(Boolean).pop() || text
  }

  function applySavedTruck(truck) {
    if (truck) {
      const next = normalizeConfig(truck)
      setForm(next)
      setStatusForm({
        status: next.status || 'inactive',
        reason_code: next.status_reason_code || '',
      })
    }
    setTruckPhoto(null)
    setInsurancePhoto(null)
  }

  async function handleStatusUpdate() {
    const nextStatus = statusForm.status || 'inactive'
    const missing = getMissing()
    if (nextStatus === 'active' && missing.length > 0) {
      showToast(`Complete required fields first: ${missing.map(k => k.replace(/_/g, ' ')).join(', ')}`, 'error')
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

  function toggleProvince(province) {
    setForm(f => {
      const list = f.operating_provinces || []
      return {
        ...f,
        operating_provinces: list.includes(province)
          ? list.filter(p => p !== province)
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
    return REQUIRED.filter(key => {
      const val = form[key]
      return Array.isArray(val) ? val.length === 0 : !val || String(val).trim() === ''
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const missing = getMissing()
    if (missing.length > 0) {
      showToast(`Please fill: ${missing.map(k => k.replace(/_/g, ' ')).join(', ')}`, 'error')
      return
    }
    setSaving(true)
    try {
      const fd = new FormData()
      const payload = {
        ...form,
        truck_type: form.truck_type || form.body_style || 'Truck',
        max_capacity: form.payload_max_tons || form.max_capacity,
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
  const statusLabel = STATUS_OPTIONS.find(item => item.value === form.status)?.label || form.status || 'Inactive'
  const statusIsActive = form.status === 'active'

  return (
    <div className="truck-config-page">
      <div className="truck-config-shell">
        <Link to="/transporter/trucks" className="inline-flex items-center gap-2 text-sm font-semibold text-[#6B7280] hover:text-[#4F46E5]">
          <i className="fas fa-arrow-left" aria-hidden="true"></i>
          Back To My Trucks
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#111827]">Truck Configuration</h1>
            <p className="mt-1 text-sm text-[#6B7280]">Set this truck&apos;s pricing, profile, and documents in one place.</p>
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
                    <span className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusIsActive ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
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
                <strong>Missing fields:</strong> {missing.map(k => k.replace(/_/g, ' ')).join(', ')}
              </div>
            )}

            <form className="truck-config-form" onSubmit={handleSubmit} noValidate>
              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Truck Status</h2>
                <p className="mt-1 text-sm text-[#6B7280]">Change truck status. Active requires all required fields to be filled.</p>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Status</span>
                    <select
                      className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                      value={statusForm.status}
                      onChange={e => setStatusForm(s => ({ ...s, status: e.target.value, reason_code: e.target.value === 'active' ? '' : s.reason_code }))}
                    >
                      {STATUS_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </label>
                  {statusForm.status !== 'active' && (
                    <label className="block">
                      <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Reason</span>
                      <select
                        className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500"
                        value={statusForm.reason_code}
                        onChange={e => setStatusForm(s => ({ ...s, reason_code: e.target.value }))}
                      >
                        <option value="">Select reason</option>
                        {STATUS_REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </select>
                    </label>
                  )}
                </div>
                {form.status_reason && (
                  <p className="mt-3 text-sm text-[#6B7280]">Last reason: <strong>{form.status_reason}</strong></p>
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

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Truck Details</h2>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Number</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="text" name="truck_number" value={form.truck_number} onChange={setField} placeholder="Example: LE-1234, ABC 12345" required />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Company</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="text" name="truck_company" value={form.truck_company} onChange={setField} placeholder="Example: Hino, ISUZU" required />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Truck Model</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="text" name="truck_model" value={form.truck_model} onChange={setField} placeholder="Example: Hino 500, ISUZU NPR" required />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Chassis Number</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="text" name="chassis_number" value={form.chassis_number} onChange={setField} placeholder="Enter chassis number" pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}" required />
                    <span className="mt-2 block text-xs italic text-gray-400">11-17 characters, letters and numbers only (I, O, Q not allowed)</span>
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Body Type</span>
                    <select className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" name="body_style" value={form.body_style} onChange={setField} required>
                      <option value="">Select Body Type</option>
                      {BODY_STYLE_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                    </select>
                    <input type="hidden" name="truck_type" value={form.truck_type || form.body_style || 'Truck'} />
                  </label>
                  <div className="truck-config-weight-field">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Weight Capacity</span>
                    <div className="truck-config-weight-row">
                      <div className="truck-config-weight-input">
                        <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="number" name="payload_min_tons" value={form.payload_min_tons} onChange={setField} min="0" step="0.1" placeholder="Min" required />
                        <span>ton</span>
                      </div>
                      <div className="truck-config-weight-input">
                        <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="number" name="payload_max_tons" value={form.payload_max_tons} onChange={setField} min="0" step="0.1" placeholder="Max" required />
                        <span>ton</span>
                      </div>
                    </div>
                    <input type="hidden" name="max_capacity" value={form.payload_max_tons || form.max_capacity} />
                  </div>
                  <div className="truck-config-weight-field truck-config-bed-field">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Cargo Bed Size (feet)</span>
                    <div className="truck-config-bed-grid">
                      <div className="truck-config-weight-input">
                        <input className="w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="number" name="bed_length_ft" value={form.bed_length_ft} onChange={setField} min="0" step="0.5" placeholder="Length" />
                        <span>ft</span>
                      </div>
                      <div className="truck-config-weight-input">
                        <input className="w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="number" name="bed_width_ft" value={form.bed_width_ft} onChange={setField} min="0" step="0.5" placeholder="Width" />
                        <span>ft</span>
                      </div>
                      <div className="truck-config-weight-input">
                        <input className="w-full rounded-lg border border-[#E5E7EB] bg-gray-50 px-4 py-3 text-sm font-semibold text-[#111827] outline-none focus:ring-2 focus:ring-indigo-500" type="number" name="bed_height_ft" value={form.bed_height_ft} onChange={setField} min="0" step="0.5" placeholder="Height" />
                        <span>ft</span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Operating Provinces</h2>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {PROVINCES.map(p => (
                    <label key={p} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border border-[#E5E7EB] bg-white px-4 py-3 text-sm font-semibold text-[#111827] transition hover:border-indigo-200 hover:bg-indigo-50/50">
                      <input className="h-4 w-4 accent-indigo-600 focus:ring-2 focus:ring-indigo-500" type="checkbox" checked={form.operating_provinces.includes(p)} onChange={() => toggleProvince(p)} />
                      <span>{p}</span>
                    </label>
                  ))}
                </div>
                <p className="mt-4 text-xs text-gray-400">Click to select or deselect provinces.</p>
              </section>

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Optional Details</h2>
                <div className="mt-5 grid gap-5 md:grid-cols-3">
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Tracking ID</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] px-4 py-3 text-sm text-[#111827] outline-none placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-500" type="text" name="tracking_id" value={form.tracking_id} onChange={setField} placeholder="Optional - Tracking / device ID" />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Driver CNIC</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] px-4 py-3 text-sm text-[#111827] outline-none placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-500" type="text" name="driver_cnic" value={form.driver_cnic} onChange={setField} placeholder="Optional - 13 digit CNIC" />
                  </label>
                  <label className="block">
                    <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Driver Name</span>
                    <input className="mt-2 w-full rounded-lg border border-[#E5E7EB] px-4 py-3 text-sm text-[#111827] outline-none placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-500" type="text" name="driver_name" value={form.driver_name} onChange={setField} placeholder="Enter driver name" />
                  </label>
                </div>
              </section>

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Documents (Optional)</h2>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <div>
                    <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-5 py-8 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40">
                      <i className="fas fa-cloud-arrow-up text-4xl text-gray-300" aria-hidden="true"></i>
                      <span className="mt-3 font-bold text-[#111827]">Truck Pic</span>
                      <span className="mt-1 text-sm font-semibold text-[#4F46E5]">Choose File</span>
                      <span className="mt-1 text-sm text-gray-400">{truckPhoto ? truckPhoto.name : form.photo ? `Saved: ${fileName(form.photo)}` : 'No file chosen'}</span>
                      <input className="hidden" type="file" accept=".jpg,.jpeg,.png,.webp" onChange={e => setTruckPhoto(e.target.files[0] || null)} />
                    </label>
                    <p className="mt-2 text-xs text-gray-400">{truckPhoto ? truckPhoto.name : form.photo ? `Saved truck photo: ${fileName(form.photo)}` : 'No truck photo selected.'}</p>
                    {form.photo && !truckPhoto && <a href={form.photo} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-xs font-semibold text-[#4F46E5]">View saved truck pic</a>}
                  </div>
                  <div>
                    <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-5 py-8 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40">
                      <i className="fas fa-file-arrow-up text-4xl text-gray-300" aria-hidden="true"></i>
                      <span className="mt-3 font-bold text-[#111827]">Insurance Paper</span>
                      <span className="mt-1 text-sm font-semibold text-[#4F46E5]">Choose File</span>
                      <span className="mt-1 text-sm text-gray-400">{insurancePhoto ? insurancePhoto.name : form.insurance_photo ? `Saved: ${fileName(form.insurance_photo)}` : 'No file chosen'}</span>
                      <input className="hidden" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={e => setInsurancePhoto(e.target.files[0] || null)} />
                    </label>
                    <p className="mt-2 text-xs text-gray-400">{insurancePhoto ? insurancePhoto.name : form.insurance_photo ? `Saved insurance paper: ${fileName(form.insurance_photo)}` : 'No insurance document selected.'}</p>
                    {form.insurance_photo && !insurancePhoto && <a href={form.insurance_photo} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-xs font-semibold text-[#4F46E5]">View saved insurance paper</a>}
                  </div>
                </div>
              </section>

              <section className="rounded-2xl bg-white p-6 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)]">
                <h2 className="text-lg font-bold text-[#111827]">Special Capabilities</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-3">
                  {[
                    ['refrigeration_supported', 'Refrigeration Supported'],
                    ['hazardous_supported', 'Hazardous Material License'],
                    ['fragile_supported', 'Fragile Goods Supported'],
                  ].map(([name, label]) => (
                    <label key={name} className="flex items-center justify-between gap-4 rounded-xl border border-[#E5E7EB] bg-white px-4 py-4 text-sm font-semibold text-[#111827]">
                      <span>{label}</span>
                      <input className="h-5 w-5 accent-indigo-600 focus:ring-2 focus:ring-indigo-500" type="checkbox" name={name} checked={form[name]} onChange={setField} />
                    </label>
                  ))}
                </div>
              </section>

              <div className="truck-config-actions">
                <button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-60" onClick={loadConfig} disabled={loading}>
                  <i className="fas fa-sync-alt" aria-hidden="true"></i>
                  Reload
                </button>
                <button type="submit" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-[#4F46E5] px-5 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60" disabled={saving}>
                  <i className="fas fa-save" aria-hidden="true"></i>
                  {saving ? 'Saving...' : 'Save Configuration'}
                </button>
              </div>
            </form>


          </>
        )}

        {toast && (
          <div className="fixed bottom-6 right-6 z-[1400]">
            <div className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold shadow-lg ${toast.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
              <i className={`fas ${toast.type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check'}`} aria-hidden="true"></i>
              <span>{toast.msg}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
