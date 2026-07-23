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

const S = {
  wrap: { position: 'relative', marginRight: 12 },
  btn: { position: 'relative', background: 'none', border: 'none', cursor: 'pointer', color: '#334155', fontSize: 20, padding: 6, lineHeight: 1 },
  badge: { position: 'absolute', top: -2, right: -2, minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8, background: '#dc2626', color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  panel: { position: 'absolute', right: 0, top: 40, width: 320, maxHeight: 420, overflowY: 'auto', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, boxShadow: '0 12px 32px rgba(0,0,0,0.14)', zIndex: 60 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid #f1f5f9', position: 'sticky', top: 0, background: '#fff' },
  headTitle: { fontWeight: 700, fontSize: 14, color: '#0f172a' },
  markAll: { background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontSize: 12, fontWeight: 600 },
  item: (unread) => ({ display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', borderBottom: '1px solid #f8fafc', cursor: 'pointer', background: unread ? '#eff6ff' : '#fff', border: 'none' }),
  itemMsg: { fontSize: 13, color: '#1e293b' },
  itemMeta: { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  empty: { padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 },
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
    <div style={S.wrap} ref={wrapRef}>
      <button
        type="button"
        style={S.btn}
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
      >
        <i className="fas fa-bell" aria-hidden="true"></i>
        {unread > 0 && <span style={S.badge}>{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div style={S.panel}>
          <div style={S.head}>
            <span style={S.headTitle}>Notifications</span>
            {unread > 0 && <button type="button" style={S.markAll} onClick={markAll}>Mark all read</button>}
          </div>
          {items.length === 0 ? (
            <div style={S.empty}>No notifications yet.</div>
          ) : (
            items.map((n) => (
              <button key={n.id} type="button" style={S.item(!n.is_read)} onClick={() => openNotification(n)}>
                <div style={S.itemMsg}>{n.message}</div>
                <div style={S.itemMeta}>Order #{n.order_id} · {timeAgo(n.created_at)}</div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
