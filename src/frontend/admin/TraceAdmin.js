import { onMounted, ref } from 'vue'
import { getAdminTrace, listAdminTraces } from '/ui/services/adminApi.js'
import SpanTree from '/ui/components/SpanTree.js'

export default {
  name: 'TraceAdmin',
  components: { SpanTree },
  setup() {
    const traces = ref([])
    const current = ref(null)
    const spans = ref([])
    const error = ref('')

    async function load() {
      error.value = ''
      try {
        traces.value = await listAdminTraces()
      } catch (e) {
        error.value = e.message
      }
    }

    async function select(id) {
      try {
        const payload = await getAdminTrace(id)
        current.value = payload.trace
        spans.value = payload.spans || []
      } catch (e) {
        error.value = e.message
      }
    }

    onMounted(load)
    return { traces, current, spans, error, load, select }
  },
  template: /*html*/`
    <section class="admin-grid trace-admin-grid">
      <div class="admin-section">
        <div class="admin-section-head">
          <h2>Trace 列表</h2>
          <button type="button" @click="load">刷新</button>
        </div>
        <p v-if="error" class="admin-error">{{ error }}</p>
        <div class="admin-list">
          <button
            v-for="trace in traces"
            :key="trace.trace_id"
            type="button"
            class="trace-admin-item"
            @click="select(trace.trace_id)"
          >
            <strong>{{ trace.question || '空问题' }}</strong>
            <span>{{ Math.round(trace.duration_ms || 0) }}ms · {{ trace.total_tokens || 0 }} tokens · {{ trace.status }}</span>
          </button>
        </div>
      </div>
      <div class="admin-section">
        <div class="admin-section-head">
          <h2>Trace 详情</h2>
        </div>
        <div v-if="current" class="trace-admin-meta">
          <div>Trace ID: {{ current.trace_id }}</div>
          <div>Session: {{ current.session_id }}</div>
          <div>状态: {{ current.status }}</div>
        </div>
        <SpanTree v-if="spans.length" :spans="spans" />
        <p v-else class="admin-muted">选择一条 trace 查看详情</p>
      </div>
    </section>
  `,
}
