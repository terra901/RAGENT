import { store } from '/ui/store.js'
import MessageList from '/ui/components/MessageList.js'
import QueryBox from '/ui/components/QueryBox.js?v=20260626-chatfix-1'

export default {
  name: 'ChatPanel',
  components: { MessageList, QueryBox },
  setup() {
    return { store }
  },
  computed: {
    title() {
      const conversation = this.store.conversations.find(item => item.id === this.store.currentConversationId)
      return conversation?.title || 'RAGENT'
    },
    hasMessages() {
      const conversation = this.store.conversations.find(item => item.id === this.store.currentConversationId)
      return !!conversation?.messages?.length
    },
  },
  template: /*html*/`
    <main class="chat-panel" :class="{ landing: !hasMessages }">
      <header class="chat-topbar">
        <div class="min-w-0">
          <h1>{{ title }}</h1>
        </div>
        <div class="chat-topbar-actions">
          <span class="status-pill" :class="store.health">
            {{ store.health === 'ok' ? '服务正常' : store.health === 'error' ? '服务异常' : '检查中' }}
          </span>
          <span class="status-pill">
            {{ store.streaming ? '生成中' : '就绪' }}
          </span>
        </div>
      </header>
      <template v-if="hasMessages">
        <MessageList />
        <QueryBox />
      </template>
      <section v-else class="chat-landing" aria-label="开始对话">
        <div class="landing-brand">
          <div class="landing-mark" aria-hidden="true">R</div>
          <h2>RAGENT</h2>
        </div>
        <QueryBox />
      </section>
    </main>
  `,
}
