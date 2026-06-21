import { useEffect, useState } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { apiGet, apiSend, formatDateTime, formatStatus, getCsrfToken } from '../client/clientUtils'

function statusClasses(status) {
  if (status === 'accepted') return 'bg-emerald-50 text-emerald-700'
  if (status === 'pending') return 'bg-amber-50 text-amber-700'
  if (status === 'not_selected') return 'bg-slate-100 text-slate-700'
  if (status === 'withdrawn') return 'bg-red-50 text-red-700'
  return 'bg-slate-100 text-slate-700'
}

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return 'PKR 0'
  return `PKR ${amount.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

export default function MyBids() {
  const [bids, setBids] = useState([])
  const [cancellations, setCancellations] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState('')
  const [notice, setNotice] = useState('')
  const [proposalInputs, setProposalInputs] = useState({})

  async function loadBids() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/orders/my-bids', { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load bids.')
      setBids(json.bids || [])
    } catch (loadError) {
      setError(loadError.message || 'Unable to load bids.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBids()
  }, [])

  useEffect(() => {
    bids
      .filter((bid) => bid.order.status === 'cancelled')
      .forEach((bid) => {
        if (!cancellations[bid.order.id]) {
          loadCancellation(bid.order.id)
        }
      })
  }, [bids])

  async function withdrawBid(bid) {
    const confirmed = window.confirm('Withdraw this pending bid?')
    if (!confirmed) return

    setActionLoading(String(bid.id))
    setError('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${bid.order.id}/bids/${bid.id}/withdraw`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to withdraw bid.')
      await loadBids()
    } catch (withdrawError) {
      setError(withdrawError.message || 'Unable to withdraw bid.')
    } finally {
      setActionLoading('')
    }
  }

  async function loadCancellation(orderId) {
    try {
      const json = await apiGet(`/api/orders/${orderId}/cancellation`)
      setCancellations((current) => ({ ...current, [orderId]: json.cancellation }))
      setProposalInputs((current) => ({
        ...current,
        [orderId]: json.cancellation?.proposed_percent != null ? String(json.cancellation.proposed_percent) : (current[orderId] || '10'),
      }))
    } catch (_) {
      // Silent by design: not every cancelled order will necessarily expose a record to this screen immediately.
    }
  }

  async function startTrip(bid) {
    setActionLoading(`start:${bid.id}`)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/orders/${bid.order.id}/trip/start`)
      setNotice('Trip started.')
      await loadBids()
    } catch (startError) {
      setError(startError.message || 'Unable to start trip.')
    } finally {
      setActionLoading('')
    }
  }

  async function updateStage(bid, stage) {
    setActionLoading(`stage:${bid.id}`)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/orders/${bid.order.id}/trip/stage`, { stage }, 'PUT')
      setNotice('Trip stage updated.')
      await loadBids()
    } catch (stageError) {
      setError(stageError.message || 'Unable to update trip stage.')
    } finally {
      setActionLoading('')
    }
  }

  async function cancelOrder(bid) {
    const confirmed = window.confirm('Are you sure? Cancellation penalty may apply.')
    if (!confirmed) return

    setActionLoading(`cancel:${bid.id}`)
    setError('')
    setNotice('')
    try {
      const json = await apiSend(`/api/orders/${bid.order.id}/cancel`)
      setNotice(json.message || 'Order cancelled.')
      await Promise.all([loadBids(), loadCancellation(bid.order.id)])
    } catch (cancelError) {
      setError(cancelError.message || 'Unable to cancel order.')
    } finally {
      setActionLoading('')
    }
  }

  async function sendProposal(orderId) {
    setActionLoading(`propose:${orderId}`)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/orders/${orderId}/cancellation/propose`, { percent: Number(proposalInputs[orderId]) })
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
      await Promise.all([loadBids(), loadCancellation(orderId)])
    } catch (acceptError) {
      setError(acceptError.message || 'Unable to accept proposal.')
    } finally {
      setActionLoading('')
    }
  }

  function renderCancellationPanel(bid) {
    const cancellation = cancellations[bid.order.id]
    if (!cancellation) return null

    const canAccept = cancellation.status === 'pending'
      && cancellation.proposed_percent != null
      && cancellation.proposed_by_user_id !== bid.transporter_user_id

    return (
      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-amber-900">Cancellation status: {formatStatus(cancellation.status)}</div>
            <div className="mt-1 text-sm text-amber-800">
              {cancellation.penalty_type === 'fixed'
                ? `Penalty applied: ${cancellation.penalty_percent}% (${formatMoney(cancellation.penalty_amount)})`
                : `Negotiation required. Proposed amount can stay between 10% and 25%.`}
            </div>
          </div>
          {cancellation.negotiation_deadline && (
            <div className="text-xs text-amber-700">Deadline: {formatDateTime(cancellation.negotiation_deadline)}</div>
          )}
        </div>
        {cancellation.proposed_percent != null && (
          <div className="mt-3 text-sm text-amber-900">
            Proposed: {cancellation.proposed_percent}% {cancellation.proposed_by_user_id === bid.transporter_user_id ? '(you)' : '(client)'}
          </div>
        )}
        {cancellation.status === 'pending' && (
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              type="number"
              min="10"
              max="25"
              step="0.5"
              value={proposalInputs[bid.order.id] || '10'}
              onChange={(event) => setProposalInputs((current) => ({ ...current, [bid.order.id]: event.target.value }))}
              className="min-h-10 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-amber-500"
            />
            <button type="button" onClick={() => sendProposal(bid.order.id)} disabled={actionLoading === `propose:${bid.order.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
              <i className={`fas ${actionLoading === `propose:${bid.order.id}` ? 'fa-spinner fa-spin' : 'fa-paper-plane'} mr-2`} aria-hidden="true"></i>
              Send Proposal
            </button>
            {canAccept && (
              <button type="button" onClick={() => acceptProposal(bid.order.id)} disabled={actionLoading === `accept:${bid.order.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60">
                <i className={`fas ${actionLoading === `accept:${bid.order.id}` ? 'fa-spinner fa-spin' : 'fa-check-circle'} mr-2`} aria-hidden="true"></i>
                Accept This Offer
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <TransporterLayout>
      <div className="space-y-6">
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">My Bids</h1>
          <p className="mt-2 text-sm text-slate-500">Track every proposal you have placed and withdraw pending bids when needed.</p>
        </div>

        {loading && <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">Loading bids...</div>}
        {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {notice && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}
        {!loading && !error && bids.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
            You have not placed any bids yet.
          </div>
        )}

        {!loading && !error && bids.length > 0 && (
          <div className="grid gap-4">
            {bids.map((bid) => (
              <article key={bid.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">{bid.order.pickup_city} to {bid.order.dropoff_city}</h2>
                    <p className="mt-1 text-sm text-slate-500">{bid.order.pickup_date} at {bid.order.pickup_time}</p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${statusClasses(bid.status)}`}>
                    {bid.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-4">
                  <div><span className="font-semibold text-slate-800">Bid:</span> {formatMoney(bid.bid_price)}</div>
                  <div><span className="font-semibold text-slate-800">Truck:</span> {bid.truck_number}</div>
                  <div><span className="font-semibold text-slate-800">Order:</span> {bid.order.status}</div>
                  <div><span className="font-semibold text-slate-800">Goods:</span> {bid.order.goods_type}</div>
                  <div><span className="font-semibold text-slate-800">Trip Stage:</span> {formatStatus(bid.order.trip_stage)}</div>
                </div>
                {bid.message && <p className="mt-3 text-sm text-slate-500">{bid.message}</p>}
                {bid.status === 'pending' && (
                  <div className="mt-4">
                    <button type="button" onClick={() => withdrawBid(bid)} disabled={actionLoading === String(bid.id)} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60">
                      <i className={`fas ${actionLoading === String(bid.id) ? 'fa-spinner fa-spin' : 'fa-ban'} mr-2`} aria-hidden="true"></i>
                      Withdraw
                    </button>
                  </div>
                )}
                {bid.status === 'accepted' && (
                  <div className="mt-4 flex flex-wrap gap-3">
                    {bid.order.status === 'accepted' && bid.order.trip_stage === 'not_started' && (
                      <button type="button" onClick={() => startTrip(bid)} disabled={actionLoading === `start:${bid.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60">
                        <i className={`fas ${actionLoading === `start:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-truck-fast'} mr-2`} aria-hidden="true"></i>
                        Trip Started
                      </button>
                    )}
                    {bid.order.status === 'in_progress' && bid.order.trip_stage === 'in_city' && (
                      <button type="button" onClick={() => updateStage(bid, 'left_city')} disabled={actionLoading === `stage:${bid.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60">
                        <i className={`fas ${actionLoading === `stage:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-location-arrow'} mr-2`} aria-hidden="true"></i>
                        Mark Left City
                      </button>
                    )}
                    {bid.order.status === 'in_progress' && bid.order.trip_stage === 'left_city' && (
                      <button type="button" onClick={() => updateStage(bid, 'loaded')} disabled={actionLoading === `stage:${bid.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60">
                        <i className={`fas ${actionLoading === `stage:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-box'} mr-2`} aria-hidden="true"></i>
                        Mark Loaded
                      </button>
                    )}
                    {(bid.order.status === 'accepted' || bid.order.status === 'in_progress') && (
                      <button type="button" onClick={() => cancelOrder(bid)} disabled={actionLoading === `cancel:${bid.id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60">
                        <i className={`fas ${actionLoading === `cancel:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-ban'} mr-2`} aria-hidden="true"></i>
                        Cancel Order
                      </button>
                    )}
                  </div>
                )}
                {renderCancellationPanel(bid)}
              </article>
            ))}
          </div>
        )}
      </div>
    </TransporterLayout>
  )
}
