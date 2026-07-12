import { useState } from 'react'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'

export default function FuelStationDetails() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [form, setForm] = useState({ station_name: '', city: '', pumps_count: '', license_no: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })

  function validate() {
    const e = {}
    if (!form.station_name.trim()) e.station_name = 'Station name is required'
    if (!form.city.trim()) e.city = 'City is required'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setLoading(true)
    try {
      const result = await submitSignup({
        station_name: form.station_name.trim(),
        city:         form.city.trim(),
        pumps_count:  form.pumps_count || undefined,
        license_no:   form.license_no.trim() || undefined,
      }, cacheUser, resolveRedirect)
      if (result.ok) {
        setNotification({ type: 'success', message: 'Account created! Redirecting...' })
      } else {
        if (result.field) setErrors({ [result.field]: result.message })
        setNotification({ type: 'error', message: result.message })
      }
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error. Please try again.' })
    } finally {
      setLoading(false)
    }
  }

  const set = f => e => setForm(p => ({ ...p, [f]: e.target.value }))

  return (
    <StepShell title="Fuel Station Manager" subtitle="Set up your pump station account" icon="⛽">
      <Notification type={notification.type} message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })} />

      <form className="auth-details-form" onSubmit={handleSubmit}>
        <InputField label="Station Name" id="station_name" type="text"
          placeholder="e.g. Al-Rehman Fuel Station" value={form.station_name}
          onChange={set('station_name')} error={errors.station_name} />

        <InputField label="City / Location" id="city" type="text"
          placeholder="e.g. Faisalabad, Sialkot" value={form.city}
          onChange={set('city')} error={errors.city} />

        <InputField label="OGRA / License Number" id="license_no" type="text"
          placeholder="License number (optional)" value={form.license_no}
          onChange={set('license_no')} error={errors.license_no} />

        <div className="auth-form-field">
          <label >
            Number of Pumps <span >(Optional)</span>
          </label>
          <select value={form.pumps_count} onChange={set('pumps_count')}
            className="auth-form-input auth-form-select">
            <option value="">Select...</option>
            <option value="1-2">1–2 pumps</option>
            <option value="3-5">3–5 pumps</option>
            <option value="6+">6+ pumps</option>
          </select>
        </div>

        <button type="submit" disabled={loading}
          className="auth-submit">
          {loading && <span className="auth-shell__spinner" aria-hidden="true" />}
          {loading ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </StepShell>
  )
}
