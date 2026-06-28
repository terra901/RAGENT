import { store } from '/ui/store.js'
import { useAuth } from '/ui/composables/useAuth.js'
import { useConversations } from '/ui/composables/useConversations.js?v=20260626-chatfix-1'

const CRITICAL_LAYOUT_STYLE_ID = 'ragent-critical-layout-inline-grid'

function ensureCriticalLayoutStyle() {
  if (typeof document === 'undefined' || document.getElementById(CRITICAL_LAYOUT_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = CRITICAL_LAYOUT_STYLE_ID
  style.textContent = `
    .libre-shell {
      width: 100% !important;
      height: 100vh !important;
      min-width: 0 !important;
      min-height: 0 !important;
      display: grid !important;
      grid-template-columns: minmax(220px, var(--sidebar-width, 252px)) 1px minmax(0, 1fr) !important;
      grid-template-rows: minmax(0, 1fr) !important;
      overflow: hidden !important;
    }
    .libre-shell.sidebar-collapsed {
      grid-template-columns: 56px minmax(0, 1fr) !important;
    }
    .sidebar {
      grid-column: 1 !important;
      grid-row: 1 !important;
      width: auto !important;
      min-width: 0 !important;
      min-height: 0 !important;
      display: flex !important;
      flex-direction: column !important;
      overflow: hidden !important;
      border-right: 1px solid var(--border) !important;
      border-bottom: 0 !important;
    }
    .sidebar-resizer {
      grid-column: 2 !important;
      grid-row: 1 !important;
      display: block !important;
      min-width: 0 !important;
      min-height: 0 !important;
    }
    .chat-panel {
      position: relative !important;
      min-width: 0 !important;
      min-height: 0 !important;
    }
    .history-block {
      display: flex !important;
      flex-direction: column !important;
      min-width: 0 !important;
      min-height: 0 !important;
      flex: 1 1 auto !important;
    }
    .account-block {
      display: grid !important;
      min-width: 0 !important;
      width: 100% !important;
    }
    @media (max-width: 860px) {
      .libre-shell {
        grid-template-columns: minmax(220px, min(var(--sidebar-width, 252px), 42vw)) 1px minmax(0, 1fr) !important;
        grid-template-rows: minmax(0, 1fr) !important;
      }
      .libre-shell.sidebar-collapsed {
        grid-template-columns: 56px minmax(0, 1fr) !important;
      }
    }
  `
  document.head.appendChild(style)
}

ensureCriticalLayoutStyle()

export default {
  name: 'Sidebar',
  props: {
    collapsed: { type: Boolean, default: false },
  },
  emits: ['toggle-sidebar'],
  setup() {
    const auth = useAuth()
    const conv = useConversations()
    return { store, auth, conv }
  },
  data() {
    return {
      accountOpen: false,
    }
  },
  methods: {
    toggleSidebar() {
      this.accountOpen = false
      this.$emit('toggle-sidebar')
    },
    async onNew() {
      this.accountOpen = false
      this.store.view = 'chat'
      this.store.draft = ''
      this.conv.createLocal()
    },
    async onSelect(id) {
      this.accountOpen = false
      this.store.view = 'chat'
      await this.conv.select(id)
    },
    openAdmin() {
      this.accountOpen = false
      this.store.view = 'admin'
    },
    async onDelete(id) {
      if (confirm('删除这个对话？')) await this.conv.remove(id)
    },
    async onLogout() {
      this.accountOpen = false
      await this.auth.logout()
    },
    formatDate(value) {
      if (!value) return ''
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) return ''
      return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
    },
  },
  template: /*html*/`
    <aside
      class="sidebar"
      :class="{ collapsed }"
      aria-label="RAGENT 侧边栏"
      style="grid-column: 1; grid-row: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; border-bottom: 0;"
    >
      <div class="sidebar-header">
        <button class="sidebar-icon-button" type="button" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleSidebar">
          <span>R</span>
        </button>
        <div v-if="!collapsed" class="sidebar-actions">
          <button class="new-chat-text-btn" type="button" @click="onNew" aria-label="新建对话">
            <span aria-hidden="true"></span>
            新建
          </button>
        </div>
        <button v-else class="new-chat-btn" type="button" @click="onNew" aria-label="新建对话">新建对话</button>
      </div>

      <div v-if="!collapsed" class="history-block" aria-label="历史聊天">
        <div class="history-search">
          <span aria-hidden="true"></span>
          <input type="search" placeholder="搜索消息" aria-label="搜索消息" />
        </div>
        <div class="sidebar-label">历史聊天</div>
        <button
          v-if="store.auth.user?.is_admin"
          class="admin-nav-button"
          :class="{ active: store.view === 'admin' }"
          type="button"
          @click="openAdmin"
        >后台管理</button>
        <div v-if="!store.conversations.length" class="history-empty">
          <strong>暂无对话</strong>
          <span>开始对话后会显示在这里。</span>
        </div>
        <ul v-else class="conv-list">
          <li v-for="c in store.conversations" :key="c.id">
            <button
              class="conv-item"
              :class="{ active: c.id === store.currentConversationId }"
              type="button"
              @click="onSelect(c.id)"
            >
              <span class="conv-title">{{ c.title || '新对话' }}</span>
              <span class="conv-date">{{ formatDate(c.lastMessageAt || c.updatedAt || c.createdAt) }}</span>
            </button>
            <button class="conv-delete" type="button" @click="onDelete(c.id)" aria-label="删除对话">删除</button>
          </li>
        </ul>
      </div>

      <div class="account-block">
        <div v-if="!collapsed" class="sidebar-product">
          <div class="product-mark" aria-hidden="true">R</div>
          <span>RAGENT</span>
        </div>
        <button class="account-trigger" type="button" @click="accountOpen = !accountOpen" :aria-expanded="accountOpen">
          <div class="account-avatar" aria-hidden="true">
            {{ (store.auth.user?.name || store.auth.user?.email || 'U').slice(0, 1).toUpperCase() }}
          </div>
          <div v-if="!collapsed" class="account-copy min-w-0">
            <div class="account-name">{{ store.auth.user?.name || store.auth.user?.email }}</div>
            <div class="account-email">{{ store.auth.user?.email }}</div>
          </div>
          <span v-if="!collapsed" class="account-caret" aria-hidden="true"></span>
        </button>
        <div v-if="accountOpen" class="account-menu">
          <button type="button" @click="auth.toggleTheme">
            {{ store.theme === 'dark' ? '切换到浅色模式' : '切换到深色模式' }}
          </button>
          <button type="button" @click="onLogout">退出登录</button>
        </div>
      </div>
    </aside>
  `,
}
