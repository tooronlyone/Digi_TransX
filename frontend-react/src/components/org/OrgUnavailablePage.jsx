import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import OrgShell from './OrgShell'

const LEGACY_ORG_STORAGE_KEYS = [
  'org_access_token',
  'org_department_token',
  'org_department_id',
]

export default function OrgUnavailablePage() {
  useEffect(() => {
    for (const key of LEGACY_ORG_STORAGE_KEYS) {
      localStorage.removeItem(key)
      sessionStorage.removeItem(key)
    }
  }, [])

  return (
    <OrgShell
      title="Organization portal unavailable"
      subtitle="The dedicated organization portal is Planned and is not currently available."
    >
      <section className="org-card">
        <h2 className="org-card__title">No organization account or session can be created here</h2>
        <p className="org-card__meta">
          Digi_TransX has no organization authentication backend yet. This page does not collect credentials, issue tokens, verify email, or provide access to organization-only pages.
        </p>
        <p className="org-card__meta">
          Companies and business service seekers should use the canonical Digi_TransX account flow. Valid addresses from Gmail, Outlook, Yahoo, company domains, and other email providers are eligible under the same provider-neutral policy.
        </p>
        <div className="org-inline-actions">
          <Link className="org-button primary" to="/login">Use standard sign in</Link>
          <Link className="org-link" to="/signup">Create a service-seeker account</Link>
        </div>
      </section>
    </OrgShell>
  )
}
