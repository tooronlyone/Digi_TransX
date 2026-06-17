import { OrgEmptyState } from './OrgShell'

function formatMetadata(metadata) {
  if (!metadata) return ''
  try {
    return JSON.stringify(metadata)
  } catch {
    return String(metadata)
  }
}

export default function OrgActivityFeed({ rows, emptyText = 'No activity yet.' }) {
  if (!rows?.length) {
    return <OrgEmptyState icon="fas fa-clock-rotate-left" text={emptyText} />
  }

  return (
    <ul className="org-list">
      {rows.map((row) => (
        <li key={row.id || `${row.action}-${row.created_at}`} className="org-card-list__item">
          <div className="org-row spread">
            <div className="org-row">
              <strong>{row.action}</strong>
              {row.department_id ? <span className="org-pill muted">dept {row.department_id}</span> : null}
            </div>
            <span className="org-pill muted">{row.created_at || 'Unknown time'}</span>
          </div>
          <div className="org-hint">
            {row.actor_email || 'unknown'}
            {row.metadata ? ` • ${formatMetadata(row.metadata)}` : ''}
          </div>
        </li>
      ))}
    </ul>
  )
}
