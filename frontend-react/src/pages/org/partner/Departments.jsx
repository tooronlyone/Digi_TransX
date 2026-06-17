import { useEffect, useState } from 'react'
import OrgDepartmentManager from '../../../components/org/OrgDepartmentManager'
import OrgShell from '../../../components/org/OrgShell'
import { clearOrgPortalState, orgAuthRequest } from '../../../lib/orgPortal'

export default function OrgPartnerDepartments() {
  const [banner, setBanner] = useState(null)
  const [subtitle, setSubtitle] = useState('Loading...')
  const [permissions, setPermissions] = useState({ manage_departments: false, manage_users: false })
  const [ready, setReady] = useState(false)

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
        const nextPermissions = partner?.partner?.permissions || {}
        setPermissions(nextPermissions)
        setSubtitle(`Signed in as ${me.user.email}`)
        if (!nextPermissions.manage_departments) {
          setBanner({ type: 'error', message: 'No permission to manage departments.' })
        }
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Unable to load partner session.' })
      } finally {
        setReady(true)
      }
    }

    bootstrap()
  }, [])

  return (
    <OrgShell
      title="Departments"
      subtitle={subtitle}
      banner={banner}
      actions={<a className="org-link" href="/org/partner/dashboard">Back</a>}
    >
      {ready ? (
        <OrgDepartmentManager
          canManageDepartments={!!permissions.manage_departments}
          canManageUsers={!!permissions.manage_users}
        />
      ) : (
        <div className="org-empty-state">
          <i className="fas fa-spinner fa-spin"></i>
          <div>Loading partner permissions...</div>
        </div>
      )}
    </OrgShell>
  )
}
