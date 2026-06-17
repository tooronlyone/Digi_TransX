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

      <form onSubmit={handleSubmit}>
        <InputField label="Your City" id="city" type="text"
          placeholder="e.g. Lahore, Multan, Peshawar" value={form.city}
          onChange={set('city')} error={errors.city} />

        <div className="mb-6">
          <label className="block mb-2 font-semibold text-gray-700 text-sm">
            How often do you need transport? <span className="font-normal text-gray-400">(Optional)</span>
          </label>
          <select value={form.transport_need} onChange={set('transport_need')}
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg text-base outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 text-gray-700">
            <option value="">Select...</option>
            <option value="rarely">Rarely (a few times a year)</option>
            <option value="monthly">Monthly</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>

        <div className="p-4 bg-violet-50 border border-violet-200 rounded-lg mb-5 text-sm text-violet-700">
          ✅ You'll get a simple, clean interface — no complex features.
        </div>

        <button type="submit" disabled={loading}
          className="w-full py-3 bg-violet-500 hover:bg-violet-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2">
          {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
          {loading ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </StepShell>
  )
}
