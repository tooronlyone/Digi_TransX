import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import OrgShell from '../../../components/org/OrgShell'
import { orgAuthRequest, setOrgDepartmentId, setOrgDepartmentToken } from '../../../lib/orgPortal'

export default function OrgUserDepartmentLogin() {
  const [params] = useSearchParams()
  const [banner, setBanner] = useState(null)
  const [status, setStatus] = useState('Working...')

  useEffect(() => {
    async function run() {
      let departmentId = params.get('department_id') || ''
      const accessCode = params.get('access_code') || ''

      try {
        if (!departmentId && accessCode) {
          const resolved = await orgAuthRequest(`/api/org/departments/access-link/resolve?code=${encodeURIComponent(accessCode)}`, { method: 'GET' })
          departmentId = String(resolved?.department?.id || '')
        }
        if (!departmentId) {
          setBanner({ type: 'error', message: 'Missing department_id or access_code.' })
          setStatus('Failed.')
          return
        }
        setStatus('Requesting department token...')
        const response = await orgAuthRequest(`/api/org/departments/${encodeURIComponent(departmentId)}/session`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        if (!response?.department_token) {
          throw new Error('No department token returned.')
        }
        setOrgDepartmentToken(response.department_token)
        setOrgDepartmentId(departmentId)
        setStatus('Success. Redirecting...')
        window.location.replace(`/org/user/department-portal?department_id=${encodeURIComponent(departmentId)}`)
      } catch (error) {
        setBanner({ type: 'error', message: error.message || 'Department login failed.' })
        setStatus('Failed.')
      }
    }

    run()
  }, [params])

  return (
    <OrgShell
      title="Department Login"
      subtitle="Issuing a department-scoped token..."
      banner={banner}
      actions={<a className="org-link" href="/org/user/departments">Back</a>}
    >
      <section className="org-card">
        <div className="org-hint">{status}</div>
      </section>
    </OrgShell>
  )
}
