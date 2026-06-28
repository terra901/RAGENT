import { defineComponent, h, ref, onMounted, watch } from 'vue'
import SpanTree from '/ui/components/SpanTree.js'
import { apiFetch } from '/ui/composables/useApiFetch.js'

export default defineComponent({
  name: 'TraceDetail',
  props: {
    traceId: { type: String, required: true },
  },
  setup(props) {
    // 根据 traceId 加载 trace 元信息和 span 列表。
    const trace = ref(null)
    const spans = ref([])
    const loading = ref(false)
    const error = ref('')

    const load = async () => {
      // 请求单条 trace 详情，并写入本地响应式状态。
      if (!props.traceId) return
      loading.value = true
      error.value = ''
      try {
        const r = await apiFetch(`/api/traces/${props.traceId}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        trace.value = data.trace
        spans.value = data.spans
      } catch (e) {
        error.value = e.message
      } finally {
        loading.value = false
      }
    }

    onMounted(load)
    watch(() => props.traceId, load)

    return () => h('div', { class: 'trace-detail' }, [
      loading.value ? h('div', { class: 'trace-loading' }, '加载中...') : null,
      error.value ? h('div', { class: 'trace-error' }, error.value) : null,
      trace.value ? h('div', { class: 'trace-meta' }, [
        h('div', `问题: ${trace.value.question}`),
        h('div', `状态: ${trace.value.status}`),
        h('div', `Tokens: ${trace.value.total_tokens}`),
        h('div', `Spans: ${spans.value.length}`),
      ]) : null,
      spans.value.length ? h(SpanTree, { spans: spans.value }) : null,
    ])
  },
})
