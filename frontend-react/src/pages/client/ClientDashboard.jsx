import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  formatMoney,
} from './clientUtils'

const initialStats = {
  walletBalance: 0,
  totalOrders: 0,
  activeOrders: 0,
  completedOrders: 0,
}

export default function ClientDashboard() {
  const [stats, setStats] = useState(initialStats)
  const [orders, setOrders] = useState([])
  const [dashboardLoading, setDashboardLoading] = useState(true)
  const [ordersLoading, setOrdersLoading] = useState(true)
  const [dashboardError, setDashboardError] = useState('')
  const [ordersError, setOrdersError] = useState('')

  async function loadDashboard() {
    setDashboardLoading(true)
    setDashboardError('')
    try {
      const [ordersJson, balanceJson] = await Promise.all([
        apiGet('/api/orders/mine'),
        apiGet('/api/wallet'),
      ])
      const myOrders = ordersJson.orders || []
      const wallet = balanceJson.wallet || {}
      setStats({
        walletBalance: wallet.balance ?? 0,
        totalOrders: myOrders.length,
        activeOrders: myOrders.filter((order) => ['open', 'accepted', 'in_progress'].includes(order.status)).length,
        completedOrders: myOrders.filter((order) => order.status === 'completed').length,
      })
    } catch (error) {
      setDashboardError(error.message || 'Failed to load dashboard.')
    } finally {
      setDashboardLoading(false)
    }
  }

  async function loadOrders() {
    setOrdersLoading(true)
    setOrdersError('')
    try {
      const json = await apiGet('/api/orders/mine')
      setOrders((json.orders || []).slice(0, 6))
    } catch (error) {
      setOrdersError(error.message || 'Failed to load recent orders.')
    } finally {
      setOrdersLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
    loadOrders()
  }, [])

  const statCards = [
    { label: 'Wallet Balance', value: formatMoney(stats.walletBalance), icon: 'fa-wallet', tone: 'bg-blue-50 text-blue-700' },
    { label: 'Total Orders', value: stats.totalOrders, icon: 'fa-receipt', tone: 'bg-emerald-50 text-emerald-700' },
    { label: 'Active Orders', value: stats.activeOrders, icon: 'fa-spinner', tone: 'bg-amber-50 text-amber-700' },
    { label: 'Completed Orders', value: stats.completedOrders, icon: 'fa-check-circle', tone: 'bg-slate-100 text-slate-700' },
  ]

  return (
    <>
      <PageTitle
        title="Client Dashboard"
        subtitle="Track your orders, compare bids, and keep an eye on your wallet balance."
      />

      <SectionCard>
        {dashboardLoading && <StateMessage type="loading">Loading dashboard...</StateMessage>}
        {dashboardError && <StateMessage type="error">{dashboardError}</StateMessage>}
        {!dashboardLoading && !dashboardError && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {statCards.map((card) => (
                <article key={card.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-slate-500">{card.label}</div>
                      <div className="mt-2 text-2xl font-bold text-slate-900">{card.value}</div>
                    </div>
                    <div className={`grid h-11 w-11 place-items-center rounded-lg ${card.tone}`}>
                      <i className={`fas ${card.icon}`} aria-hidden="true"></i>
                    </div>
                  </div>
                </article>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <Link to="/client/post-order" className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
                <i className="fas fa-plus-circle" aria-hidden="true"></i> Post Order
              </Link>
              <Link to="/client/orders" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                <i className="fas fa-gavel" aria-hidden="true"></i> My Orders
              </Link>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Recent Orders"
        icon="fa-clock"
        actions={
          <PrimaryButton type="button" onClick={loadOrders} disabled={ordersLoading}>
            <i className={`fas ${ordersLoading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
            Refresh
          </PrimaryButton>
        }
      >
        {ordersLoading && <StateMessage type="loading">Loading recent orders...</StateMessage>}
        {ordersError && <StateMessage type="error">{ordersError}</StateMessage>}
        {!ordersLoading && !ordersError && orders.length === 0 && (
          <StateMessage type="empty">No orders found yet.</StateMessage>
        )}
        {!ordersLoading && !ordersError && orders.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-normal text-slate-500">
                <tr>
                  <th className="px-4 py-3">Order ID</th>
                  <th className="px-4 py-3">Route</th>
                  <th className="px-4 py-3">Goods</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Budget</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{order.id}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {order.pickup_city || '-'} <i className="fas fa-arrow-right mx-2 text-slate-400" aria-hidden="true"></i> {order.dropoff_city || '-'}
                    </td>
                    <td className="px-4 py-3 capitalize text-slate-600">{order.goods_type || '-'}</td>
                    <td className="px-4 py-3"><StatusBadge status={order.status} /></td>
                    <td className="px-4 py-3 text-slate-700">{order.estimated_budget ? formatMoney(order.estimated_budget) : '-'}</td>
                    <td className="px-4 py-3">
                      <Link to="/client/orders" className="text-sm font-semibold text-blue-700 hover:text-blue-900">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </>
  )
}
