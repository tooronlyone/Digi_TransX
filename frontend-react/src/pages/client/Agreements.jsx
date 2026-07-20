import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  formatDate,
  formatMoney,
} from './clientUtils'

const activeAgreementStatuses = new Set(['accepted', 'in_progress', 'completed'])

export default function Agreements() {
  const [agreements, setAgreements] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadAgreements() {
    setLoading(true)
    setError('')
    try {
      const json = await apiGet('/api/orders/my-orders')
      const orders = json.orders || []
      setAgreements(orders.filter((order) => activeAgreementStatuses.has(String(order.status || '').toLowerCase())))
    } catch (err) {
      setError(err.message || 'Failed to load agreement orders.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAgreements()
  }, [])

  const metrics = useMemo(() => {
    const active = agreements.filter((order) => ['accepted', 'in_progress'].includes(String(order.status || '').toLowerCase())).length
    const completed = agreements.filter((order) => String(order.status || '').toLowerCase() === 'completed').length
    return [
      { label: 'Accepted Orders', value: agreements.length, icon: 'fa-file-signature', tone: 'bg-blue-50 text-blue-700' },
      { label: 'Active Agreements', value: active, icon: 'fa-check-circle', tone: 'bg-emerald-50 text-emerald-700' },
      { label: 'Completed Agreements', value: completed, icon: 'fa-clipboard-check', tone: 'bg-slate-100 text-slate-700' },
    ]
  }, [agreements])

  return (
    <>
      <PageTitle
        title="Agreements"
        subtitle="Review accepted order relationships and completed client-transporter agreements."
        actions={
          <>
            <Link to="/client/post-order" className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
              <i className="fas fa-plus" aria-hidden="true"></i> Post Order
            </Link>
            <PrimaryButton type="button" onClick={loadAgreements} disabled={loading}>
              <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
              Refresh
            </PrimaryButton>
          </>
        }
      />

      <SectionCard title="Agreement Orders Overview" icon="fa-file-contract">
        <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-3">
          {metrics.map((metric) => (
            <article key={metric.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-500">{metric.label}</div>
                  <div className="mt-2 text-2xl font-bold text-slate-900">{metric.value}</div>
                </div>
                <div className={`grid h-11 w-11 place-items-center rounded-lg ${metric.tone}`}>
                  <i className={`fas ${metric.icon}`} aria-hidden="true"></i>
                </div>
              </div>
            </article>
          ))}
        </div>

        {loading && <StateMessage type="loading">Loading agreement data...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {!loading && !error && agreements.length === 0 && (
          <StateMessage type="empty">No accepted or completed order agreements found yet.</StateMessage>
        )}
        {!loading && !error && agreements.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-normal text-slate-500">
                <tr>
                  <th className="px-4 py-3">Order ID</th>
                  <th className="px-4 py-3">Pickup</th>
                  <th className="px-4 py-3">Drop</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Budget</th>
                  <th className="px-4 py-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {agreements.map((order) => (
                  <tr key={order.id}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{order.id}</td>
                    <td className="px-4 py-3 text-slate-600">{order.pickup_city || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{order.dropoff_city || '-'}</td>
                    <td className="px-4 py-3"><StatusBadge status={order.status} /></td>
                    <td className="px-4 py-3 text-slate-700">{formatMoney(order.estimated_budget || 0)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(order.created_at)}</td>
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
