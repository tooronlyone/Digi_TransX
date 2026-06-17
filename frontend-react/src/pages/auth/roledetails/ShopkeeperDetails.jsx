import { useState } from 'react'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'

export default function ShopkeeperDetails() {
  const { cacheUser, resolveRedirect } = useAuthSession()
  const [form, setForm] = useState({ shop_name: '', city: '', business_type: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })

  function validate() {
    const e = {}
    if (!form.shop_name.trim()) e.shop_name = 'Shop or business name is required'
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
        shop_name:     form.shop_name.trim(),
        city:          form.city.trim(),
        business_type: form.business_type || undefined,
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
    <StepShell title="Shop Owner / Vendor" subtitle="Tell us about your shop or business" icon="🛒">
      <Notification type={notification.type} message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })} />

      <form onSubmit={handleSubmit}>
        <InputField label="Shop / Business Name" id="shop_name" type="text"
          placeholder="e.g. Bilal General Store, Ahmed Electronics" value={form.shop_name}
          onChange={set('shop_name')} error={errors.shop_name} />

        <InputField label="City / Location" id="city" type="text"
          placeholder="e.g. Lahore, Karachi, Islamabad" value={form.city}
          onChange={set('city')} error={errors.city} />

        <div className="mb-5">
          <label className="block mb-2 font-semibold text-gray-700 text-sm">
            Business Type <span className="font-normal text-gray-400">(Optional)</span>
          </label>
          <select value={form.business_type} onChange={set('business_type')}
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg text-base outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 text-gray-700">
            <option value="">Select type...</option>
            <option value="retail">Retail Shop</option>
            <option value="wholesale">Wholesale / Distributor</option>
            <option value="electronics">Electronics</option>
            <option value="groceries">Groceries / General Store</option>
            <option value="clothing">Clothing / Textiles</option>
            <option value="hardware">Hardware / Tools</option>
            <option value="pharmacy">Pharmacy / Medical</option>
            <option value="other">Other</option>
          </select>
        </div>

        <button type="submit" disabled={loading}
          className="w-full py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2">
          {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
          {loading ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </StepShell>
  )
}
