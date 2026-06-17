import { useEffect, useState } from 'react'
import OrgShell from '../../../components/org/OrgShell'
import { clearOrgPortalState, orgAuthRequest } from '../../../lib/orgPortal'

export default function OrgUserDepartments() {
  const [banner, setBanner] = useState(null)
  const [subtitle, setSubtitle] = useState('Only departments explicitly assigned to your email appear here.')
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  function logout() {
    clearOrgPortalState()
    window.location.replace('/org/user/login')
  }

  async function search(value = '') {
    setLoading(true)
    setBanner(null)
    try {
      const suffix = value ? `?q=${encodeURIComponent(value)}` : ''
      const response = await orgAuthRequest(`/api/org/departments/search${suffix}`, { method: 'GET' })
      setRows(response.departments || [])
    } catch (error) {
      setRows([])
      setBanner({ type: 'error', message: error.message || 'Unable to search departments.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const me = await orgAuthRequest('/api/org/auth/me', { method: 'GET' })
        if (me?.user?.role !== 'job_holder') {
          logout()
          return
        }
        setSubtitle(`Signed in as ${me.user.email}`)
        await search('')
      } catch {
        logout()
      }
    }

    bootstrap()
  }, [])

  return (
    <OrgShell
      title="Departments"
      subtitle={subtitle}
      banner={banner}
      actions={<button type="button" className="org-button danger" onClick={logout}>Logout</button>}
    >
      <section className="org-card">
        <div className="org-form-grid">
          <div className="org-field">
            <span>Search</span>
            <input
              type="text"
              placeholder="Type to filter departments..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  search(query.trim())
                }
              }}
            />
            <div className="org-field__hint">Unauthorized users see nothing by default.</div>
          </div>
          <div className="org-col-12 org-inline-actions">
            <button type="button" className="org-button primary" onClick={() => search(query.trim())}>
              Search
            </button>
            <button
              type="button"
              className="org-button secondary"
              onClick={() => {
                setQuery('')
                search('')
              }}
            >
              Clear
            </button>
          </div>
        </div>
      </section>

      <section className="org-card" style={{ marginTop: 16 }}>
        {loading ? (
          <div className="org-empty-state">
            <i className="fas fa-spinner fa-spin"></i>
            <div>Loading departments...</div>
          </div>
        ) : !rows.length ? (
          <div className="org-empty-state">
            <i className="fas fa-building-circle-xmark"></i>
            <div>No authorized departments found.</div>
          </div>
        ) : (
          <ul className="org-list">
            {rows.map((row) => (
              <li key={row.department.id} className="org-card-list__item">
                <div className="org-row spread">
                  <div className="org-row">
                    <strong>{row.department.name}</strong>
                    <span className="org-pill">{row.transporter?.display_name || 'Transporter'}</span>
                    <span className="org-pill muted">{row.access?.access_role || 'member'}</span>
                  </div>
                  <a className="org-button primary" href={`/org/user/department-login?department_id=${encodeURIComponent(row.department.id)}`}>
                    Department login
                  </a>
                </div>
                {row.department.description ? <div className="org-hint">{row.department.description}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </OrgShell>
  )
}
