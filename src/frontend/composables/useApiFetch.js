const ACCESS_TOKEN_KEY = 'ragent_access_token'

export function getAccessToken() {
  if (typeof window === 'undefined') return ''
  try {
    return window.localStorage?.getItem(ACCESS_TOKEN_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function setAccessToken(token) {
  if (typeof window === 'undefined') return
  try {
    if (token) window.localStorage?.setItem(ACCESS_TOKEN_KEY, token)
    else window.localStorage?.removeItem(ACCESS_TOKEN_KEY)
  } catch (_) { /* noop */ }
  window.dispatchEvent(new CustomEvent('ragent-auth-token', { detail: { token } }))
}

export function clearAccessToken() {
  setAccessToken('')
}

let refreshPromise = null

export async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    }).then(async (response) => {
      if (!response.ok) {
        clearAccessToken()
        return ''
      }
      const payload = await response.json()
      setAccessToken(payload.access_token || '')
      return payload.access_token || ''
    }).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export async function apiFetch(input, init = {}) {
  const headers = new Headers(init.headers || {})
  const token = getAccessToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const requestInit = { credentials: 'same-origin', ...init, headers }
  let response = await fetch(input, requestInit)
  const url = typeof input === 'string' ? input : input.url
  const isAuthCall = String(url).startsWith('/api/auth/')
  if (response.status !== 401 || isAuthCall || init.__retried) return response

  const newToken = await refreshAccessToken()
  if (!newToken) return response
  const retryHeaders = new Headers(init.headers || {})
  retryHeaders.set('Authorization', `Bearer ${newToken}`)
  response = await fetch(input, {
    credentials: 'same-origin',
    ...init,
    __retried: true,
    headers: retryHeaders,
  })
  return response
}
