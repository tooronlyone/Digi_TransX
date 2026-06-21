import { useEffect, useState } from 'react'
import {
  formatDateTime,
  formatStatus,
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  apiSend,
  formatMoney,
} from './clientUtils'

const FILTERS = ['all', 'open', 'accepted', 'completed', 'cancelled']

export default function MyOrders() {
  const [orders, setOrders] = useState([])
  const [selectedOrder, setSelectedOrder] = useState(null)
  const [bids, setBids] = useState([])
  const [cancellations, setCancellations] = useState({})
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [loadingBids, setLoadingBids] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [proposalInputs, setProposalInputs] = useState({})
  const [error, setError] = useState('')
  const [bidsError, setBidsError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadOrders(nextFilter = filter) {
    setLoading(true)
    setError('')
    try {
      const suffix = nextFilter && nextFilter !== 'all' ? `?status=${encodeURIComponent(nextFilter)}` : ''
      const json = await apiGet(`/api/orders/mine${suffix}`)
      setOrders(json.orders || [])
    } catch (loadError) {
      setError(loadError.message || 'Failed to load orders.')
    } finally {
      setLoading(false)
    }
  }

  async function loadCancellation(orderId, { silent = false } = {}) {
    try {
      const json = await apiGet(`/api/orders/${orderId}/cancellation`)
      setCancellations((current) => ({ ...current, [orderId]: json.cancellation }))
      setProposalInputs((current) => ({
        ...current,
        [orderId]: json.cancellation?.proposed_percent != null ? String(json.cancellation.proposed_percent) : (current[orderId] || '10'),
      }))
      return json.cancellation
    } catch (loadError) {
      if (!silent) setError(loadError.message || 'Failed to load cancellation.')
      return null
    }
  }

  useEffect(() => {
    loadOrders(filter)
  }, [filter])

  useEffect(() => {
    orders
      .filter((order) => order.status === 'cancelled')
      .forEach((order) => {
        if (!cancellations[order.id]) {
          loadCancellation(order.id, { silent: true })
        }
      })
  }, [orders])

  async function openBids(order) {
    setSelectedOrder(order)
    setLoadingBids(true)
    setBidsError('')
    try {
      const json = await apiGet(`/api/orders/${order.id}/bids`)
      setBids(json.bids || [])
    } catch (loadError) {
      setBidsError(loadError.message || 'Failed to load bids.')
      setBids([])
    } finally {
      setLoadingBids(false)
    }
  }

  async function acceptBid(order, bid) {
    const confirmed = window.confirm(`Accept this bid for ${formatMoney(bid.bid_price)}? Other bids will be rejected.`)
    if (!confirmed) return

    const actionKey = `${order.id}:${bid.id}`
    setActionLoading(actionKey)
    try {
      await apiSend(`/api/orders/${order.id}/bids/${bid.id}/accept`)
      await Promise.all([loadOrders(filter), openBids({ ...order, status: 'accepted' })])
    } catch (acceptError) {
      setBidsError(acceptError.message || 'Unable to accept bid.')
    } finally {
      setActionLoading('')
    }
  }

  async function cancelOrder(order) {
    const confirmed = window.confirm('Are you sure? Cancellation penalty may apply.')
    if (!confirmed) return

    setActionLoading(`cancel:${order.id}`)
    setError('')
    setNotice('')
    try {
      const json = await apiSend(`/api/orders/${order.id}/cancel`)
      setNotice(json.message || 'Order cancelled.')
      await Promise.all([loadOrders(filter), loadCancellation(order.id, { silent: true })])
    } catch (cancelError) {
      setError(cancelError.message || 'Unable to cancel order.')
    } finally {
      setActionLoading('')
    }
  }

  async function sendProposal(orderId) {
    const raw = proposalInputs[orderId]
    setActionLoading(`propose:${orderId}`)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/orders/${orderId}/cancellation/propose`, { percent: Number(raw) })
      setNotice('Proposal sent.')
      await loadCancellation(orderId)
    } catch (proposalError) {
      setError(proposalError.message || 'Unable to send proposal.')
    } finally {
      setActionLoading('')
    }
  }

  async function acceptProposal(orderId) {
    setActionLoading(`accept:${orderId}`)
    setError('')
    setNotice('')
    try {
      const json = await apiSend(`/api/orders/${orderId}/cancellation/accept`)
      setNotice(json.message || 'Cancellation finalized.')
      await Promise.all([loadOrders(filter), loadCancellation(orderId)])
    } catch (acceptError) {
      setError(acceptError.message || 'Unable to accept proposal.')
    } finally {
      setActionLoading('')
    }
  }

  function renderCancellationPanel(order) {
    const cancellation = cancellations[order.id]
    if (!cancellation) return null

    const canAccept = cancellation.status === 'pending'
      && cancellation.proposed_percent != null
      && cancellation.proposed_by_user_id !== order.client_user_id

    return (
      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-amber-900">Cancellation status: {formatStatus(cancellation.status)}</div>
            <div className="mt-1 text-sm text-amber-800">
              {cancellation.penalty_type === 'fixed'
                ? `Penalty applied: ${cancellation.penalty_percent}% (${formatMoney(cancellation.penalty_amount)})`
                : `Negotiation required between ${cancellation.cancelled_by} and transporter.`}
            </div>
          </div>
          {cancellation.negotiation_deadline && (
            <div className="text-xs text-amber-700">Deadline: {formatDateTime(cancellation.negotiation_deadline)}</div>
          )}
        </div>
        {cancellation.proposed_percent != null && (
          <div className="mt-3 text-sm text-amber-900">
            Proposed: {cancellation.proposed_percent}% {cancellation.proposed_by_user_id === order.client_user_id ? '(you)' : '(transporter)'}
          </div>
        )}
        {cancellation.status === 'pending' && (
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              type="number"
              min="10"
              max="25"
              step="0.5"
              value={proposalInputs[order.id] || '10'}
              onChange={(event) => setProposalInputs((current) => ({ ...current, [order.id]: event.target.value }))}
              className="min-h-10 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-amber-500"
            />
            <PrimaryButton type="button" onClick={() => sendProposal(order.id)} disabled={actionLoading === `propose:${order.id}`}>
              <i className={`fas ${actionLoading === `propose:${order.id}` ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
              Send proposal
            </PrimaryButton>
            {canAccept && (
              <SecondaryButton type="button" onClick={() => acceptProposal(order.id)} disabled={actionLoading === `accept:${order.id}`}>
                <i className={`fas ${actionLoading === `accept:${order.id}` ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
                Accept this offer
              </SecondaryButton>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <PageTitle title="My Orders" subtitle="Review posted orders, compare bids, and accept the best transporter offer." />

      <SectionCard
        title="Orders"
        icon="fa-receipt"
        actions={
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((item) => (
              item === filter ? (
                <PrimaryButton key={item} type="button" onClick={() => setFilter(item)}>{item === 'all' ? 'All' : item}</PrimaryButton>
              ) : (
                <SecondaryButton key={item} type="button" onClick={() => setFilter(item)}>{item === 'all' ? 'All' : item}</SecondaryButton>
              )
            ))}
          </div>
        }
      >
        {loading && <StateMessage type="loading">Loading your orders...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {notice && <StateMessage type="success">{notice}</StateMessage>}
        {!loading && !error && orders.length === 0 && <StateMessage type="empty">No orders found for this filter.</StateMessage>}
        {!loading && !error && orders.length > 0 && (
          <div className="grid gap-4 xl:grid-cols-2">
            {orders.map((order) => (
              <article key={order.id} className="rounded-xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold text-slate-900">{order.pickup_city} to {order.dropoff_city}</h3>
                    <p className="mt-1 text-sm text-slate-500">
                      {order.pickup_date} at {order.pickup_time}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </div>
                <div className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                  <div><span className="font-semibold text-slate-800">Truck:</span> {order.required_truck_type_name}</div>
                  <div><span className="font-semibold text-slate-800">Bids:</span> {order.bid_count}</div>
                  <div><span className="font-semibold text-slate-800">Goods:</span> {order.goods_type}</div>
                  <div><span className="font-semibold text-slate-800">Weight:</span> {order.goods_weight_tons} tons</div>
                  <div><span className="font-semibold text-slate-800">Trip stage:</span> {formatStatus(order.trip_stage)}</div>
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <PrimaryButton type="button" onClick={() => openBids(order)}>
                    <i className="fas fa-gavel" aria-hidden="true"></i>
                    View Bids
                  </PrimaryButton>
                  {(order.status === 'accepted' || order.status === 'in_progress') && (
                    <SecondaryButton type="button" onClick={() => cancelOrder(order)} disabled={actionLoading === `cancel:${order.id}`}>
                      <i className={`fas ${actionLoading === `cancel:${order.id}` ? 'fa-spinner fa-spin' : 'fa-ban'}`} aria-hidden="true"></i>
                      Cancel Order
                    </SecondaryButton>
                  )}
                </div>
                {renderCancellationPanel(order)}
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      {selectedOrder && (
        <SectionCard
          title={`Bids for Order #${selectedOrder.id}`}
          icon="fa-users"
          actions={
            <SecondaryButton type="button" onClick={() => setSelectedOrder(null)}>
              Close
            </SecondaryButton>
          }
        >
          {loadingBids && <StateMessage type="loading">Loading bids...</StateMessage>}
          {bidsError && <StateMessage type="error">{bidsError}</StateMessage>}
          {!loadingBids && !bidsError && bids.length === 0 && <StateMessage type="empty">No bids received yet.</StateMessage>}
          {!loadingBids && !bidsError && bids.length > 0 && (
            <div className="grid gap-4">
              {bids.map((bid) => (
                <article key={bid.id} className="rounded-xl border border-slate-200 bg-white p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-bold text-slate-900">{bid.transporter_name}</h3>
                      <p className="mt-1 text-sm text-slate-500">Truck {bid.truck_number} • {bid.truck_type}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-bold text-slate-900">{formatMoney(bid.bid_price)}</div>
                      <div className="text-xs text-slate-500">Rating: {bid.transporter_rating ?? 0}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <StatusBadge status={bid.status} />
                    <span className="text-sm text-slate-500">{bid.message || 'No message provided.'}</span>
                  </div>
                  {selectedOrder.status === 'open' && bid.status === 'pending' && (
                    <div className="mt-4">
                      <PrimaryButton type="button" onClick={() => acceptBid(selectedOrder, bid)} disabled={actionLoading === `${selectedOrder.id}:${bid.id}`}>
                        <i className={`fas ${actionLoading === `${selectedOrder.id}:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
                        Accept bid
                      </PrimaryButton>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </SectionCard>
      )}
    </>
  )
}
