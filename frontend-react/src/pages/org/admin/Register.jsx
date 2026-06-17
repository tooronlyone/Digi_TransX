import OrgRegisterPage from '../../../components/org/OrgRegisterPage'

export default function OrgAdminRegister() {
  return (
    <OrgRegisterPage
      role="transporter_admin"
      title="Create Transporter Admin Account"
      subtitle="Gmail verification is required before login."
      loginTo="/org/admin/login"
      loginLabel="Back to login"
    />
  )
}
