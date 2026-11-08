import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getCsrfToken } from '../client/clientUtils'
import { FeeBreakdown, SettlementSummary } from '../../components/business/BusinessRules'
import DriverAssignmentPanel from '../../components/transporter/DriverAssignmentPanel'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import '../../styles/pages/order-tracking.css'

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return 'PKR 0'
  return `PKR ${amount.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

function formatDateTime(isoString) {
  if (!isoString) return '-'
  try {
    return new Date(isoString).toLocaleString('en-PK')
  } catch {
    return isoString
  }
}

function Countdown({ deadline }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  if (!deadline) return null
  const end = new Date(deadline).getTime()
  const remaining = Math.max(0, end - now)
  const h = Math.floor(remaining / 3600000)
  const m = Math.floor((remaining % 3600000) / 60000)
  const s = Math.floor((remaining % 60000) / 1000)
  return (
    <span className="order-tracking-countdown">
      {remaining > 0 ? `${h}h ${m}m ${s}s remaining` : 'Expired — request a new OTP if needed'}
    </span>
  )
}

export default function OrderTracking() {
  const { user, status } = useAuthVerification()
  const { orderId } = useParams()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <OwnedOrderTracking key={`${user.id}:${orderId}`} />
}

function OwnedOrderTracking() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [trip, setTrip] = useState(null)
  const [payment, setPayment] = useState(null)
  const [deliveryPolicy, setDeliveryPolicy] = useState(null)
  const [settlement, setSettlement] = useState(null)
  const [deliveryOtp, setDeliveryOtp] = useState('')
  const [dispute, setDispute] = useState(null)
  const [chatThreadId, setChatThreadId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState('')
  const [notice, setNotice] = useState('')
  const [statement, setStatement] = useState('')

  async function loadOrder() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/orders/${orderId}`, { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load order.')
      setOrder(json.order || null)
      setTrip(json.trip || null)
      setPayment(json.payment || null)
      setDeliveryPolicy(json.delivery_policy || null)
      setSettlement(json.settlement || null)
      setDispute(json.dispute || null)
      setChatThreadId(json.chat_thread_id || null)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load order details.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadOrder()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId])

  async function postAction(url, body, confirmMessage, key, successMessage) {
    if (confirmMessage && !window.confirm(confirmMessage)) return false
    setActionLoading(key)
    setError('')
    setNotice('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Action failed.')
      setNotice(successMessage || json.message || 'Done.')
      await loadOrder()
      return true
    } catch (actionError) {
      setError(actionError.message || 'Action failed.')
      return false
    } finally {
      setActionLoading('')
    }
  }

  const startTrip = () =>
    postAction(
      `/api/orders/${orderId}/trips/${trip.id}/start`, null,
      'Start this trip? The full booking payment remains in escrow until verified delivery settlement.',
      'start', 'Trip started.',
    )

  const completeDelivery = () =>
    postAction(
      `/api/orders/${orderId}/trips/${trip.id}/complete-delivery`, null,
      deliveryPolicy ? 'Request a delivery OTP for the Client to inspect and accept the cargo?' : 'Mark delivery complete? The client then has 6 hours to confirm before it goes to admin review.',
      'complete', deliveryPolicy ? 'Secure delivery OTP requested. Ask the Client to inspect the cargo and share their 8-digit OTP from Order Details.' : 'Delivery marked complete. Waiting for the client to confirm.',
    )

  async function submitStatement() {
    if (!dispute || !statement.trim()) return
    await postAction(
      `/api/disputes/${dispute.id}/statement`, { statement: statement.trim() },
      null, 'statement', 'Your statement was added to the dispute.',
    )
    setStatement('')
  }

  const openChat = () =>
    navigate(chatThreadId ? `/transporter/messages?thread=${chatThreadId}` : '/transporter/messages')

  if (loading) {
    return (
      <div className="order-tracking-page">
        <div className="order-tracking-loading">Loading order details...</div>
      </div>
    )
  }

  if (error && !order) {
    return (
      <div className="order-tracking-page">
        <div className="order-tracking-error">{error}</div>
        <Link to="/transporter/my-bids" className="order-tracking-back-btn">Back to My Bids</Link>
      </div>
    )
  }

  if (!order || !trip) {
    return (
      <div className="order-tracking-page">
        <div className="order-tracking-error">Order not found.</div>
        <Link to="/transporter/my-bids" className="order-tracking-back-btn">Back to My Bids</Link>
      </div>
    )
  }

  const paymentHeld = payment && ['held', 'escrow_locked'].includes(payment.status)

  return (
    <div className="order-tracking-page">
      <div className="order-tracking-header">
        <div>
          <h1>Order #{order.id}</h1>
          <p>{order.pickup_city} → {order.dropoff_city}</p>
        </div>
        <Link to="/transporter/my-bids" className="order-tracking-back-btn">
          <i className="fas fa-arrow-left" aria-hidden="true"></i>
          Back to Bids
        </Link>
      </div>

      {notice && <div className="order-tracking-notice">{notice}</div>}
      {error && <div className="order-tracking-error-box">{error}</div>}

      <DriverAssignmentPanel tripId={trip.id} />
      {deliveryPolicy && <FeeBreakdown kind="freight" snapshot={payment?.commission_breakdown} />}
      <SettlementSummary settlement={settlement} />

      <div className="order-tracking-grid">
        <div className="order-tracking-card">
          <h2 className="order-tracking-card-title">Order Details</h2>
          <div className="order-tracking-details">
            <div className="detail-row">
              <span className="detail-label">Status</span>
              <span className={`detail-value status-${order.status}`}>{(order.status || '').replace(/_/g, ' ').toUpperCase()}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Pickup</span>
              <span className="detail-value">{order.pickup_location || order.pickup_city}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Dropoff</span>
              <span className="detail-value">{order.dropoff_location || order.dropoff_city}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Goods Type</span>
              <span className="detail-value">{order.goods_type}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Your Bid (Gross)</span>
              <span className="detail-value amount">{formatMoney(order.payment_amount)}</span>
            </div>
            {payment?.transporter_amount && (
              <div className="detail-row">
                <span className="detail-label">Net entitlement before authorized adjustments</span>
                <span className="detail-value amount" style={{ color: '#16a34a' }}>
                  {formatMoney(payment.transporter_amount)}
                </span>
              </div>
            )}
            {payment && (
              <div className="detail-row">
                <span className="detail-label">Payment</span>
                <span className="detail-value">
                  {paymentHeld ? 'Booking escrow locked' : (payment.status || '').toUpperCase()}
                </span>
              </div>
            )}
          </div>
          {chatThreadId && (
            <button onClick={openChat} className="order-tracking-btn order-tracking-btn--ghost">
              <i className="fas fa-comments" aria-hidden="true"></i> Open Chat
            </button>
          )}
        </div>

        <div className="order-tracking-card">
          <h2 className="order-tracking-card-title">Trip Status</h2>
          <div className="order-tracking-timeline">
            <div className={`timeline-item ${trip.trip_started_at ? 'completed' : 'pending'}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-label">Trip Started</div>
                <div className="timeline-time">{trip.trip_started_at ? formatDateTime(trip.trip_started_at) : 'Waiting...'}</div>
              </div>
            </div>
            <div className={`timeline-item ${trip.delivery_completion_requested_at ? 'completed' : 'pending'}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-label">Delivery Completed</div>
                <div className="timeline-time">{trip.delivery_completion_requested_at ? formatDateTime(trip.delivery_completion_requested_at) : 'Pending...'}</div>
              </div>
            </div>
            <div className={`timeline-item ${trip.delivery_confirmed_at ? 'completed' : 'pending'}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-label">Client Confirmed</div>
                <div className="timeline-time">{trip.delivery_confirmed_at ? formatDateTime(trip.delivery_confirmed_at) : 'Awaiting...'}</div>
              </div>
            </div>
          </div>

          {trip.status === 'ready_to_start' && (
            <>
              {paymentHeld && (
                <p className="order-tracking-hint">
                  <i className="fas fa-lock" aria-hidden="true"></i> The full booking fare is held in escrow. Start the trip to begin.
                </p>
              )}
              {payment?.fuel_credit_recovered && <>
                <div className="detail-row"><span className="detail-label">Authorized fuel credit recovered</span><span className="detail-value amount">{formatMoney(payment.fuel_credit_recovered)}</span></div>
                <div className="detail-row"><span className="detail-label">Actual wallet credit</span><span className="detail-value amount">{formatMoney(payment.wallet_credit_amount)}</span></div>
              </>}
              <button
                onClick={startTrip}
                disabled={actionLoading === 'start' || !paymentHeld}
                className="order-tracking-btn order-tracking-btn--primary"
              >
                <i className={`fas ${actionLoading === 'start' ? 'fa-spinner fa-spin' : 'fa-play'}`} aria-hidden="true"></i>
                Start Trip
              </button>
            </>
          )}

          {trip.status === 'in_progress' && (
            <button
              onClick={completeDelivery}
              disabled={actionLoading === 'complete'}
              className="order-tracking-btn order-tracking-btn--primary"
            >
              <i className={`fas ${actionLoading === 'complete' ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
              {deliveryPolicy ? 'Complete Order — request Client OTP' : 'Mark Delivery Completed'}
            </button>
          )}

          {trip.status === 'awaiting_client_confirmation' && (
            <div className="order-tracking-waiting">
              <i className="fas fa-hourglass-half" aria-hidden="true"></i>
              <p>
                {deliveryPolicy
                  ? 'Ask the Client to open this order, click "Inspect cargo & reveal delivery OTP", and share the 8-digit code with you.'
                  : 'Waiting for the client to confirm delivery.'}
              </p>
              <Countdown deadline={trip.confirmation_deadline_at} />
              {deliveryPolicy && (
                <form
                  onSubmit={async (event) => {
                    event.preventDefault()
                    const ok = await postAction(
                      `/api/orders/${orderId}/trips/${trip.id}/verify-delivery-otp`,
                      { otp: deliveryOtp },
                      null,
                      'verify',
                      'Delivery verified. Settlement tranches created.',
                    )
                    if (ok) setDeliveryOtp('')
                  }}
                  className="mt-3 grid gap-2"
                >
                  <label className="grid gap-1 text-sm font-semibold text-slate-800">
                    Enter 8-Digit Client Delivery OTP
                    <input
                      aria-label="Delivery OTP"
                      required
                      autoComplete="off"
                      inputMode="numeric"
                      pattern="[0-9]{8}"
                      maxLength={8}
                      placeholder="e.g. 12345678"
                      value={deliveryOtp}
                      onChange={(event) => setDeliveryOtp(event.target.value.replace(/\D/g, '').slice(0, 8))}
                      className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-lg tracking-widest"
                    />
                  </label>
                  <button type="submit" disabled={!!actionLoading || deliveryOtp.length !== 8} className="order-tracking-btn order-tracking-btn--primary">
                    <i className={`fas ${actionLoading === 'verify' ? 'fa-spinner fa-spin' : 'fa-check-double'} mr-2`} aria-hidden="true"></i>
                    Verify Client OTP &amp; complete delivery
                  </button>
                  <button type="button" disabled={!!actionLoading} onClick={completeDelivery} className="order-tracking-btn order-tracking-btn--ghost">
                    Request a new OTP if expired
                  </button>
                </form>
              )}
            </div>
          )}

          {trip.status === 'completed' && (
            <div className="order-tracking-success">
              <i className="fas fa-check-double" aria-hidden="true"></i>
              <p>{settlement ? 'Delivery verified. Your net earnings follow the settlement tranches shown above.' : 'Delivery confirmed. Your payout has been released.'}</p>
            </div>
          )}

          {(trip.status === 'delivery_disputed' || trip.status === 'admin_review') && (
            <div className="order-tracking-dispute">
              <i className="fas fa-exclamation-circle" aria-hidden="true"></i>
              <p>
                {trip.status === 'admin_review'
                  ? 'The confirmation window lapsed. An admin is reviewing this delivery.'
                  : 'The client reported a problem. An admin will review this delivery.'}
              </p>
              {dispute && dispute.status === 'open' && (
                <div className="order-tracking-statement">
                  <label htmlFor="statement">Add your statement for the admin</label>
                  <textarea
                    id="statement"
                    value={statement}
                    onChange={(e) => setStatement(e.target.value)}
                    placeholder="Explain what happened (proof of delivery, timing, etc.)"
                    rows={3}
                  />
                  <button
                    onClick={submitStatement}
                    disabled={actionLoading === 'statement' || !statement.trim()}
                    className="order-tracking-btn order-tracking-btn--secondary"
                  >
                    <i className={`fas ${actionLoading === 'statement' ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
                    Submit Statement
                  </button>
                  {dispute.transporter_statement && (
                    <p className="order-tracking-hint">Submitted: {dispute.transporter_statement}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {trip.status === 'resolved_client' && (
            <div className="order-tracking-dispute">
              <i className="fas fa-gavel" aria-hidden="true"></i>
              <p>An admin resolved this dispute in the client's favour. The payment was refunded.</p>
            </div>
          )}
        </div>
      </div>

      {order.notes && (
        <div className="order-tracking-card">
          <h2 className="order-tracking-card-title">Special Instructions</h2>
          <p className="order-tracking-notes">{order.notes}</p>
        </div>
      )}
    </div>
  )
}
