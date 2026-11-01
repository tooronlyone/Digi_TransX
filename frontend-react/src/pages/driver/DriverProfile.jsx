import { useEffect, useState } from 'react'
import { apiGet } from '../client/clientUtils'

export default function DriverProfile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiGet('/api/driver/me')
      .then((res) => {
        if (res.success) setProfile(res.driver)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="driver-card"><p>Loading profile...</p></div>
  if (!profile) return <div className="driver-card"><p>Unable to load profile.</p></div>

  return (
    <div>
      <div className="driver-card">
        <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Driver Profile &amp; ID Card</h1>
        <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
          Your verified transporter-facing credential. Transporters link this ID to their fleet trucks.
        </p>

        <div style={{ marginTop: '24px', maxWidth: '600px', border: '2px solid #3b82f6', borderRadius: '14px', background: 'white', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <div style={{ background: '#1e3a8a', color: 'white', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', opacity: 0.8 }}>DIGI_TRANSX COMMERCIAL DRIVER ID</span>
              <h2 style={{ margin: '2px 0 0 0', fontSize: '1.4rem' }}>{profile.full_name}</h2>
            </div>
            <span style={{ background: '#3b82f6', color: 'white', padding: '4px 12px', borderRadius: '6px', fontWeight: 800, fontSize: '1rem', letterSpacing: '0.05em' }}>
              {profile.unique_driver_id}
            </span>
          </div>

          <div style={{ padding: '20px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>PHONE NUMBER</span>
              <p style={{ margin: '2px 0 0 0', fontWeight: 600 }}>{profile.phone}</p>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>EMAIL ADDRESS</span>
              <p style={{ margin: '2px 0 0 0', fontWeight: 600 }}>{profile.email}</p>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>BASE CITY</span>
              <p style={{ margin: '2px 0 0 0', fontWeight: 600 }}>{profile.city || 'Pakistan'}</p>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>DRIVING LICENSE (HTV/LTV)</span>
              <p style={{ margin: '2px 0 0 0', fontWeight: 600 }}>{profile.license_number}</p>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>EXPERIENCE</span>
              <p style={{ margin: '2px 0 0 0', fontWeight: 600 }}>{profile.experience_years} Years</p>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700 }}>VERIFICATION STATUS</span>
              <p style={{ margin: '2px 0 0 0', color: '#16a34a', fontWeight: 700 }}>
                <i className="fas fa-circle-check"></i> {profile.verified_status?.toUpperCase()}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
