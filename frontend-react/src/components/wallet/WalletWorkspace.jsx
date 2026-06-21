import { useEffect, useMemo, useState } from 'react'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  apiGet,
  apiSend,
  formatDateTime,
  formatMoney,
} from '../../pages/client/clientUtils'
import '../../styles/wallet.css'

const EMPTY_FORM = {
  amount: '',
  card_number: '',
  card_expiry: '',
  card_cvc: '',
  card_holder_name: '',
}

function normalizeAmount(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number : 0
}

function calculatePreview(amount) {
  const gross = normalizeAmount(amount)
  const fee = Math.round(gross * 0.025 * 100) / 100
  const net = Math.round((gross - fee) * 100) / 100
  return { gross, fee, net }
}

function formatCardNumber(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 16)
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ')
}

function formatExpiry(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 4)
  if (digits.length <= 2) return digits
  return `${digits.slice(0, 2)}/${digits.slice(2)}`
}

function formatCvc(value) {
  return String(value || '').replace(/\D/g, '').slice(0, 3)
}

function formatCardholderName(value) {
  return String(value || '')
    .replace(/[^A-Za-z\s]/g, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/^\s+/g, '')
}

function typeLabel(type) {
  return String(type || '').replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()) || '-'
}

function transactionAmount(transaction) {
  const signedTypes = new Set(['deduct', 'penalty', 'payout'])
  const sign = signedTypes.has(transaction.type) ? '-' : '+'
  return `${sign}${formatMoney(transaction.amount)}`
}

export default function WalletWorkspace({ portal = 'client' }) {
  const [wallet, setWallet] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [walletLoading, setWalletLoading] = useState(true)
  const [transactionsLoading, setTransactionsLoading] = useState(true)
  const [walletError, setWalletError] = useState('')
  const [transactionsError, setTransactionsError] = useState('')
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupForm, setTopupForm] = useState(EMPTY_FORM)
  const [topupSaving, setTopupSaving] = useState(false)
  const [topupError, setTopupError] = useState('')
  const [topupSuccess, setTopupSuccess] = useState('')

  const preview = useMemo(() => calculatePreview(topupForm.amount), [topupForm.amount])
  const needsActivation = wallet && !wallet.is_minimum_met
  const activationShortfall = useMemo(() => {
    if (!wallet) return 0
    return Math.max(Number(wallet.minimum_required || 0) - Number(wallet.balance || 0), 0)
  }, [wallet])

  async function loadWallet() {
    setWalletLoading(true)
    setWalletError('')
    try {
      const json = await apiGet('/api/wallet')
      setWallet(json.wallet || null)
    } catch (err) {
      setWalletError(err.message || 'Failed to load wallet.')
    } finally {
      setWalletLoading(false)
    }
  }

  async function loadTransactions() {
    setTransactionsLoading(true)
    setTransactionsError('')
    try {
      const json = await apiGet('/api/wallet/transactions?page=1&page_size=20')
      setTransactions(Array.isArray(json.transactions) ? json.transactions : [])
    } catch (err) {
      setTransactionsError(err.message || 'Failed to load transactions.')
    } finally {
      setTransactionsLoading(false)
    }
  }

  useEffect(() => {
    loadWallet()
    loadTransactions()
  }, [])

  function updateTopupField(field, formatter) {
    return (event) => {
      const nextValue = formatter ? formatter(event.target.value) : event.target.value
      setTopupForm((form) => ({ ...form, [field]: nextValue }))
    }
  }

  async function submitTopup(event) {
    event.preventDefault()
    setTopupSaving(true)
    setTopupError('')
    setTopupSuccess('')

    try {
      const json = await apiSend('/api/wallet/topup', {
        amount: Number(topupForm.amount),
        card_number: topupForm.card_number,
        card_expiry: topupForm.card_expiry,
        card_cvc: topupForm.card_cvc,
        card_holder_name: topupForm.card_holder_name.trim(),
      })
      setTopupSuccess(json.message || 'Wallet topped up successfully.')
      setTopupForm(EMPTY_FORM)
      setTopupOpen(false)
      await Promise.all([loadWallet(), loadTransactions()])
    } catch (err) {
      setTopupError(err.message || 'Top-up failed.')
    } finally {
      setTopupSaving(false)
    }
  }

  const pageTitle = portal === 'transporter' ? 'Wallet & Deposits' : 'Wallet & Payments'
  const pageSubtitle = portal === 'transporter'
    ? 'Keep your wallet active so you can lock deposits and accept jobs without friction.'
    : 'Fund your wallet before placing orders and keep an eye on every credit, fee, and balance update.'
  const minimumBadgeLabel = wallet?.is_minimum_met ? 'Activated' : 'Pending'

  return (
    <div className="wallet-page">
      <PageTitle
        title={pageTitle}
        subtitle={pageSubtitle}
        actions={(
          <div className="wallet-page-actions">
            <SecondaryButton
              type="button"
              onClick={() => { loadWallet(); loadTransactions() }}
              disabled={walletLoading || transactionsLoading}
              className="wallet-action-button"
            >
              <i className={`fas ${(walletLoading || transactionsLoading) ? 'fa-spinner fa-spin' : 'fa-rotate-right'}`} aria-hidden="true"></i>
              Refresh
            </SecondaryButton>
            <PrimaryButton
              type="button"
              onClick={() => { setTopupError(''); setTopupSuccess(''); setTopupOpen(true) }}
              className="wallet-action-button"
            >
              <i className="fas fa-plus-circle" aria-hidden="true"></i>
              Add Money
            </PrimaryButton>
          </div>
        )}
      />

      <div className="wallet-feedback-stack">
        {topupSuccess && (
          <StateMessage type="success" title="Top-up complete">
            {topupSuccess}
          </StateMessage>
        )}

        {needsActivation && (
          <StateMessage type="warning" title="Wallet activation needed">
            Minimum balance of {formatMoney(wallet.minimum_required)} required to place orders / accept jobs. Add {formatMoney(activationShortfall)} more to activate your wallet.
          </StateMessage>
        )}
      </div>

      <section className="wallet-section">
        <h2 className="wallet-section-title">Balance Summary</h2>
        {walletLoading && (
          <SectionCard className="wallet-card-shell">
            <StateMessage type="loading">Loading wallet...</StateMessage>
          </SectionCard>
        )}
        {walletError && (
          <SectionCard className="wallet-card-shell">
            <StateMessage type="error">{walletError}</StateMessage>
          </SectionCard>
        )}
        {!walletLoading && !walletError && wallet && (
          <div className="wallet-summary-grid">
            <article className="wallet-summary-card">
              <div className="wallet-summary-card__header">
                <div>
                  <div className="wallet-summary-card__value">{formatMoney(wallet.available_balance)}</div>
                  <div className="wallet-summary-card__label">Available Balance</div>
                </div>
                <div className="wallet-summary-card__icon wallet-summary-card__icon--primary">
                  <i className="fas fa-wallet" aria-hidden="true"></i>
                </div>
              </div>
              <div className="wallet-summary-card__footer">
                <span>Ready for new deposits</span>
                <span className="wallet-summary-card__role">{wallet.role}</span>
              </div>
            </article>

            <article className="wallet-summary-card">
              <div className="wallet-summary-card__header">
                <div>
                  <div className="wallet-summary-card__value">{formatMoney(wallet.balance)}</div>
                  <div className="wallet-summary-card__label">Total Balance</div>
                </div>
                <div className="wallet-summary-card__icon wallet-summary-card__icon--success">
                  <i className="fas fa-sack-dollar" aria-hidden="true"></i>
                </div>
              </div>
              <div className="wallet-summary-card__footer">
                <span>Minimum target {formatMoney(wallet.minimum_required)}</span>
                <span className={`wallet-status-badge ${wallet.is_minimum_met ? 'wallet-status-badge--active' : 'wallet-status-badge--pending'}`}>
                  {minimumBadgeLabel}
                </span>
              </div>
            </article>

            <article className="wallet-summary-card">
              <div className="wallet-summary-card__header">
                <div>
                  <div className="wallet-summary-card__value">{formatMoney(wallet.locked_balance)}</div>
                  <div className="wallet-summary-card__label">Locked Balance</div>
                </div>
                <div className="wallet-summary-card__icon wallet-summary-card__icon--warning">
                  <i className="fas fa-lock" aria-hidden="true"></i>
                </div>
              </div>
              <div className="wallet-summary-card__footer">
                <span>Reserved for deposits</span>
                <span className="wallet-status-badge wallet-status-badge--warning">
                  {wallet.locked_balance > 0 ? 'Locked' : 'Clear'}
                </span>
              </div>
            </article>
          </div>
        )}
      </section>

      <div className="wallet-overview-grid">
        <SectionCard title="Wallet Activation" icon="fa-shield-halved" className="wallet-card-shell wallet-highlight-card">
          {walletLoading && <StateMessage type="loading">Loading wallet...</StateMessage>}
          {walletError && <StateMessage type="error">{walletError}</StateMessage>}
          {!walletLoading && !walletError && wallet && (
            <div className="wallet-highlight-card__content">
              <div className="wallet-highlight-card__text">
                <p className="wallet-highlight-card__eyebrow">Minimum Status</p>
                <h3 className="wallet-highlight-card__title">Minimum deposit target {formatMoney(wallet.minimum_required)}</h3>
                <p className="wallet-highlight-card__copy">
                  Keep your wallet above the threshold so you can place orders, accept jobs, and lock deposits without delay.
                </p>
              </div>
              <div className="wallet-highlight-card__aside">
                <span className={`wallet-status-badge ${wallet.is_minimum_met ? 'wallet-status-badge--active' : 'wallet-status-badge--pending'}`}>
                  {minimumBadgeLabel}
                </span>
                {!wallet.is_minimum_met && (
                  <p className="wallet-highlight-card__shortfall">
                    Add {formatMoney(activationShortfall)} more to activate.
                  </p>
                )}
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Add Money" icon="fa-credit-card" className="wallet-card-shell wallet-add-money-card">
          <div className="wallet-preview-panel">
            <div className="wallet-add-money-card__header">
              <div>
                <div className="wallet-add-money-card__title">Top up your wallet</div>
                <div className="wallet-add-money-card__subtitle">Transparent fee preview before you confirm the dummy payment flow.</div>
              </div>
              <PrimaryButton type="button" className="wallet-preview-button wallet-primary-button" onClick={() => setTopupOpen(true)}>
                <i className="fas fa-plus-circle" aria-hidden="true"></i>
                Add Money
              </PrimaryButton>
            </div>

            <div className="wallet-add-money-card__preview">
              <div className="wallet-add-money-card__preview-line">
                <span>Amount entered</span>
                <strong>{formatMoney(preview.gross)}</strong>
              </div>
              <div className="wallet-add-money-card__preview-line">
                <span>Gateway fee</span>
                <strong>{formatMoney(preview.fee)}</strong>
              </div>
              <div className="wallet-add-money-card__preview-line wallet-add-money-card__preview-line--net">
                <span>Wallet credit</span>
                <strong>{formatMoney(preview.net)}</strong>
              </div>
            </div>

            <div className="wallet-preview-note wallet-preview-note--muted">
              Dummy card details are used only to complete the form flow. They are never stored in the database.
            </div>
          </div>
        </SectionCard>
      </div>

      <section className="wallet-section">
        <h2 className="wallet-section-title">Transaction History</h2>
        <SectionCard className="wallet-card-shell wallet-table-card">
          {transactionsLoading && <StateMessage type="loading">Loading transactions...</StateMessage>}
          {transactionsError && <StateMessage type="error">{transactionsError}</StateMessage>}
          {!transactionsLoading && !transactionsError && transactions.length === 0 && (
            <StateMessage type="empty">No wallet transactions yet.</StateMessage>
          )}
          {!transactionsLoading && !transactionsError && transactions.length > 0 && (
            <div className="wallet-transaction-table">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="wallet-transaction-table__head">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Amount</th>
                    <th className="px-4 py-3">Gross / Fee</th>
                    <th className="px-4 py-3">Balance After</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {transactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDateTime(transaction.created_at)}</td>
                      <td className="px-4 py-3">
                        <span className={`wallet-type-tag wallet-type-tag--${String(transaction.type || '').toLowerCase()}`}>
                          {typeLabel(transaction.type)}
                        </span>
                      </td>
                      <td className={`px-4 py-3 font-semibold ${String(transaction.type || '').toLowerCase() === 'topup' ? 'wallet-amount-positive' : 'text-slate-700'}`}>
                        {transactionAmount(transaction)}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {transaction.gross_amount != null
                          ? `${formatMoney(transaction.gross_amount)} / ${formatMoney(transaction.gateway_fee)}`
                          : '-'}
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900">{formatMoney(transaction.balance_after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </section>

      {topupOpen && (
        <div className="wallet-modal-overlay" onClick={() => setTopupOpen(false)}>
          <form
            className="wallet-modal"
            onClick={(event) => event.stopPropagation()}
            onSubmit={submitTopup}
          >
            <div className="wallet-modal__header">
              <div>
                <h3 className="wallet-modal__title">Add Money to Wallet</h3>
                <p className="wallet-modal__subtitle">Fill the dummy card details to simulate a transparent wallet top-up flow.</p>
              </div>
              <button
                type="button"
                className="wallet-modal__close"
                onClick={() => setTopupOpen(false)}
                aria-label="Close add money form"
              >
                <i className="fas fa-times" aria-hidden="true"></i>
              </button>
            </div>

            <div className="wallet-modal__body">
              <div className="wallet-form-grid">
                <label className="wallet-field wallet-field--full">
                  <span className="wallet-field__label">Amount (PKR)</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={topupForm.amount}
                    onChange={updateTopupField('amount')}
                    className="wallet-field__input wallet-field__input--soft"
                    placeholder="30000"
                    required
                  />
                </label>
                <label className="wallet-field wallet-field--full">
                  <span className="wallet-field__label">Card Number</span>
                  <input
                    value={topupForm.card_number}
                    onChange={updateTopupField('card_number', formatCardNumber)}
                    className="wallet-field__input wallet-field__input--mono wallet-field__input--soft"
                    placeholder="1234 5678 9012 3456"
                    inputMode="numeric"
                    autoComplete="cc-number"
                    maxLength="19"
                    required
                  />
                </label>
                <label className="wallet-field">
                  <span className="wallet-field__label">Expiry</span>
                  <input
                    value={topupForm.card_expiry}
                    onChange={updateTopupField('card_expiry', formatExpiry)}
                    className="wallet-field__input wallet-field__input--mono wallet-field__input--soft"
                    placeholder="MM/YY"
                    inputMode="numeric"
                    autoComplete="cc-exp"
                    maxLength="5"
                    required
                  />
                </label>
                <label className="wallet-field">
                  <span className="wallet-field__label">CVC</span>
                  <input
                    value={topupForm.card_cvc}
                    onChange={updateTopupField('card_cvc', formatCvc)}
                    className="wallet-field__input wallet-field__input--mono wallet-field__input--soft"
                    placeholder="123"
                    inputMode="numeric"
                    autoComplete="cc-csc"
                    maxLength="3"
                    required
                  />
                </label>
                <label className="wallet-field wallet-field--full">
                  <span className="wallet-field__label">Cardholder Name</span>
                  <input
                    value={topupForm.card_holder_name}
                    onChange={updateTopupField('card_holder_name', formatCardholderName)}
                    className="wallet-field__input wallet-field__input--soft"
                    placeholder="Muhammad Ali"
                    autoComplete="cc-name"
                    required
                  />
                </label>
              </div>

              <div className="wallet-modal__preview">
                You're adding {formatMoney(preview.gross)}. Gateway fee (2.5%): {formatMoney(preview.fee)}. Amount credited to wallet: {formatMoney(preview.net)}.
              </div>

              {topupError && (
                <div className="wallet-modal__error">
                  <StateMessage type="error">{topupError}</StateMessage>
                </div>
              )}
            </div>

            <div className="wallet-modal__footer">
              <SecondaryButton type="button" onClick={() => setTopupOpen(false)} className="wallet-modal__button">
                Cancel
              </SecondaryButton>
              <PrimaryButton type="submit" disabled={topupSaving} className="wallet-modal__button wallet-primary-button">
                <i className={`fas ${topupSaving ? 'fa-spinner fa-spin' : 'fa-wallet'}`} aria-hidden="true"></i>
                Add to Wallet
              </PrimaryButton>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
