import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getCsrfToken } from '../client/clientUtils'
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

export default function OrderTracking() {
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState('')
  const [notice, setNotice] = useState('')

  async function loadOrder() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/orders/${orderId}`, { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load order.')
      setOrder(json.order || null)
      setTrip(json.trip || null)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load order details.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrder()
  }, [orderId])

  async function markTripCompleted() {
    const confirmed = window.confirm('Mark delivery as completed? Client will receive verification request.')
    if (!confirmed) return

    setActionLoading('complete')
    setError('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${orderId}/trips/${trip.id}/mark-completed`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to mark trip completed.')
      setNotice('Trip marked as completed. Awaiting client verification.')
      await loadOrder()
    } catch (completeError) {
      setError(completeError.message || 'Unable to complete trip.')
    } finally {
      setActionLoading('')
    }
  }

  if (loading) {
    return (
      <div className="order-tracking-page">
        <div className="order-tracking-loading">Loading order details...</div>
      </div>
    )
  }

  if (error) {
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

      <div className="order-tracking-grid">
        {/* Order Details Card */}
        <div className="order-tracking-card">
          <h2 className="order-tracking-card-title">Order Details</h2>
          <div className="order-tracking-details">
            <div className="detail-row">
              <span className="detail-label">Status</span>
              <span className={`detail-value status-${order.status}`}>{order.status.toUpperCase()}</span>
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
              <span className="detail-label">Date & Time</span>
              <span className="detail-value">{order.pickup_date} at {order.pickup_time}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Goods Type</span>
              <span className="detail-value">{order.goods_type}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Weight</span>
              <span className="detail-value">{order.goods_weight_tons} tons</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Your Bid</span>
              <span className="detail-value amount">{formatMoney(order.payment_amount)}</span>
            </div>
          </div>
        </div>

        {/* Trip Status Card */}
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
            <div className={`timeline-item ${trip.trip_completed_at ? 'completed' : 'pending'}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-label">Delivery Completed</div>
                <div className="timeline-time">{trip.trip_completed_at ? formatDateTime(trip.trip_completed_at) : 'Pending...'}</div>
              </div>
            </div>
            <div className={`timeline-item ${trip.delivery_confirmed_at ? 'completed' : 'pending'}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-label">Client Verified</div>
                <div className="timeline-time">{trip.delivery_confirmed_at ? formatDateTime(trip.delivery_confirmed_at) : 'Awaiting...'}</div>
              </div>
            </div>
          </div>

          {trip.status === 'in_progress' && !trip.trip_completed_at && (
            <button
              onClick={markTripCompleted}
              disabled={actionLoading === 'complete'}
              className="order-tracking-btn order-tracking-btn--primary"
            >
              <i className={`fas ${actionLoading === 'complete' ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
              Mark Delivery Complete
            </button>
          )}

          {trip.status === 'delivery_claimed' && (
            <div className="order-tracking-waiting">
              <i className="fas fa-hourglass-end" aria-hidden="true"></i>
              <p>Waiting for client to verify delivery...</p>
            </div>
          )}

          {trip.status === 'completed' && (
            <div className="order-tracking-success">
              <i className="fas fa-check-double" aria-hidden="true"></i>
              <p>Delivery verified! Payment will be released shortly.</p>
            </div>
          )}

          {trip.status === 'dispute_pending' && (
            <div className="order-tracking-dispute">
              <i className="fas fa-exclamation-circle" aria-hidden="true"></i>
              <p>Delivery verification under dispute. Admin review in progress.</p>
            </div>
          )}
        </div>
      </div>

      {/* Notes Section */}
      {order.notes && (
        <div className="order-tracking-card">
          <h2 className="order-tracking-card-title">Special Instructions</h2>
          <p className="order-tracking-notes">{order.notes}</p>
        </div>
      )}
    </div>
  )
}
