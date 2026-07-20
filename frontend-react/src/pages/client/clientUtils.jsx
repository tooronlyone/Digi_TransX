export const TRUCK_TYPES = [
  'Milk Tanker',
  'Refrigerated Truck',
  'Dumper Truck',
  'Cement Bulker',
  'Pneumatic Truck',
  'Container Carrier',
  'Oil Tanker',
  'LiveStock Truck',
  'Cargo Truck',
  'Water Tanker',
  'Garbage Truck',
]

export const GOODS_TYPES = [
  'General goods',
  'Milk',
  'Water',
  'FMCG',
  'Electronics',
  'Pharmaceuticals',
  'Chemicals',
  'Perishables',
  'Construction Material',
  'Other',
]

const ACTIVE_STATUSES = new Set([
  'pending',
  'working',
  'confirmed',
  'assigned',
  'approved',
  'in_progress',
  'in_transit',
  'active',
])

const COMPLETE_STATUSES = new Set(['completed', 'delivered'])

let cachedCsrfToken = ''

export function normalizeStatus(value) {
  return String(value || 'pending').trim().toLowerCase()
}

export function isActiveStatus(value) {
  return ACTIVE_STATUSES.has(normalizeStatus(value))
}

export function isCompletedStatus(value) {
  return COMPLETE_STATUSES.has(normalizeStatus(value))
}

export function formatStatus(value) {
  return normalizeStatus(value).replace(/_/g, ' ')
}

export function formatMoney(value) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return 'PKR 0'
  return `PKR ${number.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

export function formatNumber(value, digits = 1) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return '0'
  return number.toFixed(digits)
}

export function formatDate(value, options) {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleDateString('en-PK', options || {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch (_) {
    return String(value)
  }
}

export function formatDateTime(value) {
  return formatDate(value, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export async function getCsrfToken() {
  if (cachedCsrfToken) return cachedCsrfToken
  const stored = sessionStorage.getItem('csrf_token')
  if (stored) {
    cachedCsrfToken = stored
    return cachedCsrfToken
  }
  const response = await fetch('/auth/csrf-token', { credentials: 'same-origin' })
  const json = await response.json().catch(() => ({}))
  cachedCsrfToken = String(json.csrf_token || '')
  if (cachedCsrfToken) sessionStorage.setItem('csrf_token', cachedCsrfToken)
  return cachedCsrfToken
}

async function unwrapResponse(response) {
  const json = await response.json().catch(() => ({}))
  if (!response.ok || !json || json.success === false) {
    throw new Error(json?.message || 'Request failed. Please try again.')
  }
  if (json.csrf_token) {
    cachedCsrfToken = String(json.csrf_token)
    sessionStorage.setItem('csrf_token', cachedCsrfToken)
  }
  return json
}

export async function apiGet(url) {
  const response = await fetch(url, { credentials: 'same-origin' })
  return unwrapResponse(response)
}

export async function apiSend(url, payload = {}, method = 'POST') {
  const csrf = await getCsrfToken()
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    body: JSON.stringify(payload),
  })
  return unwrapResponse(response)
}

export function StatusBadge({ status }) {
  const value = normalizeStatus(status)
  let modifier = 'dashboard-status-pill--available'
  if (value === 'cancelled' || value === 'failed') modifier = 'dashboard-status-pill--inactive'
  else if (['working', 'assigned', 'confirmed', 'in_progress', 'in_transit', 'approved'].includes(value)) modifier = 'dashboard-status-pill--on_job'
  else if (value && value !== 'completed' && value !== 'delivered') modifier = 'dashboard-status-pill--maintenance'
  return (
    <span className={`dashboard-status-pill ${modifier}`}>
      {formatStatus(status)}
    </span>
  )
}

export function StateMessage({ type = 'empty', title, children }) {
  const icon = type === 'loading'
    ? 'fa-spinner fa-spin'
    : type === 'error'
      ? 'fa-circle-exclamation'
      : type === 'success'
        ? 'fa-circle-check'
        : type === 'warning'
          ? 'fa-triangle-exclamation'
          : 'fa-circle-info'

  return (
    <div className="t-page-card" style={{ padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <i className={`fas ${icon}`} aria-hidden="true" style={{ color: 'var(--accent-primary)', marginTop: 4 }}></i>
        <div>
          {title && <div style={{ fontWeight: 700, color: 'var(--accent-secondary)' }}>{title}</div>}
          {children && <div style={{ marginTop: title ? 4 : 0, color: type === 'error' ? 'var(--error)' : 'var(--text-secondary)' }}>{children}</div>}
        </div>
      </div>
    </div>
  )
}

export function PageTitle({ title, subtitle, actions }) {
  return (
    <div className="dashboard-page-title" style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-end' }}>
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{actions}</div>}
    </div>
  )
}

export function SectionCard({ title, icon, actions, children, className = '' }) {
  return (
    <section className={`t-page-card ${className}`} style={{ marginBottom: 28 }}>
      {(title || actions) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'center', marginBottom: 18 }}>
          {title && (
            <h2 style={{ margin: 0 }}>
              {icon && <i className={`fas ${icon}`} style={{ marginRight: 10, color: 'var(--accent-primary)' }} aria-hidden="true"></i>}
              {title}
            </h2>
          )}
          {actions && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function PrimaryButton({ children, className = '', ...props }) {
  return (
    <button className={`dashboard-action-small ${className}`} {...props}>
      {children}
    </button>
  )
}

export function SecondaryButton({ children, className = '', ...props }) {
  return (
    <button className={`dashboard-action-small ${className}`} style={{ background: 'var(--hover-bg)', color: 'var(--text-secondary)', boxShadow: 'none' }} {...props}>
      {children}
    </button>
  )
}
