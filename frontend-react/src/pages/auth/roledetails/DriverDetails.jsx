import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import StepShell from './StepShell'
import InputField from '../../../components/common/InputField'
import Notification from '../../../components/common/Notification'
import { useAuthSession } from '../../../hooks/useAuth'
import { submitSignup } from './_submitHelper'
import { useSignupWizard } from '../../../auth/signupWizardContext'

export default function DriverDetails() {
  const navigate = useNavigate()
  const { cacheUser, resolveRedirect } = useAuthSession()
  const { store } = useSignupWizard()
  const [form, setForm] = useState({
    city: '',
    license_number: '',
    license_expiry: '',
    experience_years: '2',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })

  function validate() {
    const e = {}
    if (!form.city.trim()) e.city = 'City is required.'
    if (!form.license_number.trim()) e.license_number = 'Valid Driving License number is required.'
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
        city: form.city.trim(),
        license_number: form.license_number.trim(),
        license_expiry: form.license_expiry || undefined,
        experience_years: Number(form.experience_years) || 1,
        employment_type: 'per_trip',
      }, cacheUser, resolveRedirect, store, {
        navigateTo: (destination) => navigate(destination, { replace: true }),
      })

      if (result.ok) {
        setNotification({ type: 'success', message: 'Driver Account Created! Redirecting to Driver Console...' })
      } else {
        if (result.field) setErrors({ [result.field]: result.message })
        setNotification({ type: 'error', message: result.message })
      }
    } catch {
      setNotification({ type: 'error', message: 'Network error. Please try again.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepShell roleKey="driver" title="Driver Professional Details" subtitle="Enter your driving license and experience details">
      {notification.message && <Notification type={notification.type} message={notification.message} onClose={() => setNotification({ type: '', message: '' })} />}
      <form onSubmit={handleSubmit} className="auth-form" noValidate>
        <InputField
          id="driverCity"
          label="Current Base City"
          type="text"
          placeholder="e.g. Lahore, Karachi, Rawalpindi"
          value={form.city}
          onChange={(e) => setForm({ ...form, city: e.target.value })}
          error={errors.city}
          required
        />
        <InputField
          id="driverLicense"
          label="Driving License Number (HTV / LTV)"
          type="text"
          placeholder="e.g. LHR-HTV-98214"
          value={form.license_number}
          onChange={(e) => setForm({ ...form, license_number: e.target.value })}
          error={errors.license_number}
          required
        />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <InputField
            id="driverLicenseExpiry"
            label="License Expiry Date"
            type="date"
            value={form.license_expiry}
            onChange={(e) => setForm({ ...form, license_expiry: e.target.value })}
          />
          <InputField
            id="driverExp"
            label="Experience (Years)"
            type="number"
            min="0"
            max="40"
            value={form.experience_years}
            onChange={(e) => setForm({ ...form, experience_years: e.target.value })}
          />
        </div>
        <div style={{ marginTop: '12px', marginBottom: '16px', padding: '10px 14px', background: '#f1f5f9', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
          <span style={{ fontSize: '0.8rem', color: '#475569', fontWeight: 600 }}>
            <i className="fas fa-info-circle" style={{ marginRight: '6px', color: '#3b82f6' }}></i>
            All newly registered drivers begin as <strong>Per-Trip Freelance Drivers</strong>. As you complete trips with high ratings, fleet transporters can send you monthly permanent hire contracts.
          </span>
        </div>
        <button type="submit" className="auth-submit-btn" disabled={loading}>
          {loading ? 'Registering Driver...' : 'Complete Driver Registration'}
        </button>
      </form>
    </StepShell>
  )
}
