import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadVegaEmbed } from '/ui/composables/useVegaEmbed.js'

/**
 * ChartCard：把后端 chart_generator 产出的 Vega-Lite v5 spec 渲染成图表。
 *
 * 覆盖的 mark 类型由后端白名单决定：bar / line / area / point / circle / square /
 * arc（饼图）/ rect（热力图）/ tick / text。
 *
 * 设计：
 * - 懒加载 vega-embed（首屏不拉 700KB）
 * - actions: false 关闭右上角下载菜单，避免混入站外品牌
 * - 暗色主题 + canvas 渲染（移动端更顺）
 * - watch(spec) 触发重渲染时 finalize 上一个 view，避免内存泄漏
 */
export default {
  name: 'ChartCard',
  props: {
    spec: { type: Object, required: true },
  },
  setup(props) {
    // 管理图表容器、渲染状态和 vega view 生命周期。
    const containerRef = ref(null)
    const error = ref(null)
    const ready = ref(false)
    const open = ref(true)
    let view = null

    function markLabel(spec) {
      // 提取 Vega-Lite mark 名称，用于卡片标题展示。
      if (!spec || !spec.mark) return ''
      return typeof spec.mark === 'string' ? spec.mark : (spec.mark.type || '')
    }

    async function render() {
      // 渲染或重渲染图表，并在重渲染前清理旧 view。
      if (!containerRef.value || !props.spec) return
      error.value = null
      try {
        const vegaEmbed = await loadVegaEmbed()
        if (view) {
          try { view.finalize() } catch { /* ignore */ }
          view = null
        }
        // 关键：vega-embed 内部会 structuredClone(spec)，但 Vue 3 reactive
        // 包出来的 Proxy 不可结构化克隆，会报 "could not be cloned"。
        // 用 JSON 圆环把 spec 解成纯对象（spec 是纯数据，没有函数 / 循环引用，安全）。
        const rawSpec = JSON.parse(JSON.stringify(props.spec))
        const result = await vegaEmbed(containerRef.value, rawSpec, {
          actions: false,
          renderer: 'canvas',
          mode: 'vega-lite',
          config: {
            background: 'transparent',
            view: { stroke: 'transparent' },
            axis: {
              labelColor: 'currentColor',
              titleColor: 'currentColor',
              gridColor: '#E5E7EB',
              domainColor: '#D1D5DB',
            },
            legend: { labelColor: 'currentColor', titleColor: 'currentColor' },
            title: { color: 'currentColor' },
            range: {
              category: ['#002FA7', '#111827', '#6B7280', '#D1D5DB'],
            },
          },
        })
        view = result.view
        ready.value = true
      } catch (e) {
        console.warn('[chart] render failed:', e)
        error.value = e && e.message ? e.message : String(e)
        ready.value = false
      }
    }

    onMounted(render)
    // open 切换 true 时容器才挂载到 DOM，需要再渲染一次
    watch(open, (v) => { if (v) render() })
    watch(() => props.spec, render, { deep: true })

    onBeforeUnmount(() => {
      // 组件销毁时释放 vega view，避免内存泄漏。
      if (view) {
        try { view.finalize() } catch { /* ignore */ }
        view = null
      }
    })

    return { containerRef, error, ready, open, markLabel }
  },
  template: /*html*/`
    <div class="result-card chart-card" :class="{ open }">
      <div class="result-card-header" @click="open = !open">
        <span class="arrow"></span>
        <span>图表</span>
        <span class="meta">
          <span v-if="markLabel(spec)" class="chart-mark-badge">{{ markLabel(spec) }}</span>
          <span v-if="spec && spec.title" class="chart-title-text">{{ spec.title }}</span>
        </span>
      </div>
      <div class="result-card-body">
        <div v-if="error" class="chart-error">图表渲染失败: {{ error }}</div>
        <div v-show="!error" ref="containerRef" class="chart-container"></div>
        <div v-if="!ready && !error" class="chart-loading">加载图表库中...</div>
      </div>
    </div>
  `,
}
