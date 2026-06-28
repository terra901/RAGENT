export default {
  name: 'StepsCard',
  props: {
    steps: { type: Array, required: true },
  },
  data() {
    return { open: false }
  },
  computed: {
    totalMs() {
      return Math.round(this.steps.reduce((sum, step) => sum + (step.elapsed_ms || 0), 0))
    },
  },
  template: /*html*/`
    <div class="result-card" :class="{ open }" v-if="steps.length">
      <div class="result-card-header" @click="open = !open">
        <span class="arrow"></span>
        <span>执行步骤</span>
        <span class="meta">{{ steps.length }} 步 · {{ totalMs }}ms</span>
      </div>
      <div class="result-card-body">
        <ul class="steps-list">
          <li v-for="(s, i) in steps" :key="s.name + i" class="step-card" :class="'status-' + s.status">
            <div class="step-state">
              <div v-if="s.status === 'running'" class="spinner"></div>
              <span v-else>{{ s.status === 'error' ? '错误' : '完成' }}</span>
            </div>
            <div class="step-main">
              <div class="step-name">{{ i + 1 }}. {{ s.name }}<span v-if="s.elapsed_ms" class="step-time">{{ Math.round(s.elapsed_ms) }}ms</span></div>
              <div v-if="s.detail" class="step-detail">{{ s.detail }}</div>
            </div>
          </li>
        </ul>
      </div>
    </div>
  `,
}
