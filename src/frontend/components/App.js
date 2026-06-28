import { onMounted, onUnmounted } from 'vue'
import { store } from '/ui/store.js'
import { useAuth } from '/ui/composables/useAuth.js'
import { useConversations } from '/ui/composables/useConversations.js?v=20260626-chatfix-1'
import { useHealth } from '/ui/composables/useHealth.js'
import { useQueueStatus } from '/ui/composables/useQueueStatus.js'
import AuthView from '/ui/components/AuthView.js'
import Sidebar from '/ui/components/Sidebar.js?v=20260626-chatfix-1'
import ChatPanel from '/ui/components/ChatPanel.js?v=20260626-chatfix-1'
import AdminPanel from '/ui/admin/AdminPanel.js'

const SIDEBAR_WIDTH_KEY = 'ragent_sidebar_width_v2'
const SIDEBAR_COLLAPSED_KEY = 'ragent_sidebar_collapsed_v2'
const SIDEBAR_MIN_WIDTH = 220
const SIDEBAR_MAX_WIDTH = 420
const SIDEBAR_DEFAULT_WIDTH = 252

function clampSidebarWidth(value) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Number(value) || SIDEBAR_DEFAULT_WIDTH))
}

function readSidebarWidth() {
  try {
    return clampSidebarWidth(window.localStorage?.getItem(SIDEBAR_WIDTH_KEY))
  } catch (_) {
    return SIDEBAR_DEFAULT_WIDTH
  }
}

function readSidebarCollapsed() {
  try {
    return window.localStorage?.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch (_) {
    return false
  }
}

export default {
  name: 'App',
  components: { AuthView, Sidebar, ChatPanel, AdminPanel },
  setup() {
    const auth = useAuth()
    const conv = useConversations()
    const health = useHealth()
    const queue = useQueueStatus()

    async function loadAuthedWorkspace() {
      await conv.load().catch((error) => {
        console.warn('历史对话加载失败:', error)
      })
    }

    async function onAuthenticated() {
      await loadAuthedWorkspace()
    }

    onMounted(async () => {
      const authed = await auth.bootstrap()
      health.start()
      if (authed) {
        await loadAuthedWorkspace()
        queue.start()
      }
    })

    onUnmounted(() => {
      health.stop()
      queue.stop()
    })

    return { store, onAuthenticated }
  },
  data() {
    return {
      sidebarWidth: readSidebarWidth(),
      sidebarCollapsed: readSidebarCollapsed(),
      isResizingSidebar: false,
      resizeStartX: 0,
      resizeStartWidth: SIDEBAR_DEFAULT_WIDTH,
    }
  },
  beforeUnmount() {
    this.stopSidebarResize()
  },
  computed: {
    shellStyle() {
      const columns = this.sidebarCollapsed
        ? '56px minmax(0, 1fr)'
        : `minmax(220px, ${this.sidebarWidth}px) 1px minmax(0, 1fr)`
      return {
        '--sidebar-width': `${this.sidebarWidth}px`,
        width: '100%',
        height: '100vh',
        minWidth: '0',
        minHeight: '0',
        display: 'grid',
        gridTemplateColumns: columns,
        gridTemplateRows: 'minmax(0, 1fr)',
        overflow: 'hidden',
      }
    },
  },
  methods: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      try {
        window.localStorage?.setItem(SIDEBAR_COLLAPSED_KEY, String(this.sidebarCollapsed))
      } catch (_) { /* noop */ }
    },
    resetSidebarWidth() {
      this.sidebarWidth = SIDEBAR_DEFAULT_WIDTH
      try {
        window.localStorage?.setItem(SIDEBAR_WIDTH_KEY, String(this.sidebarWidth))
      } catch (_) { /* noop */ }
    },
    startSidebarResize(event) {
      if (this.sidebarCollapsed) return
      event.preventDefault()
      this.isResizingSidebar = true
      this.resizeStartX = event.clientX
      this.resizeStartWidth = this.sidebarWidth
      document.body.classList.add('is-resizing-sidebar')
      window.addEventListener('pointermove', this.onSidebarResize)
      window.addEventListener('pointerup', this.stopSidebarResize)
    },
    onSidebarResize(event) {
      if (!this.isResizingSidebar) return
      const nextWidth = clampSidebarWidth(this.resizeStartWidth + event.clientX - this.resizeStartX)
      this.sidebarWidth = nextWidth
      try {
        window.localStorage?.setItem(SIDEBAR_WIDTH_KEY, String(nextWidth))
      } catch (_) { /* noop */ }
    },
    stopSidebarResize() {
      if (!this.isResizingSidebar) return
      this.isResizingSidebar = false
      document.body.classList.remove('is-resizing-sidebar')
      window.removeEventListener('pointermove', this.onSidebarResize)
      window.removeEventListener('pointerup', this.stopSidebarResize)
    },
  },
  template: /*html*/`
    <div class="app-root">
      <div v-if="store.auth.status === 'loading'" class="loading-screen">
        <div class="loading-panel">
          <strong>RAGENT</strong>
          <span>正在加载 RAGENT</span>
        </div>
      </div>
      <AuthView
        v-else-if="store.auth.status !== 'authenticated'"
        @authenticated="onAuthenticated"
      />
      <div
        v-else
        class="libre-shell"
        :class="{ 'sidebar-collapsed': sidebarCollapsed, 'is-resizing': isResizingSidebar }"
        :style="shellStyle"
      >
        <Sidebar :collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
        <div
          v-if="!sidebarCollapsed"
          class="sidebar-resizer"
          style="grid-column: 2; grid-row: 1; display: block; min-width: 0; min-height: 0;"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整侧边栏宽度"
          @pointerdown="startSidebarResize"
          @dblclick="resetSidebarWidth"
        ></div>
        <ChatPanel v-if="store.view === 'chat'" :style="{ gridColumn: sidebarCollapsed ? '2' : '3', gridRow: '1', minWidth: '0', minHeight: '0' }" />
        <AdminPanel v-else :style="{ gridColumn: sidebarCollapsed ? '2' : '3', gridRow: '1', minWidth: '0', minHeight: '0' }" />
      </div>
    </div>
  `,
}
