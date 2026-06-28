import { store, currentMessages } from '/ui/store.js'
import UserMessage from '/ui/components/UserMessage.js'
import AgentMessage from '/ui/components/AgentMessage.js'

export default {
  name: 'MessageList',
  components: { UserMessage, AgentMessage },
  setup() {
    return { store }
  },
  computed: {
    messages() {
      return currentMessages()
    },
  },
  updated() {
    this.$nextTick(() => {
      const list = this.$refs.list
      if (list) list.scrollTop = list.scrollHeight
    })
  },
  template: /*html*/`
    <div class="message-list" ref="list">
      <div class="message-list-inner">
        <div v-if="!messages.length" class="empty-state">
          <h1>RAGENT</h1>
          <p>输入问题开始一次 RAGENT。</p>
        </div>
        <template v-else>
          <template v-for="m in messages" :key="m.id">
            <UserMessage v-if="m.role === 'user'" :text="m.text" />
            <AgentMessage v-else :message="m" />
          </template>
        </template>
      </div>
    </div>
  `,
}
