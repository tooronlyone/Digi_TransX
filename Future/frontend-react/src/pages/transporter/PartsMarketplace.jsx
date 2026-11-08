import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePartsCart } from './partsCart'
import { apiSend } from '../client/clientUtils'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import { checkoutParts } from './marketplaceApi'
import Notification from '../../components/common/Notification'
import '../../styles/pages/parts-marketplace.css'

const CATEGORIES = [
  { id: 'all', label: 'All Parts', icon: 'fa-boxes-stacked' },
  { id: 'tyres', label: 'Tyres & Tubes', icon: 'fa-circle-dot' },
  { id: 'engine', label: 'Engine & Turbo', icon: 'fa-cogs' },
  { id: 'brakes', label: 'Brakes & Air Booster', icon: 'fa-hand-paper' },
  { id: 'clutch', label: 'Clutch & Gearbox', icon: 'fa-sliders' },
  { id: 'lubricants', label: 'Oils & Filters', icon: 'fa-oil-can' },
  { id: 'electrical', label: 'Batteries & Starter', icon: 'fa-bolt' },
]

export default function PartsMarketplace() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <PartsMarketplaceAccount key={String(user.id)} userId={user.id} />
}

function PartsMarketplaceAccount({ userId }) {
  const mounted = useRef(true)
  const checkoutAbort = useRef(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; checkoutAbort.current?.abort() } }, [])
  const navigate = useNavigate()
  const [parts, setParts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [notification, setNotification] = useState({ type: '', message: '' })
  const [trucks, setTrucks] = useState([])
  const [selectedTruck, setSelectedTruck] = useState(null)
  
  // Cart & Checkout State
  const { cart, addItem, changeQty, clearCart } = usePartsCart()
  const [showCart, setShowCart] = useState(false)
  const [checkingOut, setCheckingOut] = useState(false)
  const [deliveryType, setDeliveryType] = useState('delivery')
  const [deliveryAddress, setDeliveryAddress] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [orderSuccess, setOrderSuccess] = useState(null)

  // RFQ Broadcast Modal State
  const [showRfqModal, setShowRfqModal] = useState(false)
  const [rfqPartName, setRfqPartName] = useState('')
  const [rfqCity, setRfqCity] = useState('Lahore')
  const [rfqUrgency, setRfqUrgency] = useState('normal')
  const [rfqSubmitting, setRfqSubmitting] = useState(false)
  const [rfqSuccessMsg, setRfqSuccessMsg] = useState('')

  useEffect(() => {
    fetchTrucks()
    fetchParts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, selectedTruck])

  async function fetchTrucks() {
    try {
      const res = await fetch('/api/trucks', { credentials: 'include' })
      const data = await res.json()
      if (data.success && data.trucks?.length > 0) {
        setTrucks(data.trucks)
      }
    } catch { /* Compatibility filtering remains optional when fleet loading is unavailable. */ }
  }

  async function fetchParts() {
    setLoading(true)
    setError('')
    try {
      let url = `/api/marketplace/parts?category=${category}`
      if (search) url += `&search=${encodeURIComponent(search)}`
      if (selectedTruck?.truck_model) url += `&model=${encodeURIComponent(selectedTruck.truck_model)}`
      
      const res = await fetch(url, { credentials: 'include' })
      const data = await res.json()
      if (data.success) {
        setParts(data.parts || [])
      } else {
        setError(data.message || 'Failed to load parts')
      }
    } catch {
      setError('Network connection failed. Please retry.')
    } finally {
      setLoading(false)
    }
  }

  function handleSearchSubmit(e) {
    e.preventDefault()
    fetchParts()
  }

  function addToCart(part) {
    addItem(part)
    navigate('/transporter/parts-store/cart')
  }

  function updateQty(id, delta) {
    changeQty(id, delta)
  }

  const subtotal = cart.reduce((acc, item) => acc + (item.discounted_price || item.price) * item.qty, 0)
  const deliveryFee = deliveryType === 'delivery' && cart.length > 0 ? 500 : 0
  const grandTotal = subtotal + deliveryFee

  async function handlePlaceOrder() {
    if (checkingOut || cart.length === 0) return
    if (deliveryType === 'delivery' && !deliveryAddress.trim()) {
      setNotification({ type: 'error', message: 'Please enter a delivery address or roadside location.' })
      return
    }

    setCheckingOut(true)
    const controller = new AbortController()
    checkoutAbort.current = controller
    try {
      const payload = {
        items: cart.map(item => ({ part_id: item.id, quantity: item.qty })),
        delivery_type: deliveryType,
        delivery_address: deliveryAddress.trim(),
        contact_phone: contactPhone.trim(),
        vehicle_id: selectedTruck?.id || null,
        payment_method: 'wallet_escrow'
      }

      const data = await checkoutParts(payload, userId, { signal: controller.signal })
      if (!mounted.current) return
      if (data.success) {
        setOrderSuccess(data.order)
        clearCart()
        setShowCart(false)
      } else {
        setNotification({ type: 'error', message: data.message || 'Order failed. Please check wallet balance.' })
      }
    } catch (error) {
      if (!mounted.current) return
      setNotification({ type: 'error', message: error.message || 'The order outcome could not be confirmed. Please retry with the same cart.' })
    } finally {
      if (mounted.current) setCheckingOut(false)
    }
  }

  async function handleBroadcastRfq(e) {
    e.preventDefault()
    if (!rfqPartName.trim()) return

    setRfqSubmitting(true)
    try {
      const payload = {
        part_name: rfqPartName.trim(),
        city: rfqCity.trim(),
        urgency: rfqUrgency,
        vehicle_id: selectedTruck?.id || null
      }

      const data = await apiSend('/api/marketplace/rfq', payload)
      if (!mounted.current) return
      if (data.success) {
        setRfqSuccessMsg('Your part request has been broadcasted to verified shops! You will receive price quotes shortly.')
        setRfqPartName('')
      } else {
        setNotification({ type: 'error', message: data.message || 'Failed to submit request' })
      }
    } catch (error) {
      if (!mounted.current) return
      setNotification({ type: 'error', message: error.message || 'The request could not be sent. Please retry.' })
    } finally {
      if (mounted.current) setRfqSubmitting(false)
    }
  }

  return (
    <div className="parts-marketplace p-4 md:p-6 max-w-7xl mx-auto space-y-6">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />
      {/* Top Banner / Store Header */}
      <div className="parts-marketplace-hero rounded-2xl p-6 relative overflow-hidden">
        <div className="relative z-10 space-y-3 max-w-2xl">
          <span className="parts-marketplace-eyebrow text-xs font-semibold px-3 py-1 rounded-full uppercase tracking-wide">
            <i className="fa-solid fa-shield-halved"></i> Verified Marketplace
          </span>
          <h1 className="parts-marketplace-title text-2xl md:text-3xl font-extrabold tracking-tight">
            Truck Parts & Spares Store
          </h1>
          <p className="parts-marketplace-copy text-sm">
            Order genuine tyres, engine parts, and lubricants directly for your fleet with 
            <strong> DigiTransX Escrow Protection</strong>. Deliver to your workshop or breakdown location.
          </p>

          {/* Truck Selector Compatibility Bar */}
          <div className="parts-marketplace-actions pt-2 flex flex-wrap items-end gap-3">
            <label className="parts-truck-filter">
              <span>Truck compatibility</span>
              <select
              value={selectedTruck?.id || ''}
              onChange={e => {
                const id = parseInt(e.target.value)
                setSelectedTruck(trucks.find(t => t.id === id) || null)
              }}
              className="text-xs rounded-lg px-3 py-2 outline-none"
            >
              <option value="">All Compatible Trucks (Show All)</option>
              {trucks.map(truck => (
                <option key={truck.id} value={truck.id}>
                  {truck.truck_number} — {truck.truck_company} {truck.truck_model}
                </option>
              ))}
              </select>
            </label>

            <button
              onClick={() => setShowRfqModal(true)}
              className="parts-rfq-button ml-auto text-xs font-bold px-4 py-2 rounded-lg flex items-center gap-2 transition"
            >
              <i className="fa-solid fa-bullhorn"></i>
              Request a Missing Part
            </button>
          </div>
        </div>
      </div>

      {/* Search & Category Pills */}
      <div className="parts-marketplace-tools space-y-4">
        <div className="parts-tools-heading">
          <div>
            <h2>Find the right part</h2>
            <p>Search by product name, part number or brand.</p>
          </div>
          {cart.length > 0 && (
            <button type="button" className="parts-cart-button" onClick={() => navigate('/transporter/parts-store/cart')}>
              <i className="fa-solid fa-cart-shopping"></i> View Cart <span>{cart.reduce((sum, item) => sum + item.qty, 0)}</span>
            </button>
          )}
        </div>
        <form onSubmit={handleSearchSubmit} className="parts-search-form flex gap-2">
          <div className="relative flex-1">
            <i className="fa-solid fa-magnifying-glass absolute left-3.5 top-3.5 text-slate-400 text-sm"></i>
            <input
              type="text"
              placeholder="Search by part title, OEM part number, or brand (e.g. 11R22.5, Clutch Plate, Dunlop)..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm outline-none"
            />
          </div>
          <button
            type="submit"
            className="parts-search-button px-5 py-2.5 rounded-xl text-sm font-semibold transition"
          >
            Search
          </button>
        </form>

        {/* Category Pills */}
        <div className="parts-categories flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              onClick={() => setCategory(cat.id)}
              className={`parts-category flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition ${
                category === cat.id
                  ? 'is-active'
                  : ''
              }`}
            >
              <i className={`fa-solid ${cat.icon}`}></i>
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Order Success Dialog */}
      {orderSuccess && (
        <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 p-5 rounded-2xl flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-600 flex items-center justify-center text-xl">
              <i className="fa-solid fa-shield-check"></i>
            </div>
            <div>
              <h3 className="text-sm font-bold text-emerald-900 dark:text-emerald-200">
                Order Placed Successfully! (Order #{orderSuccess.order_number})
              </h3>
              <p className="text-xs text-emerald-700 dark:text-emerald-400">
                Amount <strong>PKR {orderSuccess.net_total?.toLocaleString()}</strong> is secured in Escrow. 
                Open My Parts Orders to request a handoff code after receiving and inspecting the parts.
              </p>
            </div>
          </div>
          <button type="button" className="store-secondary-link" onClick={() => navigate('/transporter/parts-store/orders')}>My Parts Orders</button>
          <button
            onClick={() => setOrderSuccess(null)}
            className="text-xs text-slate-500 hover:text-slate-800 underline self-start md:self-auto"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Parts Grid */}
      {loading ? (
        <div className="parts-loading text-center py-16 space-y-3">
          <div className="parts-loading-icon"><i className="fa-solid fa-box-open"></i></div>
          <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <h3>Preparing the parts catalogue</h3>
          <p className="text-sm text-slate-500">Checking verified shops and available stock...</p>
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500 text-sm">{error}</div>
      ) : parts.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-800 space-y-3">
          <div className="text-slate-400 text-3xl">
            <i className="fa-solid fa-box-open"></i>
          </div>
          <h3 className="text-base font-semibold text-slate-700 dark:text-slate-200">No parts found matching this filter</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Try switching category or broadcasting a quick request to nearby shops.
          </p>
          <button
            onClick={() => setShowRfqModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 transition"
          >
            Request Part Quote
          </button>
        </div>
      ) : (
        <div className="parts-product-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {parts.map(part => {
            const hasDiscount = part.discounted_price && part.discounted_price < part.price
            const effectivePrice = hasDiscount ? part.discounted_price : part.price

            return (
              <div
                key={part.id}
                className="parts-product-card rounded-2xl p-4 flex flex-col justify-between transition group"
              >
                <div className="space-y-3">
                  {/* Shop & Condition Tags */}
                  <div className="flex items-center justify-between text-xs">
                    <span className="parts-card-shop font-semibold flex items-center gap-1.5">
                      <i className="fa-solid fa-store text-blue-500"></i>
                      {part.shop_name}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      part.condition === 'new_oem' ? 'bg-emerald-100 text-emerald-800' :
                      part.condition === 'kabli' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
                    }`}>
                      {part.condition.replace('_', ' ')}
                    </span>
                  </div>

                  {/* Title & Brand */}
                  <div>
                    <h3 className="parts-card-title font-bold text-base transition line-clamp-2">
                      {part.title}
                    </h3>
                    <p className="parts-card-meta text-xs mt-0.5">
                      Brand: <span className="font-medium">{part.brand || 'Standard'}</span> 
                      {part.part_number && ` • PN: ${part.part_number}`}
                    </p>
                  </div>

                  {/* Compatibility Tags */}
                  {part.compatible_models?.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {part.compatible_models.slice(0, 3).map((m, idx) => (
                        <span key={idx} className="parts-fit-tag text-[10px] px-2 py-0.5 rounded">
                          ✓ Fits {m}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Description snippet */}
                  <p className="parts-card-description text-xs line-clamp-2">
                    {part.description}
                  </p>
                </div>

                {/* Price & Action */}
                <div className="parts-card-footer pt-4 mt-4 flex items-end justify-between gap-3">
                  <div>
                    <div className="parts-card-price text-lg font-black">
                      PKR {effectivePrice.toLocaleString()}
                    </div>
                    {hasDiscount && (
                      <div className="parts-old-price text-xs line-through">
                        PKR {part.price.toLocaleString()}
                      </div>
                    )}
                    {part.warranty_days > 0 && (
                      <div className="parts-warranty text-[10px] font-semibold">
                        <i className="fa-solid fa-shield"></i> {part.warranty_days} Days Warranty
                      </div>
                    )}
                  </div>

                  <button
                    onClick={() => addToCart(part)}
                    className="parts-add-button text-xs font-bold px-3.5 py-2 rounded-xl flex items-center gap-1.5 transition active:scale-95"
                  >
                    <i className="fa-solid fa-cart-plus"></i>
                    Add to Cart
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Cart Drawer / Slide-over Modal */}
      {showCart && (
        <div className="parts-cart-overlay fixed inset-0 flex justify-end">
          <div className="parts-cart-drawer w-full max-w-md h-full flex flex-col">
            <div className="parts-cart-header flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="parts-cart-icon"><i className="fa-solid fa-cart-shopping"></i></span>
                <div>
                  <span className="parts-cart-kicker">YOUR ORDER</span>
                  <h2 className="text-lg font-bold">
                    Parts Cart <span>({cart.reduce((sum, item) => sum + item.qty, 0)})</span>
                  </h2>
                </div>
              </div>
              <button
                onClick={() => setShowCart(false)}
                className="parts-cart-close"
                aria-label="Close cart"
              >
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>

            <div className="parts-cart-body space-y-5">
              <div className="space-y-4">
                {cart.length === 0 ? (
                  <div className="parts-cart-empty">
                    <i className="fa-solid fa-cart-shopping"></i>
                    <h3>Your cart is empty</h3>
                    <p>Add a truck part to continue.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {cart.map(item => (
                      <div key={item.id} className="parts-cart-item">
                        <div className="parts-cart-item-copy">
                          <h4>{item.title}</h4>
                          <span>PKR {(item.discounted_price || item.price).toLocaleString()} each</span>
                        </div>
                        <div className="parts-qty-control" aria-label={`Quantity for ${item.title}`}>
                          <button onClick={() => updateQty(item.id, -1)} aria-label="Decrease quantity">−</button>
                          <span>{item.qty}</span>
                          <button onClick={() => updateQty(item.id, 1)} aria-label="Increase quantity">+</button>
                        </div>
                      </div>
                    ))}

                    <div className="parts-delivery-section">
                      <div className="parts-cart-section-title">
                        <span>Fulfillment method</span>
                        <small>Choose how you want to receive the order</small>
                      </div>
                      <div className="parts-delivery-options grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setDeliveryType('delivery')}
                          className={deliveryType === 'delivery' ? 'is-active' : ''}
                        >
                          <i className="fa-solid fa-truck-fast"></i>
                          <span><strong>Delivery</strong><small>Workshop or roadside</small></span>
                          <b>+ PKR 500</b>
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeliveryType('pickup')}
                          className={deliveryType === 'pickup' ? 'is-active' : ''}
                        >
                          <i className="fa-solid fa-store"></i>
                          <span><strong>Self Pickup</strong><small>Collect from the shop</small></span>
                          <b>Free</b>
                        </button>
                      </div>

                      {deliveryType === 'delivery' && (
                        <div className="parts-cart-field">
                          <label>Delivery address <span>*</span></label>
                          <input
                            type="text"
                            placeholder="Workshop address or roadside location"
                            value={deliveryAddress}
                            onChange={e => setDeliveryAddress(e.target.value)}
                          />
                        </div>
                      )}

                      <div className="parts-cart-field">
                        <label>Contact phone</label>
                        <input
                          type="tel"
                          placeholder="0300 1234567"
                          value={contactPhone}
                          onChange={e => setContactPhone(e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {cart.length > 0 && (
              <div className="parts-cart-footer">
                <div className="parts-cart-totals">
                  <div><span>Parts subtotal</span><span>PKR {subtotal.toLocaleString()}</span></div>
                  {deliveryFee > 0 && <div><span>Delivery fee</span><span>PKR {deliveryFee.toLocaleString()}</span></div>}
                  <div className="parts-grand-total"><span>Total</span><strong>PKR {grandTotal.toLocaleString()}</strong></div>
                </div>
                <div className="parts-escrow-note">
                  <i className="fa-solid fa-shield-halved"></i>
                  <span>Payment stays protected in escrow until you receive the parts.</span>
                </div>
                <button
                  disabled={checkingOut}
                  onClick={handlePlaceOrder}
                  className="parts-checkout-button"
                >
                  <i className={`fa-solid ${checkingOut ? 'fa-spinner fa-spin' : 'fa-lock'}`}></i>
                  {checkingOut ? ' Securing Payment...' : ` Confirm & Pay PKR ${grandTotal.toLocaleString()}`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* RFQ Broadcast Modal */}
      {showRfqModal && (
        <div className="parts-rfq-overlay fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="parts-rfq-modal w-full max-w-lg rounded-2xl p-6 space-y-4" role="dialog" aria-modal="true" aria-labelledby="parts-rfq-title">
            <div className="parts-rfq-header flex items-start justify-between pb-4">
              <div className="flex items-center gap-3">
                <span className="parts-rfq-icon"><i className="fa-solid fa-bullhorn"></i></span>
                <div>
                  <span className="parts-rfq-kicker">PART REQUEST</span>
                  <h3 id="parts-rfq-title" className="font-bold text-base">Request a Missing Part</h3>
                </div>
              </div>
              <button onClick={() => { setShowRfqModal(false); setRfqSuccessMsg(''); }} className="parts-rfq-close" aria-label="Close request form">
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>

            {rfqSuccessMsg ? (
              <div className="parts-rfq-success p-4 text-xs rounded-xl space-y-3">
                <span className="parts-success-icon"><i className="fa-solid fa-check"></i></span>
                <div>
                  <h4>Request sent successfully</h4>
                  <p>{rfqSuccessMsg}</p>
                </div>
                <button
                  onClick={() => { setShowRfqModal(false); setRfqSuccessMsg(''); }}
                  className="px-4 py-2 rounded-lg text-xs font-semibold"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleBroadcastRfq} className="parts-rfq-form space-y-4">
                <p className="parts-rfq-intro text-xs">
                  Tell us which part you need. Your request will be shared with verified shops in your city so they can send you a price quote.
                </p>

                <div>
                  <label className="block mb-1.5">Part name or description <span>*</span></label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Hino 500 radiator hose or front shock absorber"
                    value={rfqPartName}
                    onChange={e => setRfqPartName(e.target.value)}
                    className="w-full p-3 rounded-lg outline-none"
                  />
                  <small>Add a model or part number if you know it.</small>
                </div>

                <div className="grid grid-cols-2 gap-3 parts-rfq-row">
                  <div>
                    <label className="block mb-1.5">City <span>*</span></label>
                    <input
                      type="text"
                      required
                      value={rfqCity}
                      onChange={e => setRfqCity(e.target.value)}
                      className="w-full p-3 rounded-lg outline-none"
                    />
                  </div>
                  <div>
                    <label className="block mb-1.5">Urgency</label>
                    <select
                      value={rfqUrgency}
                      onChange={e => setRfqUrgency(e.target.value)}
                      className="w-full p-3 rounded-lg outline-none"
                    >
                      <option value="normal">Normal — Workshop</option>
                      <option value="breakdown_emergency">Emergency — Breakdown</option>
                    </select>
                  </div>
                </div>

                <div className="parts-rfq-note">
                  <i className="fa-solid fa-shield-halved"></i>
                  Only verified shopkeepers can respond to this request.
                </div>

                <div className="parts-rfq-footer">
                  <button
                    type="button"
                    onClick={() => { setShowRfqModal(false); setRfqSuccessMsg(''); }}
                    className="parts-rfq-cancel"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={rfqSubmitting}
                    className="parts-rfq-submit font-bold disabled:opacity-50"
                  >
                    <i className={`fa-solid ${rfqSubmitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`}></i>
                    {rfqSubmitting ? ' Sending Request...' : ' Send Request'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
