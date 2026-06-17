import { useEffect, useState } from 'react'
import OrgShell from '../../../components/org/OrgShell'
import { clearOrgPortalState, orgAuthRequest } from '../../../lib/orgPortal'

export default function OrgPartnerDashboard() {
  const [banner, setBanner] = useState(null)
  const [subtitle, setSubtitle] = useState('Loading...')
  const [permissionsHint, setPermissionsHint] = useState('Checking permissions...')
  const [permissions, setPermissions] = useState({ manage_departments: false, view_activity: false })

  function logout() {
    clearOrgPortalState()
    window.location.replace('/org/partner/login')
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const me = await orgAuthRequest('/api/org/auth/me', { method: 'GET' })
        if (me?.user?.role !== 'partner') {
          logout()
          return
        }
        const partner = await orgAuthRequest('/api/org/partners/me', { method: 'GET' })
        const transporterName = partner?.transporter?.display_name || me?.transporter?.display_name || 'Transporter'
        setSubtitle(`Signed in as ${me.user.email} • ${transporterName}`)
        const nextPermissions = partner?.partner?.permissions || {}
        setPermissions(nextPermissions)
        const tags = []
        if (nextPermissions.manage_departments) tags.push('departments')
        if (nextPermissions.manage_users) tags.push('users')
        if (nextPermissions.view_activity) tags.push('activity')
        setPermissionsHint(
          tags.length
            ? `Permissions: ${tags.join(', ')} (scope: ${nextPermissions.scope || 'scoped'})`
            : 'No partner permissions assigned.',
        )
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Unable to load session.' })
        logout()
      }
    }

    bootstrap()
  }, [])

  return (
    <OrgShell
      title="Partner Dashboard"
      subtitle={subtitle}
      banner={banner}
      actions={<button type="button" className="org-button danger" onClick={logout}>Logout</button>}
    >
      <section className="org-card">
        <h2 className="org-card__title">Tools</h2>
        <p className="org-card__meta">{permissionsHint}</p>
        <div className="org-inline-actions">
          {permissions.manage_departments ? <a className="org-button primary" href="/org/partner/departments">Manage departments</a> : null}
          {permissions.view_activity ? <a className="org-button secondary" href="/org/partner/activity">View activity</a> : null}
        </div>
      </section>
    </OrgShell>
  )
}
