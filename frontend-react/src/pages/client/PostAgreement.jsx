import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { loadTruckCatalog } from '../../lib/truckCatalog'
import { PageTitle, PrimaryButton, SecondaryButton, SectionCard, StateMessage, apiSend } from './clientUtils'

const SERVICE_AREAS = ['Punjab', 'Sindh', 'Khyber Pakhtunkhwa', 'Balochistan', 'Islamabad', 'Karachi', 'Lahore', 'Faisalabad', 'Rawalpindi', 'Multan', 'Peshawar', 'Quetta']
const CARGO_TYPES = ['General goods', 'FMCG', 'Construction material', 'Textile', 'Pharmaceuticals', 'Chemicals', 'Perishables', 'Milk', 'Fuel', 'Other']
const EMPTY_TRUCK = { truck_type: '', capacity_tons: '', quantity: '1' }

export default function PostAgreement() {
  const navigate = useNavigate()
  const [catalog, setCatalog] = useState([])
  const [form, setForm] = useState({ title: '', cargo_type: '', service_area: [], trucks: [{ ...EMPTY_TRUCK }] })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    loadTruckCatalog().then(setCatalog).finally(() => setLoading(false))
  }, [])

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function toggleArea(area) {
    setForm((current) => {
      const exists = current.service_area.includes(area)
      return { ...current, service_area: exists ? current.service_area.filter((item) => item !== area) : [...current.service_area, area] }
    })
  }

  function updateTruck(index, field, value) {
    setForm((current) => ({
      ...current,
      trucks: current.trucks.map((truck, truckIndex) => truckIndex === index ? { ...truck, [field]: value } : truck),
    }))
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const json = await apiSend('/api/agreements/posts', form)
      setNotice('Agreement post created.')
      setTimeout(() => navigate(`/client/agreement-bids/${json.post.id}`), 700)
    } catch (submitError) {
      setError(submitError.message || 'Unable to post agreement.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageTitle title="Post Agreement" subtitle="Create a long-term shipment requirement for GPS-enabled transporters." />
      <SectionCard title="Agreement Shipment" icon="fa-file-contract">
        {loading && <StateMessage type="loading">Loading truck catalog...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {notice && <StateMessage type="success">{notice}</StateMessage>}
        <form className="grid gap-5" onSubmit={submit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Title
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" name="title" value={form.title} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Cargo type
              <select className="rounded-lg border border-slate-300 px-3 py-2.5" name="cargo_type" value={form.cargo_type} onChange={updateField} required>
                <option value="">Select cargo</option>
                {CARGO_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>

          <div>
            <div className="mb-2 text-sm font-semibold text-slate-700">Service area</div>
            <div className="flex flex-wrap gap-2">
              {SERVICE_AREAS.map((area) => (
                <button
                  key={area}
                  type="button"
                  onClick={() => toggleArea(area)}
                  className={`rounded-lg border px-3 py-2 text-sm font-semibold ${form.service_area.includes(area) ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-300 bg-white text-slate-700'}`}
                >
                  {area}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3">
            <div className="text-sm font-semibold text-slate-700">Trucks needed</div>
            {form.trucks.map((truck, index) => (
              <div key={index} className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-4">
                <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
                  Truck type
                  <select className="rounded-lg border border-slate-300 px-3 py-2.5" value={truck.truck_type} onChange={(event) => updateTruck(index, 'truck_type', event.target.value)} required>
                    <option value="">Select truck</option>
                    {catalog.map((item) => <option key={item.type_key} value={item.type_key}>{item.display_name}</option>)}
                  </select>
                </label>
                <label className="grid gap-2 text-sm font-medium text-slate-700">
                  Capacity tons
                  <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0.1" step="0.1" value={truck.capacity_tons} onChange={(event) => updateTruck(index, 'capacity_tons', event.target.value)} required />
                </label>
                <label className="grid gap-2 text-sm font-medium text-slate-700">
                  Quantity
                  <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="1" step="1" value={truck.quantity} onChange={(event) => updateTruck(index, 'quantity', event.target.value)} required />
                </label>
              </div>
            ))}
            <div className="flex flex-wrap gap-3">
              <SecondaryButton type="button" onClick={() => setForm((current) => ({ ...current, trucks: [...current.trucks, { ...EMPTY_TRUCK }] }))}>
                <i className="fas fa-plus" aria-hidden="true"></i>
                Add another truck type
              </SecondaryButton>
              {form.trucks.length > 1 && (
                <SecondaryButton type="button" onClick={() => setForm((current) => ({ ...current, trucks: current.trucks.slice(0, -1) }))}>
                  <i className="fas fa-minus" aria-hidden="true"></i>
                  Remove last row
                </SecondaryButton>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <PrimaryButton type="submit" disabled={saving || loading}>
              <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
              {saving ? 'Posting...' : 'Post agreement'}
            </PrimaryButton>
            <Link className="inline-flex min-h-10 items-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700" to="/client/my-agreements">My agreements</Link>
          </div>
        </form>
      </SectionCard>
    </>
  )
}
