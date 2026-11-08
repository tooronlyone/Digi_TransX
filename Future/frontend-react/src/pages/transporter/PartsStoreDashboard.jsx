import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { usePartsCart } from './partsCart'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import '../../styles/pages/parts-store-pages.css'
import '../../styles/pages/parts-store-dashboard-layout.css'

export default function PartsStoreDashboard() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <PartsStoreAccount key={String(user.id)} userId={user.id} />
}

function PartsStoreAccount() {
  const { cart } = usePartsCart()
  const [orders, setOrders] = useState([])
  useEffect(() => { fetch('/api/marketplace/my-orders', { credentials: 'include' }).then((r) => r.json()).then((d) => d.success && setOrders(d.orders || [])).catch(() => undefined) }, [])
  const cartCount = cart.reduce((sum, item) => sum + item.qty, 0)
  const active = orders.filter((order) => !['delivered', 'completed', 'cancelled'].includes(order.fulfillment_status)).length
  const cards = [
    ['/transporter/parts-store', 'fa-magnifying-glass', 'SHOP', 'Browse Truck Parts', 'Search genuine parts from verified shops.', 'Buy Now'],
    ['/transporter/parts-store/cart', 'fa-cart-shopping', 'CART', `${cartCount} ${cartCount === 1 ? 'Item' : 'Items'} Saved`, 'Your cart stays saved after refresh.', 'Open Cart'],
    ['/transporter/parts-store/orders', 'fa-box-open', 'ORDERS', `${orders.length} Purchases`, `${active} orders currently in progress.`, 'View History'],
    ['/transporter/parts-store/requests', 'fa-bullhorn', 'REQUESTS', 'Missing a Part?', 'Review requests and shopkeeper quotes.', 'View Requests'],
  ]
  return <main className="parts-store-page"><div className="store-page-heading"><div><span>TRUCK PARTS STORE</span><h1>Store Dashboard</h1><p>Buy parts and track every marketplace order from one place.</p></div><Link to="/transporter/parts-store" className="store-secondary-link"><i className="fa-solid fa-store"></i> Buy Parts</Link></div><section className="store-dashboard-cards">{cards.map(([path, icon, kicker, title, copy, action]) => <Link to={path} key={path}><i className={`fa-solid ${icon}`}></i><div><span>{kicker}</span><h2>{title}</h2><p>{copy}</p></div><b>{action} <i className="fa-solid fa-arrow-right"></i></b></Link>)}</section>{orders.length > 0 && <section className="store-dashboard-recent"><div><h2>Recent Orders</h2><Link to="/transporter/parts-store/orders">View all</Link></div>{orders.slice(0, 3).map((order) => <article key={order.id}><span><b>#{order.order_number}</b><small>{order.shop_name}</small></span><span><small>Status</small><b>{String(order.fulfillment_status || 'placed').replaceAll('_', ' ')}</b></span><strong>PKR {Number(order.net_total || 0).toLocaleString()}</strong></article>)}</section>}</main>
}
