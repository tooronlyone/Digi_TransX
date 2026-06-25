import { useEffect, useMemo, useState } from 'react'
import { getCsrfToken } from '../client/clientUtils'
import { loadTruckCatalog } from '../../lib/truckCatalog'

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return 'PKR 0'
  return `PKR ${amount.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

export default function AvailableBids() {
  const [orders, setOrders] = useState([])
  const [trucks, setTrucks] = useState([])
  const [catalog, setCatalog] = useState([])
  const [selectedOrderId, setSelectedOrderId] = useState(null)
  const [form, setForm] = useState({ truck_id: '', bid_price: '', message: '' })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [ordersRes, trucksRes, catalogRes] = await Promise.all([
        fetch('/api/orders/available', { credentials: 'same-origin' }),
        fetch('/api/trucks', { credentials: 'same-origin' }),
        loadTruckCatalog(),
      ])
      const ordersJson = await ordersRes.json().catch(() => ({}))
      const trucksJson = await trucksRes.json().catch(() => ({}))
      if (!ordersRes.ok || ordersJson.success === false) throw new Error(ordersJson.message || 'Unable to load bids.')
      if (!trucksRes.ok || trucksJson.success === false) throw new Error(trucksJson.message || 'Unable to load trucks.')
      setOrders(ordersJson.orders || [])
      setTrucks(trucksJson.trucks || [])
      setCatalog(catalogRes)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load available bids.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const selectedOrder = useMemo(
    () => orders.find((order) => order.id === selectedOrderId) || null,
    [orders, selectedOrderId],
  )

  const matchingActiveTrucks = useMemo(() => {
    if (!selectedOrder) return []
    return trucks.filter(
      (truck) =>
        truck.status === 'active' &&
        truck.catalog_type_key === selectedOrder.required_truck_type,
    )
  }, [selectedOrder, trucks])

  function openBidForm(order) {
    setSelectedOrderId(order.id)
    setSuccess('')
    setError('')
    setForm({ truck_id: '', bid_price: '', message: '' })
  }

  function updateForm(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function submitBid(event) {
    event.preventDefault()
    if (!selectedOrder) return

    setSubmitting(true)
    setError('')
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
          bid_price: Number(form.bid_price),
          message: form.message,
        }),
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to place bid.')
      setSuccess('Bid placed successfully.')
      setSelectedOrderId(null)
      setForm({ truck_id: '', bid_price: '', message: '' })
      await loadData()
    } catch (submitError) {
      setError(submitError.message || 'Unable to place bid.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
      <div className="space-y-6">
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">Available Bids</h1>
          <p className="mt-2 text-sm text-slate-500">Only open orders that match one of your active truck types are shown here.</p>
        </div>

        {loading && <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">Loading bids...</div>}
        {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {success && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</div>}

        {!loading && !error && orders.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
            No matching open bids right now. Activate more trucks or check back soon.
          </div>
        )}

        {!loading && !error && orders.length > 0 && (
          <div className="grid gap-4 xl:grid-cols-2">
            {orders.map((order) => {
              const truckTypeName = catalog.find((item) => item.type_key === order.required_truck_type)?.display_name || order.required_truck_type_name
              return (
                <article key={order.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">{order.pickup_city} to {order.dropoff_city}</h2>
                      <p className="mt-1 text-sm text-slate-500">{order.pickup_date} at {order.pickup_time}</p>
                    </div>
                    <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">{order.bid_count} bids</span>
                  </div>
                  <div className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                    <div><span className="font-semibold text-slate-800">Goods:</span> {order.goods_type}</div>
                    <div><span className="font-semibold text-slate-800">Weight:</span> {order.goods_weight_tons} tons</div>
                    <div><span className="font-semibold text-slate-800">Truck:</span> {truckTypeName}</div>
                    <div><span className="font-semibold text-slate-800">Budget:</span> {order.estimated_budget ? formatMoney(order.estimated_budget) : 'Not shared'}</div>
                  </div>
                  <button type="button" onClick={() => openBidForm(order)} className="mt-4 inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
                    Place Bid
                  </button>
                </article>
              )
            })}
          </div>
        )}

        {selectedOrder && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Place Bid for Order #{selectedOrder.id}</h2>
                <p className="mt-1 text-sm text-slate-500">{selectedOrder.pickup_city} to {selectedOrder.dropoff_city}</p>
              </div>
              <button type="button" onClick={() => setSelectedOrderId(null)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                Close
              </button>
            </div>

            <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={submitBid}>
              <label className="grid gap-2 text-sm font-medium text-slate-700">
                Truck
                <select className="rounded-lg border border-slate-300 px-3 py-2.5" name="truck_id" value={form.truck_id} onChange={updateForm} required>
                  <option value="">Select active matching truck</option>
                  {matchingActiveTrucks.map((truck) => (
                    <option key={truck.id} value={truck.id}>{truck.truck_number} - {truck.truck_type}</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2 text-sm font-medium text-slate-700">
                Bid price
                <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0.01" step="0.01" name="bid_price" value={form.bid_price} onChange={updateForm} required />
              </label>
              <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
                Message
                <textarea className="min-h-24 rounded-lg border border-slate-300 px-3 py-2.5" name="message" value={form.message} onChange={updateForm} placeholder="Share timing, service notes, or capacity details." />
              </label>
              <div className="md:col-span-2">
                <button type="submit" disabled={submitting || matchingActiveTrucks.length === 0} className="inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                  <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-gavel'} mr-2`} aria-hidden="true"></i>
                  {submitting ? 'Submitting bid...' : 'Submit bid'}
                </button>
                {matchingActiveTrucks.length === 0 && (
                  <p className="mt-2 text-sm text-amber-700">You do not currently have an active truck matching this order type.</p>
                )}
              </div>
            </form>
          </div>
        )}
      </div>
    
  )
}
