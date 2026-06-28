import { defineComponent, h, ref, onMounted } from 'vue'
import { apiFetch } from '/ui/composables/useApiFetch.js'

export default defineComponent({
  name: 'TraceList',
  emits: ['select'],
  setup(_, { emit }) {
    // 加载 trace 列表，并在点击时把 trace_id 抛给父组件。
    const items = ref([])
    const loading = ref(false)
    const error = ref('')

    const load = async () => {
      // 请求最近 trace 列表；trace API 未启用时展示可读错误。
      loading.value = true
      error.value = ''
      try {
        const r = await apiFetch('/api/traces?limit=50')
        if (!r.ok) {
          if (r.status === 403) {
            error.value = 'Trace API 未启用（DA_TRACE_API_ENABLED=false）'
          } else {
            error.value = `HTTP ${r.status}`
          }
          return
        }
        items.value = await r.json()
      } catch (e) {
        error.value = e.message
      } finally {
        loading.value = false
      }
    }

    onMounted(load)

    return () => h('div', { class: 'trace-list' }, [
      h('button', { onClick: load, class: 'btn-refresh' }, '刷新'),
      loading.value ? h('div', { class: 'trace-loading' }, '加载中...') : null,
      error.value ? h('div', { class: 'trace-error' }, error.value) : null,
      ...items.value.map(t => h('div', {
        class: 'trace-item',
        onClick: () => emit('select', t.trace_id),
      }, [
        h('div', { class: 'trace-q' }, t.question || '(空问题)'),
        h('div', { class: 'trace-summary' },
          `${(t.duration_ms || 0).toFixed(0)}ms · ${t.total_tokens || 0}t · ${t.span_count}span · ${t.status}`),
      ])),
    ])
  },
})
