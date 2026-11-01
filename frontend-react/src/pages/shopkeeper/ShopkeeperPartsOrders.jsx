import { useState, useEffect, useRef } from 'react'
import { FeeBreakdown } from '../../components/business/BusinessRules'
import { apiSend } from '../client/clientUtils'
import Notification from '../../components/common/Notification'

export default function ShopkeeperPartsOrders() {
  const [activeTab, setActiveTab] = useState('orders') // 'orders' | 'inventory' | 'rfqs'
  const [orders, setOrders] = useState([])
  const [parts, setParts] = useState([])
  const [rfqs, setRfqs] = useState([])
  const [loading, setLoading] = useState(true)
  const [notification, setNotification] = useState({ type: '', message: '' })
  
  // OTP Verification Modal
  const [verifyingOrder, setVerifyingOrder] = useState(null)
  const [otpInput, setOtpInput] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [otpMessage, setOtpMessage] = useState('')
  const otpTimer = useRef(null)
  useEffect(() => () => clearTimeout(otpTimer.current), [])

  // Add Part Modal
  const [showAddPart, setShowAddPart] = useState(false)
  const [newPart, setNewPart] = useState({
    title: '',
    part_number: '',
    brand: '',
    category: 'engine',
    condition: 'new_oem',
    price: '',
    stock_quantity: 5,
    warranty_days: 90,
    description: '',
    compatible_models: 'Hino 500, Isuzu FVR',
    city: 'Lahore'
  })

  // RFQ Bid State
  const [biddingRfq, setBiddingRfq] = useState(null)
  const [bidPrice, setBidPrice] = useState('')
  const [bidDeliveryHours, setBidDeliveryHours] = useState('2')
  const [bidSubmitting, setBidSubmitting] = useState(false)

  // Reload whenever the selected workspace tab changes.
  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  async function loadData() {
    setLoading(true)
    try {
      if (activeTab === 'orders') {
        const res = await fetch('/api/marketplace/shop/orders', { credentials: 'include' })
        const data = await res.json()
        if (data.success) setOrders(data.orders || [])
      } else if (activeTab === 'inventory') {
        const res = await fetch('/api/marketplace/shop/parts', { credentials: 'include' })
        const data = await res.json()
        if (data.success) setParts(data.parts || [])
      } else if (activeTab === 'rfqs') {
        const res = await fetch('/api/marketplace/rfq', { credentials: 'include' })
        const data = await res.json()
        if (data.success) setRfqs(data.rfqs || [])
      }
    } catch {
      // Keep the tab in its empty state when the marketplace is temporarily unavailable.
    }
    finally {
      setLoading(false)
    }
  }

  async function handleVerifyOtp(e) {
    e.preventDefault()
    if (otpLoading || !verifyingOrder || !/^[0-9]{6}$/.test(otpInput)) return

    setOtpLoading(true)
    setOtpMessage('')
    try {
      const data = await apiSend(`/api/marketplace/shop/orders/${verifyingOrder.id}/verify-otp`, { otp: otpInput.trim() })
      if (data.success) {
        setOtpMessage('✅ ' + data.message)
        otpTimer.current = setTimeout(() => {
          setVerifyingOrder(null)
          setOtpInput('')
          setOtpMessage('')
          loadData()
        }, 1500)
      } else {
        setOtpMessage('❌ ' + (data.message || 'OTP verification failed'))
      }
    } catch (error) {
      setOtpMessage('❌ ' + (error.message || 'Verification could not be completed.'))
    } finally {
      setOtpLoading(false)
    }
  }

  async function handleUpdateStatus(orderId, status) {
    try {
      const data = await apiSend(`/api/marketplace/shop/orders/${orderId}/status`, { status })
      if (data.success) {
        loadData()
      } else {
        setNotification({ type: 'error', message: data.message })
      }
    } catch (error) {
      setNotification({ type: 'error', message: error.message || 'Error updating status' })
    }
  }

  async function handleAddPartSubmit(e) {
    e.preventDefault()
    try {
      const payload = {
        ...newPart,
        price: parseFloat(newPart.price),
        stock_quantity: parseInt(newPart.stock_quantity),
        warranty_days: parseInt(newPart.warranty_days),
        compatible_models: newPart.compatible_models.split(',').map(s => s.trim())
      }
      const data = await apiSend('/api/marketplace/shop/parts', payload)
      if (data.success) {
        setShowAddPart(false)
        loadData()
      } else {
        setNotification({ type: 'error', message: data.message })
      }
    } catch (error) {
      setNotification({ type: 'error', message: error.message || 'The part could not be saved.' })
    }
  }

  async function handleSubmitRfqBid(e) {
    e.preventDefault()
    if (!biddingRfq || !bidPrice) return
    setBidSubmitting(true)
    try {
      const data = await apiSend(`/api/marketplace/rfq/${biddingRfq.id}/bid`, {
          offered_price: parseFloat(bidPrice),
          delivery_time_hours: parseInt(bidDeliveryHours)
      })
      if (data.success) {
        setNotification({ type: 'success', message: 'Quote sent to transporter!' })
        setBiddingRfq(null)
        setBidPrice('')
      } else {
        setNotification({ type: 'error', message: data.message })
      }
    } catch (error) {
      setNotification({ type: 'error', message: error.message || 'The quote could not be sent.' })
    } finally {
      setBidSubmitting(false)
    }
  }

  return (
    <div className="shopkeeper-parts-hub p-4 md:p-6 max-w-7xl mx-auto space-y-6">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />
      {/* Header */}
      <div className="shopkeeper-parts-hero flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <span className="text-xs font-bold text-orange-500 uppercase tracking-wider">Vendor Portal</span>
          <h1 className="text-xl md:text-2xl font-black text-slate-900">
            Truck Parts & Orders Hub
          </h1>
          <p className="text-xs text-slate-500">
            Manage your catalog, fulfill incoming transporter parts orders, and release secured escrow payments.
          </p>
        </div>

        {/* Tab Buttons */}
        <div className="shopkeeper-parts-tabs flex bg-slate-100 p-1 rounded-xl text-xs font-bold">
          <button
            onClick={() => setActiveTab('orders')}
            className={`px-4 py-2 rounded-lg transition ${activeTab === 'orders' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600'}`}
          >
            📦 Incoming Orders ({orders.length})
          </button>
          <button
            onClick={() => setActiveTab('inventory')}
            className={`px-4 py-2 rounded-lg transition ${activeTab === 'inventory' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600'}`}
          >
            🏷️ Listed Parts ({parts.length})
          </button>
          <button
            onClick={() => setActiveTab('rfqs')}
            className={`px-4 py-2 rounded-lg transition ${activeTab === 'rfqs' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600'}`}
          >
            📢 RFQs Broadcast
          </button>
        </div>
      </div>

      <FeeBreakdown kind="marketplace" />
      {/* Main Content Area */}
      {loading ? (
        <div className="text-center py-16">
          <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          <p className="text-xs text-slate-500">Loading vendor records...</p>
        </div>
      ) : activeTab === 'orders' ? (
        /* ORDERS TAB */
        <div className="space-y-4">
          {orders.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-2xl border border-dashed border-slate-300">
              <i className="fa-solid fa-inbox text-3xl text-slate-400 mb-2"></i>
              <h3 className="text-sm font-bold text-slate-700">No Orders Yet</h3>
              <p className="text-xs text-slate-500">Orders placed by transporters will appear here in real-time.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {orders.map(order => (
                <div key={order.id} className="shopkeeper-order-card bg-white border border-slate-200 rounded-2xl p-5 space-y-4 shadow-sm">
                  <div className="flex items-center justify-between border-b pb-2">
                    <div>
                      <span className="text-xs font-mono font-bold text-blue-600">#{order.order_number}</span>
                      <span className="text-xs text-slate-400 ml-2">{new Date(order.created_at).toLocaleDateString()}</span>
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                      order.fulfillment_status === 'delivered' ? 'bg-emerald-100 text-emerald-800' :
                      order.fulfillment_status === 'dispatched' ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-800'
                    }`}>
                      {order.fulfillment_status}
                    </span>
                  </div>

                  {/* Items */}
                  <div className="space-y-2 text-xs text-slate-700">
                    {order.items?.map((it, idx) => (
                      <div key={idx} className="flex justify-between gap-4 font-medium">
                        <span>{it.quantity}x {it.part_title}</span>
                        <span>PKR {it.subtotal?.toLocaleString()}</span>
                      </div>
                    ))}
                    <div className="flex justify-between font-bold pt-3 mt-2 border-t border-slate-200 text-sm text-slate-900">
                      <span>Total Payout</span>
                      <span className="text-emerald-600">PKR {order.net_total?.toLocaleString()}</span>
                    </div>
                  </div>

                  {order.commission_breakdown && <FeeBreakdown kind="marketplace" snapshot={order.commission_breakdown} />}
                  {/* Buyer & Delivery details */}
                  <div className="shopkeeper-order-details bg-slate-50 p-3.5 rounded-xl text-xs text-slate-700 space-y-1.5">
                    <div><strong>Customer:</strong> {order.contact_phone || 'Customer'}</div>
                    {order.truck_number && <div><strong>Truck:</strong> {order.truck_number}</div>}
                    <div><strong>Type:</strong> {order.delivery_type === 'delivery' ? `🚚 Deliver to: ${order.delivery_address}` : '🏬 Customer Counter Pickup'}</div>
                    <div className="text-emerald-600 font-semibold flex items-center gap-1">
                      <i className="fa-solid fa-lock"></i>
                      Payment: {order.payment_status === 'escrow_locked' ? 'Secured in Platform Escrow' : order.payment_status}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2 pt-1">
                    {order.fulfillment_status === 'placed' && (
                      <button
                        onClick={() => handleUpdateStatus(order.id, 'confirmed')}
                        className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition"
                      >
                        Confirm & Pack
                      </button>
                    )}
                    {order.fulfillment_status === 'confirmed' && (
                      <button
                        onClick={() => handleUpdateStatus(order.id, order.delivery_type === 'delivery' ? 'dispatched' : 'ready_for_pickup')}
                        className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition"
                      >
                        {order.delivery_type === 'delivery' ? 'Dispatch with Rider' : 'Mark Ready for Pickup'}
                      </button>
                    )}
                    {['dispatched', 'ready_for_pickup'].includes(order.fulfillment_status) && (
                      <button
                        onClick={() => { setVerifyingOrder(order); setOtpInput(''); setOtpMessage(''); }}
                        className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5"
                      >
                        <i className="fa-solid fa-key"></i>
                        Verify OTP & Claim Funds
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : activeTab === 'inventory' ? (
        /* INVENTORY TAB */
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              onClick={() => setShowAddPart(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 rounded-xl shadow transition flex items-center gap-2"
            >
              <i className="fa-solid fa-plus"></i>
              Add New Part / Tyre
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {parts.map(part => (
              <div key={part.id} className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2 shadow-sm">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600 uppercase">
                    {part.category}
                  </span>
                  <span className="text-xs font-bold text-emerald-600">Stock: {part.stock_quantity}</span>
                </div>
                <h3 className="font-bold text-sm text-slate-800">{part.title}</h3>
                <p className="text-xs text-slate-400">Brand: {part.brand} {part.part_number && `• ${part.part_number}`}</p>
                <div className="text-base font-extrabold text-blue-600 pt-2 border-t">
                  PKR {part.price?.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* RFQS BROADCAST TAB */
        <div className="space-y-4">
          <p className="text-xs text-slate-500">Transporters requesting emergency parts or quotes in your area:</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {rfqs.map(rfq => (
              <div key={rfq.id} className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3 shadow-sm">
                <div className="flex justify-between items-start">
                  <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                    rfq.urgency === 'breakdown_emergency' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'
                  }`}>
                    {rfq.urgency === 'breakdown_emergency' ? '🚨 Breakdown Emergency' : 'Standard Request'}
                  </span>
                  <span className="text-xs text-slate-400">{rfq.city}</span>
                </div>

                <div>
                  <h4 className="font-bold text-sm text-slate-900">{rfq.part_name}</h4>
                  <p className="text-xs text-slate-500 mt-1">{rfq.description || 'No extra notes'}</p>
                  {rfq.truck_number && (
                    <span className="text-[10px] text-blue-600 font-semibold block mt-1">Truck: {rfq.truck_number}</span>
                  )}
                </div>

                <div className="pt-2 border-t flex items-center justify-between">
                  <span className="text-xs text-slate-400">{rfq.bids_count || 0} quotes submitted</span>
                  <button
                    onClick={() => { setBiddingRfq(rfq); setBidPrice(''); }}
                    className="px-3.5 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-bold rounded-lg shadow-sm transition"
                  >
                    Submit Price Quote
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* OTP Modal */}
      {verifyingOrder && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b pb-2">
              <h3 className="font-bold text-sm text-slate-800">Verify Delivery OTP</h3>
              <button onClick={() => setVerifyingOrder(null)} className="text-slate-400">
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>
            <form onSubmit={handleVerifyOtp} className="space-y-3">
              <p className="text-xs text-slate-500">
                Ask the customer for the 6-digit handoff code after they receive the parts. Verifying it will release 
                <strong> PKR {verifyingOrder.net_total?.toLocaleString()}</strong> to your wallet.
              </p>
              <input
                type="text"
                maxLength={6}
                inputMode="numeric"
                pattern="[0-9]{6}"
                required
                placeholder="6-digit handoff code"
                value={otpInput}
                onChange={e => setOtpInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="w-full text-center text-2xl font-mono tracking-widest p-2 border rounded-xl bg-white text-slate-900 outline-none focus:border-emerald-500"
              />
              {otpMessage && <p className="text-xs font-bold text-center">{otpMessage}</p>}
              <button
                type="submit"
                disabled={otpLoading || !/^[0-9]{6}$/.test(otpInput)}
                className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow transition disabled:opacity-50"
              >
                {otpLoading ? 'Verifying...' : 'Verify OTP & Release Funds'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Quote Bid Modal */}
      {biddingRfq && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b pb-2">
              <h3 className="font-bold text-sm text-slate-800">Quote for: {biddingRfq.part_name}</h3>
              <button onClick={() => setBiddingRfq(null)} className="text-slate-400">
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>
            <form onSubmit={handleSubmitRfqBid} className="space-y-3">
              <div>
                <label className="text-xs font-bold block mb-1">Offered Price (PKR) *</label>
                <input
                  type="number"
                  required
                  placeholder="e.g. 18500"
                  value={bidPrice}
                  onChange={e => setBidPrice(e.target.value)}
                  className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-bold block mb-1">Estimated Delivery Time (Hours)</label>
                <input
                  type="number"
                  value={bidDeliveryHours}
                  onChange={e => setBidDeliveryHours(e.target.value)}
                  className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={bidSubmitting}
                className="w-full py-2 bg-orange-500 hover:bg-orange-600 text-white font-bold text-xs rounded-xl shadow transition disabled:opacity-50"
              >
                {bidSubmitting ? 'Sending...' : 'Send Quote to Transporter'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Add Part Modal */}
      {showAddPart && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-md rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center border-b pb-2">
              <h3 className="font-bold text-sm text-slate-800">Add Part to Store</h3>
              <button onClick={() => setShowAddPart(false)} className="text-slate-400">
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>
            <form onSubmit={handleAddPartSubmit} className="space-y-3">
              <div>
                <label className="text-xs font-bold block mb-1">Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Dunlop 11R22.5 SP320 Heavy Truck Tyre"
                  value={newPart.title}
                  onChange={e => setNewPart({ ...newPart, title: e.target.value })}
                  className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-bold block mb-1">Brand</label>
                  <input
                    type="text"
                    placeholder="e.g. Dunlop, Hino"
                    value={newPart.brand}
                    onChange={e => setNewPart({ ...newPart, brand: e.target.value })}
                    className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold block mb-1">Category</label>
                  <select
                    value={newPart.category}
                    onChange={e => setNewPart({ ...newPart, category: e.target.value })}
                    className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                  >
                    <option value="tyres">Tyres & Tubes</option>
                    <option value="engine">Engine & Turbo</option>
                    <option value="brakes">Brakes & Booster</option>
                    <option value="clutch">Clutch & Gearbox</option>
                    <option value="lubricants">Oils & Lubricants</option>
                    <option value="electrical">Electrical & Battery</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-bold block mb-1">Price (PKR) *</label>
                  <input
                    type="number"
                    required
                    value={newPart.price}
                    onChange={e => setNewPart({ ...newPart, price: e.target.value })}
                    className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold block mb-1">Stock Quantity</label>
                  <input
                    type="number"
                    value={newPart.stock_quantity}
                    onChange={e => setNewPart({ ...newPart, stock_quantity: e.target.value })}
                    className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs font-bold block mb-1">Compatible Trucks (Comma separated)</label>
                <input
                  type="text"
                  value={newPart.compatible_models}
                  onChange={e => setNewPart({ ...newPart, compatible_models: e.target.value })}
                  className="w-full text-xs p-2 border rounded-lg bg-white text-slate-900 outline-none"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow transition"
              >
                Save and Publish Part
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
