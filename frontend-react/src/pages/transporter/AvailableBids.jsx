import { useEffect, useMemo, useState } from 'react'
import { getCsrfToken } from '../client/clientUtils'
import { MarketReference, FeeBreakdown } from '../../components/business/BusinessRules'

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return 'PKR 0'
  return `PKR ${amount.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

function getEligibleTrucksForOrder(order, trucks) {
  if (!order) return []
  const eligibleIds = Array.isArray(order.eligible_truck_ids)
    ? order.eligible_truck_ids.map((id) => Number(id))
    : null

  if (eligibleIds && eligibleIds.length > 0) {
    const matchedById = trucks.filter(
      (truck) => truck.status === 'active' && eligibleIds.includes(Number(truck.id)),
    )
    if (matchedById.length > 0) return matchedById
  }

  const requiredTypes = Array.isArray(order.required_truck_types)
    ? order.required_truck_types
    : []
  const orderWeight = Number(order.goods_weight_tons || 0)

  return trucks.filter((truck) => {
    if (truck.status !== 'active') return false
    if (requiredTypes.length > 0) {
      const truckKey = truck.catalog_type_key || truck.truck_type
      let allowedCommodities = []
      if (truck.catalog_specs_json && typeof truck.catalog_specs_json === 'object') {
        allowedCommodities = Array.isArray(truck.catalog_specs_json.allowed_commodities)
          ? truck.catalog_specs_json.allowed_commodities
          : []
      }
      const orderCommodity = order.goods_commodity || ''
      const commodityMatches =
        orderCommodity &&
        (allowedCommodities.includes(orderCommodity) ||
          (orderCommodity === 'cement_bags' && allowedCommodities.includes('general_cargo')) ||
          (orderCommodity === 'construction_steel' && allowedCommodities.includes('machinery')))
      if (!requiredTypes.includes(truckKey) && !commodityMatches) return false
    }
    const truckCap = Number(truck.capacity_tons || truck.payload_max_tons || 0)
    // Allow 10% per-truck flexibility on weight capacity
    if (orderWeight > 0 && truckCap > 0 && orderWeight > truckCap * 1.1) {
      return false
    }
    return true
  })
}

export default function AvailableBids() {
  const [orders, setOrders] = useState([])
  const [trucks, setTrucks] = useState([])
  const [locationSetupRequired, setLocationSetupRequired] = useState(false)
  const [ordersOutOfRange, setOrdersOutOfRange] = useState(0)
  const [selectedOrderId, setSelectedOrderId] = useState(null)
  const [form, setForm] = useState({ truck_id: '', bid_price: '', message: '' })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [success, setSuccess] = useState('')

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    Promise.all([
      fetch('/api/orders/available', { credentials: 'same-origin' }),
      fetch('/api/trucks', { credentials: 'same-origin' }),
    ])
      .then(async ([ordersRes, trucksRes]) => {
        if (ignore) return
        const ordersJson = await ordersRes.json().catch(() => ({}))
        const trucksJson = await trucksRes.json().catch(() => ({}))
        if (!ordersRes.ok || ordersJson.success === false) throw new Error(ordersJson.message || 'Unable to load available orders.')
        if (!trucksRes.ok || trucksJson.success === false) throw new Error(trucksJson.message || 'Unable to load trucks.')
        setOrders(ordersJson.orders || [])
        setTrucks(trucksJson.trucks || [])
        setLocationSetupRequired(Boolean(ordersJson.location_setup_required))
        setOrdersOutOfRange(Number(ordersJson.orders_out_of_range || 0))
      })
      .catch((loadError) => {
        if (!ignore) setError(loadError.message || 'Unable to load available orders.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [reloadKey])

  const selectedOrder = useMemo(
    () => orders.find((order) => order.id === selectedOrderId) || null,
    [orders, selectedOrderId],
  )

  const activeTrucks = useMemo(
    () => getEligibleTrucksForOrder(selectedOrder, trucks),
    [selectedOrder, trucks],
  )

  function openBidForm(order) {
    if (selectedOrderId === order.id) {
      setSelectedOrderId(null)
      setSubmitError('')
      return
    }
    const matchingTrucks = getEligibleTrucksForOrder(order, trucks)
    const defaultTruckId = matchingTrucks[0] ? String(matchingTrucks[0].id) : ''
    const defaultBudget =
      order.estimated_budget && Number(order.estimated_budget) > 0
        ? String(order.estimated_budget)
        : ''
    setSelectedOrderId(order.id)
    setSuccess('')
    setSubmitError('')
    setForm({ truck_id: defaultTruckId, bid_price: defaultBudget, message: '' })
  }

  function updateForm(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function submitBid(event) {
    event.preventDefault()
    if (!selectedOrder) return

    if (!form.truck_id) {
      setSubmitError('Please select an active truck for this bid.')
      return
    }
    if (!form.bid_price || Number(form.bid_price) <= 0) {
      setSubmitError('Please enter a valid bid price in PKR.')
      return
    }

    setSubmitting(true)
    setSubmitError('')
    setSuccess('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${selectedOrder.id}/bids`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
        },
        body: JSON.stringify({
          truck_id: Number(form.truck_id),
          bid_price: form.bid_price,
          message: form.message,
        }),
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to place bid.')
      setSuccess(`Bid placed successfully for Order #${selectedOrder.id}.`)
      setSelectedOrderId(null)
      setForm({ truck_id: '', bid_price: '', message: '' })
      setLoading(true)
      setReloadKey((k) => k + 1)
    } catch (err) {
      setSubmitError(err.message || 'Unable to place bid.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Available Bids</h1>
        <p className="mt-2 text-sm text-slate-500">Open orders available for transporter bids are shown here.</p>
      </div>

      {loading && <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">Loading bids...</div>}
      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {success && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</div>}

      {!loading && !error && locationSetupRequired && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <i className="fas fa-location-dot mr-2" aria-hidden="true"></i>
          None of your active trucks has an operating location yet. Set each truck's current
          location and service radius in its configuration to see nearby orders.
        </div>
      )}

      {!loading && !error && orders.length === 0 && !locationSetupRequired && ordersOutOfRange > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
          {ordersOutOfRange} open order{ordersOutOfRange === 1 ? '' : 's'} match your trucks' cargo
          capability but the pickup is outside their service radius. Move a truck closer or widen
          its radius (up to 150 km) to bid.
        </div>
      )}

      {!loading && !error && orders.length === 0 && !locationSetupRequired && ordersOutOfRange === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
          No open bids near your trucks right now. Check back soon.
        </div>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-2">
          {orders.map((order) => {
            const isSelected = selectedOrderId === order.id
            const orderEligibleTrucks = getEligibleTrucksForOrder(order, trucks)
            return (
              <article
                key={order.id}
                className={`rounded-xl border bg-white p-5 shadow-sm transition-all ${
                  isSelected ? 'border-blue-500 ring-2 ring-blue-100 xl:col-span-2' : 'border-slate-200'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">
                        Order #{order.id}
                      </span>
                      <h2 className="text-lg font-bold text-slate-900">
                        {order.pickup_city}{' -> '}{order.dropoff_city}
                      </h2>
                    </div>
                    <p className="mt-1 text-sm text-slate-500">{order.pickup_date} at {order.pickup_time}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">{order.bid_count} bids</span>
                    {order.distance_to_pickup_km != null && (
                      <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                        <i className="fas fa-location-arrow mr-1" aria-hidden="true"></i>
                        {order.distance_to_pickup_km} km to pickup
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                  <div><span className="font-semibold text-slate-800">Goods:</span> {order.goods_type}</div>
                  <div>
                    <span className="font-semibold text-slate-800">Quantity:</span>{' '}
                    {order.volume_liters && Number(order.volume_liters) > 0
                      ? `${Number(order.volume_liters).toLocaleString('en-PK')} Liters (${order.goods_weight_tons} tons)`
                      : `${order.goods_weight_tons} tons`}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-800">Bed Length Needed:</span>{' '}
                    {order.length_cm && Number(order.length_cm) > 0
                      ? `${Math.round((Number(order.length_cm) / 30.48) * 10) / 10} ft`
                      : 'Standard'}
                  </div>
                  <div><span className="font-semibold text-slate-800">Budget:</span> {order.estimated_budget ? formatMoney(order.estimated_budget) : 'Not shared'}</div>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => openBidForm(order)}
                    className={`inline-flex min-h-10 items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold text-white transition ${
                      isSelected ? 'bg-slate-700 hover:bg-slate-800' : 'bg-blue-600 hover:bg-blue-700'
                    }`}
                  >
                    <i className={`fas ${isSelected ? 'fa-xmark' : 'fa-gavel'} mr-2`} aria-hidden="true"></i>
                    {isSelected ? 'Close Bid Form' : 'Place Bid'}
                  </button>
                  {orderEligibleTrucks.length > 0 && (
                    <span className="text-xs font-medium text-emerald-700">
                      <i className="fas fa-truck mr-1" aria-hidden="true"></i>
                      Eligible: {orderEligibleTrucks.map((t) => t.truck_number).join(', ')}
                    </span>
                  )}
                </div>

                {isSelected && (
                  <div className="mt-5 border-t border-slate-200 pt-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">Place Bid for Order #{order.id}</h3>
                        <p className="mt-0.5 text-sm text-slate-500">{order.pickup_city} to {order.dropoff_city}</p>
                      </div>
                    </div>

                    <MarketReference key={`${order.id}:${form.truck_id}`} orderId={order.id} truckId={form.truck_id} showRange />
                    <FeeBreakdown kind="freight" />

                    {submitError && (
                      <div className="my-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                        <i className="fas fa-circle-exclamation mr-2" aria-hidden="true"></i>
                        {submitError}
                      </div>
                    )}

                    <form className="mt-4 grid gap-4 md:grid-cols-2" onSubmit={submitBid} noValidate>
                      <label className="grid gap-2 text-sm font-medium text-slate-700">
                        Truck
                        <select className="rounded-lg border border-slate-300 px-3 py-2.5" name="truck_id" value={form.truck_id} onChange={updateForm} required>
                          <option value="">Select active truck</option>
                          {activeTrucks.map((truck) => (
                            <option key={truck.id} value={truck.id}>
                              {truck.truck_number} - {truck.truck_type} ({truck.capacity_tons || truck.payload_max_tons} tons)
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="grid gap-2 text-sm font-medium text-slate-700">
                        Bid price (PKR)
                        <input
                          className="rounded-lg border border-slate-300 px-3 py-2.5"
                          type="number"
                          min="1"
                          step="0.01"
                          name="bid_price"
                          value={form.bid_price}
                          onChange={updateForm}
                          placeholder="Enter your bid amount in PKR"
                          required
                        />
                      </label>
                      <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
                        Message (Optional)
                        <textarea
                          className="min-h-20 rounded-lg border border-slate-300 px-3 py-2.5"
                          name="message"
                          value={form.message}
                          onChange={updateForm}
                          placeholder="Share timing, service notes, or capacity details."
                        />
                      </label>
                      <div className="flex flex-wrap items-center gap-3 md:col-span-2">
                        <button
                          type="submit"
                          disabled={submitting || activeTrucks.length === 0}
                          className="inline-flex min-h-10 items-center justify-center rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-check'} mr-2`} aria-hidden="true"></i>
                          {submitting ? 'Submitting bid...' : 'Submit Bid'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedOrderId(null)}
                          className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          Cancel
                        </button>
                        {activeTrucks.length === 0 && (
                          <p className="text-sm text-amber-700">You do not currently have an eligible active truck available for this order.</p>
                        )}
                      </div>
                    </form>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
