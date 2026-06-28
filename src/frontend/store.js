import { reactive } from 'vue'

export const store = reactive({
  health: 'unknown',
  auth: {
    status: 'loading',
    user: null,
    permissions: null,
    token: '',
    error: '',
  },
  theme: 'light',
  view: 'chat',
  adminTab: 'models',
  currentConversationId: null,
  conversations: [],
  schema: {
    loading: false,
    error: null,
    tables: [],
  },
  streaming: false,
  draft: '',
  queue: {
    loading: false,
    queued: 0,
    started: 0,
    latest: null,
    error: '',
  },
})

export function currentConversation() {
  return store.conversations.find(c => c.id === store.currentConversationId) || null
}

export function currentMessages() {
  const conv = currentConversation()
  return conv ? conv.messages : []
}
