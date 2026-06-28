/**
 * vega-embed 懒加载：首屏不拉 ~700KB 的 vega/vega-lite/vega-embed，
 * 用户产生第一个 chart 时才动态注入 <script>，后续命中 promise 缓存直接返回。
 *
 * 选 Vega-Lite v5：后端 chart_generator 输出的 spec 锁死 $schema=v5。
 *
 * 用法：
 *   const vegaEmbed = await loadVegaEmbed()
 *   const { view } = await vegaEmbed(container, spec, options)
 */

const SCRIPTS = [
  'https://cdnjs.cloudflare.com/ajax/libs/vega/5.30.0/vega.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/vega-lite/5.21.0/vega-lite.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/vega-embed/6.26.0/vega-embed.min.js',
]

let _promise = null

function _injectScript(src) {
  // 动态注入一个脚本标签，并返回脚本加载 promise。
  return new Promise((resolve, reject) => {
    // 同 URL 已注入过：不重复加载
    if (document.querySelector(`script[data-vega-src="${src}"]`)) {
      resolve()
      return
    }
    const s = document.createElement('script')
    s.src = src
    s.async = false           // 必须按顺序：vega-lite 依赖 vega，vega-embed 依赖两者
    s.referrerPolicy = 'no-referrer'
    s.dataset.vegaSrc = src
    s.onload = () => resolve()
    s.onerror = () => reject(new Error(`脚本加载失败: ${src}`))
    document.head.appendChild(s)
  })
}

export function loadVegaEmbed() {
  // 按顺序加载 vega 相关脚本，并缓存加载 promise。
  if (_promise) return _promise
  _promise = (async () => {
    for (const src of SCRIPTS) {
      await _injectScript(src)
    }
    if (typeof window.vegaEmbed !== 'function') {
      throw new Error('vegaEmbed 未挂载到 window（脚本加载顺序可能有问题）')
    }
    return window.vegaEmbed
  })().catch((e) => {
    // 失败后清掉 promise 缓存，下次有机会重试
    _promise = null
    throw e
  })
  return _promise
}
