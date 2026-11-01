import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import DeliveryHandoffCode from './DeliveryHandoffCode'
import '../../styles/pages/parts-store-pages.css'

const STATUS_LABELS = { placed: 'Order Placed', confirmed: 'Confirmed', dispatched: 'On the Way', delivered: 'Received', completed: 'Received', cancelled: 'Cancelled' }
const formatDate = (value) => value ? new Date(value).toLocaleString('en-PK', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export default function PartsOrdersPage() {
  const { status, user } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <AccountPartsOrdersPage key={String(user.id)} />
}

function AccountPartsOrdersPage() {
  const location = useLocation()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    fetch('/api/marketplace/my-orders', { credentials: 'include' }).then((r) => r.json()).then((data) => {
      if (!data.success) throw new Error(data.message || 'Could not load orders.')
      setOrders(data.orders || [])
    }).catch((err) => setError(err.message)).finally(() => setLoading(false))
  }, [])

  return <main className="parts-store-page">
    <div className="store-page-heading"><div><span>ORDER HISTORY</span><h1>My Parts Orders</h1><p>See what you purchased, when it was ordered and its current delivery status.</p></div><Link to="/transporter/parts-store" className="store-secondary-link"><i className="fa-solid fa-plus"></i> Buy More Parts</Link></div>
    {location.state?.newOrder && orders.some(order => order.id === location.state.newOrder.id) && <div className="store-success"><i className="fa-solid fa-circle-check"></i><div><b>Order placed successfully</b><p>Order #{location.state.newOrder.order_number} is secured in escrow.</p></div></div>}
    {loading ? <div className="store-loading"><i className="fa-solid fa-spinner fa-spin"></i> Loading your orders...</div> : error ? <div className="store-error">{error}</div> : !orders.length ? <section className="store-empty-state"><i className="fa-solid fa-receipt"></i><h2>No purchases yet</h2><p>Your truck-part orders will appear here after checkout.</p><Link to="/transporter/parts-store">Browse Parts</Link></section> : <section className="store-orders-list">{orders.map((order) => {
      const status = order.fulfillment_status || 'placed'; const isOpen = expanded === order.id
      return <article className="store-order-card" key={order.id}>
        <button className="store-order-overview" onClick={() => setExpanded(isOpen ? null : order.id)}>
          <div><span className="store-order-number">#{order.order_number}</span><small>{formatDate(order.created_at)}</small></div>
          <div><small>Shop</small><b>{order.shop_name}</b></div>
          <div><small>Delivery</small><b>{order.delivery_type === 'pickup' ? 'Self Pickup' : 'Delivery'}</b></div>
          <div><small>Total</small><b>PKR {Number(order.net_total || 0).toLocaleString()}</b></div>
          <span className={`store-status status-${status}`}><i className="fa-solid fa-circle"></i>{STATUS_LABELS[status] || status}</span>
          <i className={`fa-solid fa-chevron-${isOpen ? 'up' : 'down'}`}></i>
        </button>
        {isOpen && <div className="store-order-details"><div className="store-order-items"><h3>Purchased items</h3>{(order.items || []).map((item) => <div key={item.id || item.part_id}><span><b>{item.part_title || item.title}</b><small>{item.part_number || 'Truck part'} • Qty {item.quantity}</small></span><strong>PKR {Number(item.subtotal || 0).toLocaleString()}</strong></div>)}</div><div className="store-order-info"><h3>Order information</h3><p><span>Ordered on</span><b>{formatDate(order.created_at)}</b></p><p><span>Delivery type</span><b>{order.delivery_type === 'pickup' ? 'Self Pickup' : 'Delivery'}</b></p><p><span>Address</span><b>{order.delivery_address || 'Shop pickup'}</b></p><p><span>Payment</span><b>{String(order.payment_status || '').replaceAll('_', ' ')}</b></p><p><span>Current status</span><b>{STATUS_LABELS[status] || status}</b></p>{['dispatched', 'ready_for_pickup'].includes(status) && <DeliveryHandoffCode orderId={order.id} />}</div></div>}
      </article>
    })}</section>}
  </main>
}
