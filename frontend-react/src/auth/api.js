export class ApiResponseError extends Error {
  constructor(message, { status = 0, code = '', payload = null } = {}) {
    super(message)
    this.name = 'ApiResponseError'
    this.status = status
    this.code = code
    this.payload = payload
  }
}

export function csrfToken(storage = globalThis.sessionStorage) {
  return storage?.getItem('csrf_token') || ''
}

export async function requestJson(url, {
  method = 'GET',
  body,
  signal,
  fetchImpl = globalThis.fetch,
  storage = globalThis.sessionStorage,
} = {}) {
  const normalizedMethod = String(method).toUpperCase()
  const headers = {}
  const options = {
    method: normalizedMethod,
    credentials: 'same-origin',
    headers,
    signal,
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  if (normalizedMethod !== 'GET') headers['X-CSRF-Token'] = csrfToken(storage)

  const response = await fetchImpl(url, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload?.success === false) {
    throw new ApiResponseError(
      payload?.message || 'Request failed. Please try again.',
      { status: response.status, code: payload?.code || '', payload },
    )
  }
  return payload
}
