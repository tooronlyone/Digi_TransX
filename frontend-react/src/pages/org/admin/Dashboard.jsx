import { useEffect, useState } from 'react'
import OrgShell from '../../../components/org/OrgShell'
import { clearOrgPortalState, orgAuthRequest } from '../../../lib/orgPortal'

export default function OrgAdminDashboard() {
  const [banner, setBanner] = useState(null)
  const [subtitle, setSubtitle] = useState('Loading...')
  const [profileHint, setProfileHint] = useState('Checking profile...')
  const [eligibility, setEligibility] = useState('')

  function logout() {
    clearOrgPortalState()
    window.location.replace('/org/admin/login')
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const me = await orgAuthRequest('/api/org/auth/me', { method: 'GET' })
        if (me?.user?.role !== 'transporter_admin') {
          logout()
          return
        }
        setSubtitle(`Signed in as ${me.user.email}`)
        if (me.transporter) {
          setProfileHint(`${me.transporter.display_name} • mode: ${me.transporter.mode}`)
          if (me.transporter.eligible && me.transporter.mode === 'organization') {
            setEligibility('Enterprise enabled')
          } else if (me.transporter.eligible) {
            setEligibility('Eligible (switch to Organization mode)')
          } else {
            setEligibility('Not eligible')
          }
        } else {
          setProfileHint('No transporter profile yet. Create one to enable departments.')
          setEligibility('')
        }
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Unable to load session.' })
        logout()
      }
    }

    bootstrap()
  }, [])

  return (
    <OrgShell
      title="Org Admin Dashboard"
      subtitle={subtitle}
      banner={banner}
      actions={
        <div className="org-inline-actions">
          <a className="org-link" href="/transporter/dashboard">Back to Transporter UI</a>
          <button type="button" className="org-button danger" onClick={logout}>Logout</button>
        </div>
      }
    >
      <div className="org-grid">
        <div className="org-col-6">
          <section className="org-card">
            <h2 className="org-card__title">Transporter Profile</h2>
            <p className="org-card__meta">{profileHint}</p>
            <div className="org-inline-actions">
              <a className="org-button primary" href="/org/admin/transporter-profile">Profile setup</a>
              {eligibility ? <span className={`org-pill ${eligibility.includes('Not') ? 'danger' : 'success'}`}>{eligibility}</span> : null}
            </div>
          </section>
        </div>

        <div className="org-col-6">
          <section className="org-card">
            <h2 className="org-card__title">Departments</h2>
            <p className="org-card__meta">Create departments, assign job holders by email, and enforce deny-by-default access.</p>
            <div className="org-inline-actions">
              <a className="org-button primary" href="/org/admin/departments">Manage departments</a>
              <a className="org-button secondary" href="/org/admin/activity">View activity</a>
            </div>
          </section>
        </div>

        <div className="org-col-6">
          <section className="org-card">
            <h2 className="org-card__title">Partners</h2>
            <p className="org-card__meta">Assign Level 1 partner accounts with scoped permissions.</p>
            <div className="org-inline-actions">
              <a className="org-button primary" href="/org/admin/partners">Manage partners</a>
            </div>
          </section>
        </div>
      </div>
    </OrgShell>
  )
}
