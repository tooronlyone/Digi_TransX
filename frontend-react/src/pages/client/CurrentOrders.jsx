import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  apiSend,
  formatDateTime,
  formatMoney,
  isActiveStatus,
} from './clientUtils'

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <h3 className="text-lg font-bold text-slate-900">{title}</h3>
          <SecondaryButton type="button" onClick={onClose}>Close</SecondaryButton>
        </div>
        {children}
      </div>
    </div>
  )
}

export default function CurrentOrders() {
  const [searchParams] = useSearchParams()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modal, setModal] = useState(null)
  const [busyId, setBusyId] = useState('')

  async function loadOrders() {
    setLoading(true)
    setError('')
    try {
      const json = await apiGet('/api/client/orders?limit=200')
      const rows = json.orders || json.data?.orders || []
      setOrders(rows.filter((order) => isActiveStatus(order.status)))
    } catch (err) {
      setError(err.message || 'Failed to load current orders.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  useEffect(() => {
    const orderId = searchParams.get('orderId')
    if (!orderId || !orders.length) return
    const order = orders.find((item) => String(item.order_id || item.id) === orderId)
    if (order) setModal({ type: 'details', order })
  }, [orders, searchParams])

  async function trackOrder(order) {
    const orderId = order.order_id || order.id
    setBusyId(`${orderId}:track`)
    try {
      const json = await apiGet(`/api/client/orders/${encodeURIComponent(orderId)}/tracking`)
      const history = json.tracking_history || json.data?.tracking_history || []
      setModal({ type: 'tracking', order, history })
    } catch (err) {
      setModal({ type: 'message', title: 'Tracking Error', message: err.message || 'Failed to fetch tracking updates.' })
    } finally {
      setBusyId('')
    }
  }

  async function cancelOrder(order) {
    const orderId = order.order_id || order.id
    if (!window.confirm('Are you sure you want to cancel this order?')) return
    setBusyId(`${orderId}:cancel`)
    try {
      await apiSend(`/api/client/orders/${encodeURIComponent(orderId)}/cancel`, { reason: 'Cancelled by client' })
      await loadOrders()
      setModal({ type: 'message', title: 'Order Cancelled', message: `Order ${orderId} was cancelled successfully.` })
    } catch (err) {
      setModal({ type: 'message', title: 'Cancel Error', message: err.message || 'Failed to cancel order.' })
    } finally {
      setBusyId('')
    }
  }

  return (
    <>
      <PageTitle
        title="Current Orders"
        subtitle="Track and manage your active shipments in real time."
        actions={
          <>
            <Link to="/client/place-order" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              <i className="fas fa-plus" aria-hidden="true"></i> Place Order
            </Link>
            <PrimaryButton type="button" onClick={loadOrders} disabled={loading}>
              <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
              Refresh
            </PrimaryButton>
          </>
        }
      />

      <SectionCard title="Active Orders" icon="fa-truck">
        {loading && <StateMessage type="loading">Loading current orders...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {!loading && !error && orders.length === 0 && (
          <StateMessage type="empty">No active orders found.</StateMessage>
        )}
        {!loading && !error && orders.length > 0 && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {orders.map((order) => {
              const orderId = order.order_id || order.id
              const pending = String(order.status || '').toLowerCase() === 'pending'
              return (
                <article key={orderId} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="text-sm font-bold text-slate-900">
                        <i className="fas fa-receipt mr-2 text-blue-600" aria-hidden="true"></i>
                        {orderId}
                      </div>
                      <div className="mt-2 text-sm text-slate-600">
                        {order.pickup_location || '-'} <i className="fas fa-arrow-right mx-2 text-slate-400" aria-hidden="true"></i> {order.drop_location || '-'}
                      </div>
                    </div>
                    <StatusBadge status={order.status} />
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                    <div className="rounded-lg bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-500">Order Type</div>
                      <div className="mt-1 capitalize text-slate-900">{order.order_type || '-'}</div>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-500">Total Fare</div>
                      <div className="mt-1 text-slate-900">{formatMoney(order.total_fare || order.base_fare || 0)}</div>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-500">Truck Type</div>
                      <div className="mt-1 text-slate-900">{order.truck_type || '-'}</div>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-500">Cargo Type</div>
                      <div className="mt-1 text-slate-900">{order.cargo_type || '-'}</div>
                    </div>
                  </div>

                  <div className="mt-3 text-xs text-slate-500">
                    Created: {formatDateTime(order.created_at)}
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <SecondaryButton type="button" onClick={() => setModal({ type: 'details', order })}>
                      <i className="fas fa-info-circle" aria-hidden="true"></i> Details
                    </SecondaryButton>
                    <PrimaryButton type="button" onClick={() => trackOrder(order)} disabled={busyId === `${orderId}:track`}>
                      <i className={`fas ${busyId === `${orderId}:track` ? 'fa-spinner fa-spin' : 'fa-map-marked-alt'}`} aria-hidden="true"></i>
                      Track
                    </PrimaryButton>
                    {pending && (
                      <button
                        type="button"
                        onClick={() => cancelOrder(order)}
                        disabled={busyId === `${orderId}:cancel`}
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <i className={`fas ${busyId === `${orderId}:cancel` ? 'fa-spinner fa-spin' : 'fa-times-circle'}`} aria-hidden="true"></i>
                        Cancel
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </SectionCard>

      {modal?.type === 'details' && (
        <Modal title={`Order Details - ${modal.order.order_id || modal.order.id}`} onClose={() => setModal(null)}>
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            {[
              ['Order ID', modal.order.order_id || modal.order.id],
              ['Pickup', modal.order.pickup_location || '-'],
              ['Drop', modal.order.drop_location || '-'],
              ['Status', modal.order.status || '-'],
              ['Order Type', modal.order.order_type || '-'],
              ['Total Fare', formatMoney(modal.order.total_fare || modal.order.base_fare || 0)],
              ['Truck Type', modal.order.truck_type || '-'],
              ['Cargo Type', modal.order.cargo_type || '-'],
              ['Created', formatDateTime(modal.order.created_at)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs font-semibold text-slate-500">{label}</div>
                <div className="mt-1 text-slate-900">{value}</div>
              </div>
            ))}
          </div>
        </Modal>
      )}

      {modal?.type === 'tracking' && (
        <Modal title={`Tracking - Order ${modal.order.order_id || modal.order.id}`} onClose={() => setModal(null)}>
          {modal.history.length === 0 ? (
            <StateMessage type="empty">No tracking updates yet.</StateMessage>
          ) : (
            <ol className="space-y-3">
              {modal.history.map((event, index) => (
                <li key={`${event.created_at}-${index}`} className="rounded-lg border border-slate-200 p-3">
                  <div className="font-semibold capitalize text-slate-900">{String(event.status || '-').replace(/_/g, ' ')}</div>
                  <div className="mt-1 text-sm text-slate-600">Location: {event.location || '-'}</div>
                  <div className="mt-1 text-xs text-slate-500">{formatDateTime(event.created_at)}</div>
                  {event.description && <div className="mt-2 text-sm text-slate-600">{event.description}</div>}
                </li>
              ))}
            </ol>
          )}
        </Modal>
      )}

      {modal?.type === 'message' && (
        <Modal title={modal.title} onClose={() => setModal(null)}>
          <StateMessage type={modal.title?.includes('Error') ? 'error' : 'success'}>{modal.message}</StateMessage>
        </Modal>
      )}
    </>
  )
}
