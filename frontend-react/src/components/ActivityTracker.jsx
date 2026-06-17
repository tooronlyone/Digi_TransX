/**
 * ActivityTracker — mounts once inside <BrowserRouter> and silently records:
 *   1. Every page visit        (action_type: 'page_visit')
 *   2. Every button/link click (action_type: 'button_click' | 'navigation')
 *   3. Every form submission   (action_type: 'form_submit')
 *   4. Every fetch/API call    (action_type: 'api_call')  ← patches window.fetch
 *
 * All events are sent to POST /api/track and stored in user_action_logs table.
 * If anything fails the user experience is NEVER interrupted.
 */
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { sendTrackEvent } from '../hooks/useTracker'

// ─── helpers ────────────────────────────────────────────────────────────────

const SKIP_URLS = ['/api/track']

function isSkipped(url) {
  return SKIP_URLS.some(s => String(url || '').includes(s))
}

function safeText(node) {
  try {
    return (node?.textContent || node?.value || node?.getAttribute?.('aria-label') || '').trim().slice(0, 300)
  } catch {
    return ''
  }
}

function serializeBody(body) {
  if (!body) return ''
  if (typeof body === 'string') return body.slice(0, 2000)
  if (body instanceof FormData) {
    const obj = {}
    try {
      for (const [k, v] of body.entries()) {
        obj[k] = /password|pin|secret/i.test(k) ? '***' : String(v).slice(0, 300)
      }
    } catch { /**/ }
    return JSON.stringify(obj).slice(0, 2000)
  }
  return ''
}

// ─── component ───────────────────────────────────────────────────────────────

export default function ActivityTracker({ children }) {
  const location = useLocation()
  const fetchPatched = useRef(false)
  const originalFetch = useRef(window.fetch)

  // ── 1. Page visit tracking ───────────────────────────────────────────────
  useEffect(() => {
    sendTrackEvent({
      action_type: 'page_visit',
      action_name: `Page: ${location.pathname}`,
      page_url: location.pathname,
    })
  }, [location.pathname])

  // ── 2. Patch window.fetch to capture every API call + its result ─────────
  useEffect(() => {
    if (fetchPatched.current) return
    fetchPatched.current = true
    const orig = originalFetch.current

    window.fetch = async function (...args) {
      const [input, init] = args
      const url = typeof input === 'string' ? input : input?.url || ''

      if (isSkipped(url)) return orig.apply(this, args)

      const method = (init?.method || 'GET').toUpperCase()
      const inputData = serializeBody(init?.body)
      const t0 = Date.now()

      try {
        const response = await orig.apply(this, args)
        const duration = Date.now() - t0

        let outputResult = ''
        try {
          const cloned = response.clone()
          outputResult = (await cloned.text()).slice(0, 2000)
        } catch { /**/ }

        sendTrackEvent({
          action_type: 'api_call',
          action_name: `${method} ${url}`,
          api_endpoint: url,
          http_method: method,
          input_data: inputData,
          output_result: outputResult,
          http_status: response.status,
          duration_ms: duration,
        })

        return response
      } catch (err) {
        sendTrackEvent({
          action_type: 'api_call',
          action_name: `${method} ${url}`,
          api_endpoint: url,
          http_method: method,
          input_data: inputData,
          error_message: String(err?.message || err).slice(0, 500),
          duration_ms: Date.now() - t0,
        })
        throw err
      }
    }

    return () => {
      window.fetch = orig
      fetchPatched.current = false
    }
  }, [])

  // ── 3. Global button / link click tracker (event delegation) ────────────
  useEffect(() => {
    function onDocClick(e) {
      const target = e.target.closest(
        'button, a, input[type="submit"], input[type="button"], [role="button"], [data-track]'
      )
      if (!target) return

      const tag = target.tagName.toLowerCase()
      const text = safeText(target)
      const actionType = tag === 'a' ? 'navigation' : 'button_click'
      const actionName = text || target.id || target.dataset?.track || 'Button'
      const href = target.getAttribute('href') || ''

      sendTrackEvent({
        action_type: actionType,
        action_name: actionName.slice(0, 255),
        element_id: target.id || '',
        element_text: text,
        input_data: href ? JSON.stringify({ href }) : '',
        page_url: window.location.pathname,
      })
    }

    document.addEventListener('click', onDocClick, true)
    return () => document.removeEventListener('click', onDocClick, true)
  }, [])

  // ── 4. Global form submit tracker ───────────────────────────────────────
  useEffect(() => {
    function onDocSubmit(e) {
      const form = e.target
      if (!form || form.tagName !== 'FORM') return

      const data = {}
      try {
        for (const [k, v] of new FormData(form).entries()) {
          data[k] = /password|pin|secret/i.test(k) ? '***' : String(v).slice(0, 300)
        }
      } catch { /**/ }

      sendTrackEvent({
        action_type: 'form_submit',
        action_name: form.id ? `Form: ${form.id}` : form.action ? `Submit: ${form.action}` : 'Form Submit',
        element_id: form.id || '',
        input_data: JSON.stringify(data).slice(0, 2000),
        page_url: window.location.pathname,
      })
    }

    document.addEventListener('submit', onDocSubmit, true)
    return () => document.removeEventListener('submit', onDocSubmit, true)
  }, [])

  return children
}
