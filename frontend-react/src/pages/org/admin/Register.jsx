import OrgRegisterPage from '../../../components/org/OrgRegisterPage'

export default function OrgAdminRegister() {
  return (
    <OrgRegisterPage
      title="Create Transporter Admin Account"
      subtitle="Provider-neutral email verification is required, and organization registration is not available yet."
      loginTo="/org/admin/login"
      loginLabel="Back to login"
    />
  )
}
