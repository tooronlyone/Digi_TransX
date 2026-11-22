import assert from 'node:assert/strict'
import test from 'node:test'
import { controlledStaticAssets, STATIC_ASSET_NAMES } from '../build/staticAssets.mjs'

test('build manifest emits only the declared SVG assets, never the public directory tree', () => {
  const plugin = controlledStaticAssets()
  const emitted = []
  plugin.generateBundle.call({ emitFile(asset) { emitted.push(asset) } })
  assert.deepEqual(emitted.map(asset => asset.fileName), [...STATIC_ASSET_NAMES])
  for (const asset of emitted) {
    assert.equal(asset.type, 'asset')
    assert.ok(asset.source.toString().includes('<svg'))
    assert.ok(!asset.fileName.includes('node_modules'))
  }
})

test('dev and preview static middleware serves only exact asset URLs and supports HEAD', () => {
  let handler
  const plugin = controlledStaticAssets()
  plugin.configureServer({ middlewares: { use(value) { handler = value } } })
  function request(url, method = 'GET') {
    const result = { headers: {}, next: false, ended: false }
    handler({ url, method }, {
      setHeader(key, value) { result.headers[key] = value },
      end(body) { result.body = body; result.ended = true },
    }, error => { result.next = true; result.error = error })
    return result
  }
  assert.equal(request('/favicon.svg?v=1').headers['Content-Type'], 'image/svg+xml')
  assert.equal(request('/icons.svg', 'HEAD').body, undefined)
  for (const url of ['/node_modules/package.json', '/.env', '/favicon.svg/../../.env', '/%66avicon.svg']) {
    assert.equal(request(url).next, true, url)
    assert.equal(request(url).ended, false, url)
  }
  let previewHandler
  plugin.configurePreviewServer({ middlewares: { use(value) { previewHandler = value } } })
  assert.equal(previewHandler, handler)
})
