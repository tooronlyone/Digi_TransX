import OrgLoginPage from '../../../components/org/OrgLoginPage'

export default function OrgAdminLogin() {
  return (
    <OrgLoginPage
      requiredRole="transporter_admin"
      title="Transporter Org Admin"
      subtitle="Login to manage transporter profile, departments, and access."
      dashboardTo="/org/admin/dashboard"
      registerTo="/org/admin/register"
      registerLabel="Create admin account"
      topLinks={[
        { to: '/org/user/login', label: 'Job Holder Login' },
        { to: '/org/partner/login', label: 'Partner Login' },
      ]}
    />
  )
}
