export async function getCsrf() {
  const cached = sessionStorage.getItem('csrf_token')
  if (cached) return cached
  try {
    const res = await fetch('/auth/csrf-token', { credentials: 'include' })
    const data = await res.json()
    const token = data?.csrf_token || ''
    if (token) sessionStorage.setItem('csrf_token', token)
    return token
  } catch { return '' }
}

export const PRODUCT_UNITS = [
  { value: 'piece', label: 'Piece', short: 'pcs' },
  { value: 'pair', label: 'Pair', short: 'pairs' },
  { value: 'set', label: 'Set', short: 'sets' },
  { value: 'dozen', label: 'Dozen', short: 'dozen' },
  { value: 'pack', label: 'Pack', short: 'packs' },
  { value: 'box', label: 'Box', short: 'boxes' },
  { value: 'bottle', label: 'Bottle', short: 'bottles' },
  { value: 'can', label: 'Can', short: 'cans' },
  { value: 'liter', label: 'Liter', short: 'L' },
  { value: 'milliliter', label: 'Milliliter', short: 'mL' },
  { value: 'gallon', label: 'Gallon', short: 'gal' },
  { value: 'kilogram', label: 'Kilogram', short: 'kg' },
  { value: 'gram', label: 'Gram', short: 'g' },
  { value: 'meter', label: 'Meter', short: 'm' },
  { value: 'foot', label: 'Foot', short: 'ft' },
]

export function unitLabel(unit, short = false) {
  const match = PRODUCT_UNITS.find(item => item.value === unit)
  return match ? (short ? match.short : match.label) : (short ? 'pcs' : 'Piece')
}

export function unitAllowsDecimals(unit) {
  return ['liter', 'milliliter', 'gallon', 'kilogram', 'gram', 'meter', 'foot'].includes(unit)
}

export function getUser() {
  try { return JSON.parse(sessionStorage.getItem('user') || '{}') } catch { return {} }
}

export function fmtCurrency(n) {
  return Number(n || 0).toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-PK', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch { return iso }
}

export function fmtDateTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-PK', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}
