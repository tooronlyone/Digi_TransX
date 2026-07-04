// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = {
  full_name: '',
  email: '',
  cnic: '',
  organization_role: '',
}

function formatDate(value) {
  if (!value) return 'Never'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export default function Organization() {
  const api = useApi()
  const [roles, setRoles] = useState([])
  const [members, setMembers] = useState([])
  const [summary, setSummary] = useState({ total_members: 0, active_members: 0, inactive_members: 0, role_counts: {} })
  const [form, setForm] = useState(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [busyMemberId, setBusyMemberId] = useState(0)
  const [toast, setToast] = useState(null)
  const [credentials, setCredentials] = useState(null)

  function showToast(message, type = 'success') {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3200)
  }

  function load() {
    setLoading(true)
    Promise.allSettled([
      api.get('/api/organization/roles'),
      api.get('/api/organization/members'),
    ])
      .then(([rolesRes, membersRes]) => {
        if (rolesRes.status === 'fulfilled' && rolesRes.value?.success) {
          setRoles(rolesRes.value.roles || [])
          setForm((prev) => ({
            ...prev,
            organization_role: prev.organization_role || rolesRes.value.roles?.[0]?.value || '',
          }))
        } else {
          setRoles([])
          showToast(
            rolesRes.status === 'rejected'
              ? (rolesRes.reason?.message || 'Could not load assignable roles')
              : 'Could not load assignable roles',
            'error',
          )
        }
        if (membersRes.status === 'fulfilled' && membersRes.value?.success) {
          setMembers(membersRes.value.members || [])
          setSummary(membersRes.value.summary || { total_members: 0, active_members: 0, inactive_members: 0, role_counts: {} })
        } else if (membersRes.status === 'rejected') {
          showToast(membersRes.reason?.message || 'Could not load team members', 'error')
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const activeMembers = useMemo(
    () => members.filter((member) => (member.status || '').toLowerCase() === 'active'),
    [members],
  )

  async function copyText(value, label = 'Text') {
    try {
      await navigator.clipboard.writeText(value)
      showToast(`${label} copied`)
    } catch {
      showToast(`Could not copy ${label.toLowerCase()}`, 'error')
    }
  }

  async function handleCreateMember(event) {
    event.preventDefault()
    if (!form.full_name || !form.email || !form.cnic || !form.organization_role) {
      showToast('Please fill all required fields', 'error')
      return
    }
    setSubmitting(true)
    try {
      const response = await api.post('/api/organization/members', form)
      if (!response.success) {
        showToast(response.message || 'Could not create organization user', 'error')
        return
      }
      setCredentials(response.credentials || null)
      setForm({
        ...EMPTY_FORM,
        organization_role: form.organization_role,
      })
      showToast('Organization user created successfully')
      load()
    } catch (error) {
      showToast(error.message || 'Could not create organization user', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  async function toggleStatus(member) {
    const nextStatus = (member.status || '').toLowerCase() === 'active' ? 'inactive' : 'active'
    setBusyMemberId(member.id)
    try {
      const response = await api.put(`/api/organization/members/${member.id}/status`, { status: nextStatus })
      if (response.success) {
        showToast(`Member ${nextStatus === 'active' ? 'activated' : 'deactivated'}`)
        load()
      } else {
        showToast(response.message || 'Status update failed', 'error')
      }
    } catch (error) {
      showToast(error.message || 'Status update failed', 'error')
    } finally {
      setBusyMemberId(0)
    }
  }

  async function resetCredentials(member) {
    setBusyMemberId(member.id)
    try {
      const response = await api.post(`/api/organization/members/${member.id}/reset-credentials`, {})
      if (response.success) {
        setCredentials(response.credentials || null)
        showToast('New credentials generated')
        load()
      } else {
        showToast(response.message || 'Credential reset failed', 'error')
      }
    } catch (error) {
      showToast(error.message || 'Credential reset failed', 'error')
    } finally {
      setBusyMemberId(0)
    }
  }

  return (
    <TransporterLayout>
      <div className="page-organization">
        {toast && (
          <div className={`organization-toast ${toast.type === 'error' ? 'error' : 'success'}`}>
            {toast.message}
          </div>
        )}

        <div className="top-bar">
          <div className="page-title">
            <h1>Organization Access</h1>
            <p>Create restricted team logins so every staff member lands only on their assigned work area.</p>
          </div>
        </div>

        <div className="organization-summary">
          <div className="organization-summary-card">
            <div className="summary-icon summary-team"><i className="fas fa-users"></i></div>
            <div>
              <h3>{loading ? '...' : summary.total_members}</h3>
              <p>Total Team Members</p>
            </div>
          </div>
          <div className="organization-summary-card">
            <div className="summary-icon summary-active"><i className="fas fa-user-check"></i></div>
            <div>
              <h3>{loading ? '...' : summary.active_members}</h3>
              <p>Active Access Accounts</p>
            </div>
          </div>
          <div className="organization-summary-card">
            <div className="summary-icon summary-roles"><i className="fas fa-user-shield"></i></div>
            <div>
              <h3>{roles.length}</h3>
              <p>Assignable Roles</p>
            </div>
          </div>
          <div className="organization-summary-card">
            <div className="summary-icon summary-security"><i className="fas fa-lock"></i></div>
            <div>
              <h3>Single Field</h3>
              <p>Each user sees only their assigned module</p>
            </div>
          </div>
        </div>

        <div className="organization-layout">
          <section className="organization-card organization-form-card">
            <div className="card-heading">
              <h2>Create Team User</h2>
              <p>Provide staff details and Digi_TransX will generate a separate login ID and password.</p>
            </div>

            <form className="organization-form" onSubmit={handleCreateMember}>
              <div className="organization-form-grid">
                <label className="organization-field">
                  <span>Team Member Name</span>
                  <input
                    type="text"
                    placeholder="Enter full name"
                    value={form.full_name}
                    onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
                    required
                  />
                </label>
                <label className="organization-field">
                  <span>Email Address</span>
                  <input
                    type="email"
                    placeholder="member@example.com"
                    value={form.email}
                    onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                    required
                  />
                </label>
                <label className="organization-field">
                  <span>CNIC Number</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="4210112345671"
                    value={form.cnic}
                    onChange={(event) => setForm((prev) => ({ ...prev, cnic: event.target.value.replace(/\D/g, '').slice(0, 13) }))}
                    required
                  />
                </label>
                <label className="organization-field">
                  <span>Assigned Role</span>
                  <select
                    value={form.organization_role}
                    onChange={(event) => setForm((prev) => ({ ...prev, organization_role: event.target.value }))}
                    required
                  >
                    <option value="">Select a role</option>
                    {roles.map((role) => (
                      <option key={role.value} value={role.value}>{role.label}</option>
                    ))}
                  </select>
                  {!roles.length && (
                    <small className="organization-field-hint">Roles could not be loaded. Refresh after your session is verified.</small>
                  )}
                </label>
              </div>

              <div className="organization-submit-row">
                <button type="submit" className="organization-primary-btn" disabled={submitting || !roles.length}>
                  <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-user-plus'}`}></i>
                  {submitting ? 'Generating Access...' : 'Generate Login Credentials'}
                </button>
                <p className="organization-form-note">The generated login will work on the normal transporter login screen.</p>
              </div>
            </form>
          </section>

          <aside className="organization-card organization-security-card">
            <div className="card-heading">
              <h2>How It Works</h2>
              <p>Separate staff logins keep your owner account private and reduce unnecessary visibility.</p>
            </div>

            <div className="security-steps">
              <div className="security-step">
                <div className="step-number">1</div>
                <div>
                  <strong>Create the user</strong>
                  <p>Add name, email, CNIC, and assign the exact operational role.</p>
                </div>
              </div>
              <div className="security-step">
                <div className="step-number">2</div>
                <div>
                  <strong>Share credentials securely</strong>
                  <p>The system generates a dedicated username and password for that team member only.</p>
                </div>
              </div>
              <div className="security-step">
                <div className="step-number">3</div>
                <div>
                  <strong>Restricted login flow</strong>
                  <p>After login, the member lands directly on the assigned field and the sidebar is limited.</p>
                </div>
              </div>
            </div>
          </aside>
        </div>

        <section className="organization-card organization-role-access-card">
          <div className="card-heading">
            <h2>Available Role Access</h2>
            <p>Pick the exact work area for each team member so they only land on their assigned module.</p>
          </div>

          <div className="organization-role-grid">
            {roles.map((role) => (
              <article key={role.value} className="role-chip-card">
                <strong>{role.label}</strong>
                <p>{role.description}</p>
                <span>{role.default_route}</span>
              </article>
            ))}
          </div>
        </section>

        <section className="organization-card organization-members-card">
          <div className="card-heading organization-members-heading">
            <div>
              <h2>Organization Team</h2>
              <p>Review active users, reset credentials, or deactivate access when someone leaves the team.</p>
            </div>
            <div className="organization-members-meta">
              <span>{activeMembers.length} active users</span>
              <span>{members.length} total records</span>
            </div>
          </div>

          {loading ? (
            <div className="organization-empty-state">
              <i className="fas fa-spinner fa-spin"></i>
              <p>Loading organization members...</p>
            </div>
          ) : members.length === 0 ? (
            <div className="organization-empty-state">
              <i className="fas fa-users-slash"></i>
              <p>No team user has been created yet.</p>
            </div>
          ) : (
            <>
              <div className="organization-member-grid">
                {members.map((member) => (
                  <article key={member.id} className={`organization-member-card ${member.status !== 'active' ? 'is-inactive' : ''}`}>
                    <div className="member-card-header">
                      <div>
                        <h3>{member.full_name}</h3>
                        <p>{member.organization_role_label}</p>
                      </div>
                      <span className={`member-status ${member.status === 'active' ? 'active' : 'inactive'}`}>
                        {member.status}
                      </span>
                    </div>

                    <div className="member-card-body">
                      <div className="member-detail-row">
                        <span>Email</span>
                        <strong>{member.email}</strong>
                      </div>
                      <div className="member-detail-row">
                        <span>Login ID</span>
                        <strong>{member.username}</strong>
                      </div>
                      <div className="member-detail-row">
                        <span>CNIC</span>
                        <strong>{member.cnic}</strong>
                      </div>
                      <div className="member-detail-row">
                        <span>Default Route</span>
                        <strong>{member.default_route}</strong>
                      </div>
                      <div className="member-detail-row">
                        <span>Last Login</span>
                        <strong>{formatDate(member.last_login_at)}</strong>
                      </div>
                    </div>

                    <div className="member-card-actions">
                      <button
                        type="button"
                        className="organization-secondary-btn"
                        onClick={() => copyText(member.username, 'Login ID')}
                      >
                        <i className="fas fa-copy"></i> Copy Login ID
                      </button>
                      <button
                        type="button"
                        className="organization-secondary-btn"
                        onClick={() => resetCredentials(member)}
                        disabled={busyMemberId === member.id}
                      >
                        <i className={`fas ${busyMemberId === member.id ? 'fa-spinner fa-spin' : 'fa-key'}`}></i>
                        Reset Password
                      </button>
                      <button
                        type="button"
                        className={`organization-secondary-btn ${member.status === 'active' ? 'danger' : 'success'}`}
                        onClick={() => toggleStatus(member)}
                        disabled={busyMemberId === member.id}
                      >
                        <i className={`fas ${busyMemberId === member.id ? 'fa-spinner fa-spin' : member.status === 'active' ? 'fa-user-slash' : 'fa-user-check'}`}></i>
                        {member.status === 'active' ? 'Deactivate' : 'Activate'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>

              <div className="organization-owner-note">
                <i className="fas fa-circle-info"></i>
                Team members can use the main login page with their generated login ID and password. They will be routed only to their assigned module.
              </div>
            </>
          )}
        </section>

        {credentials && (
          <div className="organization-credentials-overlay">
            <div className="organization-credentials-modal">
              <button type="button" className="credentials-close" onClick={() => setCredentials(null)}>
                <i className="fas fa-times"></i>
              </button>
              <h2>Generated Login Credentials</h2>
              <p>Share these details securely. The password is shown only in this confirmation state.</p>

              <div className="credentials-box">
                <div>
                  <span>Login ID</span>
                  <strong>{credentials.login_id}</strong>
                </div>
                <button type="button" onClick={() => copyText(credentials.login_id, 'Login ID')}>
                  <i className="fas fa-copy"></i>
                </button>
              </div>

              <div className="credentials-box">
                <div>
                  <span>Password</span>
                  <strong>{credentials.password}</strong>
                </div>
                <button type="button" onClick={() => copyText(credentials.password, 'Password')}>
                  <i className="fas fa-copy"></i>
                </button>
              </div>

              <div className="credentials-box muted">
                <div>
                  <span>Email</span>
                  <strong>{credentials.email}</strong>
                </div>
              </div>

              <div className="credentials-actions">
                <button
                  type="button"
                  className="organization-primary-btn"
                  onClick={async () => {
                    await copyText(`Login ID: ${credentials.login_id}\nPassword: ${credentials.password}`, 'Credentials')
                  }}
                >
                  <i className="fas fa-copy"></i> Copy Both
                </button>
                <button type="button" className="organization-secondary-btn" onClick={() => setCredentials(null)}>
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </TransporterLayout>
  )
}
