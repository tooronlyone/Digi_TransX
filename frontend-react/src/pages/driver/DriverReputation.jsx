import { useEffect, useState } from 'react'
import { apiGet } from '../client/clientUtils'

export default function DriverReputation() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => {
        if (res.success) setData(res)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="driver-card"><p>Loading reputation metrics...</p></div>
  if (!data) return <div className="driver-card"><p>Unable to load data.</p></div>

  const { driver, incidents } = data
  const ratingCount = Number(driver.rating_count || 0)
  const ratingValue = Number(driver.rating)
  const hasRating = ratingCount > 0 && Number.isFinite(ratingValue)

  return (
    <div>
      <div className="driver-card">
        <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Reputation &amp; Anti-Theft Record</h1>
        <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
          This public trust profile is shown to Transporters before they assign high-value cargo trips.
        </p>

        <div style={{ marginTop: '20px', display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '260px', padding: '20px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px' }}>
            <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 700 }}>OVERALL TRUST SCORE</span>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '8px' }}>
              <span style={{ fontSize: '2.5rem', fontWeight: 800, color: hasRating ? (ratingValue >= 4.0 ? '#16a34a' : '#ea580c') : '#64748b' }}>
                {hasRating ? `⭐ ${ratingValue.toFixed(1)}` : 'Not rated yet'}
              </span>
              {hasRating && <span style={{ color: '#64748b', fontSize: '1rem' }}>/ 5.0</span>}
            </div>
            <p style={{ margin: '8px 0 0 0', fontSize: '0.85rem', color: '#475569' }}>
              {hasRating
                ? `Calculated from ${ratingCount} customer review${ratingCount === 1 ? '' : 's'} and incident records.`
                : 'Your trust score will appear after your first customer review.'}
            </p>
          </div>

          <div style={{ flex: 1, minWidth: '260px', padding: '20px', background: incidents.length === 0 ? '#f0fdf4' : '#fef2f2', border: `1px solid ${incidents.length === 0 ? '#bbf7d0' : '#fecaca'}`, borderRadius: '12px' }}>
            <span style={{ fontSize: '0.8rem', color: incidents.length === 0 ? '#166534' : '#991b1b', fontWeight: 700 }}>
              BACKGROUND INTEGRITY STATUS
            </span>
            <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <i className={`fas ${incidents.length === 0 ? 'fa-shield-check' : 'fa-triangle-exclamation'}`} style={{ fontSize: '2rem', color: incidents.length === 0 ? '#16a34a' : '#dc2626' }}></i>
              <div>
                <h3 style={{ margin: 0, color: incidents.length === 0 ? '#166534' : '#991b1b' }}>
                  {incidents.length === 0 ? 'Verified Clean Record' : `${incidents.length} Incident(s) Logged`}
                </h3>
                <small style={{ color: incidents.length === 0 ? '#15803d' : '#b91c1c' }}>
                  {incidents.length === 0 ? 'Zero theft or fraud reports' : 'Subject to safety review'}
                </small>
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: '30px' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 16px 0' }}>Incident Log &amp; Misconduct History</h2>
          {incidents.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '10px' }}>
              <i className="fas fa-check-double" style={{ fontSize: '2rem', color: '#16a34a', marginBottom: '8px' }}></i>
              <p style={{ margin: 0, fontWeight: 700, color: '#334155' }}>No theft or misconduct reports on this driver profile.</p>
              <small style={{ color: '#64748b' }}>Maintaining a clean record helps you receive higher-paying long-haul trips.</small>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {incidents.map((inc) => (
                <div key={inc.id} style={{ padding: '16px', border: '1px solid #fecaca', background: '#fff5f5', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong style={{ color: '#b91c1c', textTransform: 'uppercase' }}>{inc.incident_type} ({inc.severity})</strong>
                    <span style={{ fontSize: '0.8rem', color: '#7f1d1d' }}>{new Date(inc.created_at).toLocaleDateString()}</span>
                  </div>
                  <p style={{ margin: '8px 0 0 0', color: '#374151' }}>{inc.description}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
