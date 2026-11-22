import assert from 'node:assert/strict'
import test from 'node:test'
import { JSDOM } from 'jsdom'
import { buildReceiptHtml } from '../src/pages/shopkeeper/receiptPrinting.js'
import { posLineMinor, quotePosCart } from '../src/pages/shopkeeper/posAmounts.js'

test('receipt fields remain literal text and cannot execute scripts or install event handlers', () => {
  const attack = '<script>window.auditInjected=true</script><img src=x onerror="window.auditInjected=true">&"\''
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
