import { store } from '/ui/store.js'
import ModelManagement from '/ui/admin/ModelManagement.js'
import TraceAdmin from '/ui/admin/TraceAdmin.js'

export default {
  name: 'AdminPanel',
  components: { ModelManagement, TraceAdmin },
  setup() {
    return { store }
  },
  template: /*html*/`
    <main class="admin-panel">
      <header class="admin-topbar">
        <div>
          <h1>后台管理</h1>
        </div>
        <div class="admin-tabs" role="tablist" aria-label="后台管理模块">
          <button
            type="button"
            :class="{ active: store.adminTab === 'models' }"
            @click="store.adminTab = 'models'"
          >模型管理</button>
          <button
            type="button"
            :class="{ active: store.adminTab === 'traces' }"
            @click="store.adminTab = 'traces'"
          >Trace</button>
        </div>
      </header>
      <ModelManagement v-if="store.adminTab === 'models'" />
      <TraceAdmin v-else />
    </main>
  `,
}
