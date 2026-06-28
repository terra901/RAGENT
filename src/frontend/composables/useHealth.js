import { store } from '/ui/store.js'
import { apiFetch } from '/ui/composables/useApiFetch.js'

export function useHealth() {
  // 暴露后端健康检查轮询能力。
  let timer = null

  async function check() {
    // 请求 /api/health 并更新 store.health。
    try {
      const r = await apiFetch('/api/health')
      const body = await r.json()
      store.health = body && body.status === 'ok' ? 'ok' : 'error'
    } catch {
      store.health = 'error'
    }
  }

  function start(intervalMs = 30_000) {
    // 立即检查一次，并按间隔持续轮询。
    check()
    timer = setInterval(check, intervalMs)
  }

  function stop() {
    // 停止健康检查轮询。
    if (timer) { clearInterval(timer); timer = null }
  }

  return { check, start, stop }
}
