import { useState } from 'react'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'

export default function ServiceSeekerDetails() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [form, setForm] = useState({ company_name: '', business_type: '', city: '' })
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
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setLoading(true)
    try {
      const result = await submitSignup({
        company_name:  form.company_name.trim() || undefined,
        business_type: form.business_type || undefined,
        city:          form.city.trim(),
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
    <StepShell title="Service Seeker" subtitle="Tell us a bit more about your shipping needs" icon="📦">
      <Notification type={notification.type} message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })} />

      <form onSubmit={handleSubmit}>
        <InputField label="City / Location" id="city" type="text"
          placeholder="e.g. Lahore, Karachi, Faisalabad" value={form.city}
          onChange={set('city')} error={errors.city} />

        <div className="mb-5">
          <label className="block mb-2 font-semibold text-gray-700 text-sm">
            Business Type <span className="font-normal text-gray-400">(Optional)</span>
          </label>
          <select value={form.business_type} onChange={set('business_type')}
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg text-base outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 text-gray-700">
            <option value="">Select type...</option>
            <option value="manufacturer">Manufacturer</option>
            <option value="wholesaler">Wholesaler / Trader</option>
            <option value="retailer">Retailer</option>
            <option value="individual">Individual</option>
            <option value="other">Other</option>
          </select>
        </div>

        <InputField label="Company / Business Name" id="company_name" type="text"
          placeholder="Your company or business name (optional)" value={form.company_name}
          onChange={set('company_name')} error={errors.company_name} />

        <button type="submit" disabled={loading}
          className="w-full py-3 bg-emerald-500 hover:bg-emerald-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2">
          {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
          {loading ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </StepShell>
  )
}
