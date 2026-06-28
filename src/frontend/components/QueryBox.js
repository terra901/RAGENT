import { store } from '/ui/store.js'
import { useStreaming } from '/ui/composables/useStreaming.js?v=20260626-chatfix-1'

export default {
  name: 'QueryBox',
  setup() {
    const streaming = useStreaming()
    return { store, streaming }
  },
  computed: {
    disabled() {
      return this.store.streaming || !this.store.draft.trim()
    },
    queueLabel() {
      if (this.store.queue.error) return this.store.queue.error
      if (this.store.queue.started > 0) return `运行中 ${this.store.queue.started} 个任务`
      if (this.store.queue.queued > 0) return `队列中 ${this.store.queue.queued} 个任务`
      return '队列空闲'
    },
  },
  methods: {
    submit() {
      const question = this.store.draft.trim()
      if (!question || this.store.streaming) return
      this.store.draft = ''
      this.streaming.ask(question)
    },
    onKeydown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        this.submit()
      }
    },
  },
  template: /*html*/`
    <div class="query-box">
      <div class="queue-strip" :class="{ active: store.queue.queued || store.queue.started, error: store.queue.error }">
        <span>{{ queueLabel }}</span>
        <span v-if="store.queue.latest">最近任务：{{ store.queue.latest.status }}</span>
      </div>
      <div class="query-box-inner">
        <textarea
          v-model="store.draft"
          @keydown="onKeydown"
          :placeholder="store.streaming ? 'RAGENT 生成中...' : '输入消息'"
          :disabled="store.streaming"
          rows="1"
        ></textarea>
        <button @click="submit" :disabled="disabled">
          {{ store.streaming ? '发送中' : '发送' }}
        </button>
      </div>
    </div>
  `,
}
