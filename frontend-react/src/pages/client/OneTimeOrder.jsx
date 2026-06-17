import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  TRUCK_TYPES,
  apiSend,
  formatMoney,
  formatNumber,
} from './clientUtils'

const initialForm = {
  transportType: '',
  acceptMode: 'AUTO',
  truckCount: '1',
  totalWeightTons: '',
  goodsDescription: '',
  truckCondition: '',
  pickupLocation: '',
  dropLocation: '',
  maxPriceLimit: '',
  pickupDate: '',
  pickupTime: '',
  estimatedWaitHours: '0',
  overnightNights: '0',
  specialInstructions: '',
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function fieldClass() {
  return 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100'
}

export default function OneTimeOrder() {
  const navigate = useNavigate()
  const [form, setForm] = useState(initialForm)
  const [minimumPrice, setMinimumPrice] = useState(0)
  const [minimumHint, setMinimumHint] = useState('Enter pickup and dropoff to calculate minimum price.')
  const [preview, setPreview] = useState(null)
  const [previewToken, setPreviewToken] = useState('')
  const [resultsVisible, setResultsVisible] = useState(false)
  const [resultsState, setResultsState] = useState({ type: 'info', message: 'Fill the form and run a match search to see eligible trucks.' })
  const [selectedMap, setSelectedMap] = useState({})
  const [activeBreakdown, setActiveBreakdown] = useState({ groupId: '', truckId: '' })
  const [matching, setMatching] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const today = useMemo(() => todayIso(), [])
  const requestedCount = Math.min(20, Math.max(1, Number(form.truckCount || 1)))

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function resetResults() {
    setPreview(null)
    setPreviewToken('')
    setSelectedMap({})
    setActiveBreakdown({ groupId: '', truckId: '' })
    setResultsVisible(false)
  }

  async function discardActivePreview({ silent = false, reset = true } = {}) {
    const token = previewToken
    if (reset) resetResults()
    if (!token) return
    try {
      await apiSend('/api/client/marketplace/orders/preview/discard', { preview_token: token })
    } catch (_) {
      if (!silent) {
        setResultsState({ type: 'warning', message: 'Preview cleanup could not be completed, but you can continue.' })
      }
    }
  }

  async function updateMinimumPrice() {
    if (!form.pickupLocation.trim() || !form.dropLocation.trim()) {
      setMinimumPrice(0)
      setMinimumHint('Enter pickup and dropoff to calculate minimum price.')
      return
    }
    try {
      const data = await apiSend('/api/pricing/estimate', {
        pickup: form.pickupLocation.trim(),
        dropoff: form.dropLocation.trim(),
        truck_type: form.transportType,
        goods_weight: Number(form.totalWeightTons || 0) || null,
        goods_type: form.goodsDescription.trim(),
      })
      const price = Number(data.min_total_price || 0) || 0
      setMinimumPrice(price)
      setMinimumHint(`${data.warning ? `${data.warning} ` : ''}Minimum price: ${formatMoney(price)}.`)
      if (!Number(form.maxPriceLimit || 0) || Number(form.maxPriceLimit || 0) < price) {
        updateForm('maxPriceLimit', String(Math.ceil(price)))
      }
    } catch (err) {
      setMinimumPrice(0)
      setMinimumHint(err.message || 'Minimum price could not be calculated.')
    }
  }

  function validateForm() {
    if (!form.totalWeightTons || Number(form.totalWeightTons) <= 0) return 'Total goods weight is required.'
    if (!form.goodsDescription.trim()) return 'Actual goods description is required.'
    if (!form.pickupLocation.trim() || !form.dropLocation.trim()) return 'Pickup and drop-off locations are required.'
    if (!form.maxPriceLimit || Number(form.maxPriceLimit) <= 0) return 'Max price limit is required.'
    if (minimumPrice && Number(form.maxPriceLimit || 0) < minimumPrice) {
      return `Minimum price for this route is ${formatMoney(minimumPrice)}. You cannot set a limit below this.`
    }
    if (!form.pickupDate || !form.pickupTime) return 'Pickup date and time are required.'
    return ''
  }

  function selectedGroupIds(map = selectedMap) {
    return Object.keys(map).filter((groupId) => (map[groupId] || []).length > 0)
  }

  function currentSelectedCardsForGroup(groupId, map = selectedMap) {
    const group = (preview?.transporter_groups || []).find((item) => Number(item.transporter_id || 0) === Number(groupId || 0))
    if (!group) return []
    const selected = new Set(map[groupId] || [])
    return (group.trucks || []).filter((truck) => selected.has(Number(truck.truck_id || 0)))
  }

  function currentSelectedCards(map = selectedMap) {
    return selectedGroupIds(map).flatMap((groupId) => currentSelectedCardsForGroup(groupId, map))
  }

  function completeSelectedGroups(map = selectedMap) {
    return selectedGroupIds(map).filter((groupId) => currentSelectedCardsForGroup(groupId, map).length === requestedCount)
  }

  const summary = useMemo(() => {
    const selectedCards = currentSelectedCards()
    const completeGroups = completeSelectedGroups()
    const groupTotals = completeGroups.map((groupId) => (
      currentSelectedCardsForGroup(groupId).reduce((sum, truck) => sum + Number((truck.pricing || {}).grand_total || truck.total_price || 0), 0)
    ))
    const capacity = selectedCards.reduce((sum, truck) => sum + Number(truck.capacity_tons || 0), 0)
    const truckNumbers = selectedCards.map((truck) => truck.truck_number).filter(Boolean)
    const totalLabel = groupTotals.length > 1
      ? `${formatMoney(Math.min(...groupTotals))} - ${formatMoney(Math.max(...groupTotals))}`
      : formatMoney(groupTotals[0] || 0)
    return {
      selectedCards,
      completeGroups,
      truckNumbers,
      capacity,
      totalLabel,
      canConfirm: Boolean(previewToken) && completeGroups.length >= 1 && completeGroups.length <= 3 && selectedGroupIds().length === completeGroups.length,
    }
  }, [preview, selectedMap, requestedCount, previewToken])

  async function runPreview(event) {
    event.preventDefault()
    const validationError = validateForm()
    if (validationError) {
      setResultsVisible(true)
      setResultsState({ type: 'error', message: validationError })
      return
    }

    setMatching(true)
    setResultsVisible(true)
    setResultsState({ type: 'loading', message: 'Matching eligible transporter groups...' })
    setPreview(null)
    setSelectedMap({})
    setActiveBreakdown({ groupId: '', truckId: '' })

    try {
      await discardActivePreview({ silent: true, reset: false })
      const requestedPickupAt = form.pickupDate && form.pickupTime ? `${form.pickupDate}T${form.pickupTime}` : ''
      const payload = {
        pickup_location: form.pickupLocation.trim(),
        dropoff_location: form.dropLocation.trim(),
        truck_type: form.transportType,
        accept_mode: form.acceptMode,
        max_price_limit: Number(form.maxPriceLimit || 0) || 0,
        truck_count: requestedCount,
        cargo_type: form.goodsDescription.trim(),
        actual_goods_description: form.goodsDescription.trim(),
        cargo_weight: Number(form.totalWeightTons || 0) || null,
        total_weight_tons: Number(form.totalWeightTons || 0) || null,
        truck_condition_requirements: form.truckCondition.trim(),
        estimated_wait_hours: Number(form.estimatedWaitHours || 0) || 0,
        overnight_nights: Math.max(0, Math.floor(Number(form.overnightNights || 0) || 0)),
        scheduled_date: form.pickupDate || '',
        requested_pickup_at: requestedPickupAt,
        group_by_transporter: true,
        special_instructions: form.specialInstructions.trim(),
      }
      const json = await apiSend('/api/client/marketplace/orders/preview', payload)
      const nextPreview = json.preview || json.data?.preview || {}
      setPreview(nextPreview)
      setPreviewToken(String(nextPreview.preview_token || ''))

      const suggestedType = nextPreview.effective_truck_type
        || nextPreview.recommended_truck_type
        || nextPreview.required_truck?.required_truck_type
        || form.transportType
        || '-'

      if (!Array.isArray(nextPreview.transporter_groups) || !nextPreview.transporter_groups.length) {
        setResultsState({
          type: 'warning',
          message: 'No active transporter group currently matches this truck type, truck count, and capacity requirement.',
        })
        return
      }

      const source = String(nextPreview.distance_source || '').toLowerCase()
      setResultsState({
        type: source === 'road_route' ? 'success' : 'warning',
        message: `${Number(nextPreview.matched_transporters || 0)} transporter group(s) matched across ${formatNumber(nextPreview.distance_km || 0, 2)} km. Suggested truck type: ${suggestedType}.`,
      })
    } catch (err) {
      setPreview(null)
      setPreviewToken('')
      setResultsState({ type: 'error', message: err.message || 'Failed to match trucks. Please try again.' })
    } finally {
      setMatching(false)
    }
  }

  function selectTruck(groupId, truckId) {
    const normalizedGroupId = Number(groupId || 0)
    const normalizedTruckId = Number(truckId || 0)
    if (!normalizedGroupId || !normalizedTruckId) return

    setActiveBreakdown({ groupId: String(normalizedGroupId), truckId: String(normalizedTruckId) })
    setSelectedMap((current) => {
      const key = String(normalizedGroupId)
      const currentIds = current[key] || []
      const selected = new Set(currentIds)
      if (selected.has(normalizedTruckId)) {
        selected.delete(normalizedTruckId)
      } else {
        if (!selected.size && selectedGroupIds(current).length >= 3) {
          setResultsState({ type: 'warning', message: 'You can send requests to a maximum of 3 transporter groups.' })
          return current
        }
        if (selected.size >= requestedCount) {
          setResultsState({ type: 'warning', message: `Select exactly ${requestedCount} truck(s) from one transporter.` })
          return current
        }
        selected.add(normalizedTruckId)
      }
      const next = { ...current }
      if (selected.size) next[key] = Array.from(selected)
      else delete next[key]
      return next
    })
  }

  async function submitSelection() {
    const groupsPayload = completeSelectedGroups().map((groupId) => ({
      transporter_id: Number(groupId),
      selected_truck_ids: selectedMap[groupId] || [],
    }))
    if (!previewToken) {
      setResultsState({ type: 'error', message: 'Run a preview first.' })
      return
    }
    if (!summary.canConfirm) {
      setResultsState({ type: 'error', message: `Select exactly ${requestedCount} truck(s) from 1 to 3 transporter groups.` })
      return
    }
    if (!window.confirm(`Send this request to ${groupsPayload.length} transporter group(s)?`)) return

    setConfirming(true)
    try {
      const json = await apiSend('/api/client/marketplace/orders/confirm', {
        preview_token: previewToken,
        selected_groups: groupsPayload,
      })
      const order = json.order || json.data?.order || {}
      setPreviewToken('')
      setResultsState({ type: 'success', message: `Order request sent. Order ID: ${order.order_id || ''}` })
      setTimeout(() => navigate('/client/orders/current'), 700)
    } catch (err) {
      setResultsState({ type: 'error', message: err.message || 'Failed to send the request.' })
    } finally {
      setConfirming(false)
    }
  }

  async function resetForm() {
    setForm(initialForm)
    setMinimumPrice(0)
    setMinimumHint('Enter pickup and dropoff to calculate minimum price.')
    await discardActivePreview({ silent: true })
    setResultsState({ type: 'info', message: 'Fill the form and run a match search to see eligible trucks.' })
  }

  function activeTruckForGroup(group) {
    if (Number(activeBreakdown.groupId || 0) !== Number(group.transporter_id || 0)) return null
    return (group.trucks || []).find((truck) => Number(truck.truck_id || 0) === Number(activeBreakdown.truckId || 0)) || null
  }

  return (
    <>
      <PageTitle
        title="One Time Order"
        subtitle="Fill in the details below for your single shipment."
        actions={
          <Link to="/client/place-order" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
            <i className="fas fa-arrow-left" aria-hidden="true"></i>
            Back to Order Types
          </Link>
        }
      />

      <form onSubmit={runPreview} className="space-y-6">
        <SectionCard title="Order Details" icon="fa-info-circle">
          <StateMessage type="info" title="Matching rule">
            Digi_TransX shows active trucks of the selected type, grouped transporter-wise, so you can review exact per-truck pricing before placing the request.
          </StateMessage>
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Transport Type</span>
              <select value={form.transportType} onChange={(event) => updateForm('transportType', event.target.value)} onBlur={updateMinimumPrice} className={fieldClass()}>
                <option value="">Auto suggest from goods</option>
                {TRUCK_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Number of Trucks Needed</span>
              <input type="number" min="1" max="20" value={form.truckCount} onChange={(event) => updateForm('truckCount', event.target.value)} className={fieldClass()} />
            </label>
            <div>
              <span className="text-sm font-semibold text-slate-700">Accept Mode</span>
              <div className="mt-1 grid h-10 grid-cols-2 rounded-lg border border-slate-300 bg-white p-1">
                {['AUTO', 'MANUAL'].map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => updateForm('acceptMode', mode)}
                    className={`rounded-md text-sm font-semibold ${form.acceptMode === mode ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Total Goods Weight (tons)</span>
              <input type="number" min="0.1" step="0.1" value={form.totalWeightTons} onChange={(event) => updateForm('totalWeightTons', event.target.value)} onBlur={updateMinimumPrice} className={fieldClass()} placeholder="Example: 12.5" />
            </label>
            <label className="block md:col-span-2 xl:col-span-4">
              <span className="text-sm font-semibold text-slate-700">Actual Goods Description</span>
              <textarea value={form.goodsDescription} onChange={(event) => updateForm('goodsDescription', event.target.value)} onBlur={updateMinimumPrice} rows={3} className={fieldClass()} placeholder="Describe the actual goods, for example steel coils, beverages, milk cans, cement bags, machinery parts, or electronics." />
            </label>
            <label className="block md:col-span-2 xl:col-span-4">
              <span className="text-sm font-semibold text-slate-700">Truck Condition Requirements</span>
              <textarea value={form.truckCondition} onChange={(event) => updateForm('truckCondition', event.target.value)} rows={2} className={fieldClass()} placeholder="Optional notes for truck condition, such as clean interior, sealed body, GPS available, or no leakage." />
            </label>
          </div>
        </SectionCard>

        <SectionCard title="Route & Timing" icon="fa-route">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Pickup Location</span>
              <input value={form.pickupLocation} onChange={(event) => updateForm('pickupLocation', event.target.value)} onBlur={updateMinimumPrice} className={fieldClass()} placeholder="City, area, warehouse or complete pickup address" />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Drop-off Location</span>
              <input value={form.dropLocation} onChange={(event) => updateForm('dropLocation', event.target.value)} onBlur={updateMinimumPrice} className={fieldClass()} placeholder="City, area, warehouse or complete drop-off address" />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Max Price Limit (PKR)</span>
              <input type="number" min={minimumPrice ? Math.ceil(minimumPrice) : 0} step="1" value={form.maxPriceLimit} onChange={(event) => updateForm('maxPriceLimit', event.target.value)} className={fieldClass()} />
              <span className="mt-1 block text-xs text-slate-500">{minimumHint}</span>
            </label>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm font-semibold text-slate-700">Pickup Date</span>
                <input type="date" min={today} value={form.pickupDate} onChange={(event) => updateForm('pickupDate', event.target.value)} className={fieldClass()} />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-slate-700">Pickup Time</span>
                <input type="time" value={form.pickupTime} onChange={(event) => updateForm('pickupTime', event.target.value)} className={fieldClass()} />
              </label>
            </div>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Estimated Waiting Hours</span>
              <input type="number" min="0" step="0.5" value={form.estimatedWaitHours} onChange={(event) => updateForm('estimatedWaitHours', event.target.value)} className={fieldClass()} />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Overnight Nights</span>
              <input type="number" min="0" step="1" value={form.overnightNights} onChange={(event) => updateForm('overnightNights', event.target.value)} className={fieldClass()} />
            </label>
          </div>
        </SectionCard>

        <SectionCard title="Additional Notes" icon="fa-clipboard-list">
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Special Instructions</span>
            <textarea value={form.specialInstructions} onChange={(event) => updateForm('specialInstructions', event.target.value)} rows={3} className={fieldClass()} placeholder="Optional instructions for loading, unloading, gate pass, contact person, or handling details." />
          </label>
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <SecondaryButton type="button" onClick={resetForm} disabled={matching || confirming}>
              <i className="fas fa-undo-alt" aria-hidden="true"></i> Reset Form
            </SecondaryButton>
            <PrimaryButton type="submit" disabled={matching || confirming}>
              <i className={`fas ${matching ? 'fa-spinner fa-spin' : 'fa-search'}`} aria-hidden="true"></i>
              Find Matching Trucks
            </PrimaryButton>
          </div>
        </SectionCard>
      </form>

      {resultsVisible && (
        <SectionCard title="Matched Transporters" icon="fa-layer-group">
          <div className="space-y-4">
            <StateMessage type={resultsState.type}>{resultsState.message}</StateMessage>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_340px]">
              <div className="space-y-4">
                {preview?.transporter_groups?.map((group, index) => {
                  const groupId = String(group.transporter_id || '')
                  const selectedIds = new Set(selectedMap[groupId] || [])
                  const activeTruck = activeTruckForGroup(group)
                  return (
                    <article key={groupId || index} className="rounded-lg border border-slate-200 bg-white p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <h3 className="font-bold text-slate-900">Transporter Match #{index + 1}</h3>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
                            <span className="rounded-full bg-slate-100 px-2 py-1">Rating {formatNumber(group.rating, 1)}</span>
                            <span className="rounded-full bg-slate-100 px-2 py-1">{group.completed_trips || 0} completed trips</span>
                            <span className="rounded-full bg-slate-100 px-2 py-1">{group.eligible_truck_count || 0} eligible trucks</span>
                            <span className="rounded-full bg-slate-100 px-2 py-1">Need {requestedCount} truck(s)</span>
                          </div>
                        </div>
                        <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-700">
                          Bundle total: {formatMoney(group.group_total)}
                        </div>
                      </div>

                      <div className="mt-4 space-y-3">
                        {(group.trucks || []).map((truck) => {
                          const truckId = Number(truck.truck_id || 0)
                          const selected = selectedIds.has(truckId)
                          return (
                            <button
                              type="button"
                              key={truckId}
                              onClick={() => selectTruck(groupId, truckId)}
                              className={`w-full rounded-lg border p-3 text-left transition ${selected ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-slate-50 hover:border-blue-200'}`}
                            >
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <div className="flex items-center gap-3">
                                  <span className={`grid h-5 w-5 place-items-center rounded border ${selected ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-transparent'}`}>
                                    <i className="fas fa-check text-[10px]" aria-hidden="true"></i>
                                  </span>
                                  <div>
                                    <div className="font-semibold text-slate-900">{truck.truck_number || 'Truck'}</div>
                                    <div className="text-xs text-slate-500">{truck.truck_type || '-'} | Rating {formatNumber(group.rating, 1)}</div>
                                  </div>
                                </div>
                                <div className="font-bold text-slate-900">{formatMoney(truck.total_price || truck.pricing?.grand_total)}</div>
                              </div>
                              <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                                <div className="rounded bg-white px-2 py-2"><span className="block text-slate-500">Capacity</span><strong>{formatNumber(truck.capacity_tons, 1)} tons</strong></div>
                                <div className="rounded bg-white px-2 py-2"><span className="block text-slate-500">Per KM</span><strong>{formatMoney(truck.per_km_rate)}</strong></div>
                                <div className="rounded bg-white px-2 py-2"><span className="block text-slate-500">Wait / Hour</span><strong>{formatMoney(truck.waiting_charge_per_hour)}</strong></div>
                                <div className="rounded bg-white px-2 py-2"><span className="block text-slate-500">Overnight</span><strong>{formatMoney(truck.overnight_charge)}</strong></div>
                              </div>
                            </button>
                          )
                        })}
                      </div>

                      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                        {!activeTruck ? (
                          <div className="text-sm font-semibold text-slate-600">Click any truck row to see its exact price breakdown.</div>
                        ) : (
                          <>
                            <div className="text-sm font-bold text-slate-900">Price Breakdown for {activeTruck.truck_number || 'Selected Truck'}</div>
                            <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
                              {[
                                ['Distance Charge', activeTruck.pricing?.distance_charge],
                                ['Minimum Trip', activeTruck.pricing?.minimum_trip_charge],
                                ['Loading/Unloading', activeTruck.pricing?.loading_charges],
                                ['Waiting Charges', activeTruck.pricing?.waiting_charges],
                                ['Overnight Charges', activeTruck.pricing?.overnight_charges],
                                ['Total Price', activeTruck.pricing?.grand_total],
                              ].map(([label, value]) => (
                                <div key={label} className="rounded bg-white px-2 py-2">
                                  <span className="block text-slate-500">{label}</span>
                                  <strong>{formatMoney(value)}</strong>
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </article>
                  )
                })}
              </div>

              <aside className="h-fit rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="font-bold text-slate-900">Selection Summary</h3>
                <div className="mt-4 space-y-2 text-sm">
                  {[
                    ['Requested Trucks', requestedCount],
                    ['Selected Trucks', summary.selectedCards.length],
                    ['Selected Numbers', summary.truckNumbers.length ? summary.truckNumbers.join(', ') : '-'],
                    ['Selected Capacity', summary.selectedCards.length ? `${formatNumber(summary.capacity, 1)} tons` : '-'],
                    ['Distance', preview?.distance_km ? `${formatNumber(preview.distance_km, 2)} km` : '-'],
                    ['Wait / Overnight', `${formatNumber(form.estimatedWaitHours, 1)} hr / ${Math.max(0, Math.floor(Number(form.overnightNights || 0) || 0))} night(s)`],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                      <span className="text-slate-500">{label}</span>
                      <strong className="text-right text-slate-900">{value}</strong>
                    </div>
                  ))}
                  <div className="flex justify-between gap-3 rounded-lg bg-blue-50 px-3 py-2">
                    <span className="font-semibold text-blue-700">Total Price</span>
                    <strong className="text-right text-blue-900">{summary.totalLabel}</strong>
                  </div>
                </div>
                <div className="mt-4 flex flex-col gap-2">
                  <SecondaryButton type="button" onClick={() => discardActivePreview()} disabled={confirming}>
                    <i className="fas fa-times-circle" aria-hidden="true"></i> Discard Preview
                  </SecondaryButton>
                  <PrimaryButton type="button" onClick={submitSelection} disabled={!summary.canConfirm || confirming}>
                    <i className={`fas ${confirming ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
                    Send Request
                  </PrimaryButton>
                </div>
              </aside>
            </div>
          </div>
        </SectionCard>
      )}
    </>
  )
}
