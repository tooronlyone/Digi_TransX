import OrgDepartmentManager from '../../../components/org/OrgDepartmentManager'
import OrgShell from '../../../components/org/OrgShell'

export default function OrgAdminDepartments() {
  return (
    <OrgShell
      title="Departments"
      subtitle="Departments are invisible unless a job holder email is explicitly allowed."
      actions={<a className="org-link" href="/org/admin/dashboard">Back</a>}
    >
      <OrgDepartmentManager
        canManageDepartments={true}
        canManageUsers={true}
        auxiliaryCreateAction={<a className="org-link" href="/org/admin/transporter-profile">Edit profile</a>}
        auxiliaryAccessAction={<a className="org-link" href="/org/admin/activity">View activity</a>}
      />
    </OrgShell>
  )
}
