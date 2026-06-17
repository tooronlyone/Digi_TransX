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
  let classes = 'bg-amber-50 text-amber-700 border-amber-200'
  if (value === 'completed' || value === 'delivered') classes = 'bg-emerald-50 text-emerald-700 border-emerald-200'
  else if (value === 'cancelled' || value === 'failed') classes = 'bg-red-50 text-red-700 border-red-200'
  else if (['working', 'assigned', 'confirmed', 'in_progress', 'in_transit', 'approved'].includes(value)) {
    classes = 'bg-blue-50 text-blue-700 border-blue-200'
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${classes}`}>
      {formatStatus(status)}
    </span>
  )
}

export function StateMessage({ type = 'empty', title, children }) {
  const styles = {
    loading: 'border-blue-200 bg-blue-50 text-blue-700',
    error: 'border-red-200 bg-red-50 text-red-700',
    empty: 'border-slate-200 bg-white text-slate-600',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
    info: 'border-slate-200 bg-slate-50 text-slate-700',
  }
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
    <div className={`rounded-lg border px-4 py-3 text-sm ${styles[type] || styles.empty}`}>
      <div className="flex items-start gap-3">
        <i className={`fas ${icon} mt-0.5`} aria-hidden="true"></i>
        <div>
          {title && <div className="font-semibold">{title}</div>}
          {children && <div className={title ? 'mt-1 text-current/90' : ''}>{children}</div>}
        </div>
      </div>
    </div>
  )
}

export function PageTitle({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 border-b border-slate-200 pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function SectionCard({ title, icon, actions, children, className = '' }) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {title && (
            <h2 className="text-base font-semibold text-slate-900">
              {icon && <i className={`fas ${icon} mr-2 text-blue-600`} aria-hidden="true"></i>}
              {title}
            </h2>
          )}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function PrimaryButton({ children, className = '', ...props }) {
  return (
    <button
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function SecondaryButton({ children, className = '', ...props }) {
  return (
    <button
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
