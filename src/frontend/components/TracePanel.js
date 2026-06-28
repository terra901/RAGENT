import { defineComponent, h, ref, watch } from 'vue'
import TraceList from '/ui/components/TraceList.js'
import TraceDetail from '/ui/components/TraceDetail.js'

export default defineComponent({
  name: 'TracePanel',
  props: {
    open: { type: Boolean, default: false },
    initialTraceId: { type: String, default: '' },
  },
  emits: ['close'],
  setup(props, { emit }) {
    // 保存当前选中的 trace，并响应外部传入的 initialTraceId。
    const currentTraceId = ref(props.initialTraceId || '')

    watch(() => props.initialTraceId, (v) => {
      // 外部点击消息 trace 链接时同步选中 trace。
      if (v) currentTraceId.value = v
    })

    return () => h('aside', {
      class: ['trace-panel', props.open ? 'open' : ''],
    }, [
      h('header', { class: 'trace-header' }, [
        h('h3', 'Trace'),
        h('button', { onClick: () => emit('close'), class: 'btn-close' }, '×'),
      ]),
      h('div', { class: 'trace-body' }, [
        h(TraceList, {
          onSelect: (id) => {
            // 列表选中后切换右侧详情。
            currentTraceId.value = id
          },
        }),
        currentTraceId.value
          ? h(TraceDetail, { traceId: currentTraceId.value })
          : h('div', { class: 'trace-empty' }, '选择一条 trace 查看详情'),
      ]),
    ])
  },
})
