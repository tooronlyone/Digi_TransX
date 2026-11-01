import { useEffect, useState } from 'react'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import WalletWorkspace from '../../components/wallet/WalletWorkspace'
import { apiGet, apiSend, formatMoney } from '../client/clientUtils'

export default function DriverWallet() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <OwnedDriverWallet key={String(user.id)} />
}

function OwnedDriverWallet() {
  const [balance, setBalance] = useState(0)
  const [lockedBalance, setLockedBalance] = useState('0.00')
  const [fundingOpen, setFundingOpen] = useState(false)
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [payoutMethod, setPayoutMethod] = useState('easypaisa')
  const [accountNumber, setAccountNumber] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    apiGet('/api/wallet/balance')
      .then((res) => {
        if (res.success && res.wallet) {
          setBalance(res.wallet.available_balance || '0.00')
          setLockedBalance(res.wallet.locked_balance || '0.00')
        }
      })
      .catch(failure => setMsg(failure.message || 'Unable to load wallet.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleWithdraw(e) {
    e.preventDefault()
    if (!withdrawAmount || Number(withdrawAmount) <= 0) return
    setSubmitting(true)
    setMsg('')
    try {
      const res = await apiSend('/api/wallet/withdraw', {
        amount: withdrawAmount,
        destination: `${payoutMethod.toUpperCase()}: ${accountNumber}`,
      })
      if (res.success) {
        setMsg('Withdrawal request submitted successfully! The request is subject to authorized payout processing.')
        const refreshed = await apiGet('/api/wallet/balance')
        if (refreshed.wallet) { setBalance(refreshed.wallet.available_balance || '0.00'); setLockedBalance(refreshed.wallet.locked_balance || '0.00') }
        setWithdrawAmount('')
        setAccountNumber('')
      }
    } catch (err) {
      setMsg(`Error: ${err.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <p className="mb-4 rounded border border-amber-300 bg-amber-50 p-4 text-sm">Temporary Drivers must maintain PKR 10,000 in a frozen security reserve. Frozen funds are excluded from ordinary withdrawals and fuel purchases. Allegations require investigation before an authorized recovery.</p>
      <button type="button" className="mb-4 rounded border border-indigo-600 p-3 font-semibold text-indigo-700" onClick={() => setFundingOpen(value => !value)}>{fundingOpen ? 'Close funding tools' : 'Add money & inspect wallet reserves'}</button>
      {fundingOpen && <WalletWorkspace portal="driver" />}
      <div className="driver-card">
        <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Driver Wallet &amp; Payouts</h1>
        <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
          Earnings deposited by fleet owners for completed trips and monthly contracts.
        </p>

        <div style={{ marginTop: '20px', padding: '24px', background: 'linear-gradient(135deg, #1e293b, #0f172a)', borderRadius: '12px', color: 'white' }}>
          <span style={{ fontSize: '0.85rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Available Payout Balance
          </span>
          <h2 style={{ fontSize: '2.5rem', margin: '8px 0 0 0', fontWeight: 800, color: '#38bdf8' }}>
            {loading ? '...' : formatMoney(balance)}
          </h2>
        </div>

        <p className="mt-3 text-sm text-slate-600">Frozen wallet funds: {formatMoney(lockedBalance)}. The server checks the required security reserve when accepting a temporary assignment.</p>
        {msg && (
          <div style={{ marginTop: '16px', padding: '12px', background: '#eff6ff', color: '#1e40af', borderRadius: '8px' }}>
            {msg}
          </div>
        )}

        <div style={{ marginTop: '24px', maxWidth: '500px' }}>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: '0 0 16px 0' }}>Request Instant Withdrawal</h3>
          <form onSubmit={handleWithdraw} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Withdrawal Amount (PKR)
              </label>
              <input
                type="number"
                min="100"
                max={balance}
                step="50"
                required
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder="Enter amount"
                style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Payout Destination
              </label>
              <select
                value={payoutMethod}
                onChange={(e) => setPayoutMethod(e.target.value)}
                style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              >
                <option value="easypaisa">Easypaisa Mobile Account</option>
                <option value="jazzcash">JazzCash Mobile Account</option>
                <option value="bank">Bank Account (IBAN / Account Number)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Mobile / Account Number
              </label>
              <input
                type="text"
                required
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                placeholder="03001234567 or PK..."
                style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              />
            </div>

            <button
              type="submit"
              disabled={submitting || balance <= 0}
              style={{
                marginTop: '8px',
                background: '#3b82f6',
                color: 'white',
                border: 'none',
                padding: '12px',
                borderRadius: '8px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {submitting ? 'Processing...' : 'Withdraw Funds'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
