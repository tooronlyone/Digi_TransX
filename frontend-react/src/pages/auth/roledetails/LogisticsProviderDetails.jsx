import { useState } from 'react'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'

export default function LogisticsProviderDetails() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [form, setForm] = useState({ fleet_size: '', city: '', company_name: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })

  function validate() {
    const e = {}
    if (!form.city.trim()) e.city = 'City is required'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }
    setErrors({})
    setLoading(true)
    try {
      const result = await submitSignup({
        fleet_size: form.fleet_size || undefined,
        city: form.city.trim(),
        company_name: form.company_name.trim() || undefined,
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

  const set = (field) => (event) => setForm((previous) => ({ ...previous, [field]: event.target.value }))

  return (
    <StepShell title="Logistics Provider" subtitle="Tell us about your fleet and operations" icon="fa-truck-fast">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />

      <form className="auth-details-form" onSubmit={handleSubmit}>
        <InputField
          label="City / Base Location"
          id="city"
          type="text"
          placeholder="e.g. Lahore, Karachi, Gujranwala"
          value={form.city}
          onChange={set('city')}
          error={errors.city}
        />

        <InputField
          label="Company / Truck Owner Name"
          id="company_name"
          type="text"
          placeholder="Business name (optional)"
          value={form.company_name}
          onChange={set('company_name')}
          error={errors.company_name}
        />

        <div className="auth-form-field">
          <label>
            Fleet Size <span>(Optional)</span>
          </label>
          <select value={form.fleet_size} onChange={set('fleet_size')} className="auth-form-input auth-form-select">
            <option value="">Select...</option>
            <option value="1">1 vehicle (owner-driver)</option>
            <option value="2-5">2-5 vehicles</option>
            <option value="6-20">6-20 vehicles</option>
            <option value="20+">20+ vehicles</option>
          </select>
        </div>

        <button type="submit" disabled={loading} className="auth-submit">
          {loading && <span className="auth-shell__spinner" aria-hidden="true" />}
          {loading ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </StepShell>
  )
}
