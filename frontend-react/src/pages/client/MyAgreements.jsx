import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageTitle, PrimaryButton, SectionCard, StateMessage, StatusBadge, apiGet, formatMoney } from './clientUtils'

export default function MyAgreements() {
  const [agreements, setAgreements] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/agreements/my')
      .then((json) => setAgreements(json.agreements || []))
      .catch((loadError) => setError(loadError.message || 'Unable to load agreements.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <>
      <PageTitle title="My Agreements" subtitle="Track active long-term shipment contracts and monthly obligations." />
      {loading && <StateMessage type="loading">Loading agreements...</StateMessage>}
      {error && <StateMessage type="error">{error}</StateMessage>}
      {!loading && !error && agreements.length === 0 && <StateMessage type="empty">No agreements yet.</StateMessage>}
      <div className="grid gap-4 xl:grid-cols-2">
        {agreements.map((agreement) => (
          <SectionCard key={agreement.id} title={`Agreement #${agreement.id}`} icon="fa-file-contract" actions={<StatusBadge status={agreement.status} />}>
            <div className="grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
              <div><span className="font-semibold text-slate-900">Cargo:</span> {agreement.cargo_type}</div>
              <div><span className="font-semibold text-slate-900">Duration:</span> {agreement.duration_months} months</div>
              <div><span className="font-semibold text-slate-900">Trucks:</span> {agreement.truck_count}</div>
              <div><span className="font-semibold text-slate-900">This month:</span> {formatMoney(agreement.current_month_earnings)}</div>
            </div>
            <div className="mt-4">
              <Link to={`/client/agreement/${agreement.id}`}>
                <PrimaryButton type="button">
                  <i className="fas fa-eye" aria-hidden="true"></i>
                  View Details
                </PrimaryButton>
              </Link>
            </div>
          </SectionCard>
        ))}
      </div>
    </>
  )
}
