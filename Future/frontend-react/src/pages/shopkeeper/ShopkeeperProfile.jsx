import { useEffect, useState } from 'react'
import { getCsrf } from './posUtils'

const EMPTY_PROFILE = {
  first_name: '',
  last_name: '',
  shop_name: '',
  email: '',
  phone: '',
  city: '',
  about: '',
}

function normalizeProfile(user = {}) {
  const nameParts = String(user.full_name || '').trim().split(/\s+/).filter(Boolean)
  return {
    first_name: user.first_name || nameParts[0] || '',
    last_name: user.last_name || nameParts.slice(1).join(' ') || '',
    shop_name: user.shop_name || user.company_name || '',
    email: user.email || '',
    phone: user.phone || '',
    city: user.city || '',
    about: user.about || '',
  }
}

export default function ShopkeeperProfile() {
  const [profile, setProfile] = useState(EMPTY_PROFILE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })

  useEffect(() => {
    let active = true
    fetch('/api/profile', { credentials: 'include' })
      .then(async response => ({ response, data: await response.json() }))
      .then(({ response, data }) => {
        if (!active) return
        if (response.ok && data.success !== false && data.user) {
          setProfile(normalizeProfile(data.user))
          sessionStorage.setItem('user', JSON.stringify(data.user))
        } else {
          setMessage({ type: 'error', text: 'We could not load your profile. Please try again.' })
        }
      })
      .catch(() => active && setMessage({ type: 'error', text: 'We could not connect to the profile service.' }))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  const setField = field => event => setProfile(current => ({ ...current, [field]: event.target.value }))

  async function handleSubmit(event) {
    event.preventDefault()
    if (!profile.first_name.trim() || !profile.shop_name.trim()) {
      setMessage({ type: 'error', text: 'Your name and shop name are required.' })
      return
    }
    setSaving(true)
    setMessage({ type: '', text: '' })
    try {
      const csrf = await getCsrf()
      const response = await fetch('/api/profile', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({
          first_name: `${profile.first_name.trim()} ${profile.last_name.trim()}`.trim(),
          shop_name: profile.shop_name.trim(),
          phone: profile.phone.trim(),
          city: profile.city.trim(),
          about: profile.about.trim(),
        }),
      })
      const data = await response.json()
      if (!response.ok || !data.success) {
        setMessage({ type: 'error', text: data.message || 'Your profile could not be updated. Please try again.' })
        return
      }
      const nextUser = data.user || {}
      setProfile(normalizeProfile(nextUser))
      sessionStorage.setItem('user', JSON.stringify(nextUser))
      window.dispatchEvent(new CustomEvent('dtx:user-updated', { detail: nextUser }))
      setMessage({ type: 'success', text: 'Your profile has been updated successfully.' })
    } catch {
      setMessage({ type: 'error', text: 'We could not connect to the profile service. Please try again.' })
    } finally {
      setSaving(false)
    }
  }

  const initials = `${profile.first_name.charAt(0)}${profile.last_name.charAt(0)}`.toUpperCase() || 'SK'

  return (
    <div className="shopkeeper-profile-page">
      <aside className="shopkeeper-profile-summary">
        <span className="shopkeeper-profile-summary__avatar">{initials}</span>
        <h2>{profile.first_name || 'Shopkeeper'} {profile.last_name}</h2>
        <p>{profile.shop_name || 'Your shop'}</p>
        <span className="shopkeeper-profile-summary__badge"><i className="fa-solid fa-circle-check" /> Shopkeeper Account</span>
        <div className="shopkeeper-profile-summary__tip">
          <i className="fa-solid fa-lightbulb" />
          <span><strong>Keep details current</strong><small>Accurate shop information helps customers identify your business.</small></span>
        </div>
      </aside>

      <section className="shopkeeper-profile-form-card">
        <div className="shopkeeper-profile-form-card__heading">
          <div><h2>Profile Information</h2><p>Update your personal and shop details.</p></div>
          <span><i className="fa-solid fa-user-pen" /></span>
        </div>

        {loading ? (
          <div className="shopkeeper-profile-loading"><i className="fa-solid fa-spinner fa-spin" /> Loading profile...</div>
        ) : (
          <form onSubmit={handleSubmit}>
            {message.text && <div className={`shopkeeper-profile-message ${message.type}`}><i className={`fa-solid ${message.type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation'}`} /> {message.text}</div>}
            <div className="shopkeeper-profile-grid">
              <label><span>First Name *</span><input value={profile.first_name} onChange={setField('first_name')} placeholder="Your first name" /></label>
              <label><span>Last Name</span><input value={profile.last_name} onChange={setField('last_name')} placeholder="Your last name" /></label>
              <label className="shopkeeper-profile-grid__wide"><span>Shop Name *</span><input value={profile.shop_name} onChange={setField('shop_name')} placeholder="Your shop or business name" /></label>
              <label><span>Email Address</span><input value={profile.email} disabled /><small>Email cannot be changed here.</small></label>
              <label><span>Phone Number</span><input value={profile.phone} onChange={setField('phone')} placeholder="e.g. +92 300 1234567" /></label>
              <label className="shopkeeper-profile-grid__wide"><span>City / Location</span><input value={profile.city} onChange={setField('city')} placeholder="e.g. Lahore" /></label>
              <label className="shopkeeper-profile-grid__wide"><span>About Your Shop</span><textarea rows="4" value={profile.about} onChange={setField('about')} placeholder="Tell customers what your shop sells or specializes in." maxLength="500" /><small>{profile.about.length}/500 characters</small></label>
            </div>
            <div className="shopkeeper-profile-actions">
              <button type="submit" disabled={saving}>{saving ? <><i className="fa-solid fa-spinner fa-spin" /> Saving...</> : <><i className="fa-solid fa-floppy-disk" /> Save Changes</>}</button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}
