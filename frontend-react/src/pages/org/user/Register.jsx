import OrgRegisterPage from '../../../components/org/OrgRegisterPage'

export default function OrgUserRegister() {
  return (
    <OrgRegisterPage
      title="Job Holder Account"
      subtitle="Provider-neutral email verification is required, and organization registration is not available yet."
      loginTo="/org/user/login"
      loginLabel="Login"
    />
  )
}
