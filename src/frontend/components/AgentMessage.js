import { computed } from 'vue'
import ResultCards from '/ui/components/ResultCards.js'
import { renderMarkdown } from '/ui/composables/useMarkdown.js'

export default {
  name: 'AgentMessage',
  components: { ResultCards },
  props: { message: { type: Object, required: true } },
  setup(props) {
    const renderedHtml = computed(() => {
      if (props.message.error) return ''
      if (props.message.streaming && !props.message.text) return ''
      return renderMarkdown(props.message.text || '(无回答)')
    })
    return { renderedHtml }
  },
  template: /*html*/`
    <div class="msg-agent">
      <div class="answer-text" :class="{ error: message.error }">
        <template v-if="message.error">查询失败: {{ message.error }}</template>
        <template v-else-if="message.streaming && !message.text"><em>思考中...</em></template>
        <div v-else class="markdown-body" v-html="renderedHtml"></div>
      </div>
      <ResultCards :message="message" />
    </div>
  `,
}
