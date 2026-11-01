import assert from 'node:assert/strict'
import test from 'node:test'
import { JSDOM } from 'jsdom'
import { buildReceiptHtml } from '../src/pages/shopkeeper/receiptPrinting.js'
import { posLineMinor, quotePosCart } from '../src/pages/shopkeeper/posAmounts.js'
import { controlledStaticAssets, STATIC_ASSET_NAMES } from '../build/staticAssets.mjs'

test('receipt fields remain literal text and cannot execute scripts or install event handlers', () => {
  const attack = '<script>window.auditInjected=true</script><img src=x onerror="window.auditInjected=true">&\"\''
  const receipt = buildReceiptHtml({
    receipt_number: attack, purchaser_name: attack, created_at: '2026-10-24T00:00:00Z',
    items: [{ product_name: attack, quantity: attack, unit_price: 1, subtotal: 1 }],
    total_amount: 1, amount_paid: 1, change_amount: 0,
  }, attack, attack)
  const dom = new JSDOM(receipt, { runScripts: 'dangerously', url: 'https://digi-transx.example/' })
  assert.equal(dom.window.auditInjected, undefined)
  assert.equal(dom.window.document.querySelectorAll('script,img,[onerror]').length, 0)
  assert.ok(dom.window.document.body.textContent.includes(attack))
  assert.ok(dom.window.document.title.includes(attack))
  assert.ok(dom.window.document.querySelector('style').textContent.includes('80mm'))
  dom.window.close()
})

test('POS computes exact cash comparison and rounds each measured line before summing', () => {
  const line = (price, quantity) => ({ product: { price }, quantity })
  assert.deepEqual(quotePosCart([line(0.1, 1), line(0.2, 1)], '0.30'), {
    total: 0.3, paid: 0.3, change: 0, canConfirm: true,
  })
  assert.equal(posLineMinor('0.29', '0.5'), 15n)
  assert.equal(quotePosCart([line('0.29', '0.5'), line('0.29', '0.5')], '0.30').total, 0.3)
  assert.equal(quotePosCart([line(10, '0.125')], '1.25').canConfirm, true)
  assert.equal(quotePosCart([line(10, 1)], 'NaN').canConfirm, false)
  assert.equal(quotePosCart([line(10, '-1')], '100').canConfirm, false)
  assert.equal(quotePosCart([line(10, '0.0001')], '100').canConfirm, false)
})

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
