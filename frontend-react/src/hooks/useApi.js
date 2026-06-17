export function useApi() {
  function getCsrf() {
    return sessionStorage.getItem('csrf_token') || ''
  }

  async function request(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase()
    const headers = { ...options.headers }

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
    }

    const csrf = getCsrf()
    if (csrf && method !== 'GET') {
      headers['X-CSRF-Token'] = csrf
    }

    const res = await fetch(url, {
      credentials: 'include',
      ...options,
      headers,
    })

    let data
    try {
      data = await res.json()
    } catch {
      throw new Error('Invalid server response')
    }

    if (!res.ok) {
      throw new Error(data?.message || `Request failed (${res.status})`)
    }

    return data
  }

  function get(url) {
    return request(url, { method: 'GET' })
  }

  function post(url, body) {
    return request(url, {
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
    })
  }

  function put(url, body) {
    return request(url, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  }

  function del(url) {
    return request(url, { method: 'DELETE' })
  }

  return { get, post, put, del, request }
}
