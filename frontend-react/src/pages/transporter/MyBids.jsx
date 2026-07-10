import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCsrfToken } from '../client/clientUtils'
import '../../styles/pages/my-bids.css'

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return 'PKR 0'
  return `PKR ${amount.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

export default function MyBids() {
  const [bids, setBids] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState('')
  const [notice, setNotice] = useState('')

  async function loadBids() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/orders/my-bids', { credentials: 'same-origin' })
      const json = await response.json().catch(() => ({}))
      if (response.status === 404) {
        setBids([])
        return
      }
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to load bids.')
      setBids(json.bids || [])
    } catch (loadError) {
      setError(loadError.message || 'Unable to load bids.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBids()
  }, [])

  async function withdrawBid(bid) {
    const confirmed = window.confirm('Withdraw this pending bid?')
    if (!confirmed) return

    setActionLoading(String(bid.id))
    setError('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${bid.order_id}/bids/${bid.id}/withdraw`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to withdraw bid.')
      await loadBids()
      setNotice('Bid withdrawn successfully.')
    } catch (withdrawError) {
      setError(withdrawError.message || 'Unable to withdraw bid.')
    } finally {
      setActionLoading('')
    }
  }

  function statusClasses(status) {
    return `mybids-status mybids-status--${String(status || 'default').replace(/_/g, '-')}`
  }

  return (
    <div className="mybids-page">
      <div className="mybids-page-title">
        <div>
          <h1>My Bids</h1>
          <p>Track every bid you have placed and manage your active orders.</p>
        </div>
        <Link
          to="/transporter/available-bids"
          className="mybids-primary-link"
        >
          <i className="fas fa-clipboard-list" aria-hidden="true"></i>
          Available Orders
        </Link>
      </div>

      {loading && <div className="mybids-message mybids-message--loading">Loading bids...</div>}
      {error && <div className="mybids-message mybids-message--error">{error}</div>}
      {notice && <div className="mybids-message mybids-message--success">{notice}</div>}
      {!loading && !error && bids.length === 0 && (
        <div className="mybids-empty-state">
          <i className="fas fa-gavel" aria-hidden="true"></i>
          <p>No bids yet. Start browsing available orders.</p>
          <Link to="/transporter/available-bids">Browse Orders</Link>
        </div>
      )}

      {!loading && !error && bids.length > 0 && (
        <div className="mybids-grid">
          {bids.map((bid) => (
            <article key={bid.id} className="mybids-card">
              <div className="mybids-card-header">
                <div>
                  <h2>{bid.pickup_city} → {bid.dropoff_city}</h2>
                  <p>{bid.pickup_date} at {bid.pickup_time}</p>
                </div>
                <span className={statusClasses(bid.status)}>
                  {bid.status.replace(/_/g, ' ').toUpperCase()}
                </span>
              </div>
              <div className="mybids-details">
                <div><span>Your Bid</span><strong>{formatMoney(bid.bid_price)}</strong></div>
                <div><span>Goods</span><strong>{bid.goods_type || '-'}</strong></div>
                <div><span>Weight</span><strong>{bid.goods_weight_tons} tons</strong></div>
                <div><span>Status</span><strong>{bid.status}</strong></div>
              </div>
              {bid.message && <p className="mybids-note">{bid.message}</p>}
              {bid.status === 'pending' && (
                <div className="mybids-actions">
                  <button
                    type="button"
                    onClick={() => withdrawBid(bid)}
                    disabled={actionLoading === String(bid.id)}
                    className="mybids-btn mybids-btn--danger"
                  >
                    <i className={`fas ${actionLoading === String(bid.id) ? 'fa-spinner fa-spin' : 'fa-ban'}`} aria-hidden="true"></i>
                    Withdraw Bid
                  </button>
                </div>
              )}
              {bid.status === 'accepted' && (
                <div className="mybids-actions">
                  <Link to={`/transporter/order/${bid.order_id}`} className="mybids-btn mybids-btn--primary">
                    <i className="fas fa-eye" aria-hidden="true"></i>
                    View Order
                  </Link>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
