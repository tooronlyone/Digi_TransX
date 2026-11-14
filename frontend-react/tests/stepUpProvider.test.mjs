import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('StepUpProvider keeps MPIN and proof in memory and replays exactly once', async () => {
  const provider = await source('../src/components/security/StepUpProvider.jsx')
  const accessProvider = await source('../src/components/security/AccessLockProvider.jsx')
  assert.match(provider, /first\.status === 409 && payload\?\.code === 'mpin_enrollment_required'/)
  assert.match(provider, /first\.status !== 428/)
  assert.match(provider, /payload\?\.code !== 'mpin_step_up_required'/)
  assert.match(provider, /requestJson\('\/auth\/mpin\/step-up'/)
  assert.match(provider, /authorized\.generation !== generation\.current/)
  assert.match(provider, /headers\.set\('X-MPIN-Step-Up-Proof', authorized\.proof\)/)
  assert.equal((provider.match(/return fetch\(url, \{ \.\.\.options, headers \}\)/g) || []).length, 1)
  assert.equal((provider.match(/return first/g) || []).length >= 2, true)
  assert.match(provider, /location\.key/)
  assert.match(provider, /full_login_required/)
  assert.match(provider, /identity_context_changed/)
  assert.match(accessProvider, /authorityContextKey\(auth\)/)
  assert.match(accessProvider, /notifyIdentityContextChanged\(\)/)
  assert.match(provider, /operationGeneration !== generation\.current/)
  for (const forbidden of ['localStorage', 'sessionStorage']) {
    assert.equal(provider.includes(forbidden), false, forbidden)
  }
})

test('MPIN enrollment-required response opens setup UI and routes by role without retrying', async () => {
  const provider = await source('../src/components/security/StepUpProvider.jsx')

  assert.match(provider, /MPIN setup required/)
  assert.match(provider, /Set up an MPIN in Security settings, then retry the action\./)
  assert.match(provider, /currentPresentedUser\(\)/)
  assert.match(provider, /securitySetupPathForRole\(user\?\.role\)/)
  assert.match(provider, /service_seeker', 'client', 'customer'[\s\S]*return '\/client\/security'/)
  assert.match(provider, /logistics_provider', 'transporter'[\s\S]*return '\/transporter\/security'/)
  assert.match(provider, /normalized === 'everyday_user'[\s\S]*return '\/everyday\/security'/)
  assert.match(provider, /return null/)
  assert.match(provider, /Open Security settings from your account menu/)
  assert.match(provider, /navigate\(setupRequired\.path\)/)

  const enrollmentBranch = provider.slice(
    provider.indexOf("first.status === 409 && payload?.code === 'mpin_enrollment_required'"),
    provider.indexOf("if (first.status !== 428"),
  )
  assert.equal(enrollmentBranch.includes('/auth/mpin/step-up'), false)
  assert.equal(enrollmentBranch.includes('X-MPIN-Step-Up-Proof'), false)
  assert.equal(enrollmentBranch.includes('fetch(url'), false)
  assert.match(enrollmentBranch, /return first/)
})

test('exactly five approved UI actions use protectedFetch', async () => {
  const earning = await source('../src/pages/transporter/earning.jsx')
  const checkout = await source('../src/pages/client/BidCheckout.jsx')
  const order = await source('../src/pages/client/ClientOrderDetail.jsx')

  assert.match(earning, /withdraw-locked'[\s\S]*protectedFetch/)
  assert.match(earning, /upgrade-limit'[\s\S]*protectedFetch/)
  assert.match(earning, /payout-card'[\s\S]*protectedFetch/)
  assert.match(checkout, /protectedFetch\(\`\/api\/orders\//)
  assert.match(order, /decision === 'yes' \? protectedFetch : fetch/)
  for (const forbidden of ['/api/wallet/topup', 'saved-payment', 'refund', 'dispute']) {
    assert.equal(providerUse(earning, checkout, order).includes(forbidden), false)
  }
})

function providerUse(...sources) {
  return sources
    .flatMap((text) => text.split('\n').filter((line) => line.includes('protectedFetch')))
    .join('\n')
}
