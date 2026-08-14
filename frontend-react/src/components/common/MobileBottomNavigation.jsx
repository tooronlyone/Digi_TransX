import { Link } from 'react-router-dom'

export default function MobileBottomNavigation({ items, isActive, label = 'Primary navigation' }) {
  return (
    <nav className="mobile-bottom-nav" aria-label={label}>
      {items.map((item) => {
        const active = isActive(item)
        return (
          <Link
            key={item.path}
            to={item.path}
            className={`mobile-bottom-nav__link${active ? ' active' : ''}`}
            aria-current={active ? 'page' : undefined}
          >
            <span className="mobile-bottom-nav__icon">
              <i className={`fas ${item.icon}`} aria-hidden="true" />
              {item.badge && <span className="mobile-bottom-nav__badge">{item.badge}</span>}
            </span>
            <span>{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
