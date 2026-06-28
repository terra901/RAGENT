import { apiFetch } from '/ui/composables/useApiFetch.js'

export async function getJson(url, options = {}) {
  const response = await apiFetch(url, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.error || `HTTP ${response.status}`)
  return payload
}

export function listProviders() {
  return getJson('/api/admin/model-providers')
}

export function saveProvider(provider) {
  const path = provider.id ? `/api/admin/model-providers/${encodeURIComponent(provider.id)}` : '/api/admin/model-providers'
  return getJson(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(provider),
  })
}

export function deleteProvider(id) {
  return getJson(`/api/admin/model-providers/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function listModels(providerId) {
  return getJson(`/api/admin/model-providers/${encodeURIComponent(providerId)}/models`)
}

export function saveModel(providerId, model) {
  const path = model.id
    ? `/api/admin/models/${encodeURIComponent(model.id)}`
    : `/api/admin/model-providers/${encodeURIComponent(providerId)}/models`
  return getJson(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  })
}

export function deleteModel(id) {
  return getJson(`/api/admin/models/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function setModelStatus(id, status) {
  return getJson(`/api/admin/models/${encodeURIComponent(id)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function listAdminTraces() {
  return getJson('/api/admin/traces?limit=80')
}

export function getAdminTrace(id) {
  return getJson(`/api/admin/traces/${encodeURIComponent(id)}`)
}

export function getQueueStatus() {
  return getJson('/api/jobs/queue')
}
