export default {
  name: 'TableCard',
  props: {
    columns: { type: Array, default: () => [] },
    rows: { type: Array, default: () => [] },
    rowCount: { type: Number, default: 0 },
    executionTimeMs: { type: Number, default: 0 },
    vizHint: { type: String, default: '' },
    usage: { type: Object, default: null },
  },
  data() {
    return { open: true }
  },
  computed: {
    hasData() {
      return this.rows && this.rows.length > 0
    },
  },
  template: /*html*/`
    <div class="result-card" :class="{ open }" v-if="hasData">
      <div class="result-card-header" @click="open = !open">
        <span class="arrow"></span>
        <span>结果</span>
        <span class="meta">{{ rowCount }} rows · {{ Math.round(executionTimeMs) }}ms</span>
      </div>
      <div class="result-card-body">
        <div class="result-table">
          <table>
            <thead><tr><th v-for="c in columns" :key="c">{{ c }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in rows" :key="i">
                <td v-for="(v, j) in row" :key="j">{{ v == null ? '' : v }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="result-meta">
          <span v-if="vizHint && vizHint !== 'table'" class="viz-hint">建议图表: {{ vizHint }}</span>
          <span v-if="usage && usage.total_tokens">Tokens: {{ usage.total_tokens }} ({{ usage.model_calls }} 次调用)</span>
        </div>
      </div>
    </div>
  `,
}
