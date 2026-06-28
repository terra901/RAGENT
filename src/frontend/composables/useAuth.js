import { store } from '/ui/store.js'
import { apiFetch, clearAccessToken, getAccessToken, refreshAccessToken, setAccessToken } from '/ui/composables/useApiFetch.js'

const THEME_KEY = 'ragent_theme_v2'

function fieldLabel(name) {
  return {
    name: '姓名',
    email: '邮箱',
    password: '密码',
  }[name] || name
}

function validationMessage(item) {
  const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : ''
  const label = fieldLabel(field)
  const type = item?.type || ''
  if (type === 'missing') return `请输入${label}。`
  if (type === 'string_too_short' && field === 'password') return '密码至少需要 8 个字符。'
  if (type === 'string_too_short') return `${label}长度不够。`
  if (type === 'string_too_long') return `${label}过长。`
  if (type.includes('value_error') && field === 'email') return '请输入有效的邮箱地址。'
  return item?.msg ? `${label}: ${item.msg}` : ''
}

function parseError(payload, fallback) {
  if (!payload) return fallback
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.map(validationMessage).filter(Boolean)
    if (messages.length) return [...new Set(messages)].join(' ')
  }
  if (typeof payload.error === 'string') return payload.error
  return fallback
}

async function readJson(response) {
  try {
    return await response.json()
  } catch (_) {
    return null
  }
}

export function useAuth() {
  function applyAuthPayload(payload) {
    store.auth.token = payload?.access_token || getAccessToken() || ''
    store.auth.user = payload?.user || null
    store.auth.permissions = payload?.permissions || null
    store.auth.status = store.auth.user ? 'authenticated' : 'anonymous'
    return store.auth.status === 'authenticated'
  }

  function applyTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light'
    store.theme = next
    document.documentElement.setAttribute('data-theme', next)
    try {
      window.localStorage?.setItem(THEME_KEY, next)
    } catch (_) { /* noop */ }
  }

  function toggleTheme() {
    applyTheme(store.theme === 'dark' ? 'light' : 'dark')
  }

  function loadTheme() {
    let saved = 'dark'
    try {
      saved = window.localStorage?.getItem(THEME_KEY) || 'dark'
    } catch (_) { /* noop */ }
    applyTheme(saved)
  }

  async function bootstrap() {
    loadTheme()
    store.auth.error = ''
    let token = getAccessToken()
    if (!token) {
      token = await refreshAccessToken().catch(() => '')
    }
    if (!token) {
      store.auth.status = 'anonymous'
      store.auth.user = null
      store.auth.permissions = null
      return false
    }
    store.auth.token = token
    let response = await apiFetch('/api/auth/me')
    if (response.status === 401) {
      token = await refreshAccessToken().catch(() => '')
      if (token) {
        store.auth.token = token
        response = await apiFetch('/api/auth/me')
      }
    }
    if (!response.ok) {
      clearAccessToken()
      store.auth.token = ''
      store.auth.user = null
      store.auth.permissions = null
      store.auth.status = 'anonymous'
      return false
    }
    const payload = await readJson(response)
    return applyAuthPayload(payload)
  }

  async function submitAuth(path, payload) {
    store.auth.error = ''
    const response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await readJson(response)
    if (!response.ok) {
      const message = parseError(body, '请求失败')
      store.auth.error = message
      throw new Error(message)
    }
    setAccessToken(body.access_token || '')
    applyAuthPayload(body)
    return body
  }

  async function login({ email, password }) {
    return submitAuth('/api/auth/login', { email, password })
  }

  async function register({ name, email, password }) {
    return submitAuth('/api/auth/register', { name, email, password })
  }

  async function logout() {
    await apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => null)
    clearAccessToken()
    store.auth.user = null
    store.auth.permissions = null
    store.auth.token = ''
    store.auth.status = 'anonymous'
    store.conversations = []
    store.currentConversationId = null
    store.draft = ''
  }

  return { bootstrap, login, register, logout, applyTheme, toggleTheme }
}
