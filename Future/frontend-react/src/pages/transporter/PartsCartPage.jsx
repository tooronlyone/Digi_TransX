import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePartsCart } from './partsCart'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import { checkoutParts } from './marketplaceApi'
import '../../styles/pages/parts-store-pages.css'

export default function PartsCartPage() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <PartsCartAccount key={String(user.id)} userId={user.id} />
}

function PartsCartAccount({ userId }) {
  const mounted = useRef(true)
  const checkoutAbort = useRef(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; checkoutAbort.current?.abort() } }, [])
  const navigate = useNavigate()
  const { cart, changeQty, removeItem, clearCart } = usePartsCart()
  const [deliveryType, setDeliveryType] = useState('delivery')
  const [deliveryAddress, setDeliveryAddress] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const subtotal = cart.reduce((sum, item) => sum + Number(item.discounted_price || item.price) * item.qty, 0)
  const deliveryFee = deliveryType === 'delivery' && cart.length ? 500 : 0
  const total = subtotal + deliveryFee

  async function placeOrder() {
    if (submitting || !cart.length) return
    if (deliveryType === 'delivery' && !deliveryAddress.trim()) {
      setError('Please enter the workshop or roadside delivery address.')
      return
    }
    setSubmitting(true)
    setError('')
    const controller = new AbortController()
    checkoutAbort.current = controller
    try {
      const data = await checkoutParts({
          items: cart.map((item) => ({ part_id: item.id, quantity: item.qty })),
          delivery_type: deliveryType,
          delivery_address: deliveryAddress.trim(),
          contact_phone: contactPhone.trim(),
          payment_method: 'wallet_escrow',
          vehicle_id: null,
      }, userId, { signal: controller.signal })
      if (!mounted.current) return
      clearCart()
      navigate('/transporter/parts-store/orders', { state: { newOrder: { id: data.order.id, order_number: data.order.order_number } } })
    } catch (err) {
      if (!mounted.current) return
      setError(err.message || 'The shop service could not be reached. Please try again.')
    } finally {
      if (mounted.current) setSubmitting(false)
    }
  }

  if (!cart.length) return (
    <main className="parts-store-page">
      <div className="store-page-heading"><div><span>PARTS STORE</span><h1>Your Cart</h1><p>Review selected products before placing an order.</p></div></div>
      <section className="store-empty-state"><i className="fa-solid fa-cart-shopping"></i><h2>Your cart is empty</h2><p>Products added to the cart will stay saved even after you refresh the page.</p><Link to="/transporter/parts-store">Browse Truck Parts</Link></section>
    </main>
  )

  return (
    <main className="parts-store-page">
      <div className="store-page-heading"><div><span>CHECKOUT</span><h1>Your Cart</h1><p>Confirm products, quantity and delivery details.</p></div><Link to="/transporter/parts-store" className="store-secondary-link"><i className="fa-solid fa-arrow-left"></i> Continue Shopping</Link></div>
      <div className="store-checkout-layout">
        <section className="store-panel">
          <div className="store-panel-title"><h2>Selected Products</h2><span>{cart.reduce((sum, item) => sum + item.qty, 0)} items</span></div>
          <div className="store-cart-list">{cart.map((item) => <article className="store-cart-row" key={item.id}>
            <div className="store-product-symbol"><i className="fa-solid fa-gears"></i></div>
            <div className="store-cart-product"><h3>{item.title}</h3><p>{item.shop_name || 'Verified Shop'}{item.part_number ? ` • ${item.part_number}` : ''}</p><strong>PKR {Number(item.discounted_price || item.price).toLocaleString()} each</strong></div>
            <div className="store-qty"><button onClick={() => changeQty(item.id, -1)}>−</button><b>{item.qty}</b><button onClick={() => changeQty(item.id, 1)}>+</button></div>
            <div className="store-line-price">PKR {(Number(item.discounted_price || item.price) * item.qty).toLocaleString()}</div>
            <button className="store-remove" onClick={() => removeItem(item.id)} aria-label={`Remove ${item.title}`}><i className="fa-solid fa-trash"></i></button>
          </article>)}</div>
        </section>

        <aside className="store-panel store-order-summary">
          <h2>Order Details</h2>
          <label>Fulfillment method</label>
          <div className="store-methods"><button className={deliveryType === 'delivery' ? 'active' : ''} onClick={() => setDeliveryType('delivery')}><i className="fa-solid fa-truck-fast"></i><span><b>Delivery</b><small>Workshop or roadside</small></span></button><button className={deliveryType === 'pickup' ? 'active' : ''} onClick={() => setDeliveryType('pickup')}><i className="fa-solid fa-store"></i><span><b>Self Pickup</b><small>Collect from shop</small></span></button></div>
          {deliveryType === 'delivery' && <div className="store-field"><label>Delivery address *</label><textarea value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} placeholder="Enter workshop address or roadside location" /></div>}
          <div className="store-field"><label>Contact phone</label><input type="tel" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="0300 1234567" /></div>
          {error && <div className="store-error"><i className="fa-solid fa-circle-exclamation"></i>{error}</div>}
          <div className="store-summary-lines"><div><span>Parts subtotal</span><span>PKR {subtotal.toLocaleString()}</span></div><div><span>Delivery fee</span><span>{deliveryFee ? `PKR ${deliveryFee.toLocaleString()}` : 'Free'}</span></div><div className="total"><span>Total</span><strong>PKR {total.toLocaleString()}</strong></div></div>
          <div className="store-secure-note"><i className="fa-solid fa-shield-halved"></i><span>Your payment stays protected in DigiTransX escrow until delivery.</span></div>
          <button className="store-primary-button" disabled={submitting} onClick={placeOrder}>{submitting ? <><i className="fa-solid fa-spinner fa-spin"></i> Placing Order...</> : <><i className="fa-solid fa-lock"></i> Confirm & Pay PKR {total.toLocaleString()}</>}</button>
        </aside>
      </div>
    </main>
  )
}
