import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../../styles/pages/add-truck.css'

const BODY_TYPE_OPTIONS = ['Open Body', 'Box Body', 'Trailer', 'Tanker', 'Refrigerated', 'Livestock', 'Other']

const BODY_DETAIL_OPTIONS = {
  Tanker: {
    label: 'Tanker Type',
    name: 'tanker_type',
    options: ['Fuel', 'Milk', 'Water', 'Chemical', 'LPG', 'Cement Powder', 'Food Oil', 'Bitumen', 'Molasses', 'Other'],
  },
  Trailer: {
    label: 'Trailer Type',
    name: 'trailer_type',
    options: ['Flatbed', 'Container Carrier', 'Skeletal Trailer', 'Low-bed Trailer', 'Extendable Trailer', 'Curtain Side Trailer', 'Other'],
  },
  'Open Body': {
    label: 'Open Body Type',
    name: 'open_body_type',
    options: ['Standard Flatbed', 'Low-side', 'High-side', 'High Deck', 'Other'],
  },
  'Box Body': {
    label: 'Box Type',
    name: 'box_type',
    options: ['Dry Box', 'Insulated Box', 'Parcel Box', 'Furniture Box', 'Other'],
  },
}

const TEMPERATURE_OPTIONS = [
  { value: 'Chilled (0C to 8C)', label: 'Chilled (0C to 8C)' },
  { value: 'Frozen (-18C)', label: 'Frozen (-18C)' },
  { value: 'Both', label: 'Both' },
]

const LIVESTOCK_OPTIONS = ['Cattle', 'Sheep', 'Goats', 'Poultry', 'Other']

export default function AddTruck() {
  const navigate = useNavigate()
  const [bodyType, setBodyType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess('')

    const form = e.target
    const data = new FormData(form)
    const selectedBodyType = String(data.get('body_style') || '')

    if (!selectedBodyType) {
      setError('Body Type is required.')
      return
    }

    const detailConfig = BODY_DETAIL_OPTIONS[selectedBodyType]
    if (detailConfig && !String(data.get(detailConfig.name) || '').trim()) {
      setError(`${detailConfig.label} is required.`)
      return
    }

    if (selectedBodyType === 'Refrigerated' && !String(data.get('temperature_range') || '').trim()) {
      setError('Temperature Range is required.')
      return
    }

    const livestockTypes = data.getAll('livestock_type')
    if (selectedBodyType === 'Livestock' && livestockTypes.length === 0) {
      setError('Livestock Type is required.')
      return
    }

    const bodySpecs = {
      body_type: selectedBodyType,
      detail_type: detailConfig ? data.get(detailConfig.name) : '',
      temperature_range: selectedBodyType === 'Refrigerated' ? data.get('temperature_range') : '',
      livestock_types: selectedBodyType === 'Livestock' ? livestockTypes : [],
    }
    data.set('catalog_specs_json', JSON.stringify(bodySpecs))
    data.set('truckType', selectedBodyType)
    data.set('truck_type', selectedBodyType)
    data.set('mainUse', selectedBodyType)

    setSubmitting(true)

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
        setBodyType('')
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

  const detailConfig = BODY_DETAIL_OPTIONS[bodyType]

  return (
      <div className="page-add-truck">
        <div className="page-title">
          <div>
            <h1>Register <span>New Truck</span></h1>
            <p>Fill in the details below to add your truck to the fleet</p>
          </div>
        </div>

        {error && (
          <div className="addtruck-alert addtruck-alert--error">
            <i className="fas fa-exclamation-circle"></i> {error}
          </div>
        )}
        {success && (
          <div className="addtruck-alert addtruck-alert--success">
            <i className="fas fa-check-circle"></i> {success}
          </div>
        )}

        <form id="truckForm" onSubmit={handleSubmit}>
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
                <label htmlFor="truckCompany" className="required">Truck Company</label>
                <input type="text" id="truckCompany" name="truckCompany" required
                  placeholder="Example: Hino, ISUZU" />
              </div>

              <div className="form-group">
                <label htmlFor="truckModel" className="required">Truck Model</label>
                <input type="text" id="truckModel" name="truckModel" required
                  placeholder="Example: Hino 500, ISUZU NPR" />
              </div>

              <div className="form-group weight-capacity-group">
                <label className="required">Weight Capacity</label>
                <div className="weight-capacity-row">
                  <div className="weight-capacity-field">
                    <input type="number" name="payload_min_tons" required min="0" step="0.1" placeholder="Min" />
                    <span className="weight-capacity-unit">ton</span>
                  </div>
                  <div className="weight-capacity-field">
                    <input type="number" name="payload_max_tons" required min="0" step="0.1" placeholder="Max" />
                    <span className="weight-capacity-unit">ton</span>
                  </div>
                </div>
              </div>

              <div className="form-group weight-capacity-group">
                <label>Cargo Bed Size (feet)</label>
                <p style={{ margin: '2px 0 6px', fontSize: '12px', color: '#9CA3AF' }}>
                  For long/wide loads like steel bars (sariya), girders or pipes. Leave blank if open/unlimited.
                </p>
                <div className="weight-capacity-row">
                  <div className="weight-capacity-field">
                    <input type="number" name="bed_length_ft" min="0" step="0.5" placeholder="Length" />
                    <span className="weight-capacity-unit">ft</span>
                  </div>
                  <div className="weight-capacity-field">
                    <input type="number" name="bed_width_ft" min="0" step="0.5" placeholder="Width" />
                    <span className="weight-capacity-unit">ft</span>
                  </div>
                  <div className="weight-capacity-field">
                    <input type="number" name="bed_height_ft" min="0" step="0.5" placeholder="Height" />
                    <span className="weight-capacity-unit">ft</span>
                  </div>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="bodyType" className="required">Body Type</label>
                <select id="bodyType" name="body_style" required value={bodyType} onChange={e => setBodyType(e.target.value)}>
                  <option value="" disabled>Select Body Type</option>
                  {BODY_TYPE_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                </select>
              </div>

              {detailConfig && (
                <div className="form-group body-detail-field">
                  <label htmlFor={detailConfig.name} className="required">{detailConfig.label}</label>
                  <select id={detailConfig.name} name={detailConfig.name} required>
                    <option value="" disabled>Select {detailConfig.label}</option>
                    {detailConfig.options.map(option => <option key={option} value={option}>{option}</option>)}
                  </select>
                </div>
              )}

              {bodyType === 'Refrigerated' && (
                <div className="form-group full-width body-detail-panel">
                  <label className="required">Temperature Range</label>
                  <div className="choice-grid choice-grid--radio">
                    {TEMPERATURE_OPTIONS.map(option => (
                      <label key={option.value} className="choice-pill">
                        <input type="radio" name="temperature_range" value={option.value} required />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {bodyType === 'Livestock' && (
                <div className="form-group full-width body-detail-panel">
                  <label className="required">Livestock Type</label>
                  <div className="choice-grid">
                    {LIVESTOCK_OPTIONS.map(option => (
                      <label key={option} className="choice-pill">
                        <input type="checkbox" name="livestock_type" value={option} />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="chassisNumber" className="required">Chassis Number</label>
                <input type="text" id="chassisNumber" name="chassisNumber" required
                  pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{11,17}"
                  placeholder="11 to 17 letters/numbers from vehicle documents" />
                <small>11-17 characters, letters and numbers only (I, O, Q not allowed)</small>
              </div>
            </div>
          </div>

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
