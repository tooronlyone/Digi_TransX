import { useEffect, useState } from 'react'
import { adminRequest, dateText } from './adminApi'

const POLICY_META = {
  one_time_order: {
    title: 'One-time Order Commission',
    icon: 'fa-box',
    description: 'Applied when a one-time shipment bid is accepted. Changes never affect already-accepted orders.',
  },
  agreement: {
    title: 'Agreement Commission',
    icon: 'fa-file-contract',
    description: 'Applied when an agreement is finalized. Changes never affect existing agreements or their future monthly payments.',
  },
}

const S = {
  heading:  { fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 },
  sub:      { color: '#64748b', fontSize: 14, marginTop: 4 },
  card:     { background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', padding: 24 },
  label:    { display: 'block', fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  input:    { width: '100%', padding: '10px 14px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: 14, outline: 'none', background: '#f8fafc', color: '#1e293b', boxSizing: 'border-box' },
  th:       { padding: '12px 16px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, background: '#f8fafc', textAlign: 'left', borderBottom: '1px solid #e2e8f0' },
  td:       { padding: '12px 16px', fontSize: 13, color: '#374151', borderBottom: '1px solid #f1f5f9', verticalAlign: 'top' },
  error:    { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', color: '#dc2626', fontSize: 13, marginBottom: 16 },
  success:  { background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '12px 16px', color: '#16a34a', fontSize: 13, marginBottom: 16 },
  btnBlue:  { padding: '10px 18px', borderRadius: 10, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff', fontWeight: 600, fontSize: 14 },
  btnGrey:  { padding: '10px 18px', borderRadius: 10, border: '1.5px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 600, fontSize: 14 },
}

function percentText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return `${number.toFixed(2).replace(/\.00$/, '')}%`
}

function sharePill(company, transporter, muted) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: muted ? '#f1f5f9' : '#eff6ff', color: muted ? '#64748b' : '#1d4ed8',
      borderRadius: 20, padding: '4px 12px', fontSize: 13, fontWeight: 700,
    }}>
      {percentText(company)} company / {percentText(transporter)} transporter
    </span>
  )
}

function CommissionCard({ policyType, policy, onPublished }) {
  const meta = POLICY_META[policyType]
  const [newShare, setNewShare] = useState('')
  const [summary, setSummary] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const parsedShare = Number(newShare)
  const shareValid = newShare.trim() !== '' && Number.isFinite(parsedShare)
    && parsedShare >= 0 && parsedShare < 100
    && (!newShare.includes('.') || (newShare.split('.')[1] || '').length <= 2)
  const derivedTransporter = shareValid ? 100 - parsedShare : null
  const sameRate = shareValid && policy && parsedShare === Number(policy.company_share_percent)
  const canSubmit = shareValid && !sameRate && summary.trim().length > 0 && !saving

  async function publish() {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const json = await adminRequest('/api/admin/platform-settings/commissions', {
        method: 'POST',
        body: JSON.stringify({
          policy_type: policyType,
          company_share_percent: parsedShare,
          change_summary: summary.trim(),
        }),
      })
      setSuccess(json.message || 'Commission updated.')
      setNewShare('')
      setSummary('')
      setConfirming(false)
      onPublished()
    } catch (err) {
      setError(err.message)
      setConfirming(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={S.card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10, background: '#eff6ff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#2563eb', fontSize: 17,
        }}>
          <i className={`fas ${meta.icon}`} />
        </div>
        <div>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: '#0f172a' }}>{meta.title}</h2>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            {policy ? `Version ${policy.version_number} · effective ${dateText(policy.effective_at)}` : 'Not published yet'}
          </div>
        </div>
      </div>
      <p style={{ fontSize: 13, color: '#64748b', margin: '10px 0 16px' }}>{meta.description}</p>

      <div style={{ marginBottom: 18 }}>
        <span style={S.label}>Current split</span>
        {policy ? sharePill(policy.company_share_percent, policy.transporter_share_percent) : <span style={{ color: '#94a3b8' }}>-</span>}
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}
      {success && <div style={S.success}><i className="fas fa-circle-check" style={{ marginRight: 8 }} />{success}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
        <div>
          <label style={S.label} htmlFor={`share-${policyType}`}>New company %</label>
          <input
            id={`share-${policyType}`}
            style={S.input}
            type="number"
            min="0"
            max="99.99"
            step="0.01"
            placeholder={policy ? String(policy.company_share_percent) : 'e.g. 15.5'}
            value={newShare}
            onChange={(e) => { setNewShare(e.target.value); setSuccess('') }}
          />
        </div>
        <div>
          <span style={S.label}>Derived transporter %</span>
          <div style={{ ...S.input, background: '#f1f5f9', color: '#475569', fontWeight: 600 }}>
            {derivedTransporter === null ? '—' : percentText(derivedTransporter)}
          </div>
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <label style={S.label} htmlFor={`summary-${policyType}`}>Change summary (required)</label>
        <textarea
          id={`summary-${policyType}`}
          style={{ ...S.input, minHeight: 70, resize: 'vertical', fontFamily: 'inherit' }}
          placeholder="Explain why this rate is changing — shown to users in the Terms history."
          value={summary}
          onChange={(e) => { setSummary(e.target.value); setSuccess('') }}
        />
      </div>

      {shareValid && policy && (
        <div style={{
          background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: 10,
          padding: '12px 16px', marginBottom: 14, fontSize: 13,
        }}>
          <span style={{ ...S.label, marginBottom: 8 }}>Preview</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {sharePill(policy.company_share_percent, policy.transporter_share_percent, true)}
            <i className="fas fa-arrow-right" style={{ color: '#94a3b8' }} />
            {sharePill(parsedShare, derivedTransporter)}
          </div>
          {sameRate && (
            <div style={{ color: '#d97706', marginTop: 8 }}>
              <i className="fas fa-triangle-exclamation" style={{ marginRight: 6 }} />
              Same as the current rate — nothing to publish.
            </div>
          )}
        </div>
      )}

      {!confirming ? (
        <button
          style={{ ...S.btnBlue, opacity: canSubmit ? 1 : 0.5, cursor: canSubmit ? 'pointer' : 'not-allowed' }}
          disabled={!canSubmit}
          onClick={() => setConfirming(true)}
        >
          <i className="fas fa-upload" style={{ marginRight: 8 }} />Publish new version
        </button>
      ) : (
        <div style={{
          background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, padding: '14px 16px',
        }}>
          <div style={{ fontSize: 13, color: '#92400e', fontWeight: 600, marginBottom: 10 }}>
            Publish {meta.title.toLowerCase()} as {percentText(parsedShare)} company / {percentText(derivedTransporter)} transporter?
            This creates a new immutable version and updates the platform Terms. Existing orders and agreements keep their saved rates.
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button style={S.btnBlue} disabled={saving} onClick={publish}>
              {saving ? 'Publishing…' : 'Yes, publish'}
            </button>
            <button style={S.btnGrey} disabled={saving} onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminPlatformSettings() {
  const [policies, setPolicies] = useState({})
  const [termsVersion, setTermsVersion] = useState(null)
  const [history, setHistory] = useState({ policies: [], terms_versions: [] })
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    Promise.all([
      adminRequest('/api/admin/platform-settings/commissions'),
      adminRequest('/api/admin/platform-settings/commissions/history'),
    ])
      .then(([current, past]) => {
        if (!active) return
        setPolicies(current.policies || {})
        setTermsVersion(current.terms_version || null)
        setHistory({ policies: past.policies || [], terms_versions: past.terms_versions || [] })
        setError('')
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
    return () => { active = false }
  }, [reloadKey])

  function load() {
    setReloadKey((key) => key + 1)
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={S.heading}>Platform Settings</h1>
        <p style={S.sub}>
          Manage the two independent commission rates. Every change publishes a new immutable version and a new Terms version
          {termsVersion ? ` — current Terms v${termsVersion.version_number} (effective ${dateText(termsVersion.effective_at)})` : ''}.
        </p>
      </div>

      {error && <div style={S.error}><i className="fas fa-circle-exclamation" style={{ marginRight: 8 }} />{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20, marginBottom: 28 }}>
        <CommissionCard policyType="one_time_order" policy={policies.one_time_order} onPublished={load} />
        <CommissionCard policyType="agreement" policy={policies.agreement} onPublished={load} />
      </div>

      <div style={{ ...S.card, padding: 0, marginBottom: 28 }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
            <i className="fas fa-clock-rotate-left" style={{ marginRight: 10, color: '#2563eb' }} />
            Commission Version History
          </h2>
          <p style={{ ...S.sub, marginTop: 2 }}>Published versions are immutable — changes always create a new version.</p>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>{['Type', 'Version', 'Company %', 'Transporter %', 'Effective', 'Change Summary', 'Published By'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {history.policies.map(item => (
                <tr key={item.id}>
                  <td style={{ ...S.td, fontWeight: 600, color: '#0f172a', whiteSpace: 'nowrap' }}>
                    {POLICY_META[item.policy_type]?.title || item.policy_type}
                  </td>
                  <td style={S.td}>v{item.version_number}</td>
                  <td style={{ ...S.td, fontWeight: 700 }}>{percentText(item.company_share_percent)}</td>
                  <td style={S.td}>{percentText(item.transporter_share_percent)}</td>
                  <td style={{ ...S.td, whiteSpace: 'nowrap', color: '#64748b' }}>{dateText(item.effective_at)}</td>
                  <td style={S.td}>{item.change_summary}</td>
                  <td style={S.td}>{item.created_by_name || '—'}</td>
                </tr>
              ))}
              {history.policies.length === 0 && (
                <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No versions published yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ ...S.card, padding: 0 }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
            <i className="fas fa-file-lines" style={{ marginRight: 10, color: '#2563eb' }} />
            Terms Version History
          </h2>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>{['Terms Version', 'Effective', 'Change Summary', 'Published By'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {history.terms_versions.map(item => (
                <tr key={item.id}>
                  <td style={{ ...S.td, fontWeight: 700 }}>v{item.version_number}</td>
                  <td style={{ ...S.td, whiteSpace: 'nowrap', color: '#64748b' }}>{dateText(item.effective_at)}</td>
                  <td style={S.td}>{item.change_summary}</td>
                  <td style={S.td}>{item.published_by_name || '—'}</td>
                </tr>
              ))}
              {history.terms_versions.length === 0 && (
                <tr><td colSpan={4} style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>No Terms versions yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
