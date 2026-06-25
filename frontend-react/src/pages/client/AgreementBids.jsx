import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { PageTitle, PrimaryButton, SecondaryButton, SectionCard, StateMessage, StatusBadge, apiGet, apiSend, formatMoney } from './clientUtils'

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function addMonths(value, months) {
  const date = new Date(`${value}T00:00:00`)
  date.setMonth(date.getMonth() + Number(months || 0))
  return date.toISOString().slice(0, 10)
}

export default function AgreementBids() {
  const { postId } = useParams()
  const navigate = useNavigate()
  const [post, setPost] = useState(null)
  const [bids, setBids] = useState([])
  const [selected, setSelected] = useState({})
  const [duration, setDuration] = useState('3')
  const [startDate, setStartDate] = useState(todayIso())
  const [contractText, setContractText] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadBids() {
    setLoading(true)
    setError('')
    try {
      const json = await apiGet(`/api/agreements/posts/${postId}/bids`)
      setPost(json.post)
      setBids(json.bids || [])
    } catch (loadError) {
      setError(loadError.message || 'Unable to load bids.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBids()
  }, [postId])

  const selectedTrucks = useMemo(() => {
    const chosen = []
    bids.forEach((bid) => {
      ;(bid.trucks || []).forEach((truck) => {
        if (selected[`${bid.id}:${truck.truck_id}`]) chosen.push({ bid, truck })
      })
    })
    return chosen
  }, [bids, selected])

  useEffect(() => {
    const end = addMonths(startDate, duration)
    const lines = [
      'AGREEMENT SHIPMENT CONTRACT',
      '',
      `Client: Current Client | Date: ${todayIso()}`,
      `Duration: ${duration || 0} months (${startDate} to ${end})`,
      `Cargo Type: ${post?.cargo_type || ''}`,
      `Service Area: ${(post?.service_area || []).join(', ')}`,
      '',
      'ASSIGNED TRUCKS:',
      ...selectedTrucks.flatMap(({ bid, truck }) => [
        `${truck.truck_number} - Owner: ${bid.transporter_name}`,
        `Per KM Rate: Rs ${truck.per_km_rate} | Monthly Minimum: Rs ${truck.minimum_monthly_guarantee}`,
        '',
      ]),
      'PAYMENT TERMS:',
      '- Payment due: 10th of every month',
      '- Late penalty: Rs 5,000 per 30 minutes after midnight',
      '- Company fee: 20% of all payments',
      '',
      'TERMS & CONDITIONS:',
      '- Trucks are exclusively bound to client operations during agreement period',
      '- KM counted from client base to client base (GPS verified)',
      '- Maintenance requires advance notice to client',
      '- Disputes resolved by platform admin',
    ]
    setContractText(lines.join('\n'))
  }, [post, selectedTrucks.length, duration, startDate])

  async function invite(bid) {
    setWorking(`invite:${bid.id}`)
    setError('')
    try {
      await apiSend(`/api/agreements/posts/${postId}/bids/${bid.id}/invite`)
      navigate('/client/messages')
    } catch (inviteError) {
      setError(inviteError.message || 'Unable to invite transporter.')
    } finally {
      setWorking('')
    }
  }

  async function finalize() {
    if (!selectedTrucks.length) {
      setError('Select at least one proposed truck.')
      return
    }
    setWorking('finalize')
    setError('')
    setNotice('')
    try {
      const json = await apiSend('/api/agreements/finalize', {
        post_id: Number(postId),
        duration_months: Number(duration),
        start_date: startDate,
        cargo_type: post.cargo_type,
        service_area: post.service_area,
        selected_trucks: selectedTrucks.map(({ bid, truck }) => ({ bid_id: bid.id, truck_id: truck.truck_id })),
        contract_text: contractText,
      })
      setNotice('Agreement finalized.')
      setTimeout(() => navigate(`/client/agreement/${json.agreement.id}`), 700)
    } catch (finalizeError) {
      setError(finalizeError.message || 'Unable to finalize agreement.')
    } finally {
      setWorking('')
    }
  }

  return (
    <>
      <PageTitle title="Agreement Bids" subtitle={post ? post.title : 'Review transporter proposals.'} />
      {loading && <StateMessage type="loading">Loading bids...</StateMessage>}
      {error && <StateMessage type="error">{error}</StateMessage>}
      {notice && <StateMessage type="success">{notice}</StateMessage>}

      {!loading && bids.length === 0 && <StateMessage type="empty">No bids have arrived yet.</StateMessage>}
      <div className="grid gap-4">
        {bids.map((bid) => (
          <SectionCard key={bid.id} title={bid.transporter_name} icon="fa-user-tie" actions={<StatusBadge status={bid.status} />}>
            <div className="grid gap-3 text-sm text-slate-600">
              <div>Rating: {bid.transporter_rating ?? 0} | Average rate: {formatMoney(bid.average_per_km_rate)} | {bid.exact_match ? 'Best fit' : 'Partial fit'}</div>
              <div>{bid.message || 'No message provided.'}</div>
              <div className="grid gap-2 md:grid-cols-2">
                {(bid.trucks || []).map((truck) => {
                  const key = `${bid.id}:${truck.truck_id}`
                  return (
                    <label key={key} className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <input type="checkbox" className="mt-1" checked={!!selected[key]} onChange={(event) => setSelected((current) => ({ ...current, [key]: event.target.checked }))} />
                      <span>
                        <span className="block font-semibold text-slate-900">{truck.truck_number} - {truck.truck_type_name}</span>
                        <span>{formatMoney(truck.per_km_rate)} per km | Minimum {formatMoney(truck.minimum_monthly_guarantee)}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
              <div>
                <SecondaryButton type="button" onClick={() => invite(bid)} disabled={working === `invite:${bid.id}`}>
                  <i className={`fas ${working === `invite:${bid.id}` ? 'fa-spinner fa-spin' : 'fa-comments'}`} aria-hidden="true"></i>
                  Invite to Chat
                </SecondaryButton>
              </div>
            </div>
          </SectionCard>
        ))}
      </div>

      {bids.length > 0 && (
        <SectionCard title="Finalize Agreement" icon="fa-file-signature">
          <div className="grid gap-4 md:grid-cols-3">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Duration months
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="1" value={duration} onChange={(event) => setDuration(event.target.value)} />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Start date
              <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <div className="text-sm text-slate-600">Selected trucks: <span className="font-semibold text-slate-900">{selectedTrucks.length}</span></div>
            <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-3">
              Contract preview
              <textarea className="min-h-80 rounded-lg border border-slate-300 px-3 py-2.5 font-mono text-sm" value={contractText} onChange={(event) => setContractText(event.target.value)} />
            </label>
          </div>
          <div className="mt-4">
            <PrimaryButton type="button" onClick={finalize} disabled={working === 'finalize'}>
              <i className={`fas ${working === 'finalize' ? 'fa-spinner fa-spin' : 'fa-check-circle'}`} aria-hidden="true"></i>
              Confirm & Finalize
            </PrimaryButton>
          </div>
        </SectionCard>
      )}
    </>
  )
}
