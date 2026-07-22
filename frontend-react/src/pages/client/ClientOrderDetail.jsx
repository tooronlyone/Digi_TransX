import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  SectionCard,
  StateMessage,
  formatMoney,
  formatDate,
} from './clientUtils'
import '../../styles/pages/order-detail.css'

const SORTS = [
  { key: 'price', label: 'Lowest price' },
  { key: 'newest', label: 'Newest bid' },
  { key: 'capacity', label: 'Highest weight capacity' },
]

function truckCapacityTons(truck) {
  if (!truck) return null
  const value = truck.payload_max_tons ?? truck.capacity_tons
  return Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null
}

function bedDimensions(truck) {
  if (!truck) return null
  const { bed_length_ft: l, bed_width_ft: w, bed_height_ft: h } = truck
  if (!l && !w && !h) return null
  const part = (v) => (v ? `${v}` : '—')
  return `${part(l)} × ${part(w)} × ${part(h)} ft`
}

function sortBids(bids, sortKey) {
  const copy = [...bids]
  if (sortKey === 'newest') {
    return copy.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  }
  if (sortKey === 'capacity') {
    return copy.sort((a, b) => (truckCapacityTons(b.truck) || 0) - (truckCapacityTons(a.truck) || 0))
  }
  // Default: lowest price first.
  return copy.sort((a, b) => Number(a.bid_price) - Number(b.bid_price))
}

export default function ClientOrderDetail() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [bids, setBids] = useState([])
  const [trip, setTrip] = useState(null)
  const [payment, setPayment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [sortKey, setSortKey] = useState('price')

  async function loadOrder({ silent = false } = {}) {
    if (silent) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/orders/${orderId}`, { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load order.')
      setOrder(json.order || null)
      setBids(json.bids || [])
      setTrip(json.trip || null)
      setPayment(json.payment || null)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load order details.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadOrder()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId])

  const orderOpen = order?.status === 'open'
  const budget = order?.estimated_budget ? Number(order.estimated_budget) : null

  const lowestBidId = useMemo(() => {
    if (!bids.length) return null
    return bids.reduce((best, b) => (Number(b.bid_price) < Number(best.bid_price) ? b : best)).id
  }, [bids])

  const sortedBids = useMemo(() => {
    // Accepted bid always shown first; rejected pushed to the bottom.
    const rank = (b) => (b.status === 'accepted' ? 0 : b.status === 'rejected' ? 2 : 1)
    return sortBids(bids, sortKey).sort((a, b) => rank(a) - rank(b))
  }, [bids, sortKey])

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

  const cheapest = lowestBidId ? bids.find((b) => b.id === lowestBidId) : null
  const avgBid = bids.length
    ? bids.reduce((sum, b) => sum + Number(b.bid_price), 0) / bids.length
    : 0

  return (
    <>
      <PageTitle
        title={`Order #${order.id}`}
        subtitle={`${order.pickup_city} → ${order.dropoff_city}`}
        actions={
          <button
            type="button"
            onClick={() => loadOrder({ silent: true })}
            disabled={refreshing}
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            <i className={`fas ${refreshing ? 'fa-spinner fa-spin' : 'fa-rotate-right'} mr-2`} aria-hidden="true"></i>
            Refresh bids
          </button>
        }
      />

      <div className="order-detail-grid">
        <SectionCard title="Order Details" icon="fa-box">
          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-label">Pickup Location</span>
              <span className="detail-value">{order.pickup_city}{order.pickup_area ? `, ${order.pickup_area}` : ''}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Dropoff Location</span>
              <span className="detail-value">{order.dropoff_city}{order.dropoff_area ? `, ${order.dropoff_area}` : ''}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Date &amp; Time</span>
              <span className="detail-value">{order.pickup_date} at {order.pickup_time}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Goods Type</span>
              <span className="detail-value">{order.goods_type}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Weight</span>
              <span className="detail-value">{order.goods_weight_tons} tons{order.goods_volume_cbm ? ` · ${order.goods_volume_cbm} cbm` : ''}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Budget</span>
              <span className="detail-value">{budget ? formatMoney(budget) : 'Not specified'}</span>
            </div>
            {order.notes && (
              <div className="detail-item col-span-full">
                <span className="detail-label">Special Instructions</span>
                <p className="detail-notes">{order.notes}</p>
              </div>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Bid Summary" icon="fa-chart-bar">
          <div className="summary-box">
            <div className="summary-item">
              <span className="summary-label">Total Bids</span>
              <span className="summary-value">{bids.length}</span>
            </div>
            {cheapest && (
              <div className="summary-item">
                <span className="summary-label">Lowest Bid</span>
                <span className="summary-value amount">{formatMoney(cheapest.bid_price)}</span>
              </div>
            )}
            {bids.length > 0 && (
              <div className="summary-item">
                <span className="summary-label">Avg Bid</span>
                <span className="summary-value amount">{formatMoney(avgBid)}</span>
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      {/* Post-payment status: accepted transporter, held payment, trip state. */}
      {!orderOpen && payment && (
        <SectionCard title="Payment &amp; Trip" icon="fa-shield-halved">
          <div className="payment-summary">
            <div className="payment-summary__row">
              <span className="detail-label">Payment status</span>
              <span className={`odp-pill odp-pill--${payment.status === 'held' ? 'held' : 'muted'}`}>
                {String(payment.status || '').replace(/_/g, ' ')}
              </span>
            </div>
            {trip && (
              <div className="payment-summary__row">
                <span className="detail-label">Trip status</span>
                <span className="odp-pill odp-pill--trip">{String(trip.status || '').replace(/_/g, ' ')}</span>
              </div>
            )}
            <div className="payment-summary__grid">
              <div><span className="detail-label">Transport bid</span><span className="detail-value">{formatMoney(payment.bid_amount)}</span></div>
              <div><span className="detail-label">Wallet funded</span><span className="detail-value">{formatMoney(payment.wallet_funded_amount)}</span></div>
              <div><span className="detail-label">Card funded</span><span className="detail-value">{formatMoney(payment.card_funded_amount)}</span></div>
              {Number(payment.card_funded_amount) > 0 && (
                <div>
                  <span className="detail-label">Card processing fee ({payment.processing_fee_percent}%)</span>
                  <span className="detail-value">{formatMoney(payment.processing_fee_amount)}</span>
                </div>
              )}
              {payment.total_card_charge != null && Number(payment.total_card_charge) > 0 && (
                <div><span className="detail-label">Total card charge</span><span className="detail-value">{formatMoney(payment.total_card_charge)}</span></div>
              )}
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard
        title={`${orderOpen ? 'Compare Bids' : 'Bids'} (${bids.length})`}
        icon="fa-gavel"
        actions={
          bids.length > 1 ? (
            <label className="odp-sort">
              <span className="odp-sort__label">Sort by</span>
              <select value={sortKey} onChange={(e) => setSortKey(e.target.value)} className="odp-sort__select">
                {SORTS.map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </select>
            </label>
          ) : null
        }
      >
        {bids.length === 0 ? (
          <StateMessage type="empty">
            <p>No bids yet. Transporters who own a matching, active truck will bid on your order as they see it.</p>
          </StateMessage>
        ) : (
          <div className="bids-grid">
            {sortedBids.map((bid) => {
              const truck = bid.truck
              const capacity = truckCapacityTons(truck)
              const bed = bedDimensions(truck)
              const isLowest = bid.id === lowestBidId
              const withinBudget = budget != null && Number(bid.bid_price) <= budget
              const isAccepted = bid.status === 'accepted'
              const isRejected = bid.status === 'rejected'
              const canSelect = orderOpen && bid.can_checkout && bid.status === 'pending'
              const cardClass = [
                'bid-card',
                isAccepted ? 'bid-card--accepted' : '',
                isRejected ? 'bid-card--rejected' : '',
                !canSelect && !isAccepted && orderOpen ? 'bid-card--unavailable' : '',
              ].filter(Boolean).join(' ')

              return (
                <div key={bid.id} className={cardClass}>
                  <div className="bid-header">
                    <div className="bid-price">{formatMoney(bid.bid_price)}</div>
                    <div className="bid-badges">
                      {isAccepted && <span className="bid-badge bid-badge--accepted">Accepted</span>}
                      {isRejected && <span className="bid-badge bid-badge--rejected">Not selected</span>}
                      {isLowest && !isRejected && <span className="bid-badge">Lowest Bid</span>}
                      {withinBudget && !isRejected && <span className="bid-badge bid-badge--budget">Within Budget</span>}
                    </div>
                  </div>

                  <div className="bid-transporter">
                    <div className="bid-avatar" aria-hidden="true">
                      <i className="fas fa-user-tie"></i>
                    </div>
                    <div className="bid-transporter__meta">
                      <span className="bid-transporter__name">
                        {bid.transporter?.company_name || bid.transporter?.display_name || 'Transporter'}
                      </span>
                      {bid.transporter?.company_name && bid.transporter?.display_name && (
                        <span className="bid-transporter__sub">{bid.transporter.display_name}</span>
                      )}
                      {typeof bid.transporter?.completed_trips === 'number' && bid.transporter.completed_trips > 0 && (
                        <span className="bid-transporter__trips">
                          <i className="fas fa-circle-check" aria-hidden="true"></i>
                          {bid.transporter.completed_trips} completed trip{bid.transporter.completed_trips === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="bid-truck">
                    <div className="bid-truck__photo">
                      {truck?.photo_url ? (
                        <img src={truck.photo_url} alt={truck?.truck_number || 'Truck'} loading="lazy" />
                      ) : (
                        <div className="bid-truck__fallback" aria-hidden="true">
                          <i className="fas fa-truck"></i>
                        </div>
                      )}
                    </div>
                    <div className="bid-truck__specs">
                      <div className="bid-truck__title">
                        {truck?.type_name || 'Truck'}
                        {truck?.truck_number ? <span className="bid-truck__number"> · {truck.truck_number}</span> : null}
                      </div>
                      {(truck?.company || truck?.model) && (
                        <div className="bid-truck__line">{[truck.company, truck.model].filter(Boolean).join(' ')}</div>
                      )}
                      <div className="bid-truck__chips">
                        {capacity != null && <span className="bid-chip"><i className="fas fa-weight-hanging" aria-hidden="true"></i> {capacity} t</span>}
                        {truck?.volume_max_cbm ? <span className="bid-chip"><i className="fas fa-cube" aria-hidden="true"></i> {truck.volume_max_cbm} cbm</span> : null}
                        {bed && <span className="bid-chip"><i className="fas fa-ruler-combined" aria-hidden="true"></i> {bed}</span>}
                      </div>
                    </div>
                  </div>

                  <div className="bid-details">
                    <div className="bid-detail">
                      <span className="bid-label">Submitted</span>
                      <span className="bid-value">{formatDate(bid.created_at)}</span>
                    </div>
                  </div>

                  {bid.message && (
                    <div className="bid-message">
                      <i className="fas fa-quote-left" aria-hidden="true"></i>
                      <p>{bid.message}</p>
                    </div>
                  )}

                  {orderOpen && bid.status === 'pending' && !bid.can_checkout && bid.unavailable_reason && (
                    <div className="bid-warning">
                      <i className="fas fa-triangle-exclamation" aria-hidden="true"></i>
                      <span>{bid.unavailable_reason}</span>
                    </div>
                  )}

                  {orderOpen && (
                    <button
                      type="button"
                      onClick={() => navigate(`/client/order/${order.id}/bid/${bid.id}/checkout`)}
                      disabled={!canSelect}
                      className="bid-accept-btn"
                    >
                      <i className="fas fa-circle-check" aria-hidden="true"></i>
                      {canSelect ? 'Select & Continue to Payment' : 'Unavailable'}
                    </button>
                  )}
                </div>
              )
            })}
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
