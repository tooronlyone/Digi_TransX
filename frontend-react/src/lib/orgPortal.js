const ACCESS_TOKEN_KEY = 'org_access_token'
const DEPARTMENT_TOKEN_KEY = 'org_department_token'
const DEPARTMENT_ID_KEY = 'org_department_id'

function buildError(payload, status) {
  const error = new Error(payload?.message || 'Request failed')
  error.status = status
  error.payload = payload || {}
  return error
}

export function getOrgAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || ''
}

export function setOrgAccessToken(token) {
  localStorage.setItem(ACCESS_TOKEN_KEY, String(token || ''))
}

export function clearOrgAccessToken() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
}

export function getOrgDepartmentToken() {
  return localStorage.getItem(DEPARTMENT_TOKEN_KEY) || ''
}

export function setOrgDepartmentToken(token) {
  localStorage.setItem(DEPARTMENT_TOKEN_KEY, String(token || ''))
}

export function clearOrgDepartmentToken() {
  localStorage.removeItem(DEPARTMENT_TOKEN_KEY)
  localStorage.removeItem(DEPARTMENT_ID_KEY)
}

export function getOrgDepartmentId() {
  return localStorage.getItem(DEPARTMENT_ID_KEY) || ''
}

export function setOrgDepartmentId(value) {
  localStorage.setItem(DEPARTMENT_ID_KEY, String(value || ''))
}

export function clearOrgPortalState() {
  clearOrgAccessToken()
  clearOrgDepartmentToken()
}

export async function orgRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  const method = String(options.method || 'GET').toUpperCase()

  if (!(options.body instanceof FormData) && !headers['Content-Type'] && method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers,
  })

  let payload = {}
  try {
    payload = await response.json()
  } catch {
    throw new Error('Invalid server response')
  }

  if (!response.ok) {
    throw buildError(payload, response.status)
  }

  return payload
}

export function orgAuthRequest(url, options = {}) {
  const token = getOrgAccessToken()
  return orgRequest(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  })
}

export function orgDepartmentRequest(url, options = {}) {
  const token = getOrgDepartmentToken()
  return orgRequest(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  })
}
