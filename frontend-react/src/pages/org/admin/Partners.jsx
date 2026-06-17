import { useEffect, useState } from 'react'
import OrgShell from '../../../components/org/OrgShell'
import { orgAuthRequest } from '../../../lib/orgPortal'

const EMPTY_PARTNER_FORM = {
  email: '',
  scope: 'scoped',
  manage_departments: false,
  manage_users: false,
  view_activity: false,
  status: 'active',
}

export default function OrgAdminPartners() {
  const [banner, setBanner] = useState(null)
  const [form, setForm] = useState(EMPTY_PARTNER_FORM)
  const [rows, setRows] = useState([])
  const [saving, setSaving] = useState(false)
  const [busyEmail, setBusyEmail] = useState('')

  async function load() {
    try {
      const response = await orgAuthRequest('/api/org/partners', { method: 'GET' })
      setRows(response.partners || [])
    } catch (error) {
      setRows([])
      setBanner({ type: 'error', message: error.message || 'Unable to load partners.' })
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.email.trim()) {
      setBanner({ type: 'error', message: 'Partner email is required.' })
      return
    }
    setSaving(true)
    setBanner(null)
    try {
      await orgAuthRequest('/api/org/partners', {
        method: 'POST',
        body: JSON.stringify({
          email: form.email.trim().toLowerCase(),
          status: form.status,
          permissions: {
            scope: form.scope,
            manage_departments: !!form.manage_departments,
            manage_users: !!form.manage_users,
            view_activity: !!form.view_activity,
          },
        }),
      })
      setForm(EMPTY_PARTNER_FORM)
      setBanner({ type: 'success', message: 'Partner saved.' })
      await load()
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to save partner.' })
    } finally {
      setSaving(false)
    }
  }

  async function toggleStatus(row) {
    const nextStatus = row.status === 'active' ? 'disabled' : 'active'
    const permissions = row.permissions || {}
    setBusyEmail(row.user?.email || '')
    setBanner(null)
    try {
      await orgAuthRequest('/api/org/partners', {
        method: 'POST',
        body: JSON.stringify({
          email: row.user?.email || '',
          status: nextStatus,
          permissions,
        }),
      })
      setBanner({ type: 'success', message: 'Partner updated.' })
      await load()
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to update partner.' })
    } finally {
      setBusyEmail('')
    }
  }

  return (
    <OrgShell
      title="Partners"
      subtitle="Level 1 partner accounts with scoped permissions."
      banner={banner}
      actions={<a className="org-link" href="/org/admin/dashboard">Back</a>}
    >
      <div className="org-grid">
        <div className="org-col-6">
          <section className="org-card">
            <h2 className="org-card__title">Add / Update Partner</h2>
            <p className="org-card__meta">Partner must already be registered and Gmail verified.</p>

            <form className="org-form-grid" onSubmit={handleSubmit}>
              <div className="org-field">
                <span>Partner email</span>
                <input
                  type="email"
                  placeholder="partner@example.com"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  required
                />
              </div>
              <div className="org-field half">
                <span>Scope</span>
                <select value={form.scope} onChange={(event) => setForm((prev) => ({ ...prev, scope: event.target.value }))}>
                  <option value="scoped">Scoped (requires dept access)</option>
                  <option value="all">All departments</option>
                </select>
              </div>
              <div className="org-field half">
                <span>Status</span>
                <select value={form.status} onChange={(event) => setForm((prev) => ({ ...prev, status: event.target.value }))}>
                  <option value="active">Active</option>
                  <option value="disabled">Disabled</option>
                </select>
              </div>
              <div className="org-field">
                <span>Permissions</span>
                <label className="org-hint"><input type="checkbox" checked={form.manage_departments} onChange={(event) => setForm((prev) => ({ ...prev, manage_departments: event.target.checked }))} style={{ width: 16, marginRight: 8 }} />Manage departments</label>
                <label className="org-hint"><input type="checkbox" checked={form.manage_users} onChange={(event) => setForm((prev) => ({ ...prev, manage_users: event.target.checked }))} style={{ width: 16, marginRight: 8 }} />Manage users</label>
                <label className="org-hint"><input type="checkbox" checked={form.view_activity} onChange={(event) => setForm((prev) => ({ ...prev, view_activity: event.target.checked }))} style={{ width: 16, marginRight: 8 }} />View activity</label>
              </div>
              <div className="org-col-12">
                <button type="submit" className="org-button primary" disabled={saving}>
                  <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-floppy-disk'}`}></i>
                  {saving ? 'Saving...' : 'Save partner'}
                </button>
              </div>
            </form>
          </section>
        </div>

        <div className="org-col-6">
          <section className="org-card">
            <div className="org-row spread" style={{ marginBottom: 14 }}>
              <h2 className="org-card__title">Partners List</h2>
              <button type="button" className="org-button secondary" onClick={load}>Refresh</button>
            </div>

            {!rows.length ? (
              <div className="org-empty-state">
                <i className="fas fa-handshake-slash"></i>
                <div>No partners yet.</div>
              </div>
            ) : (
              <ul className="org-list">
                {rows.map((row) => {
                  const permissions = row.permissions || {}
                  const tags = []
                  if (permissions.manage_departments) tags.push('departments')
                  if (permissions.manage_users) tags.push('users')
                  if (permissions.view_activity) tags.push('activity')
                  return (
                    <li key={row.id} className="org-card-list__item">
                      <div className="org-row spread">
                        <div className="org-row">
                          <strong>{row.user?.email || ''}</strong>
                          <span className={`org-pill ${row.status === 'active' ? 'success' : 'danger'}`}>{row.status}</span>
                          <span className="org-pill muted">scope {permissions.scope || 'scoped'}</span>
                          <span className="org-pill muted">{tags.length ? tags.join(', ') : 'no-perms'}</span>
                        </div>
                        <button
                          type="button"
                          className={`org-button ${row.status === 'active' ? 'danger' : 'primary'}`}
                          onClick={() => toggleStatus(row)}
                          disabled={busyEmail === (row.user?.email || '')}
                        >
                          <i className={`fas ${busyEmail === (row.user?.email || '') ? 'fa-spinner fa-spin' : row.status === 'active' ? 'fa-ban' : 'fa-check'}`}></i>
                          {row.status === 'active' ? 'Disable' : 'Enable'}
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </OrgShell>
  )
}
