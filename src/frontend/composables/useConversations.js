import { store } from '/ui/store.js'
import { apiFetch } from '/ui/composables/useApiFetch.js'

function newUiId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'm-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function normalizeConversation(item) {
  return {
    id: item.id,
    title: item.title || '新对话',
    createdAt: item.created_at || item.createdAt || null,
    updatedAt: item.updated_at || item.updatedAt || null,
    lastMessageAt: item.last_message_at || item.lastMessageAt || null,
    messageCount: Number(item.message_count || item.messageCount || 0),
    messages: item.messages || [],
    pending: !!item.pending,
  }
}

function toUiMessage(row) {
  const meta = row.metadata || {}
  if (row.role === 'user') {
    return { id: row.id || newUiId(), role: 'user', text: row.content || '', streaming: false }
  }
  return {
    id: row.id || newUiId(),
    role: 'agent',
    text: row.content || '',
    sql: meta.sql || null,
    rows: meta.rows || null,
    columns: meta.columns || null,
    steps: meta.steps || [],
    usage: meta.total_usage || meta.usage || null,
    rowCount: Number(meta.row_count || 0),
    executionTimeMs: Number(meta.execution_time_ms || 0),
    cacheHit: !!meta.cache_hit,
    vizHint: meta.visualization_hint || '',
    chartSpec: meta.chart_spec || null,
    traceId: row.trace_id || meta.trace_id || null,
    error: meta.error || null,
    streaming: false,
  }
}

function mergeConversationList(items) {
  const previous = new Map(store.conversations.map(item => [item.id, item]))
  store.conversations = items.map((raw) => {
    const normalized = normalizeConversation(raw)
    const old = previous.get(normalized.id)
    if (old && old.messages) normalized.messages = old.messages
    return normalized
  })
}

export function useConversations() {
  async function load() {
    if (store.auth.status !== 'authenticated') return
    const response = await apiFetch('/api/conversations')
    if (!response.ok) throw new Error('历史对话加载失败')
    const payload = await response.json()
    mergeConversationList(payload.items || [])
    if (store.conversations.length) {
      const keepCurrent = store.conversations.find(c => c.id === store.currentConversationId)
      store.currentConversationId = keepCurrent ? keepCurrent.id : store.conversations[0].id
      await loadMessages(store.currentConversationId)
    } else {
      store.currentConversationId = null
    }
  }

  async function reloadList() {
    if (store.auth.status !== 'authenticated') return
    const current = store.currentConversationId
    const response = await apiFetch('/api/conversations')
    if (!response.ok) return
    const payload = await response.json()
    mergeConversationList(payload.items || [])
    if (current && store.conversations.find(c => c.id === current)) {
      store.currentConversationId = current
    }
  }

  function createLocal(title = '新对话') {
    const existingEmpty = store.conversations.find(item => item.pending && !item.messages?.length)
    if (existingEmpty) {
      store.currentConversationId = existingEmpty.id
      return existingEmpty
    }
    const item = normalizeConversation({
      id: newUiId(),
      title,
      messages: [],
      pending: true,
    })
    store.conversations = [item, ...store.conversations]
    store.currentConversationId = item.id
    return item
  }

  async function create(title = '新对话') {
    const response = await apiFetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!response.ok) throw new Error('对话创建失败')
    const payload = await response.json()
    const item = normalizeConversation(payload.conversation)
    item.messages = []
    store.conversations = [item, ...store.conversations.filter(c => c.id !== item.id)]
    store.currentConversationId = item.id
    return item
  }

  async function select(id) {
    if (!store.conversations.find(c => c.id === id)) return
    store.currentConversationId = id
    const conv = store.conversations.find(c => c.id === id)
    if (conv?.pending) return
    await loadMessages(id)
  }

  async function loadMessages(id) {
    const conv = store.conversations.find(c => c.id === id)
    if (!conv) return
    if (conv.pending) return
    const response = await apiFetch(`/api/conversations/${encodeURIComponent(id)}`)
    if (!response.ok) return
    const payload = await response.json()
    Object.assign(conv, normalizeConversation(payload.conversation || conv))
    conv.messages = (payload.messages || []).map(toUiMessage)
  }

  async function remove(id) {
    const conv = store.conversations.find(c => c.id === id)
    if (conv?.pending) {
      store.conversations = store.conversations.filter(c => c.id !== id)
      if (store.currentConversationId === id) {
        store.currentConversationId = store.conversations[0]?.id || null
        if (store.currentConversationId) await loadMessages(store.currentConversationId)
      }
      return
    }
    const response = await apiFetch(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!response.ok) return
    store.conversations = store.conversations.filter(c => c.id !== id)
    if (store.currentConversationId === id) {
      store.currentConversationId = store.conversations[0]?.id || null
      if (store.currentConversationId) await loadMessages(store.currentConversationId)
    }
  }

  async function updateTitle(id, title) {
    const conv = store.conversations.find(c => c.id === id)
    if (conv) conv.title = title
    if (conv?.pending) return
    await apiFetch(`/api/conversations/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).catch(() => null)
  }

  function persist() {
    return null
  }

  return { load, reloadList, create, createLocal, select, loadMessages, remove, updateTitle, persist }
}
