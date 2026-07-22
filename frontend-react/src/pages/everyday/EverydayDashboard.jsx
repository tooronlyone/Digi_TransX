import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageTitle, SectionCard, StateMessage } from '../client/clientUtils'

// A deliberately simple everyday dashboard: quick actions + recent orders.
// No wallet, agreements, or business widgets (those endpoints 403 for everyday).
const QUICK_ACTIONS = [
  { to: '/everyday/post-order', icon: 'fa-shipping-fast', title: 'Post an Order', subtitle: 'Request a one-time delivery' },
  { to: '/everyday/orders', icon: 'fa-clipboard-list', title: 'My Orders', subtitle: 'Track your requests and bids' },
  { to: '/everyday/terms', icon: 'fa-file-lines', title: 'Terms & Fees', subtitle: 'How payment and fees work' },
]

export default function EverydayDashboard() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    fetch('/api/orders/my-orders', { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((json) => { if (mounted) setOrders(json.orders || []) })
      .catch(() => {})
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [])

  const recent = orders.slice(0, 5)

  return (
    <>
      <PageTitle title="Welcome" subtitle="Post a delivery and compare transporter bids — pay the one you pick by card." />

      <div className="grid gap-4 sm:grid-cols-3">
        {QUICK_ACTIONS.map((a) => (
          <Link key={a.to} to={a.to} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <i className={`fas ${a.icon}`} aria-hidden="true"></i>
            </span>
            <h3 className="mt-3 text-base font-bold text-slate-900">{a.title}</h3>
            <p className="text-sm text-slate-500">{a.subtitle}</p>
          </Link>
        ))}
      </div>

      <SectionCard title="Recent Orders" icon="fa-clock" className="mt-6">
        {loading && <StateMessage type="loading">Loading your orders...</StateMessage>}
        {!loading && recent.length === 0 && (
          <StateMessage type="empty">
            <p>You haven't posted any orders yet.</p>
            <Link to="/everyday/post-order" className="mt-3 inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
              Post Your First Order
            </Link>
          </StateMessage>
        )}
        {!loading && recent.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {recent.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">
                    {(o.pickup_location || o.pickup_city)} → {(o.dropoff_location || o.dropoff_city)}
                  </p>
                  <p className="text-xs text-slate-500">Order #{o.id} · {o.bid_count} bids · {o.status.replace(/_/g, ' ')}</p>
                </div>
                <Link to={`/everyday/order/${o.id}`} className="shrink-0 text-sm font-semibold text-blue-600 hover:text-blue-700">
                  View
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </>
  )
}
