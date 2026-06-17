import { useEffect, useState } from 'react'
import OrgShell from '../../../components/org/OrgShell'
import { orgAuthRequest } from '../../../lib/orgPortal'

const EMPTY_FORM = {
  display_name: '',
  legal_name: '',
  mode: 'solo',
  trucks_count: '0',
  rating: '0',
}

export default function OrgAdminTransporterProfile() {
  const [banner, setBanner] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [eligibility, setEligibility] = useState('')
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)

  function showEligibility(ok, reasons = []) {
    if (ok) {
      setEligibility('Eligible')
      return
    }
    setEligibility(`Not eligible: ${reasons.join(', ') || 'requirements not met'}`)
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await orgAuthRequest('/api/org/auth/me', { method: 'GET' })
        if (response?.transporter) {
          setForm({
            display_name: response.transporter.display_name || '',
            legal_name: response.transporter.legal_name || '',
            mode: response.transporter.mode || 'solo',
            trucks_count: String(response.transporter.trucks_count || 0),
            rating: String(response.transporter.rating || 0),
          })
          showEligibility(!!response.transporter.eligible, response.transporter.eligible ? [] : ['minimum requirements not met'])
        }
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Unable to load profile.' })
      }
    }

    bootstrap()
  }, [])

  async function checkEligibility() {
    setChecking(true)
    setBanner(null)
    try {
      const response = await orgAuthRequest('/api/org/transporters/eligibility', {
        method: 'POST',
        body: JSON.stringify({
          trucks_count: Number(form.trucks_count || 0),
          rating: Number(form.rating || 0),
        }),
      })
      showEligibility(!!response.eligible, response.reasons || [])
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to check eligibility.' })
    } finally {
      setChecking(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setBanner(null)
    try {
      const response = await orgAuthRequest('/api/org/transporters', {
        method: 'POST',
        body: JSON.stringify({
          display_name: form.display_name.trim(),
          legal_name: form.legal_name.trim(),
          mode: form.mode,
          trucks_count: Number(form.trucks_count || 0),
          rating: Number(form.rating || 0),
        }),
      })
      showEligibility(!!response.eligible, response.reasons || [])
      setBanner({ type: 'success', message: 'Profile saved.' })
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to save profile.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <OrgShell
      title="Transporter Profile"
      subtitle="Eligibility requires at least 15 trucks and rating 4.5 or higher."
      banner={banner}
      actions={<a className="org-link" href="/org/admin/dashboard">Back</a>}
    >
      <section className="org-card">
        <form className="org-form-grid" onSubmit={handleSubmit}>
          <div className="org-field half">
            <span>Display name</span>
            <input value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} placeholder="Your fleet name" required />
          </div>
          <div className="org-field half">
            <span>Legal name</span>
            <input value={form.legal_name} onChange={(event) => setForm((prev) => ({ ...prev, legal_name: event.target.value }))} placeholder="Registered legal name" />
          </div>
          <div className="org-field half">
            <span>Mode</span>
            <select value={form.mode} onChange={(event) => setForm((prev) => ({ ...prev, mode: event.target.value }))}>
              <option value="solo">Solo</option>
              <option value="organization">Organization</option>
            </select>
            <div className="org-field__hint">Organization mode enables departments and job holders.</div>
          </div>
          <div className="org-field half">
            <span>Trucks count</span>
            <input type="number" min="0" step="1" value={form.trucks_count} onChange={(event) => setForm((prev) => ({ ...prev, trucks_count: event.target.value }))} />
          </div>
          <div className="org-field half">
            <span>Rating</span>
            <input type="number" min="0" max="5" step="0.1" value={form.rating} onChange={(event) => setForm((prev) => ({ ...prev, rating: event.target.value }))} />
          </div>
          <div className="org-col-12 org-inline-actions">
            <button type="button" className="org-button secondary" onClick={checkEligibility} disabled={checking}>
              <i className={`fas ${checking ? 'fa-spinner fa-spin' : 'fa-circle-check'}`}></i>
              {checking ? 'Checking...' : 'Check eligibility'}
            </button>
            {eligibility ? <span className={`org-pill ${eligibility.startsWith('Eligible') ? 'success' : 'danger'}`}>{eligibility}</span> : null}
          </div>
          <div className="org-col-12 org-inline-actions">
            <button type="submit" className="org-button primary" disabled={saving}>
              <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-floppy-disk'}`}></i>
              {saving ? 'Saving...' : 'Save profile'}
            </button>
            <a className="org-button secondary" href="/org/admin/departments">Manage departments</a>
          </div>
        </form>
      </section>
    </OrgShell>
  )
}
