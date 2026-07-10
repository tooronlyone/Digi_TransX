import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  SectionCard,
  StateMessage,
  formatMoney,
  getCsrfToken,
} from './clientUtils'
import '../../styles/pages/order-detail.css'

function formatDate(dateString) {
  if (!dateString) return '-'
  try {
    return new Date(dateString).toLocaleDateString('en-PK')
  } catch {
    return dateString
  }
}

export default function ClientOrderDetail() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [bids, setBids] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBidId, setSelectedBidId] = useState(null)
  const [accepting, setAccepting] = useState(false)
  const [acceptError, setAcceptError] = useState('')

  async function loadOrder() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/orders/${orderId}`, { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load order.')
      setOrder(json.order || null)
      setBids(json.bids || [])
    } catch (loadError) {
      setError(loadError.message || 'Unable to load order details.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrder()
  }, [orderId])

  async function acceptBid(bidId) {
    const confirmed = window.confirm('Accept this bid? You will need to confirm payment afterwards.')
    if (!confirmed) return

    setAccepting(true)
    setAcceptError('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${orderId}/accept-bid/${bidId}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to accept bid.')
      setOrder(json.order)
      navigate('/client/orders')
    } catch (acceptBidError) {
      setAcceptError(acceptBidError.message || 'Unable to accept bid.')
    } finally {
      setAccepting(false)
    }
  }

  if (loading) {
    return (
      <div className="order-detail-page">
        <StateMessage type="loading">Loading order details...</StateMessage>
      </div>
    )
  }

  if (error) {
    return (
      <div className="order-detail-page">
        <StateMessage type="error">{error}</StateMessage>
        <Link to="/client/orders" className="mt-4 inline-flex items-center gap-2 text-blue-600 hover:text-blue-700">
          <i className="fas fa-arrow-left"></i>
          Back to Orders
        </Link>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="order-detail-page">
        <StateMessage type="error">Order not found.</StateMessage>
        <Link to="/client/orders" className="mt-4 inline-flex items-center gap-2 text-blue-600 hover:text-blue-700">
          <i className="fas fa-arrow-left"></i>
          Back to Orders
        </Link>
      </div>
    )
  }

  const sortedBids = [...bids].sort((a, b) => a.bid_price - b.bid_price)
  const cheapestBid = sortedBids[0]

  return (
    <>
      <PageTitle
        title={`Order #${order.id}`}
        subtitle={`${order.pickup_city} → ${order.dropoff_city}`}
      />

      <div className="order-detail-grid">
        {/* Order Details */}
        <SectionCard title="Order Details" icon="fa-box">
          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-label">Pickup Location</span>
              <span className="detail-value">{order.pickup_city}, {order.pickup_area}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Dropoff Location</span>
              <span className="detail-value">{order.dropoff_city}, {order.dropoff_area}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Date & Time</span>
              <span className="detail-value">{order.pickup_date} at {order.pickup_time}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Goods Type</span>
              <span className="detail-value">{order.goods_type}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Weight</span>
              <span className="detail-value">{order.goods_weight_tons} tons</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Budget</span>
              <span className="detail-value">{order.estimated_budget ? formatMoney(order.estimated_budget) : 'Not specified'}</span>
            </div>
            {order.notes && (
              <div className="detail-item col-span-full">
                <span className="detail-label">Special Instructions</span>
                <p className="detail-notes">{order.notes}</p>
              </div>
            )}
          </div>
        </SectionCard>

        {/* Summary Card */}
        <SectionCard title="Bid Summary" icon="fa-chart-bar">
          <div className="summary-box">
            <div className="summary-item">
              <span className="summary-label">Total Bids</span>
              <span className="summary-value">{bids.length}</span>
            </div>
            {cheapestBid && (
              <div className="summary-item">
                <span className="summary-label">Lowest Bid</span>
                <span className="summary-value amount">{formatMoney(cheapestBid.bid_price)}</span>
              </div>
            )}
            {bids.length > 0 && (
              <div className="summary-item">
                <span className="summary-label">Avg Bid</span>
                <span className="summary-value amount">
                  {formatMoney(bids.reduce((sum, b) => sum + b.bid_price, 0) / bids.length)}
                </span>
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      {/* Bids Section */}
      <SectionCard title={`Available Bids (${bids.length})`} icon="fa-gavel">
        {acceptError && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {acceptError}
          </div>
        )}

        {bids.length === 0 ? (
          <StateMessage type="empty">
            <p>No bids yet. Transporters will bid on your order as they see it.</p>
          </StateMessage>
        ) : (
          <div className="bids-grid">
            {sortedBids.map((bid) => (
              <div key={bid.id} className="bid-card">
                <div className="bid-header">
                  <div className="bid-price">{formatMoney(bid.bid_price)}</div>
                  {bid === cheapestBid && <span className="bid-badge">Lowest</span>}
                </div>

                <div className="bid-details">
                  <div className="bid-detail">
                    <span className="bid-label">Transporter</span>
                    <span className="bid-value">Transporter #{bid.transporter_user_id}</span>
                  </div>
                  <div className="bid-detail">
                    <span className="bid-label">Truck</span>
                    <span className="bid-value">Vehicle #{bid.truck_id}</span>
                  </div>
                  <div className="bid-detail">
                    <span className="bid-label">Posted</span>
                    <span className="bid-value">{formatDate(bid.created_at)}</span>
                  </div>
                </div>

                {bid.message && (
                  <div className="bid-message">
                    <i className="fas fa-quote-left" aria-hidden="true"></i>
                    <p>{bid.message}</p>
                  </div>
                )}

                <button
                  onClick={() => acceptBid(bid.id)}
                  disabled={accepting || order.status !== 'open'}
                  className="bid-accept-btn"
                >
                  <i className={`fas ${accepting ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
                  {accepting ? 'Processing...' : 'Accept This Bid'}
                </button>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <div className="flex gap-2 justify-center mt-6">
        <Link to="/client/orders" className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <i className="fas fa-arrow-left mr-2" aria-hidden="true"></i>
          Back to Orders
        </Link>
      </div>
    </>
  )
}
