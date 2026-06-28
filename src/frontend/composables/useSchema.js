import { store } from '/ui/store.js'
import { apiFetch } from '/ui/composables/useApiFetch.js'

export function useSchema() {
  // 暴露 schema 加载能力。
  async function load() {
    // 请求 /api/schema 并写入全局 store。
    store.schema.loading = true
    store.schema.error = null
    try {
      const r = await apiFetch('/api/schema')
      if (!r.ok) throw new Error('HTTP ' + r.status)
      const body = await r.json()
      store.schema.tables = body.tables || []
    } catch (e) {
      store.schema.error = e.message || '加载失败'
      store.schema.tables = []
    } finally {
      store.schema.loading = false
    }
  }
  return { load }
}
