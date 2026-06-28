import { currentConversation } from '/ui/store.js'
import SchemaTree from '/ui/components/SchemaTree.js'

export default {
  name: 'ContextPanel',
  components: { SchemaTree },
  props: {
    store: { type: Object, required: true },
  },
  computed: {
    conversation() {
      return currentConversation()
    },
    messages() {
      return this.conversation?.messages || []
    },
    latestAgentMessage() {
      return [...this.messages].reverse().find(message => message.role === 'agent') || null
    },
    modules() {
      return this.store.auth.permissions?.allowed_modules || []
    },
    resultSummary() {
      const message = this.latestAgentMessage
      if (!message) return null
      return {
        rowCount: message.rowCount || (message.rows ? message.rows.length : 0),
        executionTimeMs: Math.round(message.executionTimeMs || 0),
        stepCount: message.steps?.length || 0,
        tokens: message.usage?.total_tokens || message.usage?.totalTokens || 0,
        traceId: message.traceId || '',
      }
    },
  },
  template: /*html*/`
    <aside class="context-panel" aria-label="上下文面板">
      <section class="context-section">
        <div class="context-section-header">
          <h2>当前会话</h2>
        </div>
        <div v-if="conversation" class="context-metric-grid">
          <div>
            <span>消息</span>
            <strong>{{ messages.length }}</strong>
          </div>
          <div>
            <span>状态</span>
            <strong>{{ store.streaming ? '运行中' : '就绪' }}</strong>
          </div>
        </div>
        <div v-if="conversation" class="context-current-title" :title="conversation.title">
          {{ conversation.title || '新对话' }}
        </div>
        <div v-else class="context-empty">
          <strong>未选择会话</strong>
          <span>新建对话后会在这里显示上下文。</span>
        </div>
      </section>

      <section class="context-section">
        <div class="context-section-header">
          <h2>最近结果</h2>
        </div>
        <div v-if="resultSummary" class="context-metric-grid">
          <div>
            <span>行数</span>
            <strong>{{ resultSummary.rowCount }}</strong>
          </div>
          <div>
            <span>耗时</span>
            <strong>{{ resultSummary.executionTimeMs }}ms</strong>
          </div>
          <div>
            <span>步骤</span>
            <strong>{{ resultSummary.stepCount }}</strong>
          </div>
          <div>
            <span>Tokens</span>
            <strong>{{ resultSummary.tokens || '-' }}</strong>
          </div>
        </div>
        <div v-if="resultSummary?.traceId" class="context-long-id">
          {{ resultSummary.traceId }}
        </div>
        <div v-else-if="!resultSummary" class="context-empty">
          <strong>暂无结果</strong>
          <span>发送问题后会显示 SQL、耗时和执行摘要。</span>
        </div>
      </section>

      <section class="context-section context-section-grow">
        <div class="context-section-header">
          <h2>Schema</h2>
        </div>
        <SchemaTree />
      </section>

      <section class="context-section">
        <div class="context-section-header">
          <h2>权限模块</h2>
        </div>
        <div v-if="modules.length" class="module-chip-list">
          <span v-for="module in modules" :key="module" :title="module">{{ module }}</span>
        </div>
        <div v-else class="context-empty">
          <strong>未返回模块权限</strong>
          <span>请重新登录或检查认证服务。</span>
        </div>
      </section>
    </aside>
  `,
}
