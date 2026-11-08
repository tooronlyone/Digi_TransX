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
      .catch((failure) => setMsg(`Error: ${failure.message || 'Unable to load wallet.'}`))
      .finally(() => setLoading(false))
  }, [])

  async function handleWithdraw(event) {
    event.preventDefault()
    if (!withdrawAmount || Number(withdrawAmount) <= 0) return
    setSubmitting(true)
    setMsg('')
    try {
      const res = await apiSend('/api/wallet/withdraw', { amount: withdrawAmount, destination: `${payoutMethod.toUpperCase()}: ${accountNumber}` })
      if (res.success) {
        setMsg('Withdrawal request submitted. It is now waiting for authorized payout processing.')
        const refreshed = await apiGet('/api/wallet/balance')
        if (refreshed.wallet) { setBalance(refreshed.wallet.available_balance || '0.00'); setLockedBalance(refreshed.wallet.locked_balance || '0.00') }
        setWithdrawAmount('')
        setAccountNumber('')
      }
    } catch (error) {
      setMsg(`Error: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="driver-page">
      <div className="driver-alert driver-alert--warning"><strong>Security reserve:</strong> Temporary drivers must maintain PKR 10,000 in frozen funds. Reserved funds cannot be withdrawn or used for ordinary fuel purchases.</div>

      <section className="driver-card">
        <h1>Driver wallet &amp; payouts</h1>
        <p>Review trip earnings, protected reserves, funding tools, and payout requests from one place.</p>

        <div className="driver-wallet-balance"><span>Available payout balance</span><h2>{loading ? 'Loading…' : formatMoney(balance)}</h2></div>

        {msg && <div className={`driver-alert ${msg.startsWith('Error:') ? 'driver-alert--error' : 'driver-alert--success'}`} role="status">{msg}</div>}

        <div className="driver-wallet-layout">
          <div>
            <div className="driver-section-heading"><div><h2>Request a withdrawal</h2><p>Send available funds to your preferred destination</p></div></div>
            <form className="driver-form" onSubmit={handleWithdraw}>
              <div className="driver-form-field"><label htmlFor="driver-withdraw-amount">Withdrawal amount (PKR)</label><input id="driver-withdraw-amount" type="number" min="100" max={balance} step="50" required value={withdrawAmount} onChange={(event) => setWithdrawAmount(event.target.value)} placeholder="Enter amount" /></div>
              <div className="driver-form-field"><label htmlFor="driver-payout-method">Payout destination</label><select id="driver-payout-method" value={payoutMethod} onChange={(event) => setPayoutMethod(event.target.value)}><option value="easypaisa">Easypaisa mobile account</option><option value="jazzcash">JazzCash mobile account</option><option value="bank">Bank account (IBAN / account number)</option></select></div>
              <div className="driver-form-field"><label htmlFor="driver-account-number">Mobile or account number</label><input id="driver-account-number" type="text" required value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} placeholder="03001234567 or PK…" /></div>
              <div className="driver-form-actions"><button type="submit" className="driver-btn driver-btn--primary" disabled={submitting || Number(balance) <= 0}>{submitting ? 'Processing…' : 'Request withdrawal'}</button></div>
            </form>
          </div>

          <aside>
            <div className="driver-wallet-reserve"><strong>Frozen wallet funds: {formatMoney(lockedBalance)}</strong><p>The server checks this reserve before a temporary assignment can be accepted.</p></div>
            <button type="button" className="driver-btn driver-btn--secondary" onClick={() => setFundingOpen((value) => !value)}>{fundingOpen ? 'Close funding tools' : 'Open funding tools'}</button>
          </aside>
        </div>
      </section>

      {fundingOpen && <section className="driver-card"><WalletWorkspace portal="driver" /></section>}
    </div>
  )
}
