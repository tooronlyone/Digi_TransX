/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'

async function getCsrf() {
  const res = await fetch('/auth/csrf-token', { credentials: 'same-origin' })
  const json = await res.json()
  return json.csrf_token
}

async function apiGet(url) {
  const res = await fetch(url, { credentials: 'same-origin' })
  const json = await res.json()
  if (!json.success) throw new Error(json.message || 'Request failed.')
  return json
}

async function apiPost(url, body) {
  const csrf = await getCsrf()
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify(body),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.message || 'Request failed.')
  return json
}

function fmtPKR(n) {
  const amount = Number(n || 0)
  if (amount >= 1000000) return 'PKR ' + (amount / 1000000).toFixed(2).replace(/\.?0+$/, '') + 'M'
  if (amount >= 1000) return 'PKR ' + (amount / 1000).toFixed(amount >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'k'
  return 'PKR ' + amount.toLocaleString()
}

function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 10)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function Earning() {
  const [summary, setSummary] = useState(null)
  const [limits, setLimits] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawing, setWithdrawing] = useState(false)
  const [upgrading, setUpgrading] = useState(false)
  const [upgradeConfirm, setUpgradeConfirm] = useState(null)
  const [card, setCard] = useState(null)
  const [cardLoading, setCardLoading] = useState(true)
  const [showCardForm, setShowCardForm] = useState(false)
  const [cardForm, setCardForm] = useState({ card_number: '', card_holder: '', card_expiry: '', bank: '' })
  const [savingCard, setSavingCard] = useState(false)

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [s, l] = await Promise.all([
        apiGet('/api/wallet/earnings-summary'),
        apiGet('/api/wallet/withdrawal-limits'),
      ])
      setSummary(s)
      setLimits(l)
      try {
        setCardLoading(true)
        const cardRes = await apiGet('/api/wallet/payout-card')
        setCard(cardRes.card || false)
      } catch {
        setCard(false)
      } finally {
        setCardLoading(false)
      }
    } catch (e) {
      setError(e.message || 'Unable to load earnings.')
      setCard(false)
      setCardLoading(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  async function handleWithdraw() {
    setError('')
    setNotice('')
    const amt = Number(withdrawAmount)
    if (!amt || amt <= 0) { setError('Enter a valid amount.'); return }
    setWithdrawing(true)
    try {
      const res = await apiPost('/api/wallet/withdraw-locked', { amount: amt })
      if (res.auto_approved) {
        const remaining = res.remaining_withdrawable ?? 0
        setNotice(
          `PKR ${Number(res.withdrawn).toLocaleString()} has been transferred to your card. ` +
          `Remaining withdrawable balance: PKR ${Number(remaining).toLocaleString()}.`
        )
      } else {
        setNotice(res.message || 'Withdrawal request submitted. Admin will process it shortly.')
      }
      setWithdrawAmount('')
      await loadData()
    } catch (e) {
      setError(e.message)
    } finally {
      setWithdrawing(false)
    }
  }

  function openUpgradeConfirm(tier, duration_years, tierInfo) {
    const fee = duration_years === 3 ? tierInfo.fee_3yr : tierInfo.fee_5yr
    setUpgradeConfirm({ tier, duration_years, fee, label: `Tier ${tier} - ${duration_years} Year Plan` })
    setError('')
    setNotice('')
  }

  async function handleUpgrade() {
    if (!upgradeConfirm) return
    const { tier, duration_years } = upgradeConfirm
    setError('')
    setNotice('')
    setUpgrading(true)
    try {
      const res = await apiPost('/api/wallet/upgrade-limit', { tier, duration_years })
      setNotice(res.message)
      setUpgradeConfirm(null)
      await loadData()
    } catch (e) {
      setError(e.message)
    } finally {
      setUpgrading(false)
    }
  }

  async function handleSaveCard() {
    setError('')
    setNotice('')
    setSavingCard(true)
    try {
      await apiPost('/api/wallet/payout-card', cardForm)
      setNotice('Payout card saved successfully.')
      setShowCardForm(false)
      const cardRes = await apiGet('/api/wallet/payout-card')
      setCard(cardRes.card || false)
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingCard(false)
    }
  }

  const wallet = summary?.wallet || {}
  const transactions = summary?.recent_transactions || []
  const maxWithdrawable = Number(limits?.max_withdrawable || 0)
  const hasCard = Boolean(card)
  const canWithdraw = maxWithdrawable > 0 && hasCard
  const upgradeTiers = Object.entries(limits?.all_tiers || {})
    .filter(([t]) => Number(t) > 0)
    .sort(([a], [b]) => Number(a) - Number(b))

  const statCards = [
    { label: 'This Month', value: fmtPKR(summary?.month_earnings), icon: 'fa-calendar-days', tone: 'green' },
    { label: 'Lifetime Earned', value: fmtPKR(summary?.lifetime_earnings), icon: 'fa-award', tone: 'indigo' },
    { label: 'Pending', value: fmtPKR(summary?.pending_earnings), icon: 'fa-clock', tone: 'yellow' },
    { label: 'Trips Done', value: Number(summary?.completed_trips || 0).toLocaleString(), icon: 'fa-truck', tone: 'gray' },
  ]

  return (
    <div className="earnings-dashboard">
      <div className="payout-page-title">
        <h1>Earnings</h1>
        <p>Track agreement income, wallet balances, withdrawal limits, and payout readiness.</p>
      </div>

      {error && (
        <div className="earnings-alert earnings-alert--error">
          <i className="fas fa-circle-exclamation"></i>
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="earnings-alert earnings-alert--success">
          <i className="fas fa-check-circle"></i>
          <span>{notice}</span>
        </div>
      )}

      <div className="earnings-stats-grid">
        {statCards.map(item => (
          <article className="earnings-card earnings-stat-card" key={item.label}>
            <div className={`earnings-icon earnings-icon--${item.tone}`}>
              <i className={`fas ${item.icon}`}></i>
            </div>
            <div>
              <strong>{loading ? <i className="fas fa-spinner fa-spin"></i> : item.value}</strong>
              <span>{item.label}</span>
            </div>
          </article>
        ))}
      </div>

      <section className="earnings-card earnings-wallet-card">
        <div className="earnings-section-heading">
          <div>
            <h2>Wallet & Withdrawal</h2>
            <p>Balance overview with deposit lock and current withdrawal capacity.</p>
          </div>
        </div>
        <div className="earnings-wallet-grid">
          <div className="earnings-wallet-metric">
            <strong>{loading ? '-' : fmtPKR(wallet.balance)}</strong>
            <span>Total Balance</span>
          </div>
          <div className="earnings-wallet-metric earnings-wallet-metric--locked">
            <strong>{loading ? '-' : fmtPKR(wallet.locked_balance)}</strong>
            <span>Locked Balance</span>
            <small>Security Deposit: Rs 30,000</small>
          </div>
          <div className="earnings-wallet-metric">
            <strong>{loading ? '-' : fmtPKR(wallet.available_balance)}</strong>
            <span>Available Balance</span>
          </div>
          <div className="earnings-wallet-metric earnings-wallet-metric--accent">
            <strong>{loading ? '-' : fmtPKR(limits?.max_withdrawable)}</strong>
            <span>Max Withdrawable</span>
          </div>
        </div>
      </section>

      <div className="earnings-action-grid">
        <section className="earnings-dashed-card">
          <i className="fas fa-credit-card"></i>
          <h3>Payout Card</h3>
          {cardLoading ? (
            <p><i className="fas fa-spinner fa-spin"></i> Loading card info...</p>
          ) : card ? (
            <div className="earnings-card-summary">
              <strong>{card.card_number_masked}</strong>
              <span>{card.card_holder}</span>
              <span>{card.bank ? `${card.bank} | ` : ''}Expires {card.card_expiry}</span>
            </div>
          ) : (
            <p>No payout card saved. Add a card to receive withdrawals.</p>
          )}
          <button type="button" className="earnings-secondary-btn" onClick={() => setShowCardForm(v => !v)}>
            <i className={`fas ${card ? 'fa-pen' : 'fa-plus'}`}></i>
            {card ? 'Change Card' : 'Save Card'}
          </button>

          {showCardForm && (
            <div className="earnings-card-form">
              <label>
                <span>Card Number</span>
                <input
                  type="text"
                  placeholder="1234 5678 9012 3456"
                  maxLength={19}
                  value={cardForm.card_number}
                  onChange={e => {
                    const digits = e.target.value.replace(/\D/g, '').slice(0, 16)
                    const formatted = digits.replace(/(.{4})/g, '$1 ').trim()
                    setCardForm(f => ({ ...f, card_number: formatted }))
                  }}
                />
              </label>
              <label>
                <span>Card Holder Name</span>
                <input type="text" placeholder="Name as on card" value={cardForm.card_holder}
                  onChange={e => setCardForm(f => ({ ...f, card_holder: e.target.value }))} />
              </label>
              <div className="earnings-form-row">
                <label>
                  <span>Expiry (MM/YY)</span>
                  <input
                    type="text"
                    placeholder="MM/YY"
                    maxLength={5}
                    value={cardForm.card_expiry}
                    onChange={e => {
                      const digits = e.target.value.replace(/\D/g, '').slice(0, 4)
                      const formatted = digits.length > 2 ? digits.slice(0, 2) + '/' + digits.slice(2) : digits
                      setCardForm(f => ({ ...f, card_expiry: formatted }))
                    }}
                  />
                </label>
                <label>
                  <span>Bank Name (optional)</span>
                  <input type="text" placeholder="e.g. HBL, UBL, Meezan" value={cardForm.bank}
                    onChange={e => setCardForm(f => ({ ...f, bank: e.target.value }))} />
                </label>
              </div>
              <button type="button" className="earnings-primary-btn" disabled={savingCard} onClick={handleSaveCard}>
                {savingCard ? 'Saving...' : 'Save Card'}
              </button>
            </div>
          )}
        </section>

        <section className="earnings-dashed-card">
          <i className="fas fa-plus"></i>
          <h3>Request Withdrawal</h3>
          {!hasCard && !cardLoading && (
            <p style={{ color: 'var(--warning-text,#92400e)', fontSize: 13, marginBottom: 8 }}>
              <i className="fas fa-exclamation-triangle" style={{ marginRight: 6 }}></i>
              Please save your payout card first to enable withdrawals.
            </p>
          )}
          {hasCard && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Amount will be transferred to card <strong>{card.card_number_masked}</strong>.
            </p>
          )}
          {!loading && maxWithdrawable <= 0 && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
              <i className="fas fa-info-circle" style={{ marginRight: 6 }}></i>
              No withdrawable balance. Rs 30,000 security deposit must remain in wallet at all times.
            </p>
          )}
          <div className="earnings-withdraw-row">
            <input
              id="withdrawAmount"
              type="number"
              min="1"
              step="1"
              aria-label="Amount to Withdraw"
              placeholder={maxWithdrawable > 0 ? `Max ${fmtPKR(maxWithdrawable)}` : 'Enter amount'}
              value={withdrawAmount}
              disabled={withdrawing}
              onChange={e => setWithdrawAmount(e.target.value)}
            />
            <button type="button" className="earnings-primary-btn" disabled={withdrawing || !hasCard} onClick={handleWithdraw}>
              {withdrawing ? 'Processing...' : 'Request Withdrawal'}
            </button>
          </div>
          <div className="earnings-limit-note">
            <strong>{fmtPKR(limits?.limits?.single_max)}</strong> single limit
            <span></span>
            <strong>{fmtPKR(limits?.remaining_daily)}</strong> daily remaining
          </div>
        </section>
      </div>

      <section className="earnings-limits-section tier-section">
        <div className="earnings-section-heading">
          <div>
            <h2>Withdrawal Limits & Tiers</h2>
            <p>Upgrade tiers to increase single and daily withdrawal limits.</p>
          </div>
        </div>

        <div className="earnings-current-tier">
          <div>
            <strong>{limits?.active_tier === 0 ? 'Default' : `Tier ${limits?.active_tier || 0}`}</strong>
            <span>Current Tier</span>
            {Number(limits?.active_tier || 0) > 0 && <small>Expires: {formatDate(limits?.tier_expires_at)}</small>}
          </div>
          <div>
            <strong>{fmtPKR(limits?.limits?.single_max)}</strong>
            <span>Single Limit</span>
          </div>
          <div>
            <strong>{fmtPKR(limits?.limits?.daily_max)}</strong>
            <span>Daily Limit</span>
          </div>
          <div>
            <strong>{fmtPKR(limits?.withdrawn_24h)}</strong>
            <span>Withdrawn 24h</span>
          </div>
        </div>

        <div className="earnings-tier-grid">
          {upgradeTiers.map(([tierKey, tierInfo]) => {
            const tier = Number(tierKey)
            const isActive = tier === Number(limits?.active_tier || 0)
            return (
              <article className={`earnings-card earnings-tier-card${isActive ? ' is-active' : ''}`} key={tierKey}>
                <div className="earnings-tier-title">
                  <h3>Tier {tier}</h3>
                  {isActive && <span>ACTIVE</span>}
                </div>
                <ul>
                  <li>
                    <i className="fas fa-arrow-up"></i>
                    <span>Single max</span>
                    <strong>{fmtPKR(tierInfo.single_max)}</strong>
                  </li>
                  <li>
                    <i className="fas fa-calendar-day"></i>
                    <span>Daily max</span>
                    <strong>{fmtPKR(tierInfo.daily_max)}</strong>
                  </li>
                </ul>
                <div className="earnings-tier-actions">
                  <button type="button" className="earnings-primary-btn" disabled={upgrading} onClick={() => openUpgradeConfirm(tier, 3, tierInfo)}>
                    {isActive ? 'Renew 3yr' : 'Buy 3yr'} <span>{fmtPKR(tierInfo.fee_3yr)}</span>
                  </button>
                  <button type="button" className="earnings-outline-btn" disabled={upgrading} onClick={() => openUpgradeConfirm(tier, 5, tierInfo)}>
                    {isActive ? 'Renew 5yr' : 'Buy 5yr'} <span>{fmtPKR(tierInfo.fee_5yr)}</span>
                  </button>
                </div>
              </article>
            )
          })}
        </div>

        {upgradeConfirm && (
          <div className="earnings-card earnings-confirm-card">
            <h3>Confirm Plan Purchase</h3>
            <p>Fee will be deducted from your available wallet balance.</p>
            <div className="earnings-confirm-grid">
              <span>Plan <strong>{upgradeConfirm.label}</strong></span>
              <span>Fee <strong>{fmtPKR(upgradeConfirm.fee)}</strong></span>
              <span>Available Balance <strong>{fmtPKR(wallet.available_balance)}</strong></span>
            </div>
            <div className="earnings-confirm-actions">
              <button type="button" className="earnings-primary-btn" disabled={upgrading} onClick={handleUpgrade}>
                {upgrading ? 'Processing...' : `Confirm - Pay ${fmtPKR(upgradeConfirm.fee)}`}
              </button>
              <button type="button" className="earnings-outline-btn" disabled={upgrading} onClick={() => setUpgradeConfirm(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="earnings-card earnings-recent-card">
        <div className="earnings-section-heading">
          <div>
            <h2>Recent Earnings</h2>
            <p>Agreement trip income will appear here after completion.</p>
          </div>
        </div>
        {loading ? (
          <div className="earnings-table-empty"><i className="fas fa-spinner fa-spin"></i><p>Loading earnings...</p></div>
        ) : transactions.length === 0 ? (
          <div className="earnings-table-empty"><i className="fas fa-wallet"></i><p>No earnings yet. Complete agreement trips to see income here.</p></div>
        ) : (
          <div className="earnings-table">
            <div className="earnings-table-row earnings-table-row--head">
              <span>Date</span><span>Description</span><span>Amount</span>
            </div>
            {transactions.map(tx => (
              <div key={tx.id} className="earnings-table-row">
                <span>{formatDate(tx.created_at)}</span>
                <span>{tx.description || tx.reference_id || `Transaction ${tx.id}`}</span>
                <strong>{fmtPKR(tx.amount)}</strong>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
