import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  createSignupDraftStore,
  hasCompleteSignupBasic,
  subscribeSignupAuthReset,
} from '../src/auth/signupDraft.js'
import { createAccessLockCoordinator } from '../src/auth/accessLock.js'
import { submitSignup } from '../src/pages/auth/roledetails/_submitHelper.js'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')
const basic = (password = 'Wizard-only-9!') => ({
  name: 'Local Test',
  email: 'local@example.test',
  phone: '03000000000',
  password,
  cnic: '3310012345678',
})

function readyStore(password) {
  const store = createSignupDraftStore()
  assert.equal(store.begin(basic(password)), true)
  assert.equal(store.selectRole('service_seeker'), true)
  return store
}

function response(payload, ok = true) {
  return { ok, json: async () => payload }
}

function submissionFetch(finalPayload, finalOk = false) {
  let count = 0
  return async () => count++ === 0
    ? response({ csrf_token: 'csrf-test-only' })
    : response(finalPayload, finalOk)
}

test('pre-fix singleton APIs are absent and separate wizard instances share nothing', async () => {
  const moduleSource = await source('../src/auth/signupDraft.js')
  for (const obsolete of ['getSignupBasicDraft', 'setSignupBasicDraft', 'getSignupRole', 'setSignupRole']) {
    assert.equal(moduleSource.includes(obsolete), false)
  }
  const first = readyStore('First-only-9!')
  const second = createSignupDraftStore()
  assert.equal(first.read().basic.password, 'First-only-9!')
  assert.equal(second.read().basic, null)
})

test('password survives legitimate steps only inside its active wizard', () => {
  const store = createSignupDraftStore()
  store.begin(basic())
  assert.equal(hasCompleteSignupBasic(store.read().basic), true)
  store.selectRole('everyday_user')
  assert.equal(store.read().basic.password, 'Wizard-only-9!')
  assert.equal(store.read().role, 'everyday_user')
})

test('failed, conflict, and persistence outcomes clear password and require entry again', async () => {
  for (const [status, payload] of [
    [false, { message: 'Signup failed.' }],
    [false, { message: 'Account already exists.', field: 'email' }],
    [false, {}],
  ]) {
    const store = readyStore()
    const result = await submitSignup({}, () => {}, () => '/', store, {
      fetchImpl: submissionFetch(payload, status),
    })
    assert.equal(result.ok, false)
    assert.equal(store.read().basic.password, '')
    assert.equal(store.read().role, '')
    assert.equal(store.claimSubmission(), null)
  }
})

test('provider or network failure clears password before propagating a bounded error owner', async () => {
  const store = readyStore()
  let count = 0
  await assert.rejects(() => submitSignup({}, () => {}, () => '/', store, {
    fetchImpl: async () => {
      if (count++ === 0) return response({ csrf_token: 'csrf-test-only' })
      throw new Error('provider-test-failure')
    },
  }))
  assert.equal(store.read().basic.password, '')
  assert.equal(store.read().role, '')
})

test('success clears the draft before caching presentation or scheduling redirect', async () => {
  const store = readyStore()
  const observations = []
  const result = await submitSignup({}, () => observations.push(store.read()), () => '/client/dashboard', store, {
    fetchImpl: submissionFetch({ success: true, user: { role: 'service_seeker' } }, true),
    scheduleRedirect: (callback) => { observations.push(store.read()); assert.equal(typeof callback, 'function') },
  })
  assert.equal(result.ok, true)
  assert.equal(store.read().basic, null)
  assert.equal(observations.every((snapshot) => snapshot.basic === null), true)
})

test('clear models cancellation, logout, provider teardown, route departure, history, and refresh', () => {
  for (const reason of ['signup cancel', 'role cancel', 'details cancel', 'route departure', 'history departure', 'logout', 'teardown']) {
    const store = readyStore(`${reason}-9!`)
    store.clear()
    assert.equal(store.read().basic, null, reason)
    assert.equal(store.read().role, '', reason)
  }
  assert.equal(createSignupDraftStore().read().basic, null)
})

test('canonical full-login auth reset clears the active wizard through one subscription', () => {
  const store = readyStore('Auth-reset-9!')
  const coordinator = createAccessLockCoordinator()
  const unsubscribe = subscribeSignupAuthReset(store, coordinator)
  coordinator.notifyFullLoginRequired()
  assert.equal(store.read().basic, null)
  assert.equal(store.read().role, '')
  unsubscribe()
})

test('duplicate submission is rejected before a second network call', async () => {
  const store = readyStore()
  let release
  let calls = 0
  const first = submitSignup({}, () => {}, () => '/', store, {
    fetchImpl: async () => {
      calls += 1
      if (calls === 1) return new Promise((resolve) => { release = () => resolve(response({ csrf_token: 'csrf' })) })
      return response({ success: false }, false)
    },
  })
  const duplicate = await submitSignup({}, () => {}, () => '/', store, { fetchImpl: async () => { throw new Error('must not run') } })
  assert.equal(duplicate.duplicate, true)
  assert.equal(calls, 1)
  release()
  await first
})

test('abandonment aborts an in-flight claim and prevents the signup POST', async () => {
  const store = readyStore('Abandoned-9!')
  let release
  let calls = 0
  const pending = submitSignup({}, () => {}, () => '/', store, {
    fetchImpl: async (_url, options) => {
      calls += 1
      if (calls > 1) throw new Error('stale signup POST was sent')
      return new Promise((resolve, reject) => {
        release = () => options.signal.aborted
          ? reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
          : resolve(response({ csrf_token: 'csrf' }))
      })
    },
  })
  store.clear()
  release()
  await assert.rejects(pending, { name: 'AbortError' })
  assert.equal(calls, 1)
})

test('a stale failure cannot clear or corrupt a newer wizard generation', () => {
  const store = readyStore('Old-flow-9!')
  const old = store.claimSubmission()
  store.clear()
  store.begin(basic('New-flow-9!'))
  store.selectRole('everyday_user')
  assert.equal(store.failSubmission(old.token, 'old failure'), false)
  assert.equal(store.read().basic.password, 'New-flow-9!')
  assert.equal(store.read().role, 'everyday_user')
})

test('direct later routes are guarded and provider teardown is the route cleanup owner', async () => {
  const provider = await source('../src/components/auth/SignupWizardProvider.jsx')
  const app = await source('../src/App.jsx')
  assert.match(provider, /RequireSignupBasic/)
  assert.match(provider, /RequireSignupDraft/)
  assert.match(provider, /<Navigate to="\/signup" replace/)
  assert.match(provider, /return \(\) => \{[\s\S]*store\.clear\(\)/)
  assert.match(app, /path="\/signup" element=\{<SignupWizardProvider/)
  assert.match(app, /path="details\/service-seeker" element=\{<RequireSignupDraft/)
})

test('StrictMode cannot share a discarded provider store or clear a different instance', () => {
  const discarded = readyStore('Discarded-9!')
  discarded.clear()
  const active = readyStore('Active-9!')
  assert.equal(active.read().basic.password, 'Active-9!')
  assert.equal(discarded.read().basic, null)
})

test('password has no persistence, router-state, URL, tracking, logging, or DOM attribute owner', async () => {
  const files = await Promise.all([
    '../src/auth/signupDraft.js',
    '../src/auth/signupWizardContext.js',
    '../src/components/auth/SignupWizardProvider.jsx',
    '../src/pages/auth/Signup.jsx',
    '../src/pages/auth/RoleSelect.jsx',
    '../src/pages/auth/roledetails/_submitHelper.js',
  ].map(source))
  const combined = files.join('\n')
  for (const forbidden of [
    'localStorage', 'sessionStorage', 'indexedDB', 'location.state', 'history.state',
    'URLSearchParams', 'data-password', 'console.log', 'console.error', '/api/track',
  ]) assert.equal(combined.includes(forbidden), false, forbidden)
  assert.equal(/navigate\([^)]*password|to=.*password|['"`][^'"`\n]*[?#][^'"`\n]*password/.test(combined), false)
})

test('every production details caller uses the canonical route-scoped store', async () => {
  const files = [
    'ServiceSeekerDetails.jsx', 'LogisticsProviderDetails.jsx', 'EverydayUserDetails.jsx',
    'FuelStationDetails.jsx', 'ShopkeeperDetails.jsx',
  ]
  for (const file of files) {
    const content = await source(`../src/pages/auth/roledetails/${file}`)
    assert.match(content, /useSignupWizard/)
    assert.match(content, /resolveRedirect, store\)/)
  }
})
