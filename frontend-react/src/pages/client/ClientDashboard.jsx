import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PageTitle,
  StateMessage,
  StatusBadge,
  apiGet,
  formatMoney,
  isActiveStatus,
  isCompletedStatus,
} from './clientUtils'

const initialStats = {
  walletBalance: 0,
  totalOrders: 0,
  activeOrders: 0,
  completedOrders: 0,
}

const QUICK_ACTIONS = [
  { to: '/client/post-order', icon: 'fa-shipping-fast', title: 'Post Order', subtitle: 'Request a new shipment' },
  { to: '/client/orders', icon: 'fa-clipboard-list', title: 'My Orders', subtitle: 'Track requests and bids' },
  { to: '/client/post-agreement', icon: 'fa-file-circle-plus', title: 'Post Agreement', subtitle: 'Set up a recurring contract' },
  { to: '/client/wallet', icon: 'fa-wallet', title: 'Wallet', subtitle: 'Top up and view balance' },
  { to: '/client/messages', icon: 'fa-comments', title: 'Messages', subtitle: 'Chat with transporters' },
]

export default function ClientDashboard() {
  const [stats, setStats] = useState(initialStats)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadDashboard() {
    setLoading(true)
    setError('')
    try {
      const [ordersJson, walletJson] = await Promise.all([
        apiGet('/api/orders/my-orders'),
        apiGet('/api/wallet').catch(() => ({ wallet: {} })),
      ])
      const myOrders = ordersJson.orders || []
      const wallet = walletJson.wallet || {}
      setStats({
        walletBalance: wallet.balance ?? 0,
        totalOrders: myOrders.length,
        activeOrders: myOrders.filter((order) => isActiveStatus(order.status)).length,
        completedOrders: myOrders.filter((order) => isCompletedStatus(order.status)).length,
      })
      setOrders(myOrders.slice(0, 6))
    } catch (err) {
      setError(err.message || 'Failed to load dashboard.')
    } finally {
      setLoading(false)
    }
  }

  async function refreshOrders() {
    setOrdersLoading(true)
    try {
      const json = await apiGet('/api/orders/my-orders')
      setOrders((json.orders || []).slice(0, 6))
    } catch (_) {
      /* keep existing list on refresh error */
    } finally {
      setOrdersLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  const statCards = [
    { label: 'Wallet Balance', value: formatMoney(stats.walletBalance), icon: 'fa-wallet', variant: 'wallet' },
    { label: 'Total Orders', value: stats.totalOrders, icon: 'fa-receipt', variant: 'orders' },
    { label: 'Active Orders', value: stats.activeOrders, icon: 'fa-spinner', variant: 'active' },
    { label: 'Completed Orders', value: stats.completedOrders, icon: 'fa-circle-check', variant: 'completed' },
  ]

  return (
    <>
      <PageTitle
        title="Service Seeker Dashboard"
        subtitle="Track your shipment requests, compare bids, and keep an eye on your wallet balance."
      />

      {error && <StateMessage type="error">{error}</StateMessage>}

      <div className="dashboard-kpi-grid">
        {statCards.map((card) => (
          <article key={card.label} className="dashboard-stat-card">
            <div className="dashboard-stat-card__header">
              <div>
                <div className="dashboard-card-title">{card.label}</div>
                <div className="dashboard-card-value">
                  {loading ? <i className="fas fa-spinner fa-spin" aria-hidden="true"></i> : card.value}
                </div>
              </div>
              <div className={`dashboard-card-icon dashboard-card-icon--${card.variant}`}>
                <i className={`fas ${card.icon}`} aria-hidden="true"></i>
              </div>
            </div>
          </article>
        ))}
      </div>

      <section className="dashboard-section">
        <h2 className="dashboard-section-title">Quick Actions</h2>
        <div className="dashboard-actions-grid">
          {QUICK_ACTIONS.map((action) => (
            <Link key={action.to} to={action.to} className="dashboard-action-tile">
              <div className="dashboard-action-tile__icon">
                <i className={`fas ${action.icon}`} aria-hidden="true"></i>
              </div>
              <span>{action.title}</span>
              <div>{action.subtitle}</div>
            </Link>
          ))}
        </div>
      </section>

      <section className="dashboard-section">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 22,
          }}
        >
          <h2 className="dashboard-section-title" style={{ marginBottom: 0 }}>
            Recent Shipment Requests
          </h2>
          <button
            type="button"
            className="dashboard-action-small client-btn-ghost"
            onClick={refreshOrders}
            disabled={ordersLoading || loading}
          >
            <i className={`fas ${ordersLoading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="dashboard-loading">
            <i className="fas fa-spinner fa-spin" aria-hidden="true"></i> Loading recent requests...
          </p>
        ) : orders.length === 0 ? (
          <div className="dashboard-empty-state">
            <i className="fas fa-box-open" aria-hidden="true"></i>
            <p>
              No shipment requests yet. <Link to="/client/post-order">Post your first order</Link>
            </p>
          </div>
        ) : (
          <div className="client-order-grid">
            {orders.map((order) => (
              <article key={order.id} className="client-order-card">
                <div className="client-order-card__top">
                  <div>
                    <div className="client-order-card__route">
                      {order.pickup_city || 'Pickup'}
                      <i className="fas fa-arrow-right" aria-hidden="true"></i>
                      {order.dropoff_city || 'Dropoff'}
                    </div>
                    <div className="client-order-card__meta">
                      Order #{order.id} &middot; {order.goods_type || 'General goods'}
                    </div>
                  </div>
                  <StatusBadge status={order.status} />
                </div>
                <div className="client-order-card__stats">
                  <div>
                    <div className="client-order-card__budget-label">Budget</div>
                    <div className="client-order-card__budget-value">
                      {order.estimated_budget ? formatMoney(order.estimated_budget) : '—'}
                    </div>
                  </div>
                  <Link to={`/client/order/${order.id}`} className="dashboard-action-small">
                    View
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
