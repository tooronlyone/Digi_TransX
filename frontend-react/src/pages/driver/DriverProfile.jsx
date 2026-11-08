import { useEffect, useState } from 'react'
import { apiGet } from '../client/clientUtils'

export default function DriverProfile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => res.success ? setProfile(res.driver) : setError(res.message || 'Unable to load profile.'))
      .catch((failure) => setError(failure.message || 'Unable to load profile.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="driver-page" aria-busy="true"><div className="driver-skeleton driver-skeleton--hero" /></div>
  if (!profile) return <div className="driver-state driver-state--error" role="alert"><i className="fas fa-id-card" /><h2>Profile unavailable</h2><p>{error || 'Your driver credential could not be loaded.'}</p></div>

  const fields = [
    ['Phone number', profile.phone || 'Not provided'],
    ['Email address', profile.email || 'Not provided'],
    ['Base city', profile.city || 'Not provided'],
    ['Driving licence (HTV/LTV)', profile.license_number || 'Not provided'],
    ['Experience', profile.experience_years == null ? 'Not provided' : `${profile.experience_years} years`],
  ]
  const verificationStatus = String(profile.verified_status || '').trim().toLowerCase()
  const isVerified = verificationStatus === 'verified'
  const verificationLabel = verificationStatus
    ? verificationStatus.replaceAll('_', ' ').toUpperCase()
    : 'PENDING REVIEW'

  return (
    <div className="driver-page">
      <section className="driver-card">
        <h1>Driver profile &amp; ID card</h1>
        <p>Your transporter-facing credential. Fleet owners use this ID to link you to an assigned truck.</p>

        <div className="driver-profile-card">
          <div className="driver-profile-card__head">
            <div><small>Digi_TransX commercial driver</small><h2>{profile.full_name}</h2></div>
            <span className="driver-profile-card__id">{profile.unique_driver_id}</span>
          </div>
          <div className="driver-profile-grid">
            {fields.map(([label, value]) => <div className="driver-profile-field" key={label}><span>{label}</span><p>{value}</p></div>)}
            <div className="driver-profile-field"><span>Verification status</span><p className={isVerified ? 'is-verified' : 'is-pending'}><i className={`fas ${isVerified ? 'fa-circle-check' : 'fa-clock'}`} aria-hidden="true" /> {verificationLabel}</p></div>
          </div>
        </div>
      </section>
    </div>
  )
}
