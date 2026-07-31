const SAFE_PATH = /^\/[A-Za-z0-9/_.-]*$/
const MAX_PAGE_PATH_LENGTH = 255

/**
 * Phase 1A retains one minimal authenticated page-visit contract. It sends no
 * browser identity, form/click text, URL query/fragment, or request/response
 * content. The CSRF token is an authorization header only.
 */
export function sanitizeTrackingPath(pathname) {
  if (typeof pathname !== 'string' || !pathname) return null
  const path = pathname.split(/[?#]/, 1)[0] || '/'
  if (path.length > MAX_PAGE_PATH_LENGTH || !SAFE_PATH.test(path)) return null
  if (path.split('/').some(segment => segment === '.' || segment === '..')) return null
  return path
}

export function buildPageVisitPayload(pathname) {
  const pagePath = sanitizeTrackingPath(pathname)
  if (!pagePath) return null
  return {
    action_type: 'page_visit',
    action_name: 'page_view',
    page_url: pagePath,
    metadata: { navigation_source: 'router' },
  }
}

export async function sendPageVisit(
  pathname,
  { fetchImpl, storage, csrfToken } = {},
) {
  const payload = buildPageVisitPayload(pathname)
  if (!payload) return false

  try {
    const sessionStore = storage ?? globalThis.sessionStorage
    const csrf = csrfToken ?? sessionStore?.getItem?.('csrf_token') ?? ''
    const fetcher = fetchImpl ?? globalThis.fetch?.bind(globalThis)
    if (!csrf || !fetcher) return false
    const response = await fetcher('/api/track', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify(payload),
      keepalive: true,
    })
    return response.ok
  } catch {
    return false
  }
}
