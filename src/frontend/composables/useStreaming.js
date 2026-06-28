import { reactive } from 'vue'
import { store, currentMessages } from '/ui/store.js'
import { useConversations } from '/ui/composables/useConversations.js?v=20260626-chatfix-1'

function newMsgId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'm-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

async function* readSSE(reader) {
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      if (buffer.trim()) {
        const ev = parseBlock(buffer)
        if (ev) yield ev
      }
      return
    }
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const ev = parseBlock(block)
      if (ev) yield ev
    }
  }
}

function parseBlock(block) {
  let event = 'message', data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  try { return { event, data: data ? JSON.parse(data) : {} } }
  catch { return { event, data: {} } }
}

export function useStreaming() {
  const conv = useConversations()

  async function ask(question) {
    if (!question || store.streaming || store.auth.status !== 'authenticated') return
    let conversationId = store.currentConversationId
    if (!conversationId) {
      const created = conv.createLocal(question.slice(0, 40))
      conversationId = created.id
    }

    const messages = currentMessages()
    messages.push({ id: newMsgId(), role: 'user', text: question })

    const active = store.conversations.find(item => item.id === conversationId)
    if (active && (active.title === '新对话' || !active.title || active.pending)) {
      const nextTitle = question.slice(0, 40)
      active.title = nextTitle
      conv.updateTitle(active.id, nextTitle)
    }

    const agentMsg = reactive({
      id: newMsgId(), role: 'agent',
      text: '', sql: null, rows: null, columns: null, steps: [],
      usage: null, rowCount: 0, executionTimeMs: 0,
      cacheHit: false, vizHint: '', chartSpec: null,
      traceId: null,
      error: null, streaming: true,
    })
    messages.push(agentMsg)
    store.streaming = true

    try {
      const { apiFetch } = await import('/ui/composables/useApiFetch.js')
      const response = await apiFetch('/api/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify({ question, session_id: conversationId }),
      })
      if (!response.ok || !response.body) {
        const text = await response.text().catch(() => '')
        throw new Error(text || `HTTP ${response.status}`)
      }
      const reader = response.body.getReader()
      for await (const { event, data } of readSSE(reader)) {
        if (event === 'step') {
          const idx = agentMsg.steps.findIndex(s => s.name === data.name)
          if (idx >= 0) agentMsg.steps[idx] = { ...agentMsg.steps[idx], ...data }
          else agentMsg.steps.push({ ...data })
        } else if (event === 'sql_chunk') {
          if (data.discard) agentMsg.sql = ''
          else if (data.text) agentMsg.sql = (agentMsg.sql || '') + data.text
        } else if (event === 'sql') {
          agentMsg.sql = data.sql
        } else if (event === 'rows') {
          agentMsg.columns = data.columns
          agentMsg.rows = data.rows
        } else if (event === 'answer_chunk') {
          if (data.text) agentMsg.text = (agentMsg.text || '') + data.text
        } else if (event === 'chart') {
          if (data.spec) agentMsg.chartSpec = data.spec
        } else if (event === 'usage') {
          agentMsg.usage = { ...data }
        } else if (event === 'done') {
          if (data.answer && !agentMsg.text) agentMsg.text = data.answer
          if (data.total_usage) agentMsg.usage = data.total_usage
          agentMsg.rowCount = data.row_count || 0
          agentMsg.executionTimeMs = data.execution_time_ms || 0
          agentMsg.cacheHit = !!data.cache_hit
          agentMsg.vizHint = data.visualization_hint || ''
          if (data.chart_spec && !agentMsg.chartSpec) agentMsg.chartSpec = data.chart_spec
          if (data.trace_id) agentMsg.traceId = data.trace_id
        } else if (event === 'error') {
          agentMsg.error = data.message || '请求失败'
        }
      }
    } catch (e) {
      agentMsg.error = e.message || '请求失败'
    } finally {
      agentMsg.streaming = false
      store.streaming = false
      await conv.reloadList().catch(() => null)
      await conv.loadMessages(conversationId).catch(() => null)
    }
  }

  return { ask }
}
