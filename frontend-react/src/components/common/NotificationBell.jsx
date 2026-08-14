import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCsrfToken } from '../../pages/client/clientUtils'

// ONE notification centre shared by the business-client, everyday and
// transporter layouts. Role differences are injected via `orderPath(orderId)`,
// which builds the correct order page for that surface — there is no per-role
// copy of this component. Authorization is server-side: /api/notifications only
// ever returns the signed-in user's own rows.

const POLL_MS = 45000

function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function NotificationBell({ orderPath }) {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/notifications', { credentials: 'same-origin' })
      const json = await res.json().catch(() => ({}))
      if (res.ok && json.success !== false) {
        setItems(json.notifications || [])
        setUnread(Number(json.unread_count || 0))
      }
    } catch {
      /* transient network errors are ignored; the next poll retries */
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)   // cleanup on unmount
  }, [load])

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  async function markRead(id) {
    try {
      const csrf = await getCsrfToken()
      await fetch(`/api/notifications/${id}/read`, {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf },
      })
    } catch { /* ignore */ }
  }

  async function markAll() {
    try {
      const csrf = await getCsrfToken()
      await fetch('/api/notifications/read-all', {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf },
      })
    } catch { /* ignore */ }
    load()
  }

  async function openNotification(n) {
    if (!n.is_read) {
      await markRead(n.id)
      load()
    }
    setOpen(false)
    if (n.order_id && orderPath) navigate(orderPath(n.order_id))
  }

  return (
    <div className="notification-center" ref={wrapRef}>
      <button
        type="button"
        className="notification-center__button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
      >
        <i className="fas fa-bell" aria-hidden="true"></i>
        {unread > 0 && <span className="notification-center__badge">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div className="notification-center__panel">
          <div className="notification-center__header">
            <span>Notifications</span>
            {unread > 0 && <button type="button" className="notification-center__mark-all" onClick={markAll}>Mark all read</button>}
          </div>
          {items.length === 0 ? (
            <div className="notification-center__empty">No notifications yet.</div>
          ) : (
            items.map((n) => (
              <button key={n.id} type="button" className={`notification-center__item${!n.is_read ? ' is-unread' : ''}`} onClick={() => openNotification(n)}>
                <div className="notification-center__message">{n.message}</div>
                <div className="notification-center__meta">Order #{n.order_id} · {timeAgo(n.created_at)}</div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
