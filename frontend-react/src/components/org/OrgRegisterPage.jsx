import { Link } from 'react-router-dom'
import OrgShell from './OrgShell'

export default function OrgRegisterPage({ title, subtitle, loginTo, loginLabel = 'Back to login' }) {
  return (
    <OrgShell
      title={title}
      subtitle={subtitle}
      actions={<Link className="org-link" to={loginTo}>{loginLabel}</Link>}
    >
      <section className="org-card">
        <h2 className="org-card__title">Organization registration is not available yet</h2>
        <p className="org-card__meta">
          Digi_TransX will require provider-neutral email verification before an organization account can be created. The verification backend is not implemented, so this flow remains closed and creates no account.
        </p>
        <p className="org-card__meta">
          When implemented, valid addresses from Gmail, Outlook, Yahoo, company domains, and other email providers will be eligible under the same verification policy.
        </p>
      </section>
    </OrgShell>
  )
}
