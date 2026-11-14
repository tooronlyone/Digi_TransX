import { Link } from 'react-router-dom'

export default function OrderWorkspaceNavigation() {
  return (
    <section className="order-workspace-nav" aria-label="Order workspace">
      <div className="order-workspace-nav__modes" role="navigation" aria-label="Choose order type">
        <Link
          to="/client/post-order"
          className="order-workspace-nav__mode active"
          aria-current="page"
        >
          <i className="fas fa-box" aria-hidden="true" />
          <span><strong>One-Time Order</strong><small>Post a single shipment</small></span>
        </Link>
      </div>
      <div className="order-workspace-nav__links" aria-label="Order records">
        <Link to="/client/orders"><i className="fas fa-clipboard-list" aria-hidden="true" /> My Orders</Link>
      </div>
    </section>
  )
}
