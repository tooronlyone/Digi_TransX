import { useState } from 'react'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'

export default function EverydayUserDetails() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [form, setForm] = useState({ city: '', transport_need: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })

  function validate() {
    const e = {}
    if (!form.city.trim()) e.city = 'Please tell us your city'
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
        city:           form.city.trim(),
        transport_need: form.transport_need || undefined,
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
    <StepShell title="Everyday User" subtitle="Quick setup — just two things and you're in!" icon="🙋">
      <Notification type={notification.type} message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })} />

      <form className="auth-details-form" onSubmit={handleSubmit}>
        <InputField label="Your City" id="city" type="text"
          placeholder="e.g. Lahore, Multan, Peshawar" value={form.city}
          onChange={set('city')} error={errors.city} />

        <div className="auth-form-field">
          <label >
            How often do you need transport? <span >(Optional)</span>
          </label>
          <select value={form.transport_need} onChange={set('transport_need')}
            className="auth-form-input auth-form-select">
            <option value="">Select...</option>
            <option value="rarely">Rarely (a few times a year)</option>
            <option value="monthly">Monthly</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>

        <div className="auth-detail-note">
          ✅ You'll get a simple, clean interface — no complex features.
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
