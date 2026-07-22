import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PageTitle,
  SectionCard,
  StateMessage,
  formatMoney,
} from './clientUtils'
import useClientBasePath from '../../hooks/useClientBasePath'

function statusBadgeClass(status) {
  const baseClass = 'rounded-full px-3 py-1 text-xs font-semibold'
  const statusClasses = {
    open: 'bg-blue-50 text-blue-700',
    accepted: 'bg-yellow-50 text-yellow-700',
    in_progress: 'bg-green-50 text-green-700',
    completed: 'bg-emerald-50 text-emerald-700',
  }
  return `${baseClass} ${statusClasses[status] || 'bg-slate-50 text-slate-700'}`
}

function paymentStatusBadgeClass(status) {
  const baseClass = 'rounded-full px-2 py-0.5 text-xs font-semibold'
  const statusClasses = {
    pending: 'bg-orange-100 text-orange-700',
    paid: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
  }
  return `${baseClass} ${statusClasses[status] || 'bg-slate-100 text-slate-700'}`
}

export default function MyOrders() {
  const base = useClientBasePath()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadOrders() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/orders/my-orders', { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load orders.')
      setOrders(json.orders || [])
    } catch (loadError) {
      setError(loadError.message || 'Unable to load your orders.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  return (
    <>
      <PageTitle
        title="My Orders"
        subtitle="Track all your shipment orders and manage bids from transporters."
        actions={
          <Link to={`${base}/post-order`} className="inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            <i className="fas fa-plus-circle mr-2" aria-hidden="true"></i>
            Post New Order
          </Link>
        }
      />

      {loading && (
        <SectionCard>
          <StateMessage type="loading">Loading your orders...</StateMessage>
        </SectionCard>
      )}

      {error && (
        <SectionCard>
          <StateMessage type="error">{error}</StateMessage>
        </SectionCard>
      )}

      {!loading && !error && orders.length === 0 && (
        <SectionCard>
          <StateMessage type="empty">
            <p>You haven't posted any orders yet.</p>
            <Link to={`${base}/post-order`} className="mt-3 inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
              Post Your First Order
            </Link>
          </StateMessage>
        </SectionCard>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="space-y-5">
          {orders.map((order) => (
            <SectionCard key={order.id} className="transition-shadow hover:shadow-lg">
              {/* Header: order id + route (truncated) on the left, badges on the right */}
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-700">
                      Order #{order.id}
                    </span>
                    <span className="text-xs text-slate-500">
                      <i className="far fa-clock mr-1" aria-hidden="true"></i>
                      {order.pickup_date} · {order.pickup_time}
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-50 text-[10px] text-green-600">
                        <i className="fas fa-circle-dot" aria-hidden="true"></i>
                      </span>
                      <span className="truncate text-sm font-semibold text-slate-900" title={order.pickup_city}>
                        {order.pickup_city}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-50 text-[10px] text-red-600">
                        <i className="fas fa-location-dot" aria-hidden="true"></i>
                      </span>
                      <span className="truncate text-sm font-semibold text-slate-900" title={order.dropoff_city}>
                        {order.dropoff_city}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-2">
                  <span className={statusBadgeClass(order.status)}>
                    {order.status.replace(/_/g, ' ').toUpperCase()}
                  </span>
                  <span className={paymentStatusBadgeClass(order.payment_status)}>
                    {order.payment_status}
                  </span>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-4 rounded-xl bg-slate-50 p-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Goods</p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-900" title={order.goods_type}>{order.goods_type}</p>
                  <p className="text-xs text-slate-500">{order.goods_weight_tons} tons</p>
                </div>
                <div className="min-w-0 border-l border-slate-200 pl-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Bids</p>
                  <p className="mt-1 text-2xl font-bold leading-none text-blue-600">{order.bid_count}</p>
                  <p className="text-xs text-slate-500">received</p>
                </div>
                <div className="min-w-0 border-l border-slate-200 pl-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Budget</p>
                  <p className="mt-1 text-sm font-bold text-slate-900">
                    {order.estimated_budget ? formatMoney(order.estimated_budget) : 'Not specified'}
                  </p>
                </div>
              </div>

              {order.accepted_bid_id && (
                <div className="mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2">
                  <i className="fas fa-circle-check text-green-600" aria-hidden="true"></i>
                  <p className="text-sm font-semibold text-green-800">
                    Bid accepted — {formatMoney(order.payment_amount)}
                  </p>
                </div>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  to={`${base}/order/${order.id}`}
                  className="inline-flex min-h-9 items-center justify-center rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
                >
                  <i className="fas fa-eye mr-1.5" aria-hidden="true"></i>
                  View Order
                </Link>
                {order.status === 'open' && (
                  <button
                    className="inline-flex min-h-9 items-center justify-center rounded-lg border border-slate-300 px-4 py-1.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50"
                    onClick={() => window.location.href = `${base}/post-order?copy=${order.id}`}
                  >
                    <i className="fas fa-copy mr-1.5" aria-hidden="true"></i>
                    Duplicate
                  </button>
                )}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </>
  )
}
