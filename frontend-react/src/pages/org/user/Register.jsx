import OrgRegisterPage from '../../../components/org/OrgRegisterPage'

export default function OrgUserRegister() {
  return (
    <OrgRegisterPage
      role="job_holder"
      title="Job Holder Account"
      subtitle="Create a verified Gmail profile to search and access only the departments explicitly assigned to you."
      loginTo="/org/user/login"
      loginLabel="Login"
    />
  )
}
