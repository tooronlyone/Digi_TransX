/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const fmtPKR = (n) => {
  const amount = Number(n || 0)
  if (amount >= 1_000_000) return 'PKR ' + (amount / 1_000_000).toFixed(2).replace(/\.?0+$/, '') + 'M'
  if (amount >= 1_000) return 'PKR ' + (amount / 1_000).toFixed(amount >= 100_000 ? 0 : 1).replace(/\.0$/, '') + 'k'
  return 'PKR ' + amount.toLocaleString()
}

function formatDate(value) {
  if (!value) return 'Ã¢â‚¬â€'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function isPayoutPaid(payout) {
  const status = (payout.status || '').toLowerCase()
  const type = (payout.transaction_type || payout.type || '').toLowerCase()
  if (['pending', 'processing', 'hold'].includes(status)) return false
  if (['paid', 'completed', 'success', 'processed'].includes(status)) return true
  return type.includes('payment') ||
    type === 'credit' ||
    type === 'earning'
}

function payoutStatusLabel(payout) {
  return isPayoutPaid(payout) ? 'Paid' : 'Pending'
}

export default function Earning() {
  const { get } = useApi()
  const [transactions, setTransactions] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [period] = useState('month')

  function load() {
    setLoading(true)
    Promise.allSettled([
      get(`/api/analytics?period=${period}`),
      get('/api/history/account'),
    ]).then(([analyticsRes, txRes]) => {
      if (analyticsRes.status === 'fulfilled' && analyticsRes.value?.success) {
        setAnalytics(analyticsRes.value)
      }
      if (txRes.status === 'fulfilled' && txRes.value?.success) {
        setTransactions(txRes.value.transactions || [])
      }
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [period])

  const earnings = useMemo(() => {
    const total = Number(analytics?.earnings?.total || analytics?.total_earnings || 0) || transactions.reduce((sum, t) => {
      const type = (t.transaction_type || t.type || '').toLowerCase()
      if (type.includes('payment') || type === 'credit' || type === 'earning') return sum + Number(t.amount || 0)
      return sum
    }, 0)

    const pending = transactions
      .filter(t => (t.status || '').toLowerCase() === 'pending')
      .reduce((sum, t) => sum + Number(t.amount || 0), 0)

    return {
      total,
      pending,
      completed: analytics?.completedJobs || analytics?.completed_jobs || transactions.filter(isPayoutPaid).length,
      rating: analytics?.rating || analytics?.avg_rating || analytics?.average_rating || '4.8',
      payouts: transactions.slice(0, 8),
    }
  }, [analytics, transactions])

  const hasExtras = earnings.payouts.some(payout => payout.extras)

  return (
      <div className="page-earnings">
        <div className="payout-page-title">
          <h1>Earnings</h1>
          <p>Your payouts and balance, refreshed at every job completion.</p>
        </div>

        <div className="payout-kpi-grid">
          {[
            {
              value: fmtPKR(earnings.total),
              title: 'Total Earned',
              icon: 'fa-wallet',
              iconClass: 'payout-icon--green',
              footer: 'Last 30 days',
              action: 'Statement',
              to: '/transporter/earnings/statement',
            },
            {
              value: fmtPKR(earnings.pending),
              title: 'Pending Payout',
              icon: 'fa-coins',
              iconClass: 'payout-icon--blue',
              footer: 'Releases in 2 days',
              action: 'Details',
              to: '/transporter/earnings/pending',
            },
            {
              value: earnings.completed,
              title: 'Completed Jobs',
              icon: 'fa-check',
              iconClass: 'payout-icon--amber',
              footer: 'This month',
              action: 'History',
              to: '/transporter/bids',
            },
            {
              value: earnings.rating,
              title: 'Avg. Rating',
              icon: 'fa-star',
              iconClass: 'payout-icon--violet',
              footer: 'From shippers',
              action: 'Reviews',
              to: '/transporter/profile',
            },
          ].map(card => (
            <article className="payout-kpi-card" key={card.title}>
              <div className="payout-kpi-card__header">
                <div>
                  <div className="card-value payout-card-value">
                    {loading ? <i className="fas fa-spinner fa-spin"></i> : card.value}
                  </div>
                  <div className="payout-card-title">{card.title}</div>
                </div>
                <div className={`payout-card-icon ${card.iconClass}`}><i className={`fas ${card.icon}`}></i></div>
              </div>
              <div className="payout-card-footer">
                <span>{card.footer}</span>
                <Link to={card.to} className="payout-action-small">{card.action}</Link>
              </div>
            </article>
          ))}
        </div>

        <section className="payout-section">
          <h2 className="payout-section-title">Recent Payouts</h2>

          {loading ? (
            <div className="payout-loading">
              <i className="fas fa-spinner fa-spin"></i>
              <p>Loading payouts...</p>
            </div>
          ) : earnings.payouts.length === 0 ? (
            <div className="payout-empty-state">
              <i className="fas fa-wallet"></i>
              <p>No payouts yet. Complete a job to see your first earning.</p>
            </div>
          ) : (
            <div className="payout-table">
              <div className={`payout-table-row payout-table-row--head${hasExtras ? ' has-extras' : ''}`}>
                <span>Date</span>
                <span>Reference</span>
                <span>Job</span>
                <span>Status</span>
                {hasExtras && <span>Extras</span>}
                <span>Amount</span>
              </div>

              {earnings.payouts.map(payout => {
                const reference = payout.reference || payout.transaction_ref || payout.transaction_id || `TX-PAY-${payout.id}`
                const job = payout.job_label || payout.description || payout.job || payout.route || `Job ${payout.job_id || payout.id}`
                const status = payoutStatusLabel(payout)
                return (
                  <div key={payout.id || reference} className={`payout-table-row${hasExtras ? ' has-extras' : ''}`}>
                    <span>{formatDate(payout.created_at || payout.date)}</span>
                    <span className="payout-reference">{reference}</span>
                    <span>{job}</span>
                    <span>
                      <span className={`payout-status-pill payout-status-pill--${status.toLowerCase()}`}>
                        {status}
                      </span>
                    </span>
                    {hasExtras && <span>{payout.extras ? fmtPKR(payout.extras) : 'Ã¢â‚¬â€'}</span>}
                    <span className="payout-amount">{fmtPKR(payout.amount)}</span>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    
  )
}
