import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  apiSend,
} from './clientUtils'
import {
  CATEGORY_TREE,
  F,
  fieldsFor,
  flagsFor,
  requiredFieldsFor,
  getCommodity,
} from '../../lib/goodsTaxonomy'
import { FALLBACK_TRUCK_TYPES } from '../../lib/truckCatalog'
import LocationPicker from '../../components/common/LocationPicker'
import useClientBasePath from '../../hooks/useClientBasePath'

const TRUCK_LABELS = Object.fromEntries(FALLBACK_TRUCK_TYPES.map((t) => [t.type_key, t.display_name]))
function truckLabel(key) {
  return TRUCK_LABELS[key] || key.replace(/_/g, ' ')
}

const EMPTY_LOCATION = { location: '', lat: null, lng: null }

// Client must give the transporter at least this long to prepare the truck.
const LEAD_MINUTES = 20

function pad(n) {
  return String(n).padStart(2, '0')
}
// Earliest datetime a pickup may be scheduled: now + LEAD_MINUTES.
function earliestPickup() {
  const d = new Date(Date.now() + LEAD_MINUTES * 60 * 1000)
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  }
}

const INITIAL_FORM = {
  pickup_date: '',
  pickup_time: '',
  // goods taxonomy
  goods_category: '',
  goods_form: '',
  goods_commodity: '',
  // measurements
  goods_weight_tons: '',
  goods_volume_cbm: '',
  volume_liters: '',
  length_cm: '',
  width_cm: '',
  height_cm: '',
  quantity: '',
  animal_count: '',
  temperature_c: '',
  estimated_budget: '',
  notes: '',
}

const inputCls = 'rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100'
const labelCls = 'grid gap-2 text-sm font-medium text-slate-700'

export default function PostOrder() {
  const navigate = useNavigate()
  const base = useClientBasePath()
  const [form, setForm] = useState(INITIAL_FORM)
  const [pickup, setPickup] = useState(EMPTY_LOCATION)
  const [dropoff, setDropoff] = useState(EMPTY_LOCATION)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Lock out past dates/times plus the required lead time for the transporter.
  const earliest = earliestPickup()
  const minDate = earliest.date
  const minTime = form.pickup_date === earliest.date ? earliest.time : '00:00'

  const category = useMemo(() => CATEGORY_TREE.find((c) => c.key === form.goods_category) || null, [form.goods_category])
  const hasForms = !!(category && category.forms && category.forms.length)
  const formNode = useMemo(
    () => (hasForms ? category.forms.find((f) => f.key === form.goods_form) || null : null),
    [category, hasForms, form.goods_form],
  )
  const commodityList = hasForms ? (formNode ? formNode.commodities : []) : category ? category.commodities : []

  const commodityMeta = getCommodity(form.goods_commodity)
  const activeFields = form.goods_commodity ? fieldsFor(form.goods_commodity) : []
  const requiredFields = form.goods_commodity ? requiredFieldsFor(form.goods_commodity) : []
  const flags = form.goods_commodity ? flagsFor(form.goods_commodity) : {}
  const suitableTrucks = commodityMeta ? commodityMeta.trucks || [] : []

  function has(field) {
    return activeFields.includes(field)
  }
  function req(field) {
    return requiredFields.includes(field)
  }

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function onCategory(event) {
    setForm((current) => ({ ...current, goods_category: event.target.value, goods_form: '', goods_commodity: '' }))
  }
  function onForm(event) {
    setForm((current) => ({ ...current, goods_form: event.target.value, goods_commodity: '' }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setSuccess('')

    if (!pickup.location.trim() || !dropoff.location.trim()) {
      setError('Please enter both pickup and dropoff locations.')
      setSubmitting(false)
      return
    }
    if (!form.goods_commodity) {
      setError('Please choose the goods category and commodity.')
      setSubmitting(false)
      return
    }
    if (form.pickup_date && form.pickup_time) {
      const chosen = new Date(`${form.pickup_date}T${form.pickup_time}`)
      const floor = new Date(Date.now() + LEAD_MINUTES * 60 * 1000)
      if (chosen < floor) {
        setError(`Pickup must be at least ${LEAD_MINUTES} minutes from now so the transporter has time to prepare.`)
        setSubmitting(false)
        return
      }
    }

    const payload = {
      ...form,
      pickup_location: pickup.location.trim(),
      pickup_lat: pickup.lat,
      pickup_lng: pickup.lng,
      dropoff_location: dropoff.location.trim(),
      dropoff_lat: dropoff.lat,
      dropoff_lng: dropoff.lng,
    }

    try {
      await apiSend('/api/orders', payload)
      setSuccess('Order posted successfully. Matching transporters can start bidding now.')
      setForm(INITIAL_FORM)
      setPickup(EMPTY_LOCATION)
      setDropoff(EMPTY_LOCATION)
      setTimeout(() => navigate(`${base}/orders`), 900)
    } catch (submitError) {
      setError(submitError.message || 'Unable to post order right now.')
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
        {error && (
          <StateMessage type="error" title="Order could not be posted">
            <p>{error}</p>
          </StateMessage>
        )}
        {success && <StateMessage type="success">{success}</StateMessage>}

        <form className="grid gap-5" onSubmit={handleSubmit}>
          {/* ---- Route: single detailed location + map picker ---- */}
          <div className="grid gap-5 md:grid-cols-2">
            <LocationPicker
              label="Pickup location"
              required
              value={pickup}
              onChange={setPickup}
              placeholder="Shop / house, street, area, city"
            />
            <LocationPicker
              label="Dropoff location"
              required
              value={dropoff}
              onChange={setDropoff}
              placeholder="Shop / house, street, area, city"
            />
          </div>

          {/* ---- Schedule ---- */}
          <div className="grid gap-4 md:grid-cols-2">
            <label className={labelCls}>
              Pickup date
              <input className={inputCls} type="date" name="pickup_date" min={minDate} value={form.pickup_date} onChange={updateField} required />
            </label>
            <label className={labelCls}>
              Pickup time
              <input className={inputCls} type="time" name="pickup_time" min={minTime} value={form.pickup_time} onChange={updateField} required />
            </label>
          </div>

          {/* ---- Goods classification (State -> Form -> Commodity) ---- */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Goods classification</div>
            <div className="grid gap-4 md:grid-cols-3">
              <label className={labelCls}>
                Category
                <select className={inputCls} name="goods_category" value={form.goods_category} onChange={onCategory} required>
                  <option value="">Select state</option>
                  {CATEGORY_TREE.map((c) => (
                    <option key={c.key} value={c.key}>{c.label}</option>
                  ))}
                </select>
              </label>

              {hasForms && (
                <label className={labelCls}>
                  Form
                  <select className={inputCls} name="goods_form" value={form.goods_form} onChange={onForm} required>
                    <option value="">Select form</option>
                    {category.forms.map((f) => (
                      <option key={f.key} value={f.key}>{f.label}</option>
                    ))}
                  </select>
                </label>
              )}

              <label className={labelCls}>
                Commodity
                <select
                  className={inputCls}
                  name="goods_commodity"
                  value={form.goods_commodity}
                  onChange={updateField}
                  required
                  disabled={!category || (hasForms && !formNode)}
                >
                  <option value="">Select commodity</option>
                  {commodityList.map((item) => (
                    <option key={item.key} value={item.key}>{item.label}</option>
                  ))}
                </select>
              </label>
            </div>

            {commodityMeta && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-slate-600">Suitable trucks:</span>
                {suitableTrucks.map((k) => (
                  <span key={k} className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 font-medium text-blue-700">
                    {truckLabel(k)}
                  </span>
                ))}
                {flags.refrigerated && <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 font-medium text-sky-700"><i className="fas fa-snowflake" /> Refrigerated</span>}
                {flags.hazardous && <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 font-medium text-red-700"><i className="fas fa-triangle-exclamation" /> Hazardous</span>}
                {flags.food_grade && <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-medium text-emerald-700"><i className="fas fa-utensils" /> Food-grade</span>}
              </div>
            )}
          </div>

          {/* ---- Adaptive measurement fields ---- */}
          {form.goods_commodity && (
            <div className="grid gap-4 md:grid-cols-3">
              {has(F.DIMENSIONS) && (
                <>
                  <label className={labelCls}>
                    Length (cm){req(F.DIMENSIONS) && ' *'}
                    <input className={inputCls} type="number" min="0" step="1" name="length_cm" value={form.length_cm} onChange={updateField} required={req(F.DIMENSIONS)} />
                  </label>
                  <label className={labelCls}>
                    Width (cm){req(F.DIMENSIONS) && ' *'}
                    <input className={inputCls} type="number" min="0" step="1" name="width_cm" value={form.width_cm} onChange={updateField} required={req(F.DIMENSIONS)} />
                  </label>
                  <label className={labelCls}>
                    Height (cm){req(F.DIMENSIONS) && ' *'}
                    <input className={inputCls} type="number" min="0" step="1" name="height_cm" value={form.height_cm} onChange={updateField} required={req(F.DIMENSIONS)} />
                  </label>
                </>
              )}

              {has(F.WEIGHT) && (
                <label className={labelCls}>
                  Weight (tons){req(F.WEIGHT) && ' *'}
                  <input className={inputCls} type="number" min="0" step="0.1" name="goods_weight_tons" value={form.goods_weight_tons} onChange={updateField} required={req(F.WEIGHT)} />
                </label>
              )}

              {has(F.VOLUME_CBM) && (
                <label className={labelCls}>
                  Volume (cbm)
                  <input className={inputCls} type="number" min="0" step="0.1" name="goods_volume_cbm" value={form.goods_volume_cbm} onChange={updateField} />
                </label>
              )}

              {has(F.VOLUME_LITERS) && (
                <label className={labelCls}>
                  Volume (liters){req(F.VOLUME_LITERS) && ' *'}
                  <input className={inputCls} type="number" min="0" step="1" name="volume_liters" value={form.volume_liters} onChange={updateField} required={req(F.VOLUME_LITERS)} />
                </label>
              )}

              {has(F.QUANTITY) && (
                <label className={labelCls}>
                  Quantity (pieces)
                  <input className={inputCls} type="number" min="0" step="1" name="quantity" value={form.quantity} onChange={updateField} />
                </label>
              )}

              {has(F.ANIMAL_COUNT) && (
                <label className={labelCls}>
                  Number of animals{req(F.ANIMAL_COUNT) && ' *'}
                  <input className={inputCls} type="number" min="0" step="1" name="animal_count" value={form.animal_count} onChange={updateField} required={req(F.ANIMAL_COUNT)} />
                </label>
              )}

              {has(F.TEMPERATURE) && (
                <label className={labelCls}>
                  Required temperature (°C)
                  <input className={inputCls} type="number" step="0.5" name="temperature_c" value={form.temperature_c} onChange={updateField} placeholder="e.g. 4 or -18" />
                </label>
              )}
            </div>
          )}

          {/* ---- Budget & notes ---- */}
          <div className="grid gap-4 md:grid-cols-2">
            <label className={`${labelCls} md:col-span-2`}>
              Estimated budget
              <input className={inputCls} type="number" min="0" step="0.01" name="estimated_budget" value={form.estimated_budget} onChange={updateField} />
              <span className="text-xs font-normal text-slate-500">Optional - helps transporters bid appropriately</span>
            </label>
            <label className={`${labelCls} md:col-span-2`}>
              Notes
              <textarea className={`min-h-28 ${inputCls}`} name="notes" value={form.notes} onChange={updateField} placeholder="Loading instructions, timing flexibility, packaging notes..." />
            </label>
          </div>

          <div className="flex flex-wrap gap-3">
            <PrimaryButton type="submit" disabled={submitting}>
              <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
              {submitting ? 'Posting order...' : 'Post order'}
            </PrimaryButton>
            <Link to={`${base}/orders`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              View my orders
            </Link>
          </div>
        </form>
      </SectionCard>
    </>
  )
}
