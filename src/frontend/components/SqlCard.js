export default {
  name: 'SqlCard',
  props: {
    sql: { type: String, required: true },
    cacheHit: { type: Boolean, default: false },
  },
  data() {
    return { open: true, copied: false }
  },
  methods: {
    async copy() {
      try {
        await navigator.clipboard.writeText(this.sql)
        this.copied = true
        setTimeout(() => { this.copied = false }, 1500)
      } catch (e) {
        console.warn('复制失败:', e)
      }
    },
  },
  template: /*html*/`
    <div class="result-card" :class="{ open }">
      <div class="result-card-header" @click="open = !open">
        <span class="arrow"></span>
        <span>SQL</span>
        <span class="meta">
          <span v-if="cacheHit">缓存命中</span>
          <button class="copy-btn" @click.stop="copy">{{ copied ? '已复制' : '复制' }}</button>
        </span>
      </div>
      <div class="result-card-body">
        <pre class="sql-block">{{ sql }}</pre>
      </div>
    </div>
  `,
}
