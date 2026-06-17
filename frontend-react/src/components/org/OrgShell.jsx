import '../../styles/org-portal.css'

export function OrgBanner({ banner }) {
  if (!banner?.message) return null
  return <div className={`org-banner ${banner.type || 'info'}`}>{banner.message}</div>
}

export function OrgEmptyState({ icon = 'fa-regular fa-folder-open', text }) {
  return (
    <div className="org-empty-state">
      <i className={icon}></i>
      <div>{text}</div>
    </div>
  )
}

export default function OrgShell({ title, subtitle, actions = null, banner = null, children }) {
  return (
    <div className="org-portal">
      <div className="org-portal__container">
        <div className="org-portal__header">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p className="org-portal__subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="org-portal__actions">{actions}</div> : null}
        </div>

        <OrgBanner banner={banner} />
        {children}
      </div>
    </div>
  )
}
