// Exact decimal helpers for financial display previews. Authoritative charges remain server-calculated.
export function minorUnits(value, scale = 2) {
  const match = String(value ?? '').match(/^(\d+)(?:\.(\d+))?$/)
  if (!match || (match[2]?.length || 0) > scale) return 0n
  return BigInt(match[1]) * 10n ** BigInt(scale) + BigInt((match[2] || '').padEnd(scale, '0'))
}
export function decimalUnits(value, scale = 2) {
  const sign = value < 0n ? '-' : ''
  const absolute = value < 0n ? -value : value
  const factor = 10n ** BigInt(scale)
  return `${sign}${absolute / factor}.${String(absolute % factor).padStart(scale, '0')}`
}
export function productMoney(amount, quantity) {
  return decimalUnits((minorUnits(amount) * minorUnits(quantity) + 50n) / 100n)
}
export function legacyTopupPreview(value) {
  const gross = minorUnits(value)
  const fee = (gross * 25n + 500n) / 1000n
  return { gross: decimalUnits(gross), fee: decimalUnits(fee), net: decimalUnits(gross - fee) }
}
export function shortfallMoney(required, balance) {
  const difference = minorUnits(required) - minorUnits(balance)
  return decimalUnits(difference > 0n ? difference : 0n)
}
