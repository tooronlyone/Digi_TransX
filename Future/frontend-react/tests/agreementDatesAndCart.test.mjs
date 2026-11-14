import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { test } from 'node:test'
import { addAgreementMonths, todayAgreementDate } from '../src/pages/client/agreementDates.mjs'
import { countPartsCart, partsCartStorageKey, readPartsCart, writePartsCart } from '../src/pages/transporter/partsCartStorage.mjs'

test('agreement preview preserves the calendar day in Pakistan and other browser timezones', () => {
  const moduleUrl = new URL('../src/pages/client/agreementDates.mjs', import.meta.url).href
  for (const zone of ['Asia/Karachi', 'UTC', 'America/New_York', 'Pacific/Auckland']) {
    const code = `import { addAgreementMonths, todayAgreementDate } from ${JSON.stringify(moduleUrl)}; console.log(JSON.stringify([addAgreementMonths('2026-10-23',3),todayAgreementDate(new Date('2026-10-22T20:00:00Z'))]))`
    const output = execFileSync(process.execPath, ['--input-type=module', '-e', code], {
      env: { ...process.env, TZ: zone }, encoding: 'utf8', timeout: 10000,
    })
    assert.deepEqual(JSON.parse(output), ['2027-01-23', '2026-10-23'], zone)
  }
})

test('calendar month-end and leap-year clamping matches the backend date rule', () => {
  assert.equal(addAgreementMonths('2026-01-31', 1), '2026-02-28')
  assert.equal(addAgreementMonths('2028-01-31', 1), '2028-02-29')
  assert.equal(addAgreementMonths('2028-02-29', 12), '2029-02-28')
  assert.equal(addAgreementMonths('2026-12-31', 2), '2027-02-28')
  assert.equal(addAgreementMonths('2000-01-31', 1), '2000-02-29')
  assert.equal(addAgreementMonths('2100-01-31', 1), '2100-02-28')
})

test('empty, malformed and out-of-range calendar inputs do not crash preview rendering', () => {
  for (const [date, months] of [['', 3], ['invalid', 3], ['2026-02-30', 1], ['2026-13-01', 1],
    ['0000-01-01', 1], ['2026-10-23', ''], ['2026-10-23', 'NaN'], ['2026-10-23', 0],
    ['2026-10-23', 1.5], ['9999-12-31', 1]]) assert.equal(addAgreementMonths(date, months), '')
  assert.equal(todayAgreementDate(new Date('2026-10-23T19:00:00Z')), '2026-10-24')
})

test('cart storage requires an explicit valid owner and never adopts the legacy global cart', () => {
  const values = new Map([['dtx:parts-cart:v1', JSON.stringify([{ id: 1, qty: 8, title: 'Unowned private cart' }])]])
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  assert.equal(partsCartStorageKey(41), 'dtx:parts-cart:v2:41')
  for (const invalid of [null, undefined, '', 0, true, -1, 'unknown', Number.MAX_SAFE_INTEGER + 1]) assert.equal(partsCartStorageKey(invalid), null)
  assert.deepEqual(readPartsCart(partsCartStorageKey(41)), [])
  assert.equal(countPartsCart(), 0)
  assert.equal(values.get('dtx:parts-cart:v1').includes('Unowned private cart'), true)
})

test('cart counts and malformed rows remain scoped to their account', () => {
  const values = new Map([
    ['dtx:parts-cart:v2:42', JSON.stringify([{ id: 1, qty: 2 }, { id: 2, qty: -10 }, null])],
    ['dtx:parts-cart:v2:43', JSON.stringify([{ id: 1, qty: 9 }])],
  ])
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  assert.equal(countPartsCart(42), 2)
  assert.equal(countPartsCart(43), 9)
  assert.equal(readPartsCart(partsCartStorageKey(42)), readPartsCart(partsCartStorageKey(42)), 'snapshot identity must remain stable')
})

test('disabled persistence falls back to isolated in-memory carts instead of crashing', () => {
  globalThis.localStorage = { getItem: () => { throw new Error('Storage denied') }, setItem: () => { throw new Error('Storage denied') } }
  writePartsCart(partsCartStorageKey(44), [{ id: 7, qty: 3 }])
  assert.equal(countPartsCart(44), 3)
  assert.equal(countPartsCart(45), 0)
  assert.deepEqual(writePartsCart(null, [{ id: 7, qty: 3 }]), [])
})
