import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, formatDate } from '../../pages/client/clientUtils'

// Persistent, non-blocking notice shown to affected logged-in users after a
// new commission/Terms version is published. It stays visible on every page
// until the user clicks "I have reviewed" on the Terms page (stored in the
// database, so it follows the user across devices).

function percentText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${number.toFixed(2).replace(/\.00$/, '')}%`
}

const CHANGE_LABELS = {
  one_time_order: 'One-time order fee',
  agreement: 'Agreement fee',
}

export default function TermsUpdateNotice({ termsPath }) {
  const [terms, setTerms] = useState(null)
  const [dismissedInSession, setDismissedInSession] = useState(false)

  useEffect(() => {
    let active = true
    apiGet('/api/platform/terms/current')
      .then((json) => {
        if (active) setTerms(json.terms || null)
      })
      .catch(() => undefined)

    function handleAcknowledged() {
      setDismissedInSession(true)
    }
    window.addEventListener('dtx:terms-acknowledged', handleAcknowledged)
    return () => {
      active = false
      window.removeEventListener('dtx:terms-acknowledged', handleAcknowledged)
    }
  }, [])

  if (!terms || !terms.requires_acknowledgement || dismissedInSession) return null

  const changes = (terms.changed_policy_types || [])
    .map((type) => {
      const current = type === 'agreement' ? terms.agreement : terms.one_time
      const previous = type === 'agreement' ? terms.previous?.agreement : terms.previous?.one_time
      if (!current) return null
      return {
        type,
        label: CHANGE_LABELS[type] || type,
        oldCompany: previous?.company_share_percent,
        newCompany: current.company_share_percent,
        newTransporter: current.transporter_share_percent,
      }
    })
    .filter(Boolean)

  return (
    <div
      role="status"
      style={{
        background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 12,
        padding: '14px 18px', margin: '0 0 18px 0',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 14, flexWrap: 'wrap',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <i className="fas fa-bell" aria-hidden="true" style={{ color: '#d97706', marginTop: 3 }}></i>
        <div>
          <div style={{ fontWeight: 700, color: '#92400e', fontSize: 14 }}>
            Platform commission terms have changed. Review updated Terms.
          </div>
          <div style={{ fontSize: 13, color: '#a16207', marginTop: 4 }}>
            {changes.length > 0 ? (
              changes.map((change) => (
                <span key={change.type} style={{ marginRight: 14 }}>
                  {change.label}:{' '}
                  {change.oldCompany !== undefined && change.oldCompany !== null
                    ? `${percentText(change.oldCompany)} → ${percentText(change.newCompany)} company`
                    : `${percentText(change.newCompany)} company`}{' '}
                  ({percentText(change.newTransporter)} transporter payout)
                </span>
              ))
            ) : (
              <span>Terms version {terms.version_number}</span>
            )}
            <span>· effective {formatDate(terms.effective_at)}</span>
          </div>
        </div>
      </div>
      <Link
        to={termsPath}
        style={{
          background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff',
          padding: '9px 16px', borderRadius: 10, fontWeight: 600, fontSize: 13,
          textDecoration: 'none', whiteSpace: 'nowrap',
        }}
      >
        Review Terms
      </Link>
    </div>
  )
}
