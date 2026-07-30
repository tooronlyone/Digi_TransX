import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiGet,
  formatDate,
  formatStatus,
  StateMessage,
} from '../client/clientUtils'

const TERMINAL_STATUSES = new Set([
  'cancelled',
  'completed',
  'delivered',
  'refunded',
  'resolved_client',
])

const OPEN_STATUSES = new Set(['open', 'pending', 'bidding'])

function normalizedStatus(value) {
  return String(value || 'open').trim().toLowerCase()
}

function locationLabel(order, side) {
  return order[`${side}_location`] || order[`${side}_city`] || 'Location pending'
}

function statusTone(status) {
  const value = normalizedStatus(status)
  if (['completed', 'delivered'].includes(value)) return 'complete'
  if (['delivery_disputed', 'admin_review', 'disputed'].includes(value)) return 'attention'
  if (['cancelled', 'refunded', 'resolved_client'].includes(value)) return 'muted'
  if (OPEN_STATUSES.has(value)) return 'open'
  return 'active'
}

export default function EverydayDashboard() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let mounted = true
    apiGet('/api/orders/my-orders')
      .then((json) => {
        if (mounted) setOrders(json.orders || [])
      })
      .catch((error) => {
        if (mounted) setLoadError(error.message || 'Could not load your orders.')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const recent = orders.slice(0, 5)
  const openOrders = orders.filter((order) => OPEN_STATUSES.has(normalizedStatus(order.status))).length
  const activeOrders = orders.filter((order) => !TERMINAL_STATUSES.has(normalizedStatus(order.status))).length
  const completedOrders = orders.filter((order) => ['completed', 'delivered'].includes(normalizedStatus(order.status))).length
  const totalBids = orders.reduce((sum, order) => sum + Number(order.bid_count || 0), 0)

  return (
    <div className="everyday-dashboard">
      <section className="everyday-hero">
        <div className="everyday-hero__content">
          <div className="everyday-hero__eyebrow">
            <span className="everyday-hero__eyebrow-dot"></span>
            One-time delivery
          </div>
          <h1>Your next delivery starts here.</h1>
          <p>
            Post your route once, compare verified transporter bids, and choose
            the offer that works for you.
          </p>
          <div className="everyday-hero__actions">
            <Link to="/everyday/post-order" className="everyday-btn everyday-btn--primary">
              <i className="fas fa-plus" aria-hidden="true"></i>
              Post a new order
            </Link>
            <Link to="/everyday/orders" className="everyday-btn everyday-btn--ghost">
              View my orders
              <i className="fas fa-arrow-right" aria-hidden="true"></i>
            </Link>
          </div>
        </div>

        <div className="everyday-hero__visual" aria-hidden="true">
          <div className="everyday-route-card">
            <div className="everyday-route-card__top">
              <span>Simple booking</span>
              <span className="everyday-route-card__live">3 steps</span>
            </div>
            <div className="everyday-route-card__path">
              <span className="everyday-route-card__pin everyday-route-card__pin--start">
                <i className="fas fa-box"></i>
              </span>
              <span className="everyday-route-card__line"></span>
              <span className="everyday-route-card__truck">
                <i className="fas fa-truck-fast"></i>
              </span>
              <span className="everyday-route-card__line"></span>
              <span className="everyday-route-card__pin everyday-route-card__pin--finish">
                <i className="fas fa-location-dot"></i>
              </span>
            </div>
            <div className="everyday-route-card__labels">
              <span>Post route</span>
              <span>Compare bids</span>
              <span>Book safely</span>
            </div>
          </div>
        </div>
      </section>

      <section className="everyday-stats" aria-label="Order summary">
        <article className="everyday-stat everyday-stat--blue">
          <span className="everyday-stat__icon"><i className="fas fa-boxes-stacked" aria-hidden="true"></i></span>
          <div>
            <strong>{orders.length}</strong>
            <span>Total orders</span>
          </div>
        </article>
        <article className="everyday-stat everyday-stat--amber">
          <span className="everyday-stat__icon"><i className="fas fa-satellite-dish" aria-hidden="true"></i></span>
          <div>
            <strong>{openOrders}</strong>
            <span>Open for bids</span>
          </div>
        </article>
        <article className="everyday-stat everyday-stat--cyan">
          <span className="everyday-stat__icon"><i className="fas fa-gavel" aria-hidden="true"></i></span>
          <div>
            <strong>{totalBids}</strong>
            <span>Bids received</span>
          </div>
        </article>
        <article className="everyday-stat everyday-stat--green">
          <span className="everyday-stat__icon"><i className="fas fa-circle-check" aria-hidden="true"></i></span>
          <div>
            <strong>{completedOrders}</strong>
            <span>Completed</span>
          </div>
        </article>
      </section>

      <div className="everyday-dashboard__grid">
        <section className="everyday-panel everyday-panel--orders">
          <header className="everyday-panel__header">
            <div>
              <span className="everyday-panel__kicker">Latest activity</span>
              <h2>Recent orders</h2>
            </div>
            <Link to="/everyday/orders" className="everyday-panel__link">
              View all <i className="fas fa-arrow-right" aria-hidden="true"></i>
            </Link>
          </header>

          {loading && (
            <div className="everyday-panel__state">
              <StateMessage type="loading">Loading your orders...</StateMessage>
            </div>
          )}

          {!loading && loadError && (
            <div className="everyday-panel__state">
              <StateMessage type="error" title="Orders unavailable">
                {loadError}
              </StateMessage>
            </div>
          )}

          {!loading && !loadError && recent.length === 0 && (
            <div className="everyday-empty">
              <span className="everyday-empty__icon"><i className="fas fa-route"></i></span>
              <h3>No delivery requests yet</h3>
              <p>Post your first route and start receiving transporter bids.</p>
              <Link to="/everyday/post-order" className="everyday-btn everyday-btn--primary">
                Post your first order
              </Link>
            </div>
          )}

          {!loading && !loadError && recent.length > 0 && (
            <div className="everyday-order-list">
              {recent.map((order) => {
                const tone = statusTone(order.status)
                return (
                  <article className="everyday-order" key={order.id}>
                    <div className="everyday-order__identity">
                      <span className="everyday-order__number">#{order.id}</span>
                      <span className={`everyday-order__status everyday-order__status--${tone}`}>
                        {formatStatus(order.status)}
                      </span>
                    </div>

                    <div className="everyday-order__route">
                      <div className="everyday-order__stop">
                        <span className="everyday-order__dot everyday-order__dot--pickup"></span>
                        <div>
                          <small>Pickup</small>
                          <strong title={locationLabel(order, 'pickup')}>
                            {locationLabel(order, 'pickup')}
                          </strong>
                        </div>
                      </div>
                      <div className="everyday-order__connector" aria-hidden="true">
                        <span></span>
                        <i className="fas fa-chevron-right"></i>
                      </div>
                      <div className="everyday-order__stop">
                        <span className="everyday-order__dot everyday-order__dot--dropoff"></span>
                        <div>
                          <small>Dropoff</small>
                          <strong title={locationLabel(order, 'dropoff')}>
                            {locationLabel(order, 'dropoff')}
                          </strong>
                        </div>
                      </div>
                    </div>

                    <div className="everyday-order__meta">
                      <span>
                        <i className="fas fa-gavel" aria-hidden="true"></i>
                        {Number(order.bid_count || 0)} {Number(order.bid_count || 0) === 1 ? 'bid' : 'bids'}
                      </span>
                      {order.created_at && (
                        <span>
                          <i className="far fa-calendar" aria-hidden="true"></i>
                          {formatDate(order.created_at)}
                        </span>
                      )}
                    </div>

                    <Link to={`/everyday/order/${order.id}`} className="everyday-order__view" aria-label={`View order ${order.id}`}>
                      <span>View details</span>
                      <i className="fas fa-arrow-right" aria-hidden="true"></i>
                    </Link>
                  </article>
                )
              })}
            </div>
          )}
        </section>

        <aside className="everyday-dashboard__sidebar">
          <section className="everyday-panel everyday-quick-panel">
            <span className="everyday-panel__kicker">Shortcuts</span>
            <h2>Quick actions</h2>
            <div className="everyday-quick-list">
              <Link to="/everyday/post-order" className="everyday-quick everyday-quick--featured">
                <span className="everyday-quick__icon"><i className="fas fa-truck-fast"></i></span>
                <span>
                  <strong>Post an order</strong>
                  <small>Request a new delivery</small>
                </span>
                <i className="fas fa-arrow-right everyday-quick__arrow"></i>
              </Link>
              <Link to="/everyday/orders" className="everyday-quick">
                <span className="everyday-quick__icon"><i className="fas fa-clipboard-list"></i></span>
                <span>
                  <strong>My orders</strong>
                  <small>{activeOrders} currently active</small>
                </span>
                <i className="fas fa-arrow-right everyday-quick__arrow"></i>
              </Link>
              <Link to="/everyday/messages" className="everyday-quick">
                <span className="everyday-quick__icon"><i className="fas fa-comments"></i></span>
                <span>
                  <strong>Messages</strong>
                  <small>Talk to your transporter</small>
                </span>
                <i className="fas fa-arrow-right everyday-quick__arrow"></i>
              </Link>
              <Link to="/everyday/terms" className="everyday-quick">
                <span className="everyday-quick__icon"><i className="fas fa-file-shield"></i></span>
                <span>
                  <strong>Terms & fees</strong>
                  <small>Understand secure payments</small>
                </span>
                <i className="fas fa-arrow-right everyday-quick__arrow"></i>
              </Link>
            </div>
          </section>

          <section className="everyday-assurance">
            <span className="everyday-assurance__icon"><i className="fas fa-shield-halved"></i></span>
            <div>
              <strong>Choose with confidence</strong>
              <p>Compare bid price, transporter profile, and rating before booking.</p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
