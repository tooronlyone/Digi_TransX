import { useEffect, useMemo, useState } from 'react'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  apiSend,
  formatDateTime,
  formatMoney,
  isCompletedStatus,
} from './clientUtils'

function RatingModal({ order, onClose, onRated }) {
  const [rating, setRating] = useState(0)
  const [review, setReview] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function submitRating() {
    if (rating < 1) {
      setError('Please select a star rating.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await apiSend(`/api/client/orders/${encodeURIComponent(order.order_id)}/rate`, { rating, review })
      setMessage('Rating submitted. Thank you.')
      onRated?.()
      setTimeout(onClose, 900)
    } catch (err) {
      setError(err.message || 'Failed to submit rating.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4">
          <h3 className="text-lg font-bold text-slate-900">Rate Your Transporter</h3>
          <p className="mt-1 text-sm text-slate-500">Order: {order.order_id}</p>
        </div>

        <div className="mb-4 flex gap-2">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              className={`h-10 w-10 rounded-lg border text-lg ${value <= rating ? 'border-amber-300 bg-amber-50 text-amber-500' : 'border-slate-200 text-slate-300'}`}
              onClick={() => setRating(value)}
              aria-label={`${value} star rating`}
            >
              <i className="fas fa-star" aria-hidden="true"></i>
            </button>
          ))}
        </div>

        <textarea
          value={review}
          onChange={(event) => setReview(event.target.value)}
          rows={4}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          placeholder="Optional: share your experience..."
        />

        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {message && <div className="mt-3 text-sm text-emerald-700">{message}</div>}

        <div className="mt-5 flex gap-2">
          <PrimaryButton type="button" onClick={submitRating} disabled={saving} className="flex-1">
            <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-star'}`} aria-hidden="true"></i>
            Submit Rating
          </PrimaryButton>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default function OrderHistory() {
  const [orders, setOrders] = useState([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState('20')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ratingOrder, setRatingOrder] = useState(null)

  async function loadHistory() {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: String(Math.max(Number(limit || 20), 1)) })
      if (status) params.set('status', status)
      const json = await apiGet(`/api/client/orders?${params.toString()}`)
      setOrders(json.orders || json.data?.orders || [])
    } catch (err) {
      setError(err.message || 'Failed to load order history.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHistory()
  }, [status, limit])

  const visibleOrders = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return orders
    return orders.filter((order) => {
      return [order.order_id, order.pickup_location, order.drop_location]
        .some((value) => String(value || '').toLowerCase().includes(term))
    })
  }, [orders, search])

  return (
    <>
      <PageTitle title="Order History" subtitle="View and manage your past shipments and orders." />

      <SectionCard title="Order History" icon="fa-clock">
        <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-[180px_1fr_160px_auto] md:items-end">
          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Status</span>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              <option value="">All Orders</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
              <option value="working">Working</option>
              <option value="in_progress">In Progress</option>
              <option value="pending">Pending</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Search</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="Order ID, pickup, or drop location"
            />
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Rows per page</span>
            <select
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              <option value="10">10 rows</option>
              <option value="20">20 rows</option>
              <option value="50">50 rows</option>
              <option value="100">100 rows</option>
            </select>
          </label>

          <PrimaryButton type="button" onClick={loadHistory} disabled={loading}>
            <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
            Refresh
          </PrimaryButton>
        </div>

        {loading && <StateMessage type="loading">Loading order history...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {!loading && !error && visibleOrders.length === 0 && (
          <StateMessage type="empty">No order history found for the current filters.</StateMessage>
        )}
        {!loading && !error && visibleOrders.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-normal text-slate-500">
                <tr>
                  <th className="px-4 py-3">Order ID</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Pickup Location</th>
                  <th className="px-4 py-3">Drop Location</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Fare</th>
                  <th className="px-4 py-3">Created Date</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {visibleOrders.map((order) => (
                  <tr key={order.order_id || order.id}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{order.order_id || order.id}</td>
                    <td className="px-4 py-3 capitalize text-slate-600">{order.order_type || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{order.pickup_location || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{order.drop_location || '-'}</td>
                    <td className="px-4 py-3"><StatusBadge status={order.status} /></td>
                    <td className="px-4 py-3 text-slate-700">{formatMoney(order.total_fare)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(order.created_at)}</td>
                    <td className="px-4 py-3">
                      {isCompletedStatus(order.status) ? (
                        <button
                          type="button"
                          onClick={() => setRatingOrder(order)}
                          className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
                        >
                          <i className="fas fa-star" aria-hidden="true"></i>
                          Rate
                        </button>
                      ) : (
                        <span className="text-sm text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {ratingOrder && (
        <RatingModal
          order={ratingOrder}
          onClose={() => setRatingOrder(null)}
          onRated={loadHistory}
        />
      )}
    </>
  )
}
