import { Link } from 'react-router-dom'

export default function OrderWorkspaceNavigation({ mode = 'one-time' }) {
  return (
    <section className="order-workspace-nav" aria-label="Order workspace">
      <div className="order-workspace-nav__modes" role="navigation" aria-label="Choose order type">
        <Link
          to="/client/post-order"
          className={`order-workspace-nav__mode${mode === 'one-time' ? ' active' : ''}`}
          aria-current={mode === 'one-time' ? 'page' : undefined}
        >
          <i className="fas fa-box" aria-hidden="true" />
          <span><strong>One-Time Order</strong><small>Post a single shipment</small></span>
        </Link>
        <Link
          to="/client/post-agreement"
          className={`order-workspace-nav__mode${mode === 'agreemental' ? ' active' : ''}`}
          aria-current={mode === 'agreemental' ? 'page' : undefined}
        >
          <i className="fas fa-file-contract" aria-hidden="true" />
          <span><strong>Agreemental Order</strong><small>Plan recurring transport</small></span>
        </Link>
      </div>
      <div className="order-workspace-nav__links" aria-label="Order records">
        <Link to="/client/orders"><i className="fas fa-clipboard-list" aria-hidden="true" /> My Orders</Link>
        <Link to="/client/my-agreements"><i className="fas fa-file-signature" aria-hidden="true" /> My Agreements</Link>
      </div>
    </section>
  )
}
