import { useEffect, useState } from 'react'
import { apiGet } from '../client/clientUtils'

export default function DriverReputation() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => res.success ? setData(res) : setError(res.message || 'Unable to load reputation data.'))
      .catch((failure) => setError(failure.message || 'Unable to load reputation data.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="driver-page" aria-busy="true"><div className="driver-skeleton driver-skeleton--hero" /></div>
  if (!data) return <div className="driver-state driver-state--error" role="alert"><i className="fas fa-shield-halved" /><h2>Reputation unavailable</h2><p>{error || 'Your trust record could not be loaded.'}</p></div>

  const { driver, incidents = [] } = data
  const ratingCount = Number(driver.rating_count || 0)
  const ratingValue = Number(driver.rating)
  const hasRating = ratingCount > 0 && Number.isFinite(ratingValue)

  return (
    <div className="driver-page">
      <section className="driver-card">
        <h1>Reputation &amp; safety record</h1>
        <p>This verified trust profile helps transporters review driver history before assigning high-value cargo trips.</p>

        <div className="driver-reputation-grid">
          <article className="driver-reputation-panel">
            <span>Overall trust score</span>
            <div className="driver-reputation-score"><strong>{hasRating ? ratingValue.toFixed(1) : '—'}</strong>{hasRating && <span>/ 5.0</span>}</div>
            <p>{hasRating ? `Based on ${ratingCount} verified customer review${ratingCount === 1 ? '' : 's'} and your incident history.` : 'Your score will appear after your first verified customer review.'}</p>
          </article>

          <article className={`driver-reputation-panel ${incidents.length ? 'driver-reputation-panel--danger' : 'driver-reputation-panel--safe'}`}>
            <span>Background integrity</span>
            <div className="driver-integrity">
              <i className={`fas ${incidents.length ? 'fa-triangle-exclamation' : 'fa-shield-check'}`} aria-hidden="true" />
              <div><h3>{incidents.length ? `${incidents.length} incident${incidents.length === 1 ? '' : 's'} logged` : 'Verified clean record'}</h3><small>{incidents.length ? 'Subject to safety review' : 'No theft or fraud reports'}</small></div>
            </div>
          </article>
        </div>
      </section>

      <section className="driver-card">
        <div className="driver-section-heading"><div><h2>Incident history</h2><p>Reports attached to this driver profile</p></div></div>
        {incidents.length === 0 ? (
          <div className="driver-empty-state"><span><i className="fas fa-check-double" /></span><div><h3>No misconduct reports</h3><p>Maintaining a clean record supports eligibility for higher-trust assignments.</p></div></div>
        ) : (
          <div className="driver-dispatch-list">
            {incidents.map((incident) => (
              <article className="driver-dispatch-row" key={incident.id}>
                <span className="driver-dispatch-icon" style={{ color: 'var(--driver-red)', background: 'var(--driver-red-soft)' }}><i className="fas fa-triangle-exclamation" /></span>
                <div className="driver-dispatch-main"><strong>{incident.incident_type} <span>· {incident.severity}</span></strong><p>{incident.description}</p></div>
                <div className="driver-dispatch-value"><strong>{new Date(incident.created_at).toLocaleDateString()}</strong><span className="driver-status driver-status--failed">Review</span></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
