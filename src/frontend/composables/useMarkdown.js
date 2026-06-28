/**
 * Markdown 渲染 + XSS 净化。
 *
 * 设计：
 * - marked 解析 GitHub Flavored Markdown（含表格、删除线、单换行变 <br>）
 * - DOMPurify 用白名单 sanitize：只放行可视化标签与极少属性，杜绝 <script> / on* / javascript: 链接
 * - 任一库缺失时降级为 escape 后的纯文本，绝不直接拼接未净化 HTML
 *
 * 用法：
 *   import { renderMarkdown } from '/ui/composables/useMarkdown.js'
 *   const html = renderMarkdown(text)   // 返回安全 HTML 字符串
 */

const ALLOWED_TAGS = [
  'p', 'br', 'span',
  'strong', 'em', 'b', 'i', 'u', 's', 'del', 'mark',
  'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'pre', 'code',
  'blockquote',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'hr',
]
const ALLOWED_ATTR = ['href', 'title', 'class', 'colspan', 'rowspan', 'align', 'target', 'rel']

let _markedConfigured = false
function _ensureMarked() {
  // 配置 marked 的 Markdown 解析选项，只执行一次。
  if (_markedConfigured || typeof window.marked === 'undefined') return
  window.marked.setOptions({
    gfm: true,            // GitHub Flavored: 表格 / 删除线 / 自动链接
    breaks: true,         // 单换行 → <br>，LLM 输出更友好
    headerIds: false,     // 不生成 id（多条 message 时避免重复）
    mangle: false,
  })
  _markedConfigured = true
}

function _escape(s) {
  // 把纯文本转义为安全 HTML，供降级路径使用。
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

export function renderMarkdown(text) {
  // 将 Markdown 文本转换为经过 DOMPurify 净化的安全 HTML。
  if (text == null || text === '') return ''
  const src = String(text)

  // 库未加载 / 加载失败：降级为 escape 后的纯文本（保留换行）
  if (typeof window.marked === 'undefined' || typeof window.DOMPurify === 'undefined') {
    return _escape(src).replaceAll('\n', '<br>')
  }

  _ensureMarked()

  let html
  try {
    html = window.marked.parse(src)
  } catch (e) {
    console.warn('[markdown] parse failed, fallback to text:', e)
    return _escape(src).replaceAll('\n', '<br>')
  }

  try {
    const clean = window.DOMPurify.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      // 链接协议白名单：http(s) / mailto / 相对路径；阻止 javascript: data: 等
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[#/?])/i,
      // 强制为外链 a 添加 rel="noreferrer noopener"，target="_blank" 时尤其重要
      ADD_ATTR: ['target', 'rel'],
      RETURN_TRUSTED_TYPE: false,
    })
    return clean
  } catch (e) {
    console.warn('[markdown] sanitize failed, fallback to text:', e)
    return _escape(src).replaceAll('\n', '<br>')
  }
}
