import { useEffect, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import FuelStationLayout from '../../components/fuelstation/FuelStationLayout'

export default function FuelStationProfile() {
  const api = useApi()
  const [profile, setProfile] = useState({
    station_name: '',
    license_no: '',
    pumps_count: '',
    city: '',
    address: '',
    phone: '',
    email: '',
    full_name: '',
  })
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false
    api.get('/api/fuelstation/profile')
      .then(res => {
        if (!ignore && res.success && res.profile) {
          setProfile(res.profile)
        }
      })
      .catch(() => {
        if (!ignore) setError('Failed to load profile.')
      })
    return () => { ignore = true }
  }, [api])

  async function handleSave(e) {
    e.preventDefault()
    setError('')
    setNotice('')
    setSaving(true)
    try {
      const res = await api.put('/api/fuelstation/profile', {
        station_name: profile.station_name,
        license_no: profile.license_no,
        pumps_count: profile.pumps_count,
        city: profile.city,
        address: profile.address,
        phone: profile.phone,
      })
      if (res.success) {
        setNotice('Station profile updated successfully!')
      } else {
        setError(res.message || 'Failed to update profile.')
      }
    } catch (err) {
      setError(err.message || 'Error saving profile.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <FuelStationLayout>
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div className="fuel-card">
          <div className="fuel-card__header">
            <h2>Fuel Station &amp; Manager Profile</h2>
          </div>

          {notice && (
            <div style={{ background: '#ecf9f4', border: '1px solid #c4eadc', color: '#176b54', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
              <i className="fa-solid fa-circle-check" style={{ marginRight: 6 }} /> {notice}
            </div>
          )}

          {error && (
            <div style={{ background: '#fff0f0', border: '1px solid #ffcaca', color: '#a93737', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
              <i className="fa-solid fa-circle-exclamation" style={{ marginRight: 6 }} /> {error}
            </div>
          )}

          <form onSubmit={handleSave}>
            <div className="fuel-form-group">
              <label>Station Name *</label>
              <input
                type="text"
                className="fuel-form-input"
                value={profile.station_name}
                onChange={e => setProfile({ ...profile, station_name: e.target.value })}
                required
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="fuel-form-group">
                <label>OGRA / Ministry License Number</label>
                <input
                  type="text"
                  className="fuel-form-input"
                  value={profile.license_no}
                  onChange={e => setProfile({ ...profile, license_no: e.target.value })}
                />
              </div>

              <div className="fuel-form-group">
                <label>Number of Pumps / Bays</label>
                <input
                  type="text"
                  className="fuel-form-input"
                  value={profile.pumps_count}
                  onChange={e => setProfile({ ...profile, pumps_count: e.target.value })}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="fuel-form-group">
                <label>City / Hub</label>
                <input
                  type="text"
                  className="fuel-form-input"
                  value={profile.city}
                  onChange={e => setProfile({ ...profile, city: e.target.value })}
                />
              </div>

              <div className="fuel-form-group">
                <label>Station Contact Phone</label>
                <input
                  type="tel"
                  className="fuel-form-input"
                  value={profile.phone}
                  onChange={e => setProfile({ ...profile, phone: e.target.value })}
                />
              </div>
            </div>

            <div className="fuel-form-group">
              <label>Station Physical Address / Highway Landmark</label>
              <input
                type="text"
                className="fuel-form-input"
                placeholder="e.g. KM 42, M2 Motorway Service Area, Northbound"
                value={profile.address}
                onChange={e => setProfile({ ...profile, address: e.target.value })}
              />
            </div>

            <div style={{ borderTop: '1px solid #e1e8f0', paddingTop: 18, marginTop: 18 }}>
              <h3 style={{ fontSize: 15, color: '#52677e', margin: '0 0 12px' }}>Manager Account Details (Read-only)</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <span style={{ fontSize: 12, color: '#64748b' }}>Account Name:</span>
                  <div style={{ fontSize: 14, color: '#243b53', fontWeight: 600 }}>{profile.full_name}</div>
                </div>
                <div>
                  <span style={{ fontSize: 12, color: '#64748b' }}>Login Email:</span>
                  <div style={{ fontSize: 14, color: '#243b53', fontWeight: 600 }}>{profile.email}</div>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="fuel-btn fuel-btn--primary"
              style={{ marginTop: 24, width: '100%' }}
            >
              <i className={`fa-solid ${saving ? 'fa-spinner fa-spin' : 'fa-check'}`} />
              {saving ? 'Saving Profile...' : 'Save Changes'}
            </button>
          </form>
        </div>
      </div>
    </FuelStationLayout>
  )
}
