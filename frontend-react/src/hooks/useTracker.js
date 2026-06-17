import { useCallback } from 'react'

function _getUserInfo() {
  try {
    const raw = sessionStorage.getItem('user')
    const user = raw ? JSON.parse(raw) : null
    return {
      user_id: user?.id ?? sessionStorage.getItem('user_id') ?? null,
      user_email: user?.email ?? '',
      user_role: user?.role ?? sessionStorage.getItem('user_role') ?? 'transporter',
      session_id: sessionStorage.getItem('csrf_token') ?? '',
    }
  } catch {
    return { user_id: null, user_email: '', user_role: 'transporter', session_id: '' }
  }
}

/**
 * Sends a single tracking event to /api/track.
 * Fire-and-forget — never throws, never blocks the caller.
 */
export async function sendTrackEvent(payload) {
  try {
    const userInfo = _getUserInfo()
    await fetch('/api/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...userInfo,
        page_url: window.location.pathname,
        ...payload,
      }),
      keepalive: true,
    })
  } catch {
    // Tracking must never break the app
  }
}

/**
 * useTracker — call track(actionType, actionName, details?) to log any event.
 *
 * actionType examples: 'button_click', 'form_submit', 'navigation', 'filter',
 *                      'modal_open', 'modal_close', 'api_call', 'page_visit'
 */
export function useTracker() {
  const track = useCallback((actionType, actionName, details = {}) => {
    sendTrackEvent({ action_type: actionType, action_name: actionName, ...details })
  }, [])

  return { track }
}
