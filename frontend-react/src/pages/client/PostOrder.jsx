import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  apiGet,
  apiSend,
} from './clientUtils'
import {
  CLIENT_GOODS_GROUPS,
  F,
  FT_TO_CM,
  LENGTH_FEET_PRESETS,
  LIQUID_QUICK_PRESETS,
  LIVESTOCK_PRESETS,
  MAX_ORDER_LITERS,
  MAX_ORDER_TONS,
  MIN_ORDER_LITERS,
  MIN_ORDER_TONS,
  TEMPERATURE_PRESETS,
  WEIGHT_QUICK_PRESETS,
  fieldsFor,
  findGroupForCommodity,
  flagsFor,
  getCommodity,
  inferPakistanProvince,
  requiredFieldsFor,
  supportsLitersForCommodity,
} from '../../lib/goodsTaxonomy'
import { FALLBACK_TRUCK_TYPES } from '../../lib/truckCatalog'
import LocationPicker from '../../components/common/LocationPicker'
import OrderWorkspaceNavigation from '../../components/client/OrderWorkspaceNavigation'
import { openPendingReviewModal } from '../../components/common/reviewEvents'
import useClientBasePath from '../../hooks/useClientBasePath'
import { pickupBounds, pickupScheduleError } from '../../lib/pickupSchedule'

const TRUCK_LABELS = Object.fromEntries(FALLBACK_TRUCK_TYPES.map((t) => [t.type_key, t.display_name]))
function truckLabel(key) {
  return TRUCK_LABELS[key] || key.replace(/_/g, ' ')
}

const EMPTY_LOCATION = { location: '', lat: null, lng: null }

function buildInitialSchedule() {
  const { earliest } = pickupBounds(Date.now() + 15 * 60_000)
  return {
    pickup_date: earliest.date,
    pickup_time: earliest.time,
  }
}

function createInitialForm() {
  const sched = buildInitialSchedule()
  return {
    pickup_date: sched.pickup_date,
    pickup_time: sched.pickup_time,
    // goods taxonomy
    goods_group: 'general_shifting',
    goods_category: 'solid',
    goods_form: 'packaged',
    goods_commodity: 'general_cargo',
    // measurements
    goods_weight_tons: '3.5',
    goods_volume_cbm: '',
    volume_liters: '',
    length_ft: '',
    length_cm: '',
    width_cm: '',
    height_cm: '',
    quantity: '',
    animal_count: '',
    livestock_type: 'Cattle',
    temperature_c: '',
    estimated_budget: '',
    notes: '',
  }
}

const inputCls = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100'
const labelCls = 'grid gap-1.5 text-sm font-semibold text-slate-700'

export default function PostOrder() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const base = useClientBasePath()
  const [form, setForm] = useState(createInitialForm)
  const [capacityUnit, setCapacityUnit] = useState('tons')
  const [capacityWarning, setCapacityWarning] = useState('')
  const [pickup, setPickup] = useState(EMPTY_LOCATION)
  const [dropoff, setDropoff] = useState(EMPTY_LOCATION)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [scheduleNow, setScheduleNow] = useState(Date.now)

  useEffect(() => {
    const timer = setInterval(() => setScheduleNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])

  // Pre-fill form if duplicating an existing order (?copy=<order_id>)
  useEffect(() => {
    const copyId = searchParams.get('copy')
    if (!copyId) return
    let cancelled = false
    apiGet(`/api/orders/${copyId}`)
      .then((res) => {
        if (cancelled || !res || !res.order) return
        const o = res.order
        const commKey = o.goods_commodity || 'general_cargo'
        const grpKey = findGroupForCommodity(commKey) || 'general_shifting'
        const lenCm = Number(o.length_cm)
        const lenFt = Number.isFinite(lenCm) && lenCm > 0 ? String(Math.round((lenCm / FT_TO_CM) * 10) / 10) : ''
        setForm((prev) => ({
          ...prev,
          goods_group: grpKey,
          goods_category: o.goods_category || prev.goods_category,
          goods_form: o.goods_form || '',
          goods_commodity: commKey,
          goods_weight_tons: o.goods_weight_tons != null ? String(o.goods_weight_tons) : '',
          goods_volume_cbm: o.goods_volume_cbm != null ? String(o.goods_volume_cbm) : '',
          volume_liters: o.volume_liters != null ? String(o.volume_liters) : '',
          length_ft: lenFt,
          length_cm: o.length_cm != null ? String(o.length_cm) : '',
          width_cm: o.width_cm != null ? String(o.width_cm) : '',
          height_cm: o.height_cm != null ? String(o.height_cm) : '',
          quantity: o.quantity != null ? String(o.quantity) : '',
          animal_count: o.animal_count != null ? String(o.animal_count) : '',
          temperature_c: o.temperature_c != null ? String(o.temperature_c) : '',
          estimated_budget: o.estimated_budget != null ? String(o.estimated_budget) : '',
          notes: o.notes || '',
        }))
        if (o.pickup_location || o.pickup_city) {
          setPickup({
            location: o.pickup_location || o.pickup_city || '',
            lat: o.pickup_lat || null,
            lng: o.pickup_lng || null,
          })
        }
        if (o.dropoff_location || o.dropoff_city) {
          setDropoff({
            location: o.dropoff_location || o.dropoff_city || '',
            lat: o.dropoff_lat || null,
            lng: o.dropoff_lng || null,
          })
        }
      })
      .catch((err) => {
        console.warn('Could not load order to duplicate:', err)
      })
    return () => {
      cancelled = true
    }
  }, [searchParams])

  // Lock out past dates/times plus the required lead time for the transporter.
  const { earliest, latest } = pickupBounds(scheduleNow)
  const minDate = earliest.date
  const minTime = form.pickup_date === earliest.date ? earliest.time : '00:00'
  const maxTime = form.pickup_date === latest.date ? latest.time : '23:59'

  const activeGroup = useMemo(
    () => CLIENT_GOODS_GROUPS.find((g) => g.key === form.goods_group) || CLIENT_GOODS_GROUPS[0],
    [form.goods_group],
  )
  const commodityMeta = getCommodity(form.goods_commodity)
  const activeFields = form.goods_commodity ? fieldsFor(form.goods_commodity) : []
  const requiredFields = form.goods_commodity ? requiredFieldsFor(form.goods_commodity) : []
  const flags = form.goods_commodity ? flagsFor(form.goods_commodity) : {}
  const suitableTrucks = commodityMeta ? commodityMeta.trucks || [] : []
  const supportsLiters = supportsLitersForCommodity(form.goods_commodity)
  const effectiveUnit = supportsLiters ? capacityUnit : 'tons'

  const pickupProvince = useMemo(() => inferPakistanProvince(pickup.location), [pickup.location])
  const dropoffProvince = useMemo(() => inferPakistanProvince(dropoff.location), [dropoff.location])

  function has(field) {
    return activeFields.includes(field)
  }
  function req(field) {
    return requiredFields.includes(field)
  }

  function applyCommoditySelection(groupKey, commKey) {
    const group = CLIENT_GOODS_GROUPS.find((g) => g.key === groupKey)
    const item = group?.commodities.find((c) => c.key === commKey)
    const tax = getCommodity(commKey)
    const defaultTons = item?.defaultTons || '5'
    const isLiquid = supportsLitersForCommodity(commKey)
    const defaultLiters = isLiquid ? String(Math.round(Number(defaultTons) * 1000)) : ''
    let defaultTemp = ''
    if (commKey === 'frozen_food') defaultTemp = '-18'
    else if (commKey === 'pharmaceuticals' || commKey === 'milk') defaultTemp = '4'

    setCapacityWarning('')
    if (!isLiquid) setCapacityUnit('tons')

    setForm((current) => ({
      ...current,
      goods_group: groupKey,
      goods_commodity: commKey,
      goods_category: tax?.category || 'solid',
      goods_form: tax?.form || '',
      goods_weight_tons: defaultTons,
      volume_liters: defaultLiters,
      length_ft: item?.suggestLengthFt ? '20' : '',
      length_cm: item?.suggestLengthFt ? String(Math.round(20 * FT_TO_CM * 100) / 100) : '',
      width_cm: '',
      height_cm: '',
      animal_count: commKey === 'livestock' ? current.animal_count || '10' : '',
      temperature_c: defaultTemp,
    }))
  }

  function handleGroupSelect(groupKey) {
    const group = CLIENT_GOODS_GROUPS.find((g) => g.key === groupKey)
    if (!group || !group.commodities.length) return
    applyCommoditySelection(groupKey, group.commodities[0].key)
  }

  function handleCommoditySelect(commKey) {
    applyCommoditySelection(form.goods_group, commKey)
  }

  function handleTonsChange(rawVal) {
    const raw = String(rawVal ?? '')
    if (raw === '') {
      setCapacityWarning('')
      setForm((cur) => ({ ...cur, goods_weight_tons: '', volume_liters: '' }))
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_ORDER_TONS) {
      setCapacityWarning(
        `Maximum single-truck load is ${MAX_ORDER_TONS} Tons (${MAX_ORDER_LITERS.toLocaleString()} Liters).${
          supportsLiters ? ' If you are entering Liters, switch unit to Liters.' : ''
        }`,
      )
      setForm((cur) => ({
        ...cur,
        goods_weight_tons: String(MAX_ORDER_TONS),
        volume_liters: supportsLiters ? String(MAX_ORDER_LITERS) : cur.volume_liters,
      }))
      return
    }
    setCapacityWarning('')
    const syncedLiters =
      supportsLiters && Number.isFinite(num) && num > 0 ? String(Math.round(num * 1000)) : ''
    setForm((cur) => ({
      ...cur,
      goods_weight_tons: raw,
      volume_liters: supportsLiters ? syncedLiters : cur.volume_liters,
    }))
  }

  function handleLitersChange(rawVal) {
    const raw = String(rawVal ?? '')
    if (raw === '') {
      setCapacityWarning('')
      setForm((cur) => ({ ...cur, volume_liters: '', goods_weight_tons: '' }))
      return
    }
    const num = Number(raw)
    if (Number.isFinite(num) && num > MAX_ORDER_LITERS) {
      setCapacityWarning(
        `Maximum single-truck liquid volume is ${MAX_ORDER_LITERS.toLocaleString()} Liters (${MAX_ORDER_TONS} Tons).`,
      )
      setForm((cur) => ({
        ...cur,
        volume_liters: String(MAX_ORDER_LITERS),
        goods_weight_tons: String(MAX_ORDER_TONS),
      }))
      return
    }
    setCapacityWarning('')
    const syncedTons = Number.isFinite(num) && num > 0 ? String(Math.round((num / 1000) * 100) / 100) : ''
    setForm((cur) => ({
      ...cur,
      volume_liters: raw,
      goods_weight_tons: syncedTons,
    }))
  }

  function handleLengthFeetChange(ftVal) {
    const raw = String(ftVal ?? '')
    const num = Number(raw)
    const clampedFt = Number.isFinite(num) && num > 45 ? '45' : raw
    const cmVal =
      clampedFt && Number.isFinite(Number(clampedFt)) && Number(clampedFt) > 0
        ? String(Math.round(Number(clampedFt) * FT_TO_CM * 100) / 100)
        : ''
    setForm((cur) => ({
      ...cur,
      length_ft: clampedFt,
      length_cm: cmVal,
    }))
  }

  function handleLivestockChange(nextType, nextCountRaw) {
    const preset = LIVESTOCK_PRESETS.find((p) => p.key === nextType) || LIVESTOCK_PRESETS[0]
    const countNum = Number(nextCountRaw)
    const estTons =
      Number.isFinite(countNum) && countNum > 0
        ? String(Math.min(MAX_ORDER_TONS, Math.max(0.5, Math.round(countNum * preset.avgTonsPerHead * 10) / 10)))
        : form.goods_weight_tons
    setForm((cur) => ({
      ...cur,
      livestock_type: nextType,
      animal_count: nextCountRaw,
      goods_weight_tons: estTons,
    }))
  }

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setSuccess('')

    if (!pickup.location.trim() || !dropoff.location.trim()) {
      setError('Step 1: Please enter both Pickup location and Dropoff location.')
      setSubmitting(false)
      return
    }
    if (!form.pickup_date || !form.pickup_time) {
      setError('Step 1: Please choose both Pickup date and Pickup time.')
      setSubmitting(false)
      return
    }
    if (!form.goods_commodity) {
      setError('Step 2: Please choose what goods you are shipping.')
      setSubmitting(false)
      return
    }

    // Auto-bump pickup_time if the default time just slipped inside the 20-minute lead window while filling the form
    let effectiveDate = form.pickup_date
    let effectiveTime = form.pickup_time
    const scheduleErr = pickupScheduleError(effectiveDate, effectiveTime)
    if (scheduleErr) {
      const fresh = buildInitialSchedule()
      if (effectiveDate === fresh.pickup_date && effectiveTime < fresh.pickup_time) {
        effectiveDate = fresh.pickup_date
        effectiveTime = fresh.pickup_time
        setForm((cur) => ({ ...cur, pickup_date: effectiveDate, pickup_time: effectiveTime }))
      } else {
        setError(`Step 1: ${scheduleErr}`)
        setSubmitting(false)
        return
      }
    }

    if (req(F.ANIMAL_COUNT) && (!Number.isFinite(Number(form.animal_count)) || Number(form.animal_count) <= 0)) {
      setError('Step 3: Please enter the number of animals / crates.')
      setSubmitting(false)
      return
    }

    const weightNum = Number(form.goods_weight_tons)
    const litersNum = Number(form.volume_liters)
    if (supportsLiters) {
      if (effectiveUnit === 'liters') {
        if (!Number.isFinite(litersNum) || litersNum < MIN_ORDER_LITERS || litersNum > MAX_ORDER_LITERS) {
          setError(`Step 3: Please enter a liquid volume between ${MIN_ORDER_LITERS} and ${MAX_ORDER_LITERS.toLocaleString()} Liters.`)
          setSubmitting(false)
          return
        }
      } else if (!Number.isFinite(weightNum) || weightNum < MIN_ORDER_TONS || weightNum > MAX_ORDER_TONS) {
        setError(`Step 3: Please enter a load weight between ${MIN_ORDER_TONS} and ${MAX_ORDER_TONS} Tons.`)
        setSubmitting(false)
        return
      }
    } else if (!Number.isFinite(weightNum) || weightNum < MIN_ORDER_TONS || weightNum > MAX_ORDER_TONS) {
      setError(`Step 3: Please enter a load weight between ${MIN_ORDER_TONS} and ${MAX_ORDER_TONS} Tons.`)
      setSubmitting(false)
      return
    }

    const finalWeightTons =
      supportsLiters && effectiveUnit === 'liters'
        ? String(Math.round((litersNum / 1000) * 100) / 100)
        : form.goods_weight_tons
    const finalVolumeLiters =
      supportsLiters
        ? effectiveUnit === 'tons'
          ? String(Math.round(weightNum * 1000))
          : form.volume_liters
        : ''

    const notesParts = []
    if (form.goods_commodity === 'livestock' && form.livestock_type) {
      notesParts.push(`[Animal Type: ${form.livestock_type}]`)
    }
    if (form.notes && form.notes.trim()) {
      notesParts.push(form.notes.trim())
    }

    const payload = {
      ...form,
      pickup_date: effectiveDate,
      pickup_time: effectiveTime,
      goods_weight_tons: finalWeightTons,
      volume_liters: finalVolumeLiters,
      notes: notesParts.join(' '),
      pickup_location: pickup.location.trim(),
      pickup_lat: pickup.lat,
      pickup_lng: pickup.lng,
      dropoff_location: dropoff.location.trim(),
      dropoff_lat: dropoff.lat,
      dropoff_lng: dropoff.lng,
    }

    try {
      await apiSend('/api/orders', payload)
      setSuccess('Order posted! Transporters matching your cargo, weight, radius, and route permit can now bid.')
      setForm(createInitialForm())
      setPickup(EMPTY_LOCATION)
      setDropoff(EMPTY_LOCATION)
      setTimeout(() => navigate(`${base}/orders`), 900)
    } catch (submitError) {
      if (submitError.code === 'review_required' && submitError.payload?.pending_review) {
        openPendingReviewModal(submitError.payload.pending_review)
      }
      setError(submitError.message || 'Unable to post order right now.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageTitle
        title="Post Order"
        subtitle="3-step smart shipment setup — matched automatically with verified trucks by cargo use, capacity, pickup radius & route permit."
        actions={
          base === '/everyday' ? (
            <Link to={`${base}/orders`} className="order-workspace-nav__record-link">
              <i className="fas fa-clipboard-list" aria-hidden="true" /> My Orders
            </Link>
          ) : null
        }
      />

      {base === '/client' && <OrderWorkspaceNavigation mode="one-time" />}

      <SectionCard title="Create Shipment Request" icon="fa-boxes-stacked">
        {error && (
          <StateMessage type="error" title="Order could not be posted">
            <p>{error}</p>
          </StateMessage>
        )}
        {success && <StateMessage type="success">{success}</StateMessage>}

        <form className="everyday-order-form grid gap-6" onSubmit={handleSubmit} noValidate>
          {/* ==================== STEP 1: ROUTE & PICKUP SCHEDULE ==================== */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="mb-4 flex items-center gap-2.5 border-b border-slate-100 pb-3">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                1
              </span>
              <div>
                <h3 className="text-base font-bold text-slate-900">Route & Pickup Schedule</h3>
                <p className="text-xs text-slate-500">
                  Enter pickup and drop-off locations. Only trucks operating near your pickup with legal route permits for both provinces will see your order.
                </p>
              </div>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <LocationPicker
                label="Pickup location"
                required
                value={pickup}
                onChange={setPickup}
                placeholder="Factory, warehouse, shop or house, area, city"
              />
              <LocationPicker
                label="Dropoff location"
                required
                value={dropoff}
                onChange={setDropoff}
                placeholder="Destination warehouse, market or house, area, city"
              />
            </div>

            {(pickupProvince || dropoffProvince) && (
              <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50/70 px-3.5 py-2.5 text-xs text-indigo-950">
                <i className="fas fa-route text-indigo-600" aria-hidden="true" />
                <span className="font-semibold">Route Permit Check:</span>
                <span className="rounded-md bg-white px-2 py-0.5 font-semibold text-indigo-700 shadow-2xs">
                  {pickupProvince || 'Pickup Province'} → {dropoffProvince || 'Drop-off Province'}
                </span>
                <span className="text-slate-600">
                  Only active trucks permitted in{' '}
                  <strong>
                    {pickupProvince && dropoffProvince && pickupProvince !== dropoffProvince
                      ? `both ${pickupProvince} & ${dropoffProvince}`
                      : pickupProvince || dropoffProvince}
                  </strong>{' '}
                  will be matched.
                </span>
              </div>
            )}

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <label className={labelCls}>
                Pickup date *
                <input
                  className={inputCls}
                  type="date"
                  name="pickup_date"
                  min={minDate}
                  max={latest.date}
                  value={form.pickup_date}
                  onChange={updateField}
                  aria-describedby="pickup-schedule-help"
                  required
                />
              </label>
              <label className={labelCls}>
                Pickup time *
                <input
                  className={inputCls}
                  type="time"
                  name="pickup_time"
                  min={minTime}
                  max={maxTime}
                  value={form.pickup_time}
                  onChange={updateField}
                  aria-describedby="pickup-schedule-help"
                  required
                />
              </label>
              <p id="pickup-schedule-help" className="text-xs text-slate-500 md:col-span-2">
                Choose a pickup within the next 24 hours, with at least 20 minutes preparation time (Pakistan Standard Time).
              </p>
            </div>
          </div>

          {/* ==================== STEP 2: WHAT GOODS ARE YOU SHIPPING? ==================== */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="mb-4 flex items-center gap-2.5 border-b border-slate-100 pb-3">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                2
              </span>
              <div>
                <h3 className="text-base font-bold text-slate-900">What Goods Are You Shipping?</h3>
                <p className="text-xs text-slate-500">
                  Select the category and specific goods so our system locks the right truck body type and safety standard.
                </p>
              </div>
            </div>

            {/* 6 Visual Category Cards */}
            <div className="mb-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                2A. Select Goods Category
              </div>
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {CLIENT_GOODS_GROUPS.map((grp) => {
                  const selected = form.goods_group === grp.key
                  return (
                    <button
                      key={grp.key}
                      type="button"
                      onClick={() => handleGroupSelect(grp.key)}
                      className={`flex items-start gap-3 rounded-xl border p-3.5 text-left transition ${
                        selected
                          ? 'border-blue-600 bg-blue-50/70 ring-2 ring-blue-100'
                          : 'border-slate-200 bg-slate-50/60 hover:border-slate-300 hover:bg-white'
                      }`}
                    >
                      <span
                        className={`mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-base ${
                          selected ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200'
                        }`}
                      >
                        <i className={`fas ${grp.icon}`} aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-bold text-slate-900">{grp.title}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-slate-500">{grp.subtitle}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Specific Commodity Cards within Selected Category */}
            {activeGroup && (
              <div className="mt-4">
                <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                  2B. Select Exact Cargo Type
                </div>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {activeGroup.commodities.map((item) => {
                    const active = form.goods_commodity === item.key
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => handleCommoditySelect(item.key)}
                        className={`flex items-start justify-between gap-3 rounded-xl border p-3.5 text-left transition ${
                          active
                            ? 'border-indigo-600 bg-indigo-50/60 ring-2 ring-indigo-100'
                            : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                        }`}
                      >
                        <div>
                          <div className="text-sm font-bold text-slate-900">{item.title}</div>
                          <div className="mt-0.5 text-xs text-slate-500">{item.desc}</div>
                        </div>
                        <span
                          className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs ${
                            active
                              ? 'border-indigo-600 bg-indigo-600 text-white'
                              : 'border-slate-300 bg-white text-transparent'
                          }`}
                        >
                          ✓
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Matched Truck Classes Banner */}
            {commodityMeta && (
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-slate-700">
                    <i className="fas fa-truck-fast mr-1.5 text-blue-600" aria-hidden="true" />
                    Auto-Matched Truck Classes:
                  </span>
                  {suitableTrucks.map((k) => (
                    <span
                      key={k}
                      className="rounded-full border border-blue-200 bg-white px-2.5 py-1 font-semibold text-blue-700 shadow-2xs"
                    >
                      {truckLabel(k)}
                    </span>
                  ))}
                  {flags.refrigerated && (
                    <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 font-semibold text-sky-700">
                      <i className="fas fa-snowflake mr-1" aria-hidden="true" /> Cold-Chain Locked
                    </span>
                  )}
                  {flags.hazardous && (
                    <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 font-semibold text-red-700">
                      <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" /> Hazmat Certified Only
                    </span>
                  )}
                  {flags.food_grade && (
                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700">
                      <i className="fas fa-utensils mr-1" aria-hidden="true" /> Food-Grade Tanker Only
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ==================== STEP 3: SMART QUANTITY & LOAD SPECS ==================== */}
          {form.goods_commodity && (
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-4 flex items-center gap-2.5 border-b border-slate-100 pb-3">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                  3
                </span>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Load Quantity & Smart Specifications</h3>
                  <p className="text-xs text-slate-500">
                    {supportsLiters
                      ? 'Enter liquid load in Tons (default, max 100 Tons) or switch to Liters (max 100,000 L).'
                      : 'Enter total load weight in Tons (max 100 Tons) or pick a quick truck-load estimate below.'}
                  </p>
                </div>
              </div>

              <div className="grid gap-5">
                {/* ---- 3A. LIVESTOCK ANIMAL SELECTOR & HEAD COUNT ---- */}
                {has(F.ANIMAL_COUNT) && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                    <div className="mb-2.5 text-xs font-bold uppercase tracking-wider text-amber-900">
                      Livestock Details (Animal Type & Head Count)
                    </div>
                    <div className="grid gap-2.5 sm:grid-cols-3">
                      {LIVESTOCK_PRESETS.map((preset) => {
                        const selected = form.livestock_type === preset.key
                        return (
                          <button
                            key={preset.key}
                            type="button"
                            onClick={() => handleLivestockChange(preset.key, form.animal_count)}
                            className={`rounded-lg border p-2.5 text-left text-xs transition ${
                              selected
                                ? 'border-amber-600 bg-white font-bold text-amber-950 ring-2 ring-amber-200'
                                : 'border-amber-200/80 bg-white/70 text-slate-700 hover:bg-white'
                            }`}
                          >
                            <div>{preset.label}</div>
                            <div className="mt-0.5 text-[11px] font-normal text-slate-500">
                              Avg ~{preset.avgTonsPerHead} Ton / unit
                            </div>
                          </button>
                        )
                      })}
                    </div>

                    <div className="mt-3 max-w-xs">
                      <label className={labelCls}>
                        Number of Animals / Crates {req(F.ANIMAL_COUNT) && '*'}
                        <input
                          className={inputCls}
                          type="number"
                          min="1"
                          max="5000"
                          step="1"
                          name="animal_count"
                          value={form.animal_count}
                          onChange={(e) => handleLivestockChange(form.livestock_type, e.target.value)}
                          required={req(F.ANIMAL_COUNT)}
                          placeholder="e.g. 10"
                        />
                      </label>
                    </div>
                  </div>
                )}

                {/* ---- 3B. WEIGHT (TONS) OR LIQUID VOLUME (TONS | LITERS) ---- */}
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-bold text-slate-900">
                        {supportsLiters
                          ? effectiveUnit === 'liters'
                            ? 'Liquid Load Volume (Liters) *'
                            : 'Liquid Load Weight (Tons) *'
                          : 'Total Load Weight (Tons) *'}
                      </div>
                      <div className="text-xs text-slate-500">
                        {supportsLiters
                          ? `Max limit: ${MAX_ORDER_TONS} Tons (${MAX_ORDER_LITERS.toLocaleString()} Liters) per tanker`
                          : `Max limit: ${MAX_ORDER_TONS} Tons per truck`}
                      </div>
                    </div>

                    {/* Unit Toggle ONLY for Liquid Tanker Commodities */}
                    {supportsLiters && (
                      <div
                        className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 shadow-2xs"
                        role="group"
                        aria-label="Liquid load unit"
                      >
                        <button
                          type="button"
                          onClick={() => {
                            setCapacityUnit('tons')
                            setCapacityWarning('')
                          }}
                          className={`rounded-md px-3 py-1.5 text-xs font-bold transition ${
                            effectiveUnit === 'tons'
                              ? 'bg-blue-600 text-white'
                              : 'text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          Tons (Default)
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setCapacityUnit('liters')
                            setCapacityWarning('')
                          }}
                          className={`rounded-md px-3 py-1.5 text-xs font-bold transition ${
                            effectiveUnit === 'liters'
                              ? 'bg-blue-600 text-white'
                              : 'text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          Liters
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Quick Helper Chips */}
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {supportsLiters
                      ? LIQUID_QUICK_PRESETS.map((chip) => {
                          const isActive =
                            effectiveUnit === 'liters'
                              ? form.volume_liters === chip.liters
                              : form.goods_weight_tons === chip.tons
                          return (
                            <button
                              key={chip.tons}
                              type="button"
                              onClick={() => {
                                setCapacityWarning('')
                                setForm((cur) => ({
                                  ...cur,
                                  goods_weight_tons: chip.tons,
                                  volume_liters: chip.liters,
                                }))
                              }}
                              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                                isActive
                                  ? 'border-blue-600 bg-blue-600 text-white'
                                  : 'border-slate-300 bg-white text-slate-700 hover:border-blue-400'
                              }`}
                            >
                              {chip.label}
                            </button>
                          )
                        })
                      : WEIGHT_QUICK_PRESETS.map((chip) => {
                          const isActive = form.goods_weight_tons === chip.tons
                          return (
                            <button
                              key={chip.tons}
                              type="button"
                              onClick={() => handleTonsChange(chip.tons)}
                              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                                isActive
                                  ? 'border-blue-600 bg-blue-600 text-white'
                                  : 'border-slate-300 bg-white text-slate-700 hover:border-blue-400'
                              }`}
                            >
                              {chip.label}
                            </button>
                          )
                        })}
                  </div>

                  {/* Single Active Numeric Input */}
                  <div className="grid gap-3 sm:grid-cols-2 sm:items-center">
                    {supportsLiters && effectiveUnit === 'liters' ? (
                      <input
                        className={inputCls}
                        type="number"
                        min={MIN_ORDER_LITERS}
                        max={MAX_ORDER_LITERS}
                        step="100"
                        name="volume_liters"
                        value={form.volume_liters}
                        onChange={(e) => handleLitersChange(e.target.value)}
                        placeholder="e.g. 12000"
                        required
                      />
                    ) : (
                      <input
                        className={inputCls}
                        type="number"
                        min={MIN_ORDER_TONS}
                        max={MAX_ORDER_TONS}
                        step="0.1"
                        name="goods_weight_tons"
                        value={form.goods_weight_tons}
                        onChange={(e) => handleTonsChange(e.target.value)}
                        placeholder="e.g. 10"
                        required
                      />
                    )}

                    <div className="text-xs font-semibold text-slate-600">
                      {supportsLiters ? (
                        effectiveUnit === 'liters' ? (
                          <span>
                            Auto-converted weight:{' '}
                            <strong className="text-slate-900">{form.goods_weight_tons || '0'} Tons</strong>
                          </span>
                        ) : (
                          <span>
                            Auto-converted volume:{' '}
                            <strong className="text-slate-900">
                              {form.volume_liters ? Number(form.volume_liters).toLocaleString() : '0'} Liters
                            </strong>
                          </span>
                        )
                      ) : (
                        <span>
                          Only trucks with at least{' '}
                          <strong className="text-slate-900">{form.goods_weight_tons || '0'} Tons</strong> capacity will match.
                        </span>
                      )}
                    </div>
                  </div>

                  {capacityWarning && (
                    <div
                      className="mt-2.5 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900"
                      role="alert"
                    >
                      <i className="fas fa-triangle-exclamation text-amber-600" aria-hidden="true" />
                      <span>{capacityWarning}</span>
                    </div>
                  )}
                </div>

                {/* ---- 3C. TEMPERATURE PRESETS FOR COLD CHAIN ---- */}
                {has(F.TEMPERATURE) && (
                  <div className="rounded-xl border border-sky-200 bg-sky-50/50 p-4">
                    <div className="mb-2 text-xs font-bold uppercase tracking-wider text-sky-900">
                      Required Cooling / Temperature Regime
                    </div>
                    <div className="grid gap-2.5 sm:grid-cols-3">
                      {TEMPERATURE_PRESETS.filter(
                        (p) => !(form.goods_commodity === 'frozen_food' && p.value === ''),
                      ).map((preset) => {
                        const selected = String(form.temperature_c) === preset.value
                        return (
                          <button
                            key={preset.label}
                            type="button"
                            onClick={() => setForm((cur) => ({ ...cur, temperature_c: preset.value }))}
                            className={`rounded-lg border p-3 text-left text-xs transition ${
                              selected
                                ? 'border-sky-600 bg-white font-bold text-sky-950 ring-2 ring-sky-200'
                                : 'border-sky-200/80 bg-white/80 text-slate-700 hover:bg-white'
                            }`}
                          >
                            <div className="font-bold">{preset.label}</div>
                            <div className="mt-0.5 text-[11px] font-normal text-slate-500">{preset.desc}</div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* ---- 3D. BED LENGTH REQUIREMENT IN FEET (FOR LONG / PACKAGED ITEMS) ---- */}
                {has(F.DIMENSIONS) && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-bold text-slate-900">
                          Minimum Truck Bed Length (Feet) — Optional
                        </div>
                        <div className="text-xs text-slate-500">
                          Shipping long Sariya, Pipes, Girders or a 20ft/40ft load? Select required truck bed length in Feet (ft).
                        </div>
                      </div>
                      {form.length_ft && (
                        <span className="rounded-md bg-indigo-100 px-2.5 py-1 text-xs font-bold text-indigo-800">
                          Requires ≥ {form.length_ft} ft truck bed
                        </span>
                      )}
                    </div>

                    <div className="mb-3 flex flex-wrap gap-1.5">
                      {LENGTH_FEET_PRESETS.map((preset) => {
                        const active = String(form.length_ft) === preset.ft
                        return (
                          <button
                            key={preset.label}
                            type="button"
                            onClick={() => handleLengthFeetChange(preset.ft)}
                            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                              active
                                ? 'border-indigo-600 bg-indigo-600 text-white'
                                : 'border-slate-300 bg-white text-slate-700 hover:border-indigo-400'
                            }`}
                          >
                            {preset.label}
                          </button>
                        )
                      })}
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className={labelCls}>
                        Custom Cargo Length (Feet - ft)
                        <input
                          className={inputCls}
                          type="number"
                          min="0"
                          max="45"
                          step="1"
                          name="length_ft"
                          value={form.length_ft}
                          onChange={(e) => handleLengthFeetChange(e.target.value)}
                          placeholder="Leave blank for standard cartons/furniture"
                        />
                      </label>

                      {has(F.QUANTITY) && (
                        <label className={labelCls}>
                          Number of Cartons / Bags / Pieces (Optional)
                          <input
                            className={inputCls}
                            type="number"
                            min="0"
                            step="1"
                            name="quantity"
                            value={form.quantity}
                            onChange={updateField}
                            placeholder="e.g. 200 bags or 40 cartons"
                          />
                        </label>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== BUDGET & NOTES ==================== */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="grid gap-4 md:grid-cols-2">
              <label className={labelCls}>
                Estimated budget (PKR — Optional)
                <input
                  className={inputCls}
                  type="number"
                  min="0"
                  step="100"
                  name="estimated_budget"
                  value={form.estimated_budget}
                  onChange={updateField}
                  placeholder="e.g. 45000"
                />
                <span className="text-xs font-normal text-slate-500">
                  Optional — helps transporters see your target rate when placing bids.
                </span>
              </label>
              <label className={labelCls}>
                Loading / Special Instructions (Optional)
                <textarea
                  className={`min-h-24 ${inputCls}`}
                  name="notes"
                  value={form.notes}
                  onChange={updateField}
                  placeholder="Floor number, labour needed, tarpaulin cover required, gate timing..."
                />
              </label>
            </div>
          </div>

          {error && (
            <StateMessage type="error" title="Order could not be posted">
              <p>{error}</p>
            </StateMessage>
          )}
          {success && <StateMessage type="success">{success}</StateMessage>}

          <div className="flex flex-wrap gap-3">
            <PrimaryButton type="submit" disabled={submitting}>
              <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
              {submitting ? 'Posting order...' : 'Post order'}
            </PrimaryButton>
            <Link
              to={`${base}/orders`}
              className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              View my orders
            </Link>
          </div>
        </form>
      </SectionCard>
    </>
  )
}
