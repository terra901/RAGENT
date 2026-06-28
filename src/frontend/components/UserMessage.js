export default {
  name: 'UserMessage',
  props: { text: { type: String, required: true } },
  template: /*html*/`
    <div class="msg-user">
      <div class="bubble">{{ text }}</div>
    </div>
  `,
}
