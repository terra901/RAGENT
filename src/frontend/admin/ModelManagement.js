import { onMounted, reactive, ref } from 'vue'
import {
  deleteModel,
  deleteProvider,
  listModels,
  listProviders,
  saveModel,
  saveProvider,
  setModelStatus,
} from '/ui/services/adminApi.js'

const emptyProvider = () => ({ id: '', name: '', code: '', baseUrl: '', apiType: 'openai_compatible', status: 'enabled', timeoutSeconds: 60, maxRetries: 2, remark: '' })
const emptyModel = () => ({ id: '', name: '', code: '', type: 'chat', usagePosition: 'chat', contextLength: '', apiKey: '', status: 'enabled', remark: '' })

export default {
  name: 'ModelManagement',
  setup() {
    const providers = ref([])
    const models = ref([])
    const selectedProviderId = ref('')
    const providerForm = reactive(emptyProvider())
    const modelForm = reactive(emptyModel())
    const loading = ref(false)
    const error = ref('')

    function fill(target, data) {
      Object.keys(target).forEach(key => { target[key] = data[key] ?? emptyProvider()[key] ?? emptyModel()[key] ?? '' })
    }

    async function loadProviders() {
      loading.value = true
      error.value = ''
      try {
        const payload = await listProviders()
        providers.value = payload.providers || []
        if (!selectedProviderId.value && providers.value.length) selectedProviderId.value = providers.value[0].id
        if (selectedProviderId.value) await loadModels(selectedProviderId.value)
      } catch (e) {
        error.value = e.message
      } finally {
        loading.value = false
      }
    }

    async function loadModels(providerId) {
      selectedProviderId.value = providerId
      const payload = await listModels(providerId)
      models.value = payload.models || []
    }

    async function submitProvider() {
      try {
        const payload = await saveProvider(providerForm)
        Object.assign(providerForm, emptyProvider())
        selectedProviderId.value = payload.provider.id
        await loadProviders()
      } catch (e) {
        error.value = e.message
      }
    }

    async function submitModel() {
      if (!selectedProviderId.value) {
        error.value = '请先选择供应商'
        return
      }
      try {
        await saveModel(selectedProviderId.value, modelForm)
        Object.assign(modelForm, emptyModel())
        await loadModels(selectedProviderId.value)
      } catch (e) {
        error.value = e.message
      }
    }

    async function removeProvider(id) {
      if (!confirm('删除这个供应商及其模型？')) return
      await deleteProvider(id)
      selectedProviderId.value = ''
      await loadProviders()
    }

    async function removeModel(id) {
      if (!confirm('删除这个模型？')) return
      await deleteModel(id)
      await loadModels(selectedProviderId.value)
    }

    async function toggleModel(model) {
      const next = model.status === 'enabled' ? 'disabled' : 'enabled'
      await setModelStatus(model.id, next)
      await loadModels(selectedProviderId.value)
    }

    onMounted(loadProviders)
    return { providers, models, selectedProviderId, providerForm, modelForm, loading, error, fill, loadProviders, loadModels, submitProvider, submitModel, removeProvider, removeModel, toggleModel }
  },
  template: /*html*/`
    <section class="admin-grid">
      <div class="admin-section">
        <div class="admin-section-head">
          <h2>供应商</h2>
          <button type="button" @click="loadProviders">刷新</button>
        </div>
        <p v-if="error" class="admin-error">{{ error }}</p>
        <form class="admin-form" @submit.prevent="submitProvider">
          <input v-model="providerForm.name" placeholder="供应商名称" />
          <input v-model="providerForm.code" placeholder="供应商编码" />
          <input v-model="providerForm.baseUrl" placeholder="Base URL" />
          <div class="admin-form-row">
            <input v-model.number="providerForm.timeoutSeconds" type="number" min="1" placeholder="超时秒数" />
            <input v-model.number="providerForm.maxRetries" type="number" min="0" placeholder="重试次数" />
          </div>
          <button type="submit">{{ providerForm.id ? '保存供应商' : '新增供应商' }}</button>
        </form>
        <div class="admin-list">
          <article v-for="provider in providers" :key="provider.id" class="admin-row" :class="{ active: provider.id === selectedProviderId }">
            <button type="button" class="admin-row-main" @click="loadModels(provider.id)">
              <strong>{{ provider.name }}</strong>
              <span>{{ provider.baseUrl }}</span>
            </button>
            <button type="button" @click="fill(providerForm, provider)">编辑</button>
            <button type="button" @click="removeProvider(provider.id)">删除</button>
          </article>
        </div>
      </div>

      <div class="admin-section">
        <div class="admin-section-head">
          <h2>模型</h2>
        </div>
        <form class="admin-form" @submit.prevent="submitModel">
          <div class="admin-form-row">
            <input v-model="modelForm.name" placeholder="模型名称" />
            <input v-model="modelForm.code" placeholder="模型型号" />
          </div>
          <div class="admin-form-row">
            <select v-model="modelForm.type">
              <option value="chat">chat</option>
              <option value="reasoning">reasoning</option>
              <option value="embedding">embedding</option>
            </select>
            <input v-model="modelForm.usagePosition" placeholder="使用位置" />
          </div>
          <input v-model="modelForm.apiKey" type="password" placeholder="API Key" />
          <input v-model="modelForm.remark" placeholder="备注" />
          <button type="submit">{{ modelForm.id ? '保存模型' : '新增模型' }}</button>
        </form>
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead><tr><th>名称</th><th>型号</th><th>用途</th><th>Key</th><th>连通</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="model in models" :key="model.id">
                <td>{{ model.name }}</td>
                <td>{{ model.code }}</td>
                <td>{{ model.usagePosition }}</td>
                <td>{{ model.keyMask || '未设置' }}</td>
                <td>{{ model.connectivity }}</td>
                <td>{{ model.status }}</td>
                <td>
                  <button type="button" @click="fill(modelForm, model)">编辑</button>
                  <button type="button" @click="toggleModel(model)">{{ model.status === 'enabled' ? '禁用' : '启用' }}</button>
                  <button type="button" @click="removeModel(model.id)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
}
