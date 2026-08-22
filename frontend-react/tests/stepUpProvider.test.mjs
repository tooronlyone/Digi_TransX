import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('StepUpProvider keeps MPIN and proof in memory and replays exactly once', async () => {
  const provider = await source('../src/components/security/StepUpProvider.jsx')
  assert.match(provider, /first\.status !== 428/)
  assert.match(provider, /payload\?\.code !== 'mpin_step_up_required'/)
  assert.match(provider, /requestJson\('\/auth\/mpin\/step-up'/)
  assert.match(provider, /authorized\.generation !== generation\.current/)
  assert.match(provider, /headers\.set\('X-MPIN-Step-Up-Proof', authorized\.proof\)/)
  assert.equal((provider.match(/return fetch\(url, \{ \.\.\.options, headers \}\)/g) || []).length, 1)
  assert.match(provider, /location\.key/)
  assert.match(provider, /full_login_required/)
  assert.match(provider, /operationGeneration !== generation\.current/)
  for (const forbidden of ['localStorage', 'sessionStorage']) {
    assert.equal(provider.includes(forbidden), false, forbidden)
  }
})

test('exactly six approved UI actions use protectedFetch', async () => {
  const earning = await source('../src/pages/transporter/earning.jsx')
  const checkout = await source('../src/pages/client/BidCheckout.jsx')
  const agreement = await source('../src/pages/client/AgreementBids.jsx')
  const order = await source('../src/pages/client/ClientOrderDetail.jsx')

  assert.match(earning, /withdraw-locked'[\s\S]*protectedFetch/)
  assert.match(earning, /upgrade-limit'[\s\S]*protectedFetch/)
  assert.match(earning, /payout-card'[\s\S]*protectedFetch/)
  assert.match(checkout, /protectedFetch\(\`\/api\/orders\//)
  assert.match(agreement, /agreements\/finalize'[\s\S]*protectedFetch/)
  assert.match(order, /decision === 'yes' \? protectedFetch : fetch/)
  for (const forbidden of ['/api/wallet/topup', 'saved-payment', 'refund', 'dispute']) {
    assert.equal(providerUse(earning, checkout, agreement, order).includes(forbidden), false)
  }
})

function providerUse(...sources) {
  return sources
    .flatMap((text) => text.split('\n').filter((line) => line.includes('protectedFetch')))
    .join('\n')
}
