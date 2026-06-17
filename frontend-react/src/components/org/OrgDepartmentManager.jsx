import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { OrgBanner, OrgEmptyState } from './OrgShell'
import { orgAuthRequest } from '../../lib/orgPortal'

function TreeNode({ node, onSelect, showAccessAction }) {
  const content = (
    <div className="org-row spread">
      <div className="org-row">
        <strong>{node.name}</strong>
        <span className="org-pill muted">ID {node.id}</span>
      </div>
      {showAccessAction ? (
        <button type="button" className="org-button primary" onClick={() => onSelect(node)}>
          Manage Access
        </button>
      ) : null}
    </div>
  )

  if (node.children?.length) {
    return (
      <li>
        <details open>
          <summary>{content}</summary>
          {node.description ? <div className="org-hint">{node.description}</div> : null}
          <ul className="org-list org-tree">
            {node.children.map((child) => (
              <TreeNode key={child.id} node={child} onSelect={onSelect} showAccessAction={showAccessAction} />
            ))}
          </ul>
        </details>
      </li>
    )
  }

  return (
    <li className="org-card-list__item">
      {content}
      {node.description ? <div className="org-hint">{node.description}</div> : null}
    </li>
  )
}

export default function OrgDepartmentManager({
  canManageDepartments,
  canManageUsers,
  auxiliaryCreateAction = null,
  auxiliaryAccessAction = null,
}) {
  const [banner, setBanner] = useState(null)
  const [loading, setLoading] = useState(true)
  const [departments, setDepartments] = useState([])
  const [tree, setTree] = useState([])
  const [accessEntries, setAccessEntries] = useState([])
  const [selectedDepartment, setSelectedDepartment] = useState(null)
  const [accessLink, setAccessLink] = useState('')
  const [creating, setCreating] = useState(false)
  const [savingAccess, setSavingAccess] = useState(false)
  const [linkBusy, setLinkBusy] = useState('')
  const [departmentForm, setDepartmentForm] = useState({ name: '', parent_id: '', description: '' })
  const [accessForm, setAccessForm] = useState({ email: '', access_role: 'member', include_descendants: false })

  const parentOptions = useMemo(() => {
    const rows = []
    function walk(nodes, prefix = '') {
      nodes.forEach((node) => {
        rows.push({ id: node.id, label: `${prefix}${node.name} (ID ${node.id})` })
        if (node.children?.length) walk(node.children, `${prefix}— `)
      })
    }
    walk(tree)
    return rows
  }, [tree])

  async function loadDepartments() {
    setLoading(true)
    try {
      const response = await orgAuthRequest('/api/org/departments', { method: 'GET' })
      setDepartments(response.departments || [])
      setTree(response.tree || [])
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to load departments.' })
      setDepartments([])
      setTree([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDepartments()
  }, [])

  async function loadAccess(department) {
    if (!department || !canManageUsers) {
      setAccessEntries([])
      return
    }
    try {
      const response = await orgAuthRequest(`/api/org/departments/${department.id}/access`, { method: 'GET' })
      setAccessEntries(response.access || [])
    } catch (error) {
      setAccessEntries([])
      setBanner({ type: 'error', message: error.message || 'Unable to load department access.' })
    }
  }

  async function selectDepartment(node) {
    setSelectedDepartment(node)
    setAccessLink('')
    await loadAccess(node)
  }

  async function handleCreateDepartment(event) {
    event.preventDefault()
    if (!canManageDepartments) {
      setBanner({ type: 'error', message: 'No permission to manage departments.' })
      return
    }
    if (!departmentForm.name.trim()) {
      setBanner({ type: 'error', message: 'Department name is required.' })
      return
    }
    setCreating(true)
    setBanner(null)
    try {
      await orgAuthRequest('/api/org/departments', {
        method: 'POST',
        body: JSON.stringify({
          name: departmentForm.name.trim(),
          description: departmentForm.description.trim(),
          parent_id: departmentForm.parent_id ? Number(departmentForm.parent_id) : null,
        }),
      })
      setDepartmentForm({ name: '', parent_id: '', description: '' })
      setBanner({ type: 'success', message: 'Department created.' })
      await loadDepartments()
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to create department.' })
    } finally {
      setCreating(false)
    }
  }

  async function handleGrantAccess(event) {
    event.preventDefault()
    if (!canManageUsers) {
      setBanner({ type: 'error', message: 'No permission to manage users.' })
      return
    }
    if (!selectedDepartment) {
      setBanner({ type: 'error', message: 'Select a department first.' })
      return
    }
    if (!accessForm.email.trim()) {
      setBanner({ type: 'error', message: 'Email is required.' })
      return
    }
    setSavingAccess(true)
    setBanner(null)
    try {
      await orgAuthRequest(`/api/org/departments/${selectedDepartment.id}/access`, {
        method: 'POST',
        body: JSON.stringify({
          email: accessForm.email.trim().toLowerCase(),
          access_role: accessForm.access_role,
          include_descendants: !!accessForm.include_descendants,
        }),
      })
      setAccessForm({ email: '', access_role: 'member', include_descendants: false })
      setBanner({ type: 'success', message: 'Access updated.' })
      await loadAccess(selectedDepartment)
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Unable to update access.' })
    } finally {
      setSavingAccess(false)
    }
  }

  async function handleLoadAccessLink(rotate = false) {
    if (!selectedDepartment) {
      setBanner({ type: 'error', message: 'Select a department first.' })
      return
    }
    setLinkBusy(rotate ? 'rotate' : 'show')
    setBanner(null)
    try {
      const endpoint = rotate
        ? `/api/org/departments/${selectedDepartment.id}/access-link/rotate`
        : `/api/org/departments/${selectedDepartment.id}/access-link`
      const response = await orgAuthRequest(endpoint, {
        method: rotate ? 'POST' : 'GET',
        body: rotate ? JSON.stringify({}) : undefined,
      })
      setAccessLink(response.link_path || '')
      if (rotate) {
        setBanner({ type: 'success', message: 'Access link rotated.' })
      }
    } catch (error) {
      setAccessLink('')
      setBanner({ type: 'error', message: error.message || 'Unable to load access link.' })
    } finally {
      setLinkBusy('')
    }
  }

  return (
    <div className="org-grid">
      <div className="org-col-12">
        <OrgBanner banner={banner} />
      </div>

      <div className="org-col-6">
        <section className="org-card org-stack">
          <div className="org-row spread">
            <div>
              <h2 className="org-card__title">Create Department</h2>
              <p className="org-card__meta">Build department structure first, then assign job holders by email.</p>
            </div>
            {auxiliaryCreateAction}
          </div>

          <form className="org-form-grid" onSubmit={handleCreateDepartment}>
            <div className="org-field">
              <span>Name</span>
              <input
                type="text"
                placeholder="Dispatch, HR, Finance..."
                value={departmentForm.name}
                onChange={(event) => setDepartmentForm((prev) => ({ ...prev, name: event.target.value }))}
                required
              />
            </div>
            <div className="org-field">
              <span>Parent</span>
              <select
                value={departmentForm.parent_id}
                onChange={(event) => setDepartmentForm((prev) => ({ ...prev, parent_id: event.target.value }))}
              >
                <option value="">No parent</option>
                {parentOptions.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </div>
            <div className="org-field">
              <span>Description</span>
              <textarea
                placeholder="Optional"
                value={departmentForm.description}
                onChange={(event) => setDepartmentForm((prev) => ({ ...prev, description: event.target.value }))}
              />
            </div>
            <div className="org-col-12">
              <button type="submit" className="org-button primary" disabled={creating || !canManageDepartments}>
                <i className={`fas ${creating ? 'fa-spinner fa-spin' : 'fa-plus'}`}></i>
                {creating ? 'Creating...' : 'Create Department'}
              </button>
              {!canManageDepartments ? (
                <div className="org-field__hint warning">This account cannot create or edit departments.</div>
              ) : null}
            </div>
          </form>
        </section>

        <section className="org-card" style={{ marginTop: 16 }}>
          <h2 className="org-card__title">Departments Tree</h2>
          <p className="org-card__meta">Select a department to manage user access and open department links.</p>

          {loading ? (
            <OrgEmptyState icon="fas fa-spinner fa-spin" text="Loading departments..." />
          ) : !departments.length ? (
            <OrgEmptyState text="No departments yet." />
          ) : (
            <ul className="org-list org-tree">
              {tree.map((node) => (
                <TreeNode key={node.id} node={node} onSelect={selectDepartment} showAccessAction={true} />
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="org-col-6">
        <section className="org-card org-stack">
          <div className="org-row spread">
            <div>
              <h2 className="org-card__title">Department Access</h2>
              <p className="org-card__meta">
                {selectedDepartment
                  ? `Managing access for ${selectedDepartment.name} (ID ${selectedDepartment.id})`
                  : 'Select a department to manage access.'}
              </p>
            </div>
            {auxiliaryAccessAction}
          </div>

          {canManageUsers ? (
            <form className="org-form-grid" onSubmit={handleGrantAccess}>
              <div className="org-field">
                <span>Job holder email</span>
                <input
                  type="email"
                  placeholder="employee@example.com"
                  value={accessForm.email}
                  onChange={(event) => setAccessForm((prev) => ({ ...prev, email: event.target.value }))}
                />
              </div>
              <div className="org-field half">
                <span>Access role</span>
                <select
                  value={accessForm.access_role}
                  onChange={(event) => setAccessForm((prev) => ({ ...prev, access_role: event.target.value }))}
                >
                  <option value="member">Member</option>
                  <option value="manager">Manager</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="org-field half">
                <span>Scope</span>
                <label className="org-hint" style={{ marginTop: 0 }}>
                  <input
                    type="checkbox"
                    checked={accessForm.include_descendants}
                    onChange={(event) => setAccessForm((prev) => ({ ...prev, include_descendants: event.target.checked }))}
                    style={{ width: 16, marginRight: 8 }}
                  />
                  Include sub-departments
                </label>
              </div>
              <div className="org-col-12">
                <button type="submit" className="org-button primary" disabled={savingAccess || !selectedDepartment}>
                  <i className={`fas ${savingAccess ? 'fa-spinner fa-spin' : 'fa-user-lock'}`}></i>
                  {savingAccess ? 'Saving...' : 'Grant / Update Access'}
                </button>
              </div>
            </form>
          ) : (
            <OrgEmptyState icon="fas fa-user-lock" text="This account cannot manage department user access." />
          )}

          {selectedDepartment ? (
            <div className="org-card-list__item">
              <div className="org-row spread">
                <strong>Access Link</strong>
                <div className="org-inline-actions">
                  <button type="button" className="org-button secondary" onClick={() => handleLoadAccessLink(false)} disabled={!!linkBusy}>
                    <i className={`fas ${linkBusy === 'show' ? 'fa-spinner fa-spin' : 'fa-link'}`}></i>
                    Show link
                  </button>
                  <button type="button" className="org-button danger" onClick={() => handleLoadAccessLink(true)} disabled={!!linkBusy}>
                    <i className={`fas ${linkBusy === 'rotate' ? 'fa-spinner fa-spin' : 'fa-rotate'}`}></i>
                    Rotate link
                  </button>
                </div>
              </div>
              <div className="org-hint">{accessLink || 'No access link loaded yet.'}</div>
            </div>
          ) : null}

          {canManageUsers ? (
            <div>
              <h3 className="org-card__title">Current Access Entries</h3>
              {!selectedDepartment ? (
                <OrgEmptyState icon="fas fa-diagram-project" text="Select a department to see access records." />
              ) : accessEntries.length ? (
                <ul className="org-list">
                  {accessEntries.map((entry) => (
                    <li key={entry.id} className="org-card-list__item">
                      <div className="org-row">
                        <strong>{entry.user_email}</strong>
                        <span className="org-pill">{entry.access_role}</span>
                        <span className={`org-pill ${entry.status === 'active' ? 'success' : 'muted'}`}>{entry.status}</span>
                        {entry.include_descendants ? <span className="org-pill warning">subtree</span> : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <OrgEmptyState icon="fas fa-user-slash" text="No access entries yet." />
              )}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
