// Wallet entries store signed balance changes. Lock/unlock only move money
// between available and reserved balances; they are not income or spending.
export function walletTransactionMovement(transaction) {
  const parsed = Number(transaction.amount)
  const amount = Number.isFinite(parsed) ? parsed : 0
  const type = String(transaction.type || '').toLowerCase()
  const reservation = type === 'lock' || type === 'unlock'
  return {
    amount: Math.abs(amount),
    direction: reservation ? 'reservation' : amount > 0 ? 'credit' : amount < 0 ? 'debit' : 'neutral',
    sign: reservation || amount === 0 ? '' : amount > 0 ? '+' : '-',
    note: type === 'lock' ? 'reserved' : type === 'unlock' ? 'released' : '',
  }
}
