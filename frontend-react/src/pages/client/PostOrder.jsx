import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  apiSend,
} from './clientUtils'
import { loadTruckCatalog } from '../../lib/truckCatalog'

const GOODS_OPTIONS = [
  'General goods',
  'FMCG',
  'Construction material',
  'Electronics',
  'Pharmaceuticals',
  'Chemicals',
  'Milk',
  'Perishables',
  'Textile',
  'Other',
]

const INITIAL_FORM = {
  pickup_city: '',
  pickup_area: '',
  dropoff_city: '',
  dropoff_area: '',
  pickup_date: '',
  pickup_time: '',
  goods_type: '',
  goods_weight_tons: '',
  goods_volume_cbm: '',
  required_truck_type: '',
  estimated_budget: '',
  notes: '',
}

export default function PostOrder() {
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL_FORM)
  const [truckTypes, setTruckTypes] = useState([])
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [walletBlocked, setWalletBlocked] = useState(false)
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let ignore = false
    loadTruckCatalog()
      .then((items) => {
        if (!ignore) setTruckTypes(items)
      })
      .finally(() => {
        if (!ignore) setLoadingCatalog(false)
      })
    return () => {
      ignore = true
    }
  }, [])

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setSuccess('')
    setWalletBlocked(false)

    try {
      await apiSend('/api/orders', form)
      setSuccess('Order posted successfully. Transporters can start bidding now.')
      setForm(INITIAL_FORM)
      setTimeout(() => navigate('/client/orders'), 900)
    } catch (submitError) {
      const message = submitError.message || 'Unable to post order right now.'
      setError(message)
      setWalletBlocked(message.includes('Minimum wallet balance'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageTitle
        title="Post Order"
        subtitle="Create a shipment request and let matching transporters compete with reverse bids."
      />

      <SectionCard title="Shipment Details" icon="fa-boxes-stacked">
        {loadingCatalog && <StateMessage type="loading">Loading truck catalog...</StateMessage>}
        {error && (
          <StateMessage type="error" title="Order could not be posted">
            <div className="space-y-3">
              <p>{error}</p>
              {walletBlocked && (
                <Link
                  to="/client/wallet"
                  className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600"
                >
                  <i className="fas fa-wallet" aria-hidden="true"></i>
                  Go to Wallet
                </Link>
              )}
            </div>
          </StateMessage>
        )}
        {success && <StateMessage type="success">{success}</StateMessage>}

        <form className="grid gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Pickup city
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" name="pickup_city" value={form.pickup_city} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Pickup area
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" name="pickup_area" value={form.pickup_area} onChange={updateField} />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Dropoff city
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" name="dropoff_city" value={form.dropoff_city} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Dropoff area
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" name="dropoff_area" value={form.dropoff_area} onChange={updateField} />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Pickup date
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="date" name="pickup_date" value={form.pickup_date} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Pickup time
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="time" name="pickup_time" value={form.pickup_time} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Goods type
              <select className="rounded-lg border border-slate-300 px-3 py-2.5" name="goods_type" value={form.goods_type} onChange={updateField} required>
                <option value="">Select goods</option>
                {GOODS_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Goods weight (tons)
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0.1" step="0.1" name="goods_weight_tons" value={form.goods_weight_tons} onChange={updateField} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Goods volume (cbm)
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0" step="0.1" name="goods_volume_cbm" value={form.goods_volume_cbm} onChange={updateField} />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Required truck type
              <select className="rounded-lg border border-slate-300 px-3 py-2.5" name="required_truck_type" value={form.required_truck_type} onChange={updateField} required>
                <option value="">Select truck type</option>
                {truckTypes.map((type) => (
                  <option key={type.type_key} value={type.type_key}>{type.display_name}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
              Estimated budget
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0" step="0.01" name="estimated_budget" value={form.estimated_budget} onChange={updateField} />
              <span className="text-xs font-normal text-slate-500">Optional - helps transporters bid appropriately</span>
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
              Notes
              <textarea className="min-h-28 rounded-lg border border-slate-300 px-3 py-2.5" name="notes" value={form.notes} onChange={updateField} placeholder="Loading instructions, timing flexibility, packaging notes..." />
            </label>
          </div>

          <div className="flex flex-wrap gap-3">
            <PrimaryButton type="submit" disabled={submitting || loadingCatalog}>
              <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
              {submitting ? 'Posting order...' : 'Post order'}
            </PrimaryButton>
            <Link to="/client/orders" className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              View my orders
            </Link>
          </div>
        </form>
      </SectionCard>
    </>
  )
}
