import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PageTitle,
  SectionCard,
  StateMessage,
  formatMoney,
} from './clientUtils'

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
          <Link to="/client/post-order" className="inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
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
            <Link to="/client/post-order" className="mt-3 inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
              Post Your First Order
            </Link>
          </StateMessage>
        </SectionCard>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="space-y-4">
          {orders.map((order) => (
            <SectionCard key={order.id} className="hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">#{order.id} - {order.pickup_city} → {order.dropoff_city}</h2>
                  <p className="text-sm text-slate-600 mt-1">{order.pickup_date} at {order.pickup_time}</p>
                </div>
                <div className="flex gap-2">
                  <span className={statusBadgeClass(order.status)}>
                    {order.status.replace(/_/g, ' ').toUpperCase()}
                  </span>
                  <span className={paymentStatusBadgeClass(order.payment_status)}>
                    {order.payment_status}
                  </span>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3 mb-4 pt-4 border-t border-slate-200">
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase">Goods</p>
                  <p className="text-sm font-semibold text-slate-900">{order.goods_type}</p>
                  <p className="text-xs text-slate-600">{order.goods_weight_tons} tons</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase">Bids Received</p>
                  <p className="text-2xl font-bold text-blue-600">{order.bid_count}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase">Budget</p>
                  <p className="text-lg font-bold text-slate-900">
                    {order.estimated_budget ? formatMoney(order.estimated_budget) : 'Not specified'}
                  </p>
                </div>
              </div>

              {order.accepted_bid_id && (
                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm font-semibold text-blue-900">
                    <i className="fas fa-check-circle mr-2 text-green-600"></i>
                    Bid Accepted - {formatMoney(order.payment_amount)}
                  </p>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <Link
                  to={`/client/order/${order.id}`}
                  className="inline-flex min-h-9 items-center justify-center rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  <i className="fas fa-eye mr-1.5" aria-hidden="true"></i>
                  View Order
                </Link>
                {order.status === 'open' && (
                  <>
                    <button
                      className="inline-flex min-h-9 items-center justify-center rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                      onClick={() => window.location.href = `/client/post-order?copy=${order.id}`}
                    >
                      <i className="fas fa-copy mr-1.5" aria-hidden="true"></i>
                      Duplicate
                    </button>
                  </>
                )}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </>
  )
}
