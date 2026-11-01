/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react'
import { apiGet } from '../../pages/client/clientUtils'

export const INSURANCE_NOTICE = "Goods Insurance is recommended. Uninsured cargo is transported at shipper's own risk."
export const INSURANCE_NOTICE_VERSION = 'rules-1-4-v1'

export function InsuranceNotice({ accepted, onChange }) {
  return <aside aria-label="Goods insurance notice" className="my-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
    <p className="font-semibold">{INSURANCE_NOTICE}</p>
    <p className="mt-1">This notice preserves mandatory legal obligations and liability established through verified misconduct.</p>
    {onChange && <label className="mt-3 flex items-start gap-2"><input type="checkbox" required checked={accepted} onChange={event => onChange(event.target.checked)} />I have read this goods insurance notice and the applicable booking terms.</label>}
  </aside>
}

export function moneyText(value) {
  if (value == null || value === '') return 'Unavailable'
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/)
  if (!match) return 'Unavailable'
  return `PKR ${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${match[3] ? `.${match[3]}` : ''}`
}

export function MarketReference({ orderId, truckId = '', refreshKey = '', showRange = false }) {
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    const controller = new AbortController()
    apiGet(`/api/orders/${encodeURIComponent(orderId)}/market-reference${truckId ? `?truck_id=${encodeURIComponent(truckId)}` : ''}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, loading: false }) })
      .catch(error => { if (!controller.signal.aborted) setState({ error: error.message, loading: false }) })
    return () => controller.abort()
  }, [orderId, truckId, refreshKey])
  return <section aria-label="Market reference" className="my-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-slate-800">
    {state.loading ? <p>Loading market reference...</p> : state.error ? <p role="status">Market reference unavailable: {state.error}</p> : <>
      <p className="font-semibold">Market Average Rate: {state.data.market_average == null ? 'Awaiting first eligible bid' : moneyText(state.data.market_average)}</p>
      {state.data.bootstrap && <p>The first eligible bid establishes the initial market reference.</p>}
      {showRange && state.data.minimum_bid != null && state.data.maximum_bid != null && <p>Your permitted bid range: {moneyText(state.data.minimum_bid)} – {moneyText(state.data.maximum_bid)}</p>}
      <p className="mt-1 text-xs">The server validates against the current reference when you submit. Accepted booking prices stay fixed.</p>
    </>}
  </section>
}

export function FeeBreakdown({ kind = 'freight', snapshot = null }) {
  const [schedule, setSchedule] = useState(null)
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    if (snapshot) return undefined
    const controller = new AbortController()
    apiGet('/api/business-rules/fees', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setSchedule(data[kind] || data.fees?.[kind] || null) })
      .catch(() => { if (!controller.signal.aborted) setUnavailable(true) })
    return () => controller.abort()
  }, [kind, snapshot])
  const data = snapshot || schedule
  if (!data) return <p role="status" className="my-3 text-sm text-slate-600">{unavailable ? 'Itemized fee schedule unavailable. Reload before confirming fees.' : 'Loading itemized fees...'}</p>
  const heading = kind === 'marketplace' ? 'Total Marketplace Fee' : kind === 'freight' ? 'Total Platform Deductions' : 'Platform commission'
  return <section aria-label={`${kind} fee breakdown`} className="my-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
    <h3 className="font-semibold">{kind === 'freight' ? 'Transporter settlement fees' : kind === 'marketplace' ? 'Shopkeeper settlement fees' : `${kind === 'fuel' ? 'Fuel Station' : 'Client'} fees`}</h3>
    {data.components?.length > 0 && <dl className="mt-2 space-y-2">{data.components.map(item => <div key={item.code || item.label} className="flex justify-between gap-4"><dt>{item.label} ({item.percentage}%)</dt><dd>{item.amount != null ? moneyText(item.amount) : `${item.percentage}%`}</dd></div>)}</dl>}
    <p className="mt-3 font-semibold">{heading}: {data.total_fee != null ? moneyText(data.total_fee) : `${data.percentage}%`}</p>
    {data.net_amount != null && <p>Net proceeds before other authorized adjustments: {moneyText(data.net_amount)}</p>}
    {kind === 'freight' && <p className="mt-2 text-xs text-slate-600">Client platform commission: 0%. Deductions apply once upon successful delivery settlement.</p>}
    {kind === 'fuel' && <p>Fuel stations receive the full verified dispense value.</p>}
  </section>
}

export function SettlementSummary({ settlement }) {
  if (!settlement) return null
  return <section aria-label="Freight settlement" className="my-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm">
    <h3 className="font-semibold">Delivery settlement</h3>
    <dl className="mt-2 grid gap-2 sm:grid-cols-2">{[
      ['Gross fare', settlement.gross_amount], ['Platform deductions', settlement.company_fee], ['Net entitlement', settlement.net_entitlement],
      ['Fuel credit recovered from earnings', settlement.fuel_credit_recovered], ['Security reserve contribution', settlement.reserve_contribution],
      ['First tranche', settlement.tranche1_amount], ['Second tranche held', settlement.tranche2_amount],
    ].filter(([, value]) => value != null).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="font-semibold">{moneyText(value)}</dd></div>)}</dl>
    {settlement.dispute_deadline_at && <p className="mt-2">Delivery dispute deadline: {new Date(settlement.dispute_deadline_at).toLocaleString('en-PK')}.</p>}
    {settlement.release_eligible_at && <p>Second tranche eligible for release: {new Date(settlement.release_eligible_at).toLocaleString('en-PK')}. Due settlements are processed by the scheduled worker; qualifying disputes keep applicable funds frozen.</p>}
    {String(settlement.reserve_policy_state || '').includes('approval_required') && <p className="mt-2 font-semibold text-amber-900">Progressive reserve policy requires business approval. No progressive reserve deduction was applied.</p>}
    <p>Status: {String(settlement.status || 'pending').replaceAll('_', ' ')}</p>
  </section>
}
