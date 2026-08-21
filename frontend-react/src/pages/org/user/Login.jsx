import OrgLoginPage from '../../../components/org/OrgLoginPage'

export default function OrgUserLogin() {
  return (
    <OrgLoginPage
      requiredRole="job_holder"
      title="Job Holder Login"
      subtitle="Organization access requires an authorized account and will use provider-neutral verified email when verification is implemented."
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
