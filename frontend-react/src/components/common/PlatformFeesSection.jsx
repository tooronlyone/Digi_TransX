import { useEffect, useState } from 'react'
import { apiGet, apiSend, formatDate } from '../../pages/client/clientUtils'

// Reusable, backend-driven "Platform Fees & Payout Shares" section shown on
// every Terms page (transporter + client portals). All backend text (change
// summaries) is rendered as plain text through React's default escaping —
// never as HTML.

const S = {
  card: {
    background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)', padding: 24, marginBottom: 20,
  },
  h2: { margin: 0, fontSize: 18, fontWeight: 700, color: '#0f172a' },
  sub: { fontSize: 13, color: '#64748b', marginTop: 4 },
  label: { fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5 },
  feeCard: {
    flex: '1 1 260px', border: '1px solid #e2e8f0', borderRadius: 12,
    padding: '16px 18px', background: '#f8fafc',
  },
  bigPercent: { fontSize: 26, fontWeight: 800, color: '#1d4ed8' },
  ackBtn: {
    padding: '10px 18px', borderRadius: 10, border: 'none', cursor: 'pointer',
    background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 600, fontSize: 14,
  },
}

function percentText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${number.toFixed(2).replace(/\.00$/, '')}%`
}

function FeeCard({ title, icon, policy, highlight }) {
  if (!policy) return null
  return (
    <div style={{ ...S.feeCard, ...(highlight ? { borderColor: '#bfdbfe', background: '#eff6ff' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <i className={`fas ${icon}`} style={{ color: '#2563eb' }} aria-hidden="true"></i>
        <strong style={{ color: '#0f172a', fontSize: 14 }}>{title}</strong>
      </div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div>
          <div style={S.label}>Company fee</div>
          <div style={S.bigPercent}>{percentText(policy.company_share_percent)}</div>
        </div>
        <div>
          <div style={S.label}>Transporter payout</div>
          <div style={{ ...S.bigPercent, color: '#047857' }}>{percentText(policy.transporter_share_percent)}</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 10 }}>
        Version {policy.version_number} · effective {formatDate(policy.effective_at)}
      </div>
    </div>
  )
}

export default function PlatformFeesSection({ audience = 'client' }) {
  const [terms, setTerms] = useState(null)
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [acknowledging, setAcknowledging] = useState(false)

  const isEveryday = audience === 'everyday'

  useEffect(() => {
    let active = true
    Promise.all([
      apiGet('/api/platform/terms/current'),
      apiGet('/api/platform/terms/history'),
    ])
      .then(([current, history]) => {
        if (!active) return
        setTerms(current.terms || null)
        setVersions(history.versions || [])
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err.message || 'Could not load platform fees.')
        setLoading(false)
      })
    return () => { active = false }
  }, [])

  async function acknowledge() {
    if (!terms) return
    setAcknowledging(true)
    try {
      await apiSend(`/api/platform/terms/${terms.id}/acknowledge`, {})
      setTerms({ ...terms, acknowledged: true, requires_acknowledgement: false })
      window.dispatchEvent(new CustomEvent('dtx:terms-acknowledged'))
    } catch (err) {
      setError(err.message || 'Could not save your review. Please try again.')
    } finally {
      setAcknowledging(false)
    }
  }

  if (loading) {
    return (
      <section style={S.card} aria-busy="true">
        <h2 style={S.h2}>Platform Fees &amp; Payout Shares</h2>
        <p style={S.sub}><i className="fas fa-spinner fa-spin" aria-hidden="true" style={{ marginRight: 8 }}></i>Loading current fees…</p>
      </section>
    )
  }

  if (error || !terms) {
    return (
      <section style={S.card}>
        <h2 style={S.h2}>Platform Fees &amp; Payout Shares</h2>
        <p style={{ ...S.sub, color: '#dc2626' }}>{error || 'Platform fees are not available right now.'}</p>
      </section>
    )
  }

  const shownVersions = versions.slice(0, 8)

  return (
    <section style={S.card} id="platform-fees">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={S.h2}>Platform Fees &amp; Payout Shares</h2>
          <p style={S.sub}>
            Terms version {terms.version_number} · effective {formatDate(terms.effective_at)}. These percentages are
            published by Digi_TransX and update automatically when a new version is approved.
          </p>
        </div>
        {terms.acknowledged && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, background: '#f0fdf4',
            color: '#16a34a', borderRadius: 20, padding: '6px 14px', fontSize: 13, fontWeight: 600,
          }}>
            <i className="fas fa-circle-check" aria-hidden="true"></i> Reviewed
          </span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 16 }}>
        <FeeCard
          title="One-time Orders"
          icon="fa-box"
          policy={terms.one_time}
          highlight
        />
        {!isEveryday && (
          <FeeCard
            title="Monthly Agreements"
            icon="fa-file-contract"
            policy={terms.agreement}
          />
        )}
      </div>

      {isEveryday && (
        <p style={{ ...S.sub, marginTop: 10 }}>
          As an Everyday User you book one-time deliveries, so the one-time order fee is what applies to you.
        </p>
      )}

      <p style={{ fontSize: 13, color: '#475569', marginTop: 14 }}>
        The commission that applies to an order is locked in when a bid is accepted, and for an agreement when it is
        finalized. Later fee changes never alter accepted orders, existing agreements, completed payments or payouts.
      </p>

      {terms.change_summary && (
        <div style={{
          marginTop: 12, background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#475569',
        }}>
          <span style={S.label}>Latest change</span>
          <div style={{ marginTop: 4 }}>{terms.change_summary}</div>
        </div>
      )}

      {terms.requires_acknowledgement && (
        <div style={{
          marginTop: 16, background: '#fffbeb', border: '1px solid #fde68a',
          borderRadius: 10, padding: '14px 16px',
        }}>
          <div style={{ fontSize: 13, color: '#92400e', fontWeight: 600, marginBottom: 10 }}>
            <i className="fas fa-bell" aria-hidden="true" style={{ marginRight: 8 }}></i>
            Platform commission terms have changed. Please confirm you have reviewed the updated fees above.
          </div>
          <button type="button" style={S.ackBtn} disabled={acknowledging} onClick={acknowledge}>
            {acknowledging ? 'Saving…' : 'I have reviewed'}
          </button>
        </div>
      )}

      {shownVersions.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <span style={S.label}>Fee version history</span>
          <div style={{ overflowX: 'auto', marginTop: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Version', 'Effective', 'One-time (company / transporter)', ...(!isEveryday ? ['Agreement (company / transporter)'] : []), 'Change summary'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 10px', color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, borderBottom: '1px solid #e2e8f0' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shownVersions.map((version) => (
                  <tr key={version.id}>
                    <td style={{ padding: '8px 10px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9' }}>v{version.version_number}</td>
                    <td style={{ padding: '8px 10px', color: '#64748b', whiteSpace: 'nowrap', borderBottom: '1px solid #f1f5f9' }}>{formatDate(version.effective_at)}</td>
                    <td style={{ padding: '8px 10px', color: '#374151', borderBottom: '1px solid #f1f5f9' }}>
                      {percentText(version.one_time?.company_share_percent)} / {percentText(version.one_time?.transporter_share_percent)}
                    </td>
                    {!isEveryday && (
                      <td style={{ padding: '8px 10px', color: '#374151', borderBottom: '1px solid #f1f5f9' }}>
                        {percentText(version.agreement?.company_share_percent)} / {percentText(version.agreement?.transporter_share_percent)}
                      </td>
                    )}
                    <td style={{ padding: '8px 10px', color: '#475569', borderBottom: '1px solid #f1f5f9' }}>{version.change_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
