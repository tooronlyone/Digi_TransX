import OrgLoginPage from '../../../components/org/OrgLoginPage'

export default function OrgPartnerLogin() {
  return (
    <OrgLoginPage
      requiredRole="partner"
      title="Partner Login"
      subtitle="Login with your verified partner account to access scoped organization tools."
      dashboardTo="/org/partner/dashboard"
      topLinks={[
        { to: '/org/user/login', label: 'Job Holder Login' },
        { to: '/org/admin/login', label: 'Admin Login' },
      ]}
    />
  )
}
