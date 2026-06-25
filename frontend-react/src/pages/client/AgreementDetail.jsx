import { Fragment, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import AgreementTripMap from '../../components/AgreementTripMap'
import { PageTitle, SectionCard, StateMessage, StatusBadge, apiGet, apiSend, formatDate, formatMoney, formatNumber } from './clientUtils'

export default function AgreementDetail() {
  const { id } = useParams()
  const [agreement, setAgreement] = useState(null)
  const [payments, setPayments] = useState([])
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [disputing, setDisputing] = useState(null)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    Promise.all([
      apiGet(`/api/agreements/${id}`),
      apiGet(`/api/agreements/${id}/payments`),
      apiGet(`/api/agreements/${id}/trips`),
    ])
      .then(([detail, paymentJson, tripJson]) => {
        setAgreement(detail.agreement)
        setPayments(paymentJson.payments || [])
        setTrips(tripJson.trips || [])
      })
      .catch((loadError) => setError(loadError.message || 'Unable to load agreement.'))
      .finally(() => setLoading(false))
  }, [id])

  async function disputeTrip(tripId) {
    if (!window.confirm('Are you sure you want to dispute this trip? Admin will investigate.')) return
    setDisputing(tripId)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/agreements/trips/${tripId}/dispute`, {})
      setNotice('Trip marked as disputed. Admin will review shortly.')
      const tripJson = await apiGet(`/api/agreements/${id}/trips`)
      setTrips(tripJson.trips || [])
    } catch (err) {
      setError(err.message || 'Unable to dispute trip.')
    } finally {
      setDisputing(null)
    }
  }

  if (loading) return <StateMessage type="loading">Loading agreement...</StateMessage>
  if (error) return <StateMessage type="error">{error}</StateMessage>
  if (!agreement) return <StateMessage type="empty">Agreement not found.</StateMessage>

  return (
    <>
      <PageTitle title={`Agreement #${agreement.id}`} subtitle={`${agreement.cargo_type} | ${agreement.service_area_text}`} actions={<StatusBadge status={agreement.status} />} />

      <SectionCard title="Assigned Trucks" icon="fa-truck">
        <div className="grid gap-3 md:grid-cols-2">
          {(agreement.trucks || []).map((truck) => (
            <div key={truck.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              <div className="font-semibold text-slate-900">{truck.truck_number} - {truck.truck_type_name}</div>
              <div>Transporter: {truck.transporter_name}</div>
              <div>{formatMoney(truck.per_km_rate)} per km | Minimum {formatMoney(truck.minimum_monthly_guarantee)}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Monthly Payments" icon="fa-wallet">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {payments.map((payment) => (
            <div key={payment.id} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-900">{payment.month_year} | {payment.truck_number}</div>
                <StatusBadge status={payment.status} />
              </div>
              <div className="mt-2 text-slate-600">Due {formatDate(payment.payment_due_date)}</div>
              <div className="mt-1 text-slate-600">KM {formatNumber(payment.total_km)} | Payable {formatMoney(payment.final_amount)}</div>
              <div className="mt-1 text-slate-600">Penalty {formatMoney(payment.penalty_amount)}</div>
              {payment.status === 'failed' && (
                <div className="mt-2 rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                  Payment failed. Penalties of {formatMoney(payment.penalty_amount)} applied. Top up wallet to clear.
                </div>
              )}
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Trips History" icon="fa-route">
        {notice && <StateMessage type="success">{notice}</StateMessage>}
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr><th className="py-2 pr-4">Date</th><th className="py-2 pr-4">Truck</th><th className="py-2 pr-4">KM</th><th className="py-2 pr-4">Status</th><th className="py-2 pr-4">Description</th><th className="py-2 pr-4">Action</th></tr>
            </thead>
            <tbody>
              {trips.map((trip) => (
                <Fragment key={trip.id}>
                  <tr className="border-b border-slate-100">
                    <td className="py-3 pr-4">{formatDate(trip.trip_date)}</td>
                    <td className="py-3 pr-4">{trip.truck_number}</td>
                    <td className="py-3 pr-4">{formatNumber(trip.distance_km)}</td>
                    <td className="py-3 pr-4"><StatusBadge status={trip.status} /></td>
                    <td className="py-3 pr-4">{trip.pickup_description}</td>
                    {trip.status === 'completed' ? (
                      <td className="py-3 pr-4">
                        <button
                          onClick={() => disputeTrip(trip.id)}
                          disabled={disputing === trip.id}
                          className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                        >
                          {disputing === trip.id ? 'Disputing...' : 'Dispute'}
                        </button>
                      </td>
                    ) : trip.status === 'disputed' ? (
                      <td className="py-3 pr-4"><span className="text-xs font-semibold text-amber-600">Under Review</span></td>
                    ) : (
                      <td className="py-3 pr-4" />
                    )}
                  </tr>
                  {trip.status === 'in_progress' && (
                    <tr key={`map-${trip.id}`}>
                      <td colSpan={6} className="pb-3 pt-1 pr-4">
                        <AgreementTripMap tripId={trip.id} isActive={true} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </>
  )
}
