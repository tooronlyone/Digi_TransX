import OrgLoginPage from '../../../components/org/OrgLoginPage'

export default function OrgUserLogin() {
  return (
    <OrgLoginPage
      requiredRole="job_holder"
      title="Job Holder Login"
      subtitle="Login with your verified Gmail to see only authorized departments."
      dashboardTo="/org/user/departments"
      registerTo="/org/user/register"
      registerLabel="Create account"
      topLinks={[
        { to: '/org/admin/login', label: 'Admin Login' },
        { to: '/org/partner/login', label: 'Partner Login' },
      ]}
    />
  )
}
