import { store } from '/ui/store.js'
import { useSchema } from '/ui/composables/useSchema.js'

export default {
  name: 'SchemaTree',
  data() {
    // 保存表展开状态，key 为表名。
    return { open: {} }  // tableName -> bool
  },
  computed: {
    schema() {
      // 从全局 store 读取 schema 加载状态和表结构。
      return store.schema
    },
  },
  methods: {
    toggle(name) {
      // 展开或收起指定表。
      this.open[name] = !this.open[name]
    },
    pick(text) {
      // 把点击的表名或列名追加到输入框。
      store.draft = (store.draft ? store.draft + ' ' : '') + text
    },
    retry() {
      // schema 加载失败时重新拉取。
      useSchema().load()
    },
  },
  template: /*html*/`
    <div class="schema-tree">
      <div v-if="schema.loading" style="color:var(--text-muted);font-size:11px;padding:6px">加载中...</div>
      <div v-else-if="schema.error" class="schema-error" @click="retry">
        加载失败 · 点击重试
      </div>
      <div v-else-if="!schema.tables.length" style="color:var(--text-muted);font-size:11px;padding:6px">无表</div>
      <div v-else>
        <div v-for="t in schema.tables" :key="t.name" class="schema-table">
          <div class="schema-table-name" @click="toggle(t.name)" :title="t.comment || ''">
            <span>{{ open[t.name] ? '▼' : '▶' }}</span>
            <span @click.stop="pick(t.name)">{{ t.name }}</span>
            <span class="row-count" v-if="t.row_count !== null">{{ t.row_count }} rows</span>
          </div>
          <ul v-if="open[t.name]" class="schema-cols">
            <li v-for="c in t.columns" :key="c.name" class="schema-col"
                @click="pick(t.name + '.' + c.name)" :title="c.comment || ''">
              <span>{{ c.name }}<span v-if="c.is_primary_key" style="color:var(--accent)"> *</span></span>
              <span class="col-type">{{ c.data_type }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  `,
}
