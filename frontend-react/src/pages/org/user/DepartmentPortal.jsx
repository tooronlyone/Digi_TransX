import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import OrgActivityFeed from '../../../components/org/OrgActivityFeed'
import OrgShell from '../../../components/org/OrgShell'
import { clearOrgPortalState, getOrgDepartmentId, getOrgDepartmentToken, orgDepartmentRequest } from '../../../lib/orgPortal'

export default function OrgUserDepartmentPortal() {
  const [params] = useSearchParams()
  const [banner, setBanner] = useState(null)
  const [title, setTitle] = useState('Department Portal')
  const [subtitle, setSubtitle] = useState('Loading...')
  const [details, setDetails] = useState({ access: null, department: null, user: null })
  const [activity, setActivity] = useState([])

  function logout() {
    clearOrgPortalState()
    window.location.replace('/org/user/login')
  }

  async function loadActivity(departmentId) {
    const response = await orgDepartmentRequest(`/api/org/departments/${encodeURIComponent(departmentId)}/activity?limit=50`, { method: 'GET' })
    setActivity(response.activity || [])
  }

  useEffect(() => {
    async function bootstrap() {
      const departmentId = params.get('department_id') || getOrgDepartmentId()
      if (!departmentId) {
        setBanner({ type: 'error', message: 'Missing department_id.' })
        return
      }
      if (!getOrgDepartmentToken()) {
        window.location.replace('/org/user/departments')
        return
      }
      setSubtitle(`Department ID ${departmentId}`)
      try {
        const response = await orgDepartmentRequest(`/api/org/departments/${encodeURIComponent(departmentId)}/profile`, { method: 'GET' })
        setDetails({
          access: response.access || null,
          department: response.department || null,
          user: response.user || null,
        })
        if (response.department?.name) {
          setTitle(`${response.department.name} Portal`)
        }
        await loadActivity(departmentId)
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Unable to load department profile.' })
      }
    }

    bootstrap()
  }, [params])

  return (
    <OrgShell
      title={title}
      subtitle={subtitle}
      banner={banner}
      actions={
        <div className="org-inline-actions">
          <a className="org-link" href="/org/user/departments">Back to departments</a>
          <button type="button" className="org-button danger" onClick={logout}>Logout</button>
        </div>
      }
    >
      <div className="org-details-list">
        <div className="org-details-list__item">
          <span>Access</span>
          <strong>
            {details.access
              ? `Role: ${details.access.access_role} • Email: ${details.user?.email || ''}`
              : '—'}
          </strong>
        </div>
        <div className="org-details-list__item">
          <span>Department</span>
          <strong>{details.department?.description || '—'}</strong>
        </div>
      </div>

      <section className="org-card" style={{ marginTop: 16 }}>
        <div className="org-row spread" style={{ marginBottom: 14 }}>
          <h2 className="org-card__title">Recent Activity</h2>
          <button
            type="button"
            className="org-button secondary"
            onClick={() => {
              const departmentId = params.get('department_id') || getOrgDepartmentId()
              if (departmentId) loadActivity(departmentId)
            }}
          >
            Refresh
          </button>
        </div>
        <OrgActivityFeed rows={activity} emptyText="No activity yet." />
      </section>
    </OrgShell>
  )
}
