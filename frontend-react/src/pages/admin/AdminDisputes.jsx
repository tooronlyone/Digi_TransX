import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminRequest, dateText, money } from './adminApi'
import { detailMatchesSelection, shouldAcceptDetail } from './disputeGuards'

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:      { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' },
  th:       { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:       { padding: '14px 16px', fontSize: 14, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'middle' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  badgeStatus: (s) => {
    const map = { pending: ['#fffbeb','#d97706'], resolved: ['#f0fdf4','#16a34a'] }
    const [bg, color] = map[s] || ['#f1f5f9','#475569']
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: bg, color }
  },
  textarea: { width: '100%', padding: '12px 16px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', resize: 'vertical', boxSizing: 'border-box' },
  btnPrimary: { padding: '12px 24px', borderRadius: 10, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 700, fontSize: 14 },
  btnOutline: { padding: '10px 18px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
  btnChat:    { padding: '10px 18px', borderRadius: 10, border: '1.5px solid #bfdbfe', cursor: 'pointer', background: '#eff6ff', color: '#2563eb', fontWeight: 600, fontSize: 14 },
}

function DecisionBtn({ value, current, onClick, title, sub }) {
  const active = current === value
  return (
    <button onClick={onClick} style={{
      padding: '14px 16px', borderRadius: 12, textAlign: 'left', cursor: 'pointer',
      border: active ? '2px solid #2563eb' : '2px solid #e2e8f0',
      background: active ? '#eff6ff' : '#fff',
      transition: 'all 0.15s',
    }}>
      <div style={{ fontWeight: 700, color: active ? '#2563eb' : '#0f172a', fontSize: 14 }}>{title}</div>
      <div style={{ fontSize: 12, color: active ? '#3b82f6' : '#64748b', marginTop: 4 }}>{sub}</div>
    </button>
  )
}

export default function AdminDisputes() {
  const navigate = useNavigate()
  const [items, setItems]       = useState([])
  const [selected, setSelected] = useState(null)
  const [decision, setDecision] = useState('km_approved')
  const [adminNote, setAdminNote] = useState('')
  const [error, setError]       = useState('')
  // One-time delivery disputes (client_no / confirmation_timeout).
  const [otItems, setOtItems]   = useState([])
  const [otSelected, setOtSelected] = useState(null)
  const [otResolution, setOtResolution] = useState('transporter_win')
  const [otNotes, setOtNotes]   = useState('')
  const [otBusy, setOtBusy]     = useState(false)
  const [otDetail, setOtDetail] = useState(null)
  const [otDetailLoading, setOtDetailLoading] = useState(false)
  const [otDetailError, setOtDetailError] = useState('')
  // Race-safety: a monotonic token identifies the latest detail request, an
  // AbortController cancels the in-flight one, and mountedRef stops any
  // setState after unmount.
  const otReqRef = useRef(0)
  const otAbortRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    return () => {
      mountedRef.current = false
      otReqRef.current += 1              // invalidate any pending response
      otAbortRef.current?.abort()
    }
  }, [])

  async function openOneTimeDispute(item) {
    // Admins must review the full evidence before resolving. Opening a new case
    // invalidates the previous request (token bump) and aborts its fetch, so a
    // late response for dispute A can never populate the modal for dispute B.
    const token = ++otReqRef.current
    otAbortRef.current?.abort()
    const controller = new AbortController()
    otAbortRef.current = controller

    setOtSelected(item); setOtResolution('transporter_win'); setOtNotes('')
    setOtDetail(null); setOtDetailError(''); setOtDetailLoading(true)
    try {
      const json = await adminRequest(`/api/admin/one-time-disputes/${item.id}`, {
        signal: controller.signal,
      })
      // Apply ONLY if this is still the latest request AND the response is for
      // the dispute the admin currently has open.
      if (!mountedRef.current) return
      if (!shouldAcceptDetail(json.dispute?.id, item.id, token, otReqRef.current)) return
      setOtDetail(json.dispute || null)
      setOtDetailLoading(false)
    } catch (err) {
      if (err?.name === 'AbortError') return          // superseded/closed — ignore
      if (!mountedRef.current || token !== otReqRef.current) return
      setOtDetailError(err.message || 'Unable to load dispute details.')
      setOtDetailLoading(false)
    }
  }

  function closeOneTimeDispute() {
    otReqRef.current += 1                 // invalidate any pending response
    otAbortRef.current?.abort()
    setOtSelected(null); setOtDetail(null); setOtDetailError(''); setOtDetailLoading(false); setOtNotes('')
  }

  async function load() {
    try {
      const json = await adminRequest('/api/admin/disputes')
      setItems(json.disputes || [])
    } catch (err) { setError(err.message) }
    try {
      const otJson = await adminRequest('/api/admin/one-time-disputes?status=open')
      setOtItems(otJson.disputes || [])
    } catch (err) { setError(err.message) }
  }
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load() }, [])

  async function resolveOneTime() {
    if (!otSelected) return
    // The loaded evidence must belong to the currently selected dispute — never
    // resolve against stale/mismatched detail. Checked before confirming...
    if (!detailMatchesSelection(otDetail, otSelected)) {
      setError('Dispute evidence is not loaded for this case. Reopen the dispute and try again.')
      return
    }
    if (!otNotes.trim()) { setError('Admin notes are required to resolve a delivery dispute.'); return }
    if (!window.confirm(
      otResolution === 'transporter_win'
        ? 'Release the held payment to the transporter and complete this order?'
        : 'Refund the client and mark this order resolved in their favour?'
    )) return
    // ...and again right before posting (state may have changed during confirm).
    if (!detailMatchesSelection(otDetail, otSelected)) {
      setError('Dispute selection changed. No action was taken.')
      return
    }
    const disputeId = otSelected.id
    setOtBusy(true)
    setError('')
    try {
      await adminRequest(`/api/admin/one-time-disputes/${disputeId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution: otResolution, notes: otNotes.trim() }),
      })
      closeOneTimeDispute(); setOtResolution('transporter_win'); load()
    } catch (err) { setError(err.message) } finally { setOtBusy(false) }
  }

  async function openChat() {
    try {
      const json = await adminRequest(`/api/admin/disputes/${selected.id}/group-chat`, { method: 'POST', body: JSON.stringify({}) })
      navigate(`/admin/dispute-chat/${json.thread_id}`)
    } catch (err) { setError(err.message) }
  }

  async function resolve() {
    if (!selected || !window.confirm('Confirm this dispute decision?')) return
    try {
      await adminRequest(`/api/admin/disputes/${selected.id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ decision, admin_note: adminNote }),
      })
      setSelected(null); setAdminNote(''); load()
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={S.heading}>Disputes</h1>
        <p style={S.sub}>Trip KM disputes awaiting admin review and resolution.</p>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Trip','Agreement','Truck','Transporter','Client','Date','KM','Status',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>#{item.id}</td>
                <td style={S.td}>#{item.agreement_id}</td>
                <td style={S.td}>{item.truck_number}</td>
                <td style={S.td}>{item.transporter_name}</td>
                <td style={S.td}>{item.client_name}</td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.trip_date)}</td>
                <td style={S.td}>{item.distance_km || 0}</td>
                <td style={S.td}><span style={S.badgeStatus(item.status)}>{item.status}</span></td>
                <td style={S.td}>
                  <button onClick={() => { setSelected(item); setDecision('km_approved') }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontWeight: 600, fontSize: 13 }}>
                    Resolve →
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No disputes found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 8px 32px rgba(0,0,0,0.12)', padding: 28, width: '100%', maxWidth: 560 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>Trip #{selected.id}</h2>
                <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                  {selected.pickup_description} · {selected.distance_km || 0} km reported
                </p>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20 }}>
                <i className="fas fa-times" />
              </button>
            </div>

            {/* Open Chat */}
            <button onClick={openChat} style={S.btnChat}>
              <i className="fas fa-comments" style={{ marginRight: 8 }} />Open Group Chat
            </button>

            {/* Decision selection */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 20 }}>
              <DecisionBtn
                value="km_approved" current={decision} onClick={() => setDecision('km_approved')}
                title="Approve KM" sub="Rs 5,000 penalty to client"
              />
              <DecisionBtn
                value="km_rejected" current={decision} onClick={() => setDecision('km_rejected')}
                title="Reject KM" sub="Rs 5,000 penalty to transporter"
              />
            </div>

            {/* Note */}
            <textarea rows={4} style={{ ...S.textarea, marginTop: 16 }}
              placeholder="Admin note (optional)" value={adminNote}
              onChange={e => setAdminNote(e.target.value)} />

            {/* Actions */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
              <button onClick={() => setSelected(null)} style={S.btnOutline}>Cancel</button>
              <button onClick={resolve} style={S.btnPrimary}>
                <i className="fas fa-gavel" style={{ marginRight: 8 }} />Confirm Decision
              </button>
            </div>
          </div>
        </div>
      )}

      {/* One-time delivery disputes ------------------------------------ */}
      <div style={{ margin: '32px 0 16px' }}>
        <h1 style={S.heading}>One-time Delivery Disputes</h1>
        <p style={S.sub}>Client-denied or 6-hour-timeout deliveries. Payment stays held until you resolve.</p>
      </div>
      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Dispute','Order','Route','Transporter','Client','Trigger','Opened',''].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {otItems.map(item => (
              <tr key={item.id}>
                <td style={{ ...S.td, fontWeight: 700, color: '#0f172a' }}>#{item.id}</td>
                <td style={S.td}>#{item.shipment_id}</td>
                <td style={S.td}>{item.pickup_city} → {item.dropoff_city}</td>
                <td style={S.td}>{item.transporter_name}</td>
                <td style={S.td}>{item.client_name}</td>
                <td style={S.td}>{String(item.trigger || '').replace(/_/g, ' ')}</td>
                <td style={{ ...S.td, color: '#64748b' }}>{dateText(item.created_at)}</td>
                <td style={S.td}>
                  <button onClick={() => openOneTimeDispute(item)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontWeight: 600, fontSize: 13 }}>
                    Review →
                  </button>
                </td>
              </tr>
            ))}
            {otItems.length === 0 && (
              <tr><td colSpan={8} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No open delivery disputes.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {otSelected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 8px 32px rgba(0,0,0,0.12)', padding: 28, width: '100%', maxWidth: 640, maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>Order #{otSelected.shipment_id}</h2>
                <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                  {otSelected.pickup_city} → {otSelected.dropoff_city} · trigger: {String(otSelected.trigger || '').replace(/_/g, ' ')}
                </p>
              </div>
              <button onClick={closeOneTimeDispute} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20 }}>
                <i className="fas fa-times" />
              </button>
            </div>

            {otDetailLoading && (
              <div style={{ padding: 24, textAlign: 'center', color: '#64748b', fontSize: 14 }}>
                <i className="fas fa-spinner fa-spin" style={{ marginRight: 8 }} />Loading dispute evidence…
              </div>
            )}
            {otDetailError && (
              <div style={{ ...S.error, marginTop: 8 }}>{otDetailError}</div>
            )}

            {!otDetailLoading && !otDetailError && otDetail && (
              <>
                {/* Evidence: parties + statuses */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13, color: '#475569', marginBottom: 12 }}>
                  <div><strong>Client:</strong> {otDetail.client_name}</div>
                  <div><strong>Transporter:</strong> {otDetail.transporter_name}</div>
                  <div><strong>Shipment status:</strong> {String(otDetail.shipment_status || '').replace(/_/g, ' ')}</div>
                  <div><strong>Trip status:</strong> {String(otDetail.trip_status || '').replace(/_/g, ' ')}</div>
                </div>

                {/* Client reason + transporter statement */}
                <p style={{ fontSize: 13, color: '#475569', margin: '4px 0' }}>
                  <strong>Client reason:</strong> {otDetail.client_reason || <em style={{ color: '#94a3b8' }}>none provided</em>}
                </p>
                <p style={{ fontSize: 13, color: '#475569', margin: '4px 0' }}>
                  <strong>Transporter statement:</strong> {otDetail.transporter_statement || <em style={{ color: '#94a3b8' }}>none submitted</em>}
                </p>

                {/* Payment split / refund evidence */}
                {otDetail.payment && (
                  <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: 12, margin: '10px 0', fontSize: 13, color: '#475569' }}>
                    <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                      Payment — {String(otDetail.payment.status || '').toUpperCase()}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                      <div>Bid amount: {money(otDetail.payment.bid_amount)}</div>
                      <div>Company fee: {money(otDetail.payment.company_fee)}</div>
                      <div>Transporter payout: {money(otDetail.payment.transporter_amount)}</div>
                      <div>Wallet funded: {money(otDetail.payment.wallet_funded_amount)}</div>
                      <div>Card funded: {money(otDetail.payment.card_funded_amount)}</div>
                      {otDetail.payment.total_card_charge != null && (
                        <div>Total card charge: {money(otDetail.payment.total_card_charge)}</div>
                      )}
                    </div>
                  </div>
                )}

                {/* Status history */}
                {Array.isArray(otDetail.status_history) && otDetail.status_history.length > 0 && (
                  <div style={{ margin: '10px 0' }}>
                    <div style={{ fontWeight: 700, color: '#0f172a', fontSize: 13, marginBottom: 4 }}>Status history</div>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#64748b' }}>
                      {otDetail.status_history.map((h, i) => (
                        <li key={i}>{String(h.old_status || '—').replace(/_/g, ' ')} → {String(h.new_status || '').replace(/_/g, ' ')} · {dateText(h.created_at)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Read-only chat transcript */}
                <div style={{ margin: '10px 0' }}>
                  <div style={{ fontWeight: 700, color: '#0f172a', fontSize: 13, marginBottom: 4 }}>Chat transcript (read-only)</div>
                  <div style={{ maxHeight: 160, overflowY: 'auto', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: 10 }}>
                    {Array.isArray(otDetail.chat_messages) && otDetail.chat_messages.length > 0 ? (
                      otDetail.chat_messages.map((m) => (
                        <div key={m.id} style={{ fontSize: 12, color: '#334155', marginBottom: 6 }}>
                          <strong>{m.sender_name}:</strong> {m.content || <em style={{ color: '#94a3b8' }}>[{m.message_type}]</em>}
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: 12, color: '#94a3b8' }}>No messages.</div>
                    )}
                  </div>
                </div>

                {/* Decision + mandatory notes */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
                  <DecisionBtn value="transporter_win" current={otResolution} onClick={() => setOtResolution('transporter_win')}
                    title="Transporter wins" sub="Release the held payout" />
                  <DecisionBtn value="client_win" current={otResolution} onClick={() => setOtResolution('client_win')}
                    title="Client wins" sub="Refund the client, no payout" />
                </div>

                <textarea rows={3} style={{ ...S.textarea, marginTop: 16 }}
                  placeholder="Admin notes (required)" value={otNotes}
                  onChange={e => setOtNotes(e.target.value)} />
              </>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
              <button onClick={closeOneTimeDispute} style={S.btnOutline}>Cancel</button>
              <button onClick={resolveOneTime} disabled={otBusy || !detailMatchesSelection(otDetail, otSelected) || !otNotes.trim()} style={S.btnPrimary}>
                <i className="fas fa-gavel" style={{ marginRight: 8 }} />Resolve Dispute
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
