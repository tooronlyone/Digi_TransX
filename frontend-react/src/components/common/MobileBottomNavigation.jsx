import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

const PRIMARY_ITEM_COUNT = 4

export default function MobileBottomNavigation({ items, isActive, label = 'Primary navigation' }) {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreButtonRef = useRef(null)
  const closeButtonRef = useRef(null)
  const sheetRef = useRef(null)
  const primaryItems = items.slice(0, PRIMARY_ITEM_COUNT)
  const moreItems = items.slice(PRIMARY_ITEM_COUNT)
  const moreIsActive = moreItems.some(isActive)

  useEffect(() => {
    if (!moreOpen) return undefined
    const previousFocus = document.activeElement
    const moreButton = moreButtonRef.current
    closeButtonRef.current?.focus()

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMoreOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const focusable = [...(sheetRef.current?.querySelectorAll('a[href], button:not([disabled])') || [])]
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (previousFocus?.isConnected) previousFocus.focus()
      else moreButton?.focus()
    }
  }, [moreOpen])

  function renderItem(item, className = 'mobile-bottom-nav__link') {
    const active = isActive(item)
    return (
      <Link
        key={item.path}
        to={item.path}
        className={`${className}${active ? ' active' : ''}`}
        aria-current={active ? 'page' : undefined}
        onClick={() => setMoreOpen(false)}
      >
        <span className="mobile-bottom-nav__icon">
          <i className={`fas ${item.icon}`} aria-hidden="true" />
          {item.badge && <span className="mobile-bottom-nav__badge">{item.badge}</span>}
        </span>
        <span>{item.label}</span>
      </Link>
    )
  }

  return (
    <>
      <nav className="mobile-bottom-nav" aria-label={label}>
        {primaryItems.map((item) => renderItem(item))}
        {moreItems.length > 0 && (
          <button
            ref={moreButtonRef}
            type="button"
            className={`mobile-bottom-nav__link${moreIsActive ? ' active' : ''}`}
            onClick={() => setMoreOpen(true)}
            aria-expanded={moreOpen}
            aria-controls="mobile-more-destinations"
          >
            <span className="mobile-bottom-nav__icon"><i className="fas fa-ellipsis" aria-hidden="true" /></span>
            <span>More</span>
          </button>
        )}
      </nav>

      {moreOpen && (
        <div className="mobile-more" role="presentation">
          <button className="mobile-more__backdrop" type="button" aria-label="Close more destinations" onClick={() => setMoreOpen(false)} />
          <section
            ref={sheetRef}
            id="mobile-more-destinations"
            className="mobile-more__sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-more-title"
          >
            <div className="mobile-more__header">
              <h2 id="mobile-more-title">More destinations</h2>
              <button ref={closeButtonRef} type="button" className="mobile-more__close" onClick={() => setMoreOpen(false)} aria-label="Close more destinations">
                <i className="fas fa-xmark" aria-hidden="true" />
              </button>
            </div>
            <div className="mobile-more__grid">
              {moreItems.map((item) => renderItem(item, 'mobile-more__link'))}
            </div>
          </section>
        </div>
      )}
    </>
  )
}
