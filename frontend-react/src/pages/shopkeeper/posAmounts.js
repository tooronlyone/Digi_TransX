function scaled(value, digits) {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(String(value).trim())
  if (!match || (match[2] || '').length > digits) return null
  return BigInt(match[1]) * 10n ** BigInt(digits) + BigInt((match[2] || '').padEnd(digits, '0') || '0')
}

export function posLineMinor(price, quantity) {
  const priceMinor = scaled(price, 2)
  const quantityMilli = scaled(quantity, 3)
  if (priceMinor === null || quantityMilli === null) return null
  // Match the backend: round each measured line HALF_UP to paisa, then sum.
  return (priceMinor * quantityMilli + 500n) / 1000n
}

export function quotePosCart(cart, amountPaid) {
  let totalMinor = 0n
  let valid = cart.length > 0
  for (const line of cart) {
    const subtotal = posLineMinor(line.product.price, line.quantity)
    if (subtotal === null || Number(line.quantity) <= 0) { valid = false; continue }
    totalMinor += subtotal
  }
  const paidMinor = scaled(amountPaid === '' ? '0' : amountPaid, 2)
  return {
    total: Number(totalMinor) / 100,
    paid: paidMinor === null ? 0 : Number(paidMinor) / 100,
    change: paidMinor === null ? 0 : Number(paidMinor - totalMinor) / 100,
    canConfirm: valid && paidMinor !== null && paidMinor >= totalMinor,
  }
}
