import { defineComponent, h, ref, computed } from 'vue'

const KIND_EMOJI = {
  llm: '🤖', retrieval: '🔍', tool: '🛠', sql_exec: '🗄',
  cache: '⚡', chain: '🧭', decision: '🚦',
}

export default defineComponent({
  name: 'SpanTree',
  props: {
    spans: { type: Array, required: true },
  },
  setup(props) {
    // 把 span 平铺列表组织成可展开的树形结构。
    const expanded = ref(new Set())

    const tree = computed(() => {
      // 按 parent_span_id 分组，再递归构建树。
      const byParent = new Map()
      for (const s of props.spans) {
        const k = s.parent_span_id || '_root'
        if (!byParent.has(k)) byParent.set(k, [])
        byParent.get(k).push(s)
      }
      const build = (parent) => {
        // 递归构建指定父节点下的所有子节点。
        return (byParent.get(parent) || []).map(s => ({
          ...s,
          children: build(s.span_id),
          duration_ms: s.ended_at && s.started_at
            ? ((s.ended_at - s.started_at) * 1000).toFixed(1)
            : '?',
        }))
      }
      return build('_root')
    })

    const toggle = (id) => {
      // 展开或收起一个 span 节点。
      const next = new Set(expanded.value)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      expanded.value = next
    }

    const renderNode = (node, depth = 0) => {
      // 渲染单个 span 节点及其子节点。
      return h('div', { class: 'span-node', style: { marginLeft: `${depth * 16}px` } }, [
        h('div', {
          class: ['span-row', node.error ? 'has-error' : ''],
          onClick: () => toggle(node.span_id),
        }, [
          h('span', { class: 'span-kind' }, KIND_EMOJI[node.kind] || '·'),
          h('span', { class: 'span-name' }, node.name),
          h('span', { class: 'span-duration' }, `${node.duration_ms}ms`),
          node.tokens != null ? h('span', { class: 'span-tokens' }, `${node.tokens}t`) : null,
          node.error ? h('span', { class: 'span-error' }, '❌') : null,
        ]),
        expanded.value.has(node.span_id) ? h('div', { class: 'span-detail' }, [
          node.inputs_json ? h('pre', { class: 'span-json' }, `inputs: ${node.inputs_json}`) : null,
          node.outputs_json ? h('pre', { class: 'span-json' }, `outputs: ${node.outputs_json}`) : null,
          node.error ? h('pre', { class: 'span-json error' }, node.error) : null,
        ]) : null,
        ...node.children.map(c => renderNode(c, depth + 1)),
      ])
    }

    return () => h('div', { class: 'span-tree' }, tree.value.map(n => renderNode(n)))
  },
})
