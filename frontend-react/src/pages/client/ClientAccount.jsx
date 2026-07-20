import { useEffect, useState } from 'react'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  apiGet,
  apiSend,
} from './clientUtils'

const emptyProfile = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  company_name: '',
  contact_phone: '',
  billing_address: '',
}

export default function ClientAccount() {
  const [profile, setProfile] = useState(emptyProfile)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadProfile() {
    setLoading(true)
    setError('')
    try {
      const json = await apiGet('/api/profile')
      const loaded = json.user || json.profile || json.data?.profile || {}
      setProfile({
        first_name: loaded.first_name || '',
        last_name: loaded.last_name || '',
        email: loaded.email || '',
        phone: loaded.phone || '',
        company_name: loaded.company_name || '',
        contact_phone: loaded.contact_phone || '',
        billing_address: loaded.billing_address || loaded.address || '',
      })
    } catch (err) {
      setError(err.message || 'Failed to load profile.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProfile()
  }, [])

  function updateField(field, value) {
    setProfile((current) => ({ ...current, [field]: value }))
  }

  async function saveProfile() {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const billingAddress = profile.billing_address || ''
      const json = await apiSend('/api/profile', {
        first_name: profile.first_name || null,
        last_name: profile.last_name || null,
        phone: profile.phone || null,
        company_name: profile.company_name || null,
        contact_phone: profile.contact_phone || null,
        billing_address: billingAddress || null,
        address: billingAddress || null,
      }, 'PUT')
      const loaded = json.user || json.profile || json.data?.profile || {}
      setProfile((current) => ({
        ...current,
        first_name: loaded.first_name || '',
        last_name: loaded.last_name || '',
        phone: loaded.phone || '',
        company_name: loaded.company_name || '',
        contact_phone: loaded.contact_phone || '',
        billing_address: loaded.billing_address || loaded.address || '',
      }))
      setMessage('Profile updated successfully.')
    } catch (err) {
      setError(err.message || 'Failed to update profile.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageTitle title="Account Settings" subtitle="Manage your profile information and account preferences." />

      <SectionCard
        title="Profile Settings"
        actions={
          <>
            <a href="/client/security-settings.html" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              <i className="fas fa-shield-alt" aria-hidden="true"></i> Security Settings
            </a>
            <SecondaryButton type="button" onClick={loadProfile} disabled={loading}>
              <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
              Reload
            </SecondaryButton>
            <PrimaryButton type="button" onClick={saveProfile} disabled={saving || loading}>
              <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-save'}`} aria-hidden="true"></i>
              Save Changes
            </PrimaryButton>
          </>
        }
      >
        {loading && <StateMessage type="loading">Loading profile...</StateMessage>}
        {error && <StateMessage type="error">{error}</StateMessage>}
        {message && <div className="mb-4"><StateMessage type="success">{message}</StateMessage></div>}
        {!loading && (
          <form className="grid grid-cols-1 gap-4 md:grid-cols-2" onSubmit={(event) => event.preventDefault()}>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">First Name</span>
              <input
                value={profile.first_name}
                onChange={(event) => updateField('first_name', event.target.value)}
                maxLength={120}
                className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="Enter your first name"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Last Name</span>
              <input
                value={profile.last_name}
                onChange={(event) => updateField('last_name', event.target.value)}
                maxLength={120}
                className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="Enter your last name"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Email Address</span>
              <input
                value={profile.email}
                disabled
                className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-slate-100 px-3 text-sm text-slate-500"
                placeholder="Email address"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Phone Number</span>
              <input
                value={profile.phone}
                onChange={(event) => updateField('phone', event.target.value)}
                maxLength={32}
                className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="+92 XXX XXXXXXX"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Company Name</span>
              <input
                value={profile.company_name}
                onChange={(event) => updateField('company_name', event.target.value)}
                maxLength={180}
                className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="Your company or business name"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Contact Phone</span>
              <input
                value={profile.contact_phone}
                onChange={(event) => updateField('contact_phone', event.target.value)}
                maxLength={32}
                className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="Alternative contact number"
              />
            </label>
            <label className="block md:col-span-2">
              <span className="text-sm font-semibold text-slate-700">Billing Address</span>
              <textarea
                value={profile.billing_address}
                onChange={(event) => updateField('billing_address', event.target.value)}
                maxLength={600}
                rows={4}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="Enter your complete billing address"
              />
            </label>
          </form>
        )}
      </SectionCard>

      <SectionCard title="Fast Login Security">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-600">Configure MPIN or biometric unlock for quick and secure access.</p>
          <a href="/client/security-settings.html" className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            <i className="fas fa-fingerprint" aria-hidden="true"></i>
            Manage Security
          </a>
        </div>
      </SectionCard>

      <SectionCard title="Danger Zone" icon="fa-exclamation-triangle">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => window.alert('Please contact support to deactivate your account.')}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700"
          >
            <i className="fas fa-ban" aria-hidden="true"></i>
            Deactivate Account
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm('WARNING: This action is permanent. Are you sure you want to delete your account?')) {
                window.alert('Please contact support to permanently delete your account.')
              }
            }}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700"
          >
            <i className="fas fa-trash-alt" aria-hidden="true"></i>
            Delete Account
          </button>
        </div>
      </SectionCard>
    </>
  )
}
