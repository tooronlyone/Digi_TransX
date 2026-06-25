import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = {
  truck_number: '', truck_type: '', max_capacity: '', chassis_number: '',
  operating_provinces: [],
  catalog_type_key: '', body_style: '', payload_min_kg: '', payload_max_kg: '',
  volume_min_cbm: '', volume_max_cbm: '', catalog_specs_json: '',
  tracking_id: '', driver_name: '', driver_cnic: '',
  per_km_rate: '', waiting_charge_per_hour: '', loading_charge: '',
  refrigeration_supported: false, hazardous_supported: false, fragile_supported: false,
  photo: '', insurance_photo: '', rc_book_photo: '',
  status: 'inactive', status_reason_code: '', status_reason: '',
}

const REQUIRED = ['truck_number', 'truck_type', 'max_capacity', 'chassis_number', 'operating_provinces', 'per_km_rate', 'waiting_charge_per_hour']

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
  { type_key: 'mini_pickup', display_name: 'Mini pickup', common_uses: ['Last-mile retail supply', 'Cartons'], payload_min_kg: 500, payload_max_kg: 700, volume_min_cbm: 2, volume_max_cbm: 3, typical_body_style: 'Low-side deck', class_segment: 'Small urban cargo' },
  { type_key: 'one_ton_pickup', display_name: 'One-ton pickup', common_uses: ['Field deliveries', 'Agri-inputs'], payload_min_kg: 900, payload_max_kg: 1300, volume_min_cbm: 3, volume_max_cbm: 5, typical_body_style: 'Open bed', class_segment: 'Small urban cargo' },
  { type_key: 'cargo_van_panel_van', display_name: 'Cargo van / panel van', common_uses: ['Parcel movement', 'Pharmacy stock'], payload_min_kg: 400, payload_max_kg: 800, volume_min_cbm: 2.5, volume_max_cbm: 4.5, typical_body_style: 'Closed metal van', class_segment: 'Small enclosed cargo' },
  { type_key: 'mini_truck_high_deck_mini_truck', display_name: 'Mini truck / high-deck mini truck', common_uses: ['City cargo', 'Market supply'], payload_min_kg: 1000, payload_max_kg: 2000, volume_min_cbm: 5, volume_max_cbm: 10, typical_body_style: 'High deck / open bed', class_segment: 'Light rigid truck' },
  { type_key: 'light_truck_2_3_5_ton', display_name: 'Light truck 2-3.5 ton', common_uses: ['Branch replenishment', 'Consumer goods'], payload_min_kg: 2000, payload_max_kg: 3500, volume_min_cbm: 10, volume_max_cbm: 18, typical_body_style: 'Open bed / dry box', class_segment: 'Light rigid truck' },
  { type_key: 'light_truck_3_5_5_ton', display_name: 'Light truck 3.5-5 ton', common_uses: ['Retail distribution', 'Packaging'], payload_min_kg: 3500, payload_max_kg: 5000, volume_min_cbm: 15, volume_max_cbm: 24, typical_body_style: 'Open bed / dry box', class_segment: 'Light rigid truck' },
  { type_key: 'medium_rigid_truck_5_9_ton', display_name: 'Medium rigid truck 5-9 ton', common_uses: ['General cargo', 'Textile'], payload_min_kg: 5000, payload_max_kg: 9000, volume_min_cbm: 20, volume_max_cbm: 36, typical_body_style: 'Rigid cargo body', class_segment: 'Medium rigid truck' },
  { type_key: 'heavy_rigid_truck_9_15_ton', display_name: 'Heavy rigid truck 9-15 ton', common_uses: ['Long-route cargo', 'Industrial goods'], payload_min_kg: 9000, payload_max_kg: 15000, volume_min_cbm: 30, volume_max_cbm: 55, typical_body_style: 'Rigid cargo body', class_segment: 'Heavy rigid truck' },
  { type_key: 'heavy_rigid_truck_15_25_ton', display_name: 'Heavy rigid truck 15-25 ton', common_uses: ['Heavy cargo', 'Bulk industrial loads'], payload_min_kg: 15000, payload_max_kg: 25000, volume_min_cbm: 40, volume_max_cbm: 70, typical_body_style: 'Rigid cargo body', class_segment: 'Heavy rigid truck' },
  { type_key: 'flatbed_trailer_open_semi_trailer', display_name: 'Flatbed trailer / open semi-trailer', common_uses: ['Steel', 'Machinery'], payload_min_kg: 20000, payload_max_kg: 45000, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Open flatbed', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'container_carrier_skeletal_trailer', display_name: 'Container carrier / skeletal trailer', common_uses: ['Container transport'], payload_min_kg: 20000, payload_max_kg: 30000, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Skeletal semi-trailer', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'low_bed_low_loader_trailer', display_name: 'Low-bed / low-loader trailer', common_uses: ['Heavy machinery', 'Oversized loads'], payload_min_kg: 25000, payload_max_kg: 60000, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Low-bed trailer', class_segment: 'Trailer-based heavy transport' },
  { type_key: 'fuel_oil_tanker', display_name: 'Fuel / oil tanker', common_uses: ['Petrol', 'Diesel', 'Furnace oil'], payload_min_kg: 8000, payload_max_kg: 35000, volume_min_cbm: 10, volume_max_cbm: 45, typical_body_style: 'Tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'milk_tanker', display_name: 'Milk tanker', common_uses: ['Raw milk', 'Dairy liquids'], payload_min_kg: 5000, payload_max_kg: 28000, volume_min_cbm: 6, volume_max_cbm: 30, typical_body_style: 'Food-grade tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'chemical_tanker', display_name: 'Chemical tanker', common_uses: ['Industrial chemicals'], payload_min_kg: 8000, payload_max_kg: 32000, volume_min_cbm: 10, volume_max_cbm: 40, typical_body_style: 'Chemical tanker', class_segment: 'Tanker vehicle' },
  { type_key: 'refrigerated_rigid_truck', display_name: 'Refrigerated rigid truck', common_uses: ['Frozen food', 'Pharma', 'Fresh produce'], payload_min_kg: 1000, payload_max_kg: 12000, volume_min_cbm: 6, volume_max_cbm: 40, typical_body_style: 'Insulated reefer body', class_segment: 'Cold-chain vehicle' },
  { type_key: 'reefer_trailer_reefer_container_carrier', display_name: 'Reefer trailer / reefer container carrier', common_uses: ['Frozen exports', 'Cold-chain bulk'], payload_min_kg: 12000, payload_max_kg: 28000, volume_min_cbm: 40, volume_max_cbm: 75, typical_body_style: 'Reefer trailer', class_segment: 'Cold-chain vehicle' },
  { type_key: 'insulated_or_dry_box_truck', display_name: 'Insulated or dry box truck', common_uses: ['Sensitive packaged goods', 'Dry groceries'], payload_min_kg: 1000, payload_max_kg: 12000, volume_min_cbm: 8, volume_max_cbm: 45, typical_body_style: 'Closed box body', class_segment: 'Enclosed cargo' },
  { type_key: 'dump_truck_tipper', display_name: 'Dump truck / tipper', common_uses: ['Sand', 'Gravel', 'Construction materials'], payload_min_kg: 5000, payload_max_kg: 25000, volume_min_cbm: 4, volume_max_cbm: 16, typical_body_style: 'Tipper body', class_segment: 'Construction and bulk haulage' },
  { type_key: 'bulk_cement_tanker_powder_bulker', display_name: 'Bulk cement tanker / powder bulker', common_uses: ['Bulk cement', 'Fly ash'], payload_min_kg: 15000, payload_max_kg: 35000, volume_min_cbm: 18, volume_max_cbm: 45, typical_body_style: 'Pneumatic dry bulk tanker', class_segment: 'Construction and bulk haulage' },
  { type_key: 'livestock_carrier', display_name: 'Livestock carrier', common_uses: ['Livestock', 'Poultry'], payload_min_kg: 0, payload_max_kg: 0, volume_min_cbm: 0, volume_max_cbm: 0, typical_body_style: 'Ventilated body', class_segment: 'Specialized cargo' },
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
  const [statusForm, setStatusForm] = useState({ status: 'active', reason_code: '' })
  const [toast, setToast] = useState(null)

  function normalizeConfig(raw) {
    const cfg = raw || {}
    return {
      ...EMPTY_FORM,
      ...cfg,
      operating_provinces: Array.isArray(cfg.operating_provinces)
        ? cfg.operating_provinces
        : typeof cfg.operating_provinces === 'string'
          ? cfg.operating_provinces.split(',').map(s => s.trim()).filter(Boolean)
          : [],
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

  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
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
      max_capacity: catalog?.payload_max_kg ? String(Number(catalog.payload_max_kg) / 1000) : f.max_capacity,
      body_style: catalog?.typical_body_style || f.body_style,
      payload_min_kg: catalog?.payload_min_kg || f.payload_min_kg,
      payload_max_kg: catalog?.payload_max_kg || f.payload_max_kg,
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
      Object.entries(form).forEach(([k, v]) => {
        if (Array.isArray(v)) fd.append(k, v.join(','))
        else if (typeof v === 'boolean') fd.append(k, v ? '1' : '0')
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

  async function handleStatusUpdate() {
    const nextStatus = statusForm.status || 'inactive'
    const missing = getMissing()
    if (nextStatus === 'active' && missing.length > 0) {
      showToast(`Please fill: ${missing.map(k => k.replace(/_/g, ' ')).join(', ')}`, 'error')
      return
    }
    if (nextStatus !== 'active' && !statusForm.reason_code) {
      showToast('Please select a reason before changing truck status.', 'error')
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
      showToast(err.message || 'Failed to update truck status', 'error')
    } finally {
      setStatusSaving(false)
    }
  }

  const completeness = calcCompleteness()
  const missing = getMissing()
  const statusLabel = STATUS_OPTIONS.find(item => item.value === form.status)?.label || form.status || 'Inactive'

  return (
      <div className="page-truck-configuration">
        <div className="config-shell">
          <Link className="back-link" to="/transporter/trucks">
            <i className="fas fa-arrow-left"></i> Back To My Trucks
          </Link>

          <div className="page-header">
            <h1>Truck Configuration</h1>
            <p>Set this truck&apos;s pricing, profile, and documents in one place.</p>
          </div>

          {loading ? (
            <div className="loading-state">
              <i className="fas fa-spinner fa-spin"></i>
              <p>Loading configuration...</p>
            </div>
          ) : (
            <>
              <div className="status-panel">
                <div className="status-item">
                  <div className="status-label">Current Status</div>
                  <div className={`status-badge ${form.status === 'active' ? 'status-active' : 'status-draft'}`}>
                    {statusLabel}
                  </div>
                </div>
                <div className="status-item">
                  <div className="status-label">Configuration</div>
                  <div className="config-completeness">{completeness}% Complete</div>
                </div>
                {missing.length > 0 && (
                  <div className="missing-fields">
                    <div className="missing-fields-title">Missing Fields</div>
                    <p className="missing-fields-copy">{missing.map(k => k.replace(/_/g, ' ')).join(', ')}</p>
                  </div>
                )}
              </div>

              <div className="config-card">
                <h2>Truck Status</h2>
                <p className="section-note">Required configuration activates the truck automatically. Non-active status needs a selected reason.</p>
                <div className="field-grid">
                  <label>
                    Status
                    <select
                      value={statusForm.status}
                      onChange={e => setStatusForm(current => ({ ...current, status: e.target.value, reason_code: e.target.value === 'active' ? '' : current.reason_code }))}
                    >
                      {STATUS_OPTIONS.map(option => (
                        <option
                          key={option.value}
                          value={option.value}
                          disabled={option.value === 'active' && missing.length > 0}
                        >
                          {option.label}
                          {option.value === 'active' && missing.length > 0 ? ' (complete required fields first)' : ''}
                        </option>
                      ))}
                    </select>
                    {missing.length > 0 && (
                      <small>Complete these fields before activation: {missing.map(k => k.replace(/_/g, ' ')).join(', ')}</small>
                    )}
                  </label>
                  {statusForm.status !== 'active' && (
                    <label>
                      Reason
                      <select
                        value={statusForm.reason_code}
                        onChange={e => setStatusForm(current => ({ ...current, reason_code: e.target.value }))}
                      >
                        <option value="">Select reason</option>
                        {STATUS_REASONS.map(reason => <option key={reason.value} value={reason.value}>{reason.label}</option>)}
                      </select>
                      <small>Reason must be selected from the list.</small>
                    </label>
                  )}
                  <label>
                    Last Reason
                    <input type="text" value={form.status_reason || 'None'} readOnly />
                  </label>
                </div>
                <div className="form-actions">
                  <button type="button" className="btn secondary" onClick={handleStatusUpdate} disabled={statusSaving}>
                    <i className="fas fa-toggle-on"></i> {statusSaving ? 'Updating...' : 'Update Status'}
                  </button>
                </div>
              </div>

              <form className="config-form" onSubmit={handleSubmit} noValidate>
                <div className="config-card">
                  <h2>Truck Details</h2>
                  <p className="section-note">Enter required truck details for activation.</p>
                  <div className="field-grid">
                    <label>
                      Truck Number
                      <input type="text" name="truck_number" value={form.truck_number} onChange={setField}
                        placeholder="Example: LE-1234" required />
                    </label>
                    <label>
                      Truck Type
                      <select name="catalog_type_key" value={form.catalog_type_key} onChange={e => applyCatalogType(e.target.value)} required>
                        <option value="">Select truck type</option>
                        {truckTypes.map(t => <option key={t.type_key} value={t.type_key}>{t.display_name}</option>)}
                      </select>
                      <input type="hidden" name="truck_type" value={form.truck_type} />
                    </label>
                    <label>
                      Truck Capacity (tons)
                      <input type="number" name="max_capacity" value={form.max_capacity} onChange={setField}
                        min="0.1" step="0.1" required />
                    </label>
                    <label>
                      Chassis Number
                      <input type="text" name="chassis_number" value={form.chassis_number} onChange={setField}
                        placeholder="Enter chassis number" pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}" required />
                      <small>11-17 characters, letters and numbers only (I, O, Q not allowed)</small>
                    </label>
                    <label>
                      Body Style
                      <input type="text" name="body_style" value={form.body_style} onChange={setField}
                        placeholder="Catalog body style" />
                    </label>
                    <label>
                      Payload Range (kg)
                      <input type="text" value={`${form.payload_min_kg || 0} - ${form.payload_max_kg || 0}`} readOnly />
                      <small>Loaded from Pakistan vehicle catalog.</small>
                    </label>
                    {catalogFields.length > 0 && (
                      <label className="full-width">
                        Catalog Fields
                        <textarea readOnly rows={3} value={catalogFields.map(field => field.field_label).join(', ')} />
                        <small>Use these fields as the reference for this vehicle type.</small>
                      </label>
                    )}
                    <label className="full-width">
                      Operating Provinces
                      <div className="province-grid">
                        {PROVINCES.map(p => (
                          <label
                            key={p}
                            className={`province-chip ${form.operating_provinces.includes(p) ? 'selected' : ''}`}
                          >
                            <input
                              type="checkbox"
                              checked={form.operating_provinces.includes(p)}
                              onChange={() => toggleProvince(p)}
                            />
                            <span>{p}</span>
                          </label>
                        ))}
                      </div>
                      <small>Click to select or deselect provinces.</small>
                    </label>
                  </div>
                </div>

                <div className="config-card">
                  <h2>Optional Details</h2>
                  <p className="section-note">Tracking and driver information (optional).</p>
                  <div className="field-grid">
                    <label>
                      Tracking ID
                      <input type="text" name="tracking_id" value={form.tracking_id} onChange={setField}
                        placeholder="Optional - Tracking / device ID" />
                    </label>
                    <label>
                      Driver Name
                      <input type="text" name="driver_name" value={form.driver_name} onChange={setField}
                        placeholder="Enter driver name" />
                    </label>
                    <label>
                      Driver CNIC
                      <input type="text" name="driver_cnic" value={form.driver_cnic} onChange={setField}
                        placeholder="Optional - 13 digit CNIC" />
                    </label>
                  </div>
                </div>

                <div className="config-card">
                  <h2>Documents (Optional)</h2>
                  <p className="section-note">Truck photo and insurance paper are optional.</p>
                  <div className="field-grid">
                    <label className="upload-field full-width">
                      Truck Pic
                      <input type="file" accept=".jpg,.jpeg,.png,.webp"
                        onChange={e => setTruckPhoto(e.target.files[0] || null)} />
                      <small>
                        {truckPhoto
                          ? truckPhoto.name
                          : form.photo
                            ? `Saved: ${fileName(form.photo)}`
                            : 'No truck photo selected.'}
                      </small>
                      {form.photo && !truckPhoto && (
                        <a href={form.photo} target="_blank" rel="noreferrer">View saved truck pic</a>
                      )}
                    </label>
                    <label className="upload-field full-width">
                      Insurance Paper
                      <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
                        onChange={e => setInsurancePhoto(e.target.files[0] || null)} />
                      <small>
                        {insurancePhoto
                          ? insurancePhoto.name
                          : form.insurance_photo
                            ? `Saved: ${fileName(form.insurance_photo)}`
                            : 'No insurance document selected.'}
                      </small>
                      {form.insurance_photo && !insurancePhoto && (
                        <a href={form.insurance_photo} target="_blank" rel="noreferrer">View saved insurance paper</a>
                      )}
                    </label>
                  </div>
                </div>

                <div className="config-card">
                  <h2>Activation Details</h2>
                  <p className="section-note">Loading and unloading charges can be left blank if not applicable.</p>
                  <div className="field-grid">
                    <label>
                      Per KM Rate (PKR)
                      <input type="number" name="per_km_rate" value={form.per_km_rate} onChange={setField}
                        min="0.01" step="0.01" required />
                    </label>
                    <label>
                      Waiting Charges / Hour (PKR)
                      <input type="number" name="waiting_charge_per_hour" value={form.waiting_charge_per_hour} onChange={setField}
                        min="0.01" step="0.01" required />
                    </label>
                    <label>
                      Loading/Unloading Charges (PKR)
                      <input type="number" name="loading_charge" value={form.loading_charge} onChange={setField}
                        min="0" step="0.01" />
                    </label>
                  </div>
                </div>

                <div className="config-card">
                  <h2>Special Capabilities</h2>
                  <p className="section-note">Capabilities based on the selected truck type.</p>
                  <div className="field-grid">
                    <label className="checkbox-field">
                      <input type="checkbox" name="refrigeration_supported"
                        checked={form.refrigeration_supported} onChange={setField} />
                      <span>Refrigeration Supported</span>
                    </label>
                    <label className="checkbox-field">
                      <input type="checkbox" name="hazardous_supported"
                        checked={form.hazardous_supported} onChange={setField} />
                      <span>Hazardous Material License</span>
                    </label>
                    <label className="checkbox-field">
                      <input type="checkbox" name="fragile_supported"
                        checked={form.fragile_supported} onChange={setField} />
                      <span>Fragile Goods Supported</span>
                    </label>
                  </div>
                </div>

                <div className="form-actions">
                  <button type="button" className="btn secondary" onClick={loadConfig} disabled={loading}>
                    <i className="fas fa-sync-alt"></i> Reload
                  </button>
                  <button type="submit" className="btn primary" disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Configuration'}
                  </button>
                </div>
              </form>

              <div className="footer">
                <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
                <div className="footer-links">
                  <Link to="/transporter/about">About Us</Link>
                  <Link to="/transporter/contact">Contact</Link>
                  <Link to="/transporter/terms">Terms &amp; Conditions</Link>
                  <Link to="/transporter/privacy">Privacy Policy</Link>
                  <Link to="/transporter/help">Help Center</Link>
                  <Link to="/transporter/partner">Partner With Us</Link>
                </div>
              </div>
            </>
          )}
          {toast && (
            <div className="toast-container">
              <div className={`toast ${toast.type}`}>
                <i className={`fas ${toast.type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check'}`}></i>
                <span>{toast.msg}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    
  )
}
