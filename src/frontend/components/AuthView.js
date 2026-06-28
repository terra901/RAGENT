import { store } from '/ui/store.js'
import { useAuth } from '/ui/composables/useAuth.js'

export default {
  name: 'AuthView',
  emits: ['authenticated'],
  setup() {
    const auth = useAuth()
    return { store, auth }
  },
  data() {
    return {
      mode: 'login',
      name: '',
      email: '',
      password: '',
      confirmPassword: '',
      showPassword: false,
      agreeTerms: false,
      submitting: false,
      localError: '',
    }
  },
  computed: {
    isRegister() {
      return this.mode === 'register'
    },
    passwordRules() {
      return [
        { label: '至少 8 位', passed: this.password.length >= 8 },
        { label: '包含字母', passed: /[A-Za-z]/.test(this.password) },
        { label: '包含数字', passed: /\d/.test(this.password) },
      ]
    },
  },
  methods: {
    switchMode(mode) {
      this.mode = mode
      this.localError = ''
      this.store.auth.error = ''
    },
    validateForm() {
      const email = this.email.trim()
      const password = this.password || ''
      if (this.isRegister && !this.name.trim()) {
        this.localError = '请输入姓名。'
        return false
      }
      if (!email) {
        this.localError = '请输入邮箱。'
        return false
      }
      if (!password) {
        this.localError = '请输入密码。'
        return false
      }
      if (this.isRegister && password.length < 8) {
        this.localError = '密码至少需要 8 个字符。'
        return false
      }
      if (this.isRegister && !/[A-Za-z]/.test(password)) {
        this.localError = '密码需要包含英文字母。'
        return false
      }
      if (this.isRegister && !/\d/.test(password)) {
        this.localError = '密码需要包含数字。'
        return false
      }
      if (this.isRegister && password !== this.confirmPassword) {
        this.localError = '两次输入的密码不一致。'
        return false
      }
      if (this.isRegister && !this.agreeTerms) {
        this.localError = '请先同意服务条款。'
        return false
      }
      return true
    },
    async submit() {
      if (this.submitting) return
      this.localError = ''
      if (!this.validateForm()) return
      this.submitting = true
      try {
        if (this.isRegister) {
          await this.auth.register({
            name: this.name.trim(),
            email: this.email.trim(),
            password: this.password,
          })
        } else {
          await this.auth.login({
            email: this.email.trim(),
            password: this.password,
          })
        }
        this.$emit('authenticated')
      } catch (error) {
        this.localError = error.message || '请求失败'
      } finally {
        this.submitting = false
      }
    },
  },
  template: /*html*/`
    <main class="auth-shell">
      <button class="auth-theme-button" type="button" @click="auth.toggleTheme" aria-label="切换主题">
        {{ store.theme === 'dark' ? '浅色' : '深色' }}
      </button>

      <section class="auth-card" aria-label="RAGENT 账号">
        <div class="auth-logo" aria-hidden="true">
          <span>R</span>
        </div>

        <div class="auth-heading">
          <h1>{{ isRegister ? '创建 RAGENT 账号' : '登录 RAGENT' }}</h1>
          <p>{{ isRegister ? '注册后可继续保存历史对话。' : '使用邮箱和密码继续访问 RAGENT。' }}</p>
        </div>

        <div v-if="localError || store.auth.error" class="auth-alert" role="alert">
          {{ localError || store.auth.error }}
        </div>

        <form class="auth-form" @submit.prevent="submit">
          <label v-if="isRegister" class="field">
            <span>姓名</span>
            <input v-model.trim="name" autocomplete="name" required maxlength="80" placeholder="请输入姓名" />
          </label>

          <label class="field">
            <span>邮箱</span>
            <input v-model.trim="email" type="email" autocomplete="email" required maxlength="255" placeholder="name@company.com" />
          </label>

          <label class="field">
            <span>密码</span>
            <div class="password-row">
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                required
                :minlength="isRegister ? 8 : 1"
                maxlength="128"
                placeholder="请输入密码"
              />
              <button type="button" @click="showPassword = !showPassword" :aria-label="showPassword ? '隐藏密码' : '显示密码'">
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </div>
          </label>

          <label v-if="isRegister" class="field">
            <span>确认密码</span>
            <input
              v-model="confirmPassword"
              type="password"
              autocomplete="new-password"
              required
              minlength="8"
              maxlength="128"
              placeholder="请再次输入密码"
            />
          </label>

          <div v-if="isRegister" class="password-rules">
            <span v-for="rule in passwordRules" :key="rule.label" :class="{ passed: rule.passed }">
              {{ rule.label }}
            </span>
          </div>

          <label v-if="isRegister" class="auth-check">
            <input v-model="agreeTerms" type="checkbox" />
            <span>我已阅读并同意服务条款</span>
          </label>

          <button class="auth-submit" type="submit" :disabled="submitting">
            {{ submitting ? '处理中' : (isRegister ? '注册' : '登录') }}
          </button>
        </form>

        <div class="auth-switch">
          <span>{{ isRegister ? '已有账号？' : '没有账号？' }}</span>
          <button type="button" @click="switchMode(isRegister ? 'login' : 'register')">
            {{ isRegister ? '返回登录' : '注册账号' }}
          </button>
        </div>
      </section>
    </main>
  `,
}
