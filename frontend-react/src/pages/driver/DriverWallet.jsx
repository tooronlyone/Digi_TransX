import { useEffect, useState } from 'react'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import WalletWorkspace from '../../components/wallet/WalletWorkspace'
import { apiGet, formatMoney } from '../client/clientUtils'

export default function DriverWallet() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <OwnedDriverWallet key={String(user.id)} />
}

function OwnedDriverWallet() {
  const [balance, setBalance] = useState(0)
  const [totalBalance, setTotalBalance] = useState(0)
  const [lockedBalance, setLockedBalance] = useState(0)
  const [fundingOpen, setFundingOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    let ignore = false
    apiGet('/api/wallet')
      .then((res) => {
        if (ignore) return
        if (res.success && res.wallet) {
          setBalance(res.wallet.available_balance ?? 0)
          setTotalBalance(res.wallet.balance ?? 0)
          setLockedBalance(res.wallet.locked_balance ?? 0)
        }
      })
      .catch((failure) => {
        if (!ignore) setMsg(`Error: ${failure.message || 'Unable to load wallet.'}`)
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => {
      ignore = true
    }
  }, [])

  return (
    <div className="driver-page">
      <div className="driver-alert driver-alert--warning"><strong>Security reserve:</strong> Temporary drivers must maintain PKR 10,000 in frozen funds. Reserved funds cannot be withdrawn or used for ordinary expenses.</div>

      <section className="driver-card">
        <h1>Driver wallet &amp; payouts</h1>
        <p>Review trip earnings, protected reserves, funding tools, and payout status from one place.</p>

        <div className="driver-wallet-balance">
          <span>Available balance</span>
          <h2>{loading ? 'Loading…' : formatMoney(balance)}</h2>
          {!loading && <p>Total ledger balance: {formatMoney(totalBalance)}</p>}
        </div>

        {msg && <div className={`driver-alert ${msg.startsWith('Error:') ? 'driver-alert--error' : 'driver-alert--success'}`} role="status">{msg}</div>}

        <div className="driver-wallet-layout">
          <div>
            <div className="driver-section-heading">
              <div>
                <h2>Driver payouts</h2>
                <p>Payout requests require a verified live payout processor</p>
              </div>
            </div>
            <div className="driver-alert driver-alert--warning" role="note">
              <strong>Payouts unavailable in V1 private testing:</strong> Automated Easypaisa, JazzCash, and bank withdrawals are disabled until live payout execution and verification controls are enabled. Your earnings and reserve balance remain tracked in your wallet ledger below.
            </div>
          </div>

          <aside>
            <div className="driver-wallet-reserve">
              <strong>Frozen wallet funds: {formatMoney(lockedBalance)}</strong>
              <p>The server checks this reserve before a temporary assignment can be accepted.</p>
            </div>
            <button type="button" className="driver-btn driver-btn--secondary" onClick={() => setFundingOpen((value) => !value)}>
              {fundingOpen ? 'Close wallet ledger & funding' : 'Open wallet ledger & funding'}
            </button>
          </aside>
        </div>
      </section>

      {fundingOpen && <section className="driver-card"><WalletWorkspace portal="driver" /></section>}
    </div>
  )
}
