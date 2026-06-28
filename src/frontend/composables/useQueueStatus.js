import { onUnmounted } from 'vue'
import { store } from '/ui/store.js'
import { getQueueStatus } from '/ui/services/adminApi.js'

let timer = null

export function useQueueStatus() {
  async function refresh() {
    if (store.auth.status !== 'authenticated') return
    store.queue.loading = true
    store.queue.error = ''
    try {
      const payload = await getQueueStatus()
      store.queue.queued = Number(payload.queued || 0)
      store.queue.started = Number(payload.started || 0)
      store.queue.latest = payload.latest || null
    } catch (error) {
      store.queue.error = error.message || '队列状态读取失败'
    } finally {
      store.queue.loading = false
    }
  }

  function start() {
    if (timer) return
    refresh()
    timer = window.setInterval(refresh, 5000)
  }

  function stop() {
    if (!timer) return
    window.clearInterval(timer)
    timer = null
  }

  onUnmounted(stop)
  return { refresh, start, stop }
}
