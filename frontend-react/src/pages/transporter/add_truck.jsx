import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

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

export default function AddTruck() {
  const navigate = useNavigate()
  const [truckTypes, setTruckTypes] = useState([])
  const [selectedTypeKey, setSelectedTypeKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    fetch('/api/catalog/truck-types', { credentials: 'include' })
      .then(res => (res.ok ? res.json() : Promise.reject(new Error('catalog unavailable'))))
      .then(data => {
        const items = data.truck_types || data.items || []
        setTruckTypes(items.length ? items : FALLBACK_TRUCK_TYPES)
      })
      .catch(() => setTruckTypes(FALLBACK_TRUCK_TYPES))
  }, [])

  const selectedCatalog = useMemo(
    () => truckTypes.find(item => item.type_key === selectedTypeKey) || null,
    [truckTypes, selectedTypeKey],
  )

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess('')
    setSubmitting(true)

    const form = e.target
    const data = new FormData(form)
    if (selectedCatalog) {
      data.set('catalog_type_key', selectedCatalog.type_key)
      data.set('truckType', selectedCatalog.display_name)
      data.set('truck_type', selectedCatalog.display_name)
      data.set('payload_min_kg', selectedCatalog.payload_min_kg || '')
      data.set('payload_max_kg', selectedCatalog.payload_max_kg || '')
      data.set('volume_min_cbm', selectedCatalog.volume_min_cbm || '')
      data.set('volume_max_cbm', selectedCatalog.volume_max_cbm || '')
      data.set('body_style', selectedCatalog.typical_body_style || '')
      data.set('catalog_specs_json', JSON.stringify({
        class_segment: selectedCatalog.class_segment,
        common_local_names: selectedCatalog.common_local_names,
        common_uses: selectedCatalog.common_uses,
        companies_models: selectedCatalog.companies_models,
        engine_fuel_notes: selectedCatalog.engine_fuel_notes,
        routes_terrain_suitability: selectedCatalog.routes_terrain_suitability,
        special_transport_features: selectedCatalog.special_transport_features,
        constraints_tradeoffs: selectedCatalog.constraints_tradeoffs,
      }))
      if (!data.get('capacity') && selectedCatalog.payload_max_kg) {
        data.set('capacity', String(Number(selectedCatalog.payload_max_kg) / 1000))
      }
      if (!data.get('mainUse') && Array.isArray(selectedCatalog.common_uses)) {
        data.set('mainUse', selectedCatalog.common_uses[0] || 'General Cargo')
      }
    }

    try {
      const csrf = sessionStorage.getItem('csrf_token') || ''
      const res = await fetch('/api/trucks', {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': csrf } : {},
        body: data,
      })
      const result = await res.json()

      if (result.success) {
        setSuccess('Truck registered successfully!')
        form.reset()
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

  return (
      <div className="page-add-truck">
        {/* Page Title */}
        <div className="page-title">
          <div>
            <h1>Register <span>New Truck</span></h1>
            <p>Fill in the details below to add your truck to the fleet</p>
          </div>
        </div>

        {/* Alerts */}
        {error && (
          <div style={{
            background: '#fee2e2', color: '#dc2626', padding: '0.75rem 1rem',
            borderRadius: '8px', marginBottom: '1rem', fontSize: '0.9rem',
            border: '1px solid #fca5a5'
          }}>
            <i className="fas fa-exclamation-circle"></i> {error}
          </div>
        )}
        {success && (
          <div style={{
            background: '#dcfce7', color: '#16a34a', padding: '0.75rem 1rem',
            borderRadius: '8px', marginBottom: '1rem', fontSize: '0.9rem',
            border: '1px solid #86efac'
          }}>
            <i className="fas fa-check-circle"></i> {success}
          </div>
        )}

        {/* Truck Registration Form */}
        <form id="truckForm" onSubmit={handleSubmit}>

          {/* Card 1: Truck Details */}
          <div className="form-card">
            <div className="card-header">
              <div className="card-icon"><i className="fas fa-truck"></i></div>
              <div>
                <h2 className="card-title">Truck Details</h2>
                <p className="card-subtitle">Basic information about your truck</p>
              </div>
            </div>

            <div className="fields-grid">
              <div className="form-group">
                <label htmlFor="truckNumber" className="required">Truck Number</label>
                <input type="text" id="truckNumber" name="truckNumber" required
                  placeholder="Example: LE-1234, ABC 12345" />
              </div>

              <div className="form-group">
                <label htmlFor="truckType" className="required">Truck Type</label>
                <select
                  id="truckType"
                  name="truckType"
                  required
                  value={selectedTypeKey}
                  onChange={e => setSelectedTypeKey(e.target.value)}
                >
                  <option value="">Select Truck Type</option>
                  {truckTypes.map(type => (
                    <option key={type.type_key} value={type.type_key}>{type.display_name}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="chassisNumber" className="required">Chassis Number</label>
                <input type="text" id="chassisNumber" name="chassisNumber" required
                  pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}"
                  placeholder="11 to 17 letters/numbers from vehicle documents" />
                <small>11-17 characters, letters and numbers only (I, O, Q not allowed)</small>
              </div>

              <div className="form-group">
                <label htmlFor="capacity" className="required">Capacity (tons)</label>
                <input type="number" id="capacity" name="capacity" required min="0.1" step="0.1"
                  placeholder={selectedCatalog?.payload_max_kg ? `Catalog max: ${(Number(selectedCatalog.payload_max_kg) / 1000).toFixed(1)} tons` : 'Example: 10'} />
              </div>

              <div className="form-group full-width">
                <label htmlFor="mainUse" className="required">Main Use</label>
                <select id="mainUse" name="mainUse" required>
                  <option value="">Select Main Use</option>
                  {(selectedCatalog?.common_uses?.length ? selectedCatalog.common_uses : [
                    'Milk Transport', 'Water Transport', 'Oil Transport', 'Cement Transport',
                    'Container Transport', 'General Cargo', 'Refrigerated Goods', 'Waste/Garbage', 'Livestock',
                  ]).map(use => <option key={use} value={use}>{use}</option>)}
                </select>
              </div>
            </div>
            {selectedCatalog && (
              <div style={{ marginTop: '1rem', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem' }}>
                <div style={{ fontWeight: 700, color: '#1e293b', marginBottom: 6 }}>{selectedCatalog.class_segment}</div>
                <div style={{ color: '#475569', fontSize: '0.9rem' }}>{selectedCatalog.common_local_names}</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', marginTop: '0.8rem', fontSize: '0.85rem' }}>
                  <div><strong>Payload:</strong> {Number(selectedCatalog.payload_min_kg || 0).toLocaleString()}-{Number(selectedCatalog.payload_max_kg || 0).toLocaleString()} kg</div>
                  <div><strong>Volume:</strong> {selectedCatalog.volume_min_cbm}-{selectedCatalog.volume_max_cbm} cbm</div>
                  <div><strong>Body:</strong> {selectedCatalog.typical_body_style || '-'}</div>
                  <div><strong>Companies:</strong> {selectedCatalog.companies_models || '-'}</div>
                </div>
              </div>
            )}
          </div>

          {/* Card 2: Driver & Tracking (Optional) */}
          <div className="form-card">
            <div className="card-header">
              <div className="card-icon card-icon-green"><i className="fas fa-id-badge"></i></div>
              <div>
                <h2 className="card-title">Driver &amp; Tracking <span className="badge-optional">Optional</span></h2>
                <p className="card-subtitle">You can fill these later from truck settings</p>
              </div>
            </div>

            <div className="fields-grid">
              <div className="form-group">
                <label htmlFor="driverName" className="optional">Driver Name</label>
                <input type="text" id="driverName" name="driverName"
                  placeholder="Optional - Driver full name" />
              </div>

              <div className="form-group">
                <label htmlFor="driverCnic" className="optional">Driver CNIC</label>
                <input type="text" id="driverCnic" name="driverCnic"
                  placeholder="Optional - 13 digit CNIC" />
              </div>

              <div className="form-group">
                <label htmlFor="trackingId" className="optional">GPS Device IMEI</label>
                <input type="text" id="trackingId" name="trackingId"
                  placeholder="Optional - 15-digit GPS device IMEI number" />
              </div>
            </div>
          </div>

          {/* Submit Button */}
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
