import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('shared Security page owns one standalone logout-all danger action', async () => {
  const [page, action] = await Promise.all([
    source('../src/pages/shared/SecuritySettings.jsx'),
    source('../src/components/security/LogoutAllAction.jsx'),
  ])
  assert.equal((page.match(/<LogoutAllAction \/>/g) || []).length, 1)
  assert.match(action, /Log out from all devices/)
  assert.match(action, /Your current access will end too/)
  assert.match(action, /every other active session and trusted device/)
  assert.equal(/session list|device list|revoke-one|revoke one/i.test(action), false)
})

test('explicit confirmation routes MPIN through StepUpProvider and password only through memory state', async () => {
  const action = await source('../src/components/security/LogoutAllAction.jsx')
  assert.match(action, /useStepUp\(\)/)
  assert.match(action, /requestLogoutAll\(protectedFetch, passwordValue\)/)
  assert.match(action, /stage === 'confirm'/)
  assert.match(action, /current_password_required/)
  assert.match(action, /type="password"/)
  assert.match(action, /setPassword\(''\)/)
  assert.match(action, /generation\.current/)
  for (const forbidden of [
    'localStorage', 'sessionStorage', 'URLSearchParams', 'history.',
    'analytics', 'console.', 'setTimeout(',
  ]) assert.equal(action.includes(forbidden), false, forbidden)
})

test('logout-all transport has no automatic retry and success clears all local auth presentation', async () => {
  const [owner, utilities] = await Promise.all([
    source('../src/auth/logout.js'),
    source('../src/pages/client/clientUtils.jsx'),
  ])
  const logoutAll = owner.slice(
    owner.indexOf('export async function requestLogoutAll'),
    owner.indexOf('export async function logoutCurrentSession'),
  )
  assert.equal((logoutAll.match(/protectedFetch\('/g) || []).length, 1)
  assert.equal(/retry|setTimeout|while\s*\(|for\s*\(/.test(logoutAll), false)
  assert.match(owner, /clearCachedCsrfToken\(\)/)
  assert.match(owner, /clearAuthPresentation\(\)/)
  assert.match(owner, /navigate\('\/login', \{ replace: true \}\)/)
  assert.match(utilities, /export function clearCachedCsrfToken\(\)/)
  assert.match(utilities, /cachedCsrfToken = null/)
})

test('dialog has keyboard focus, error announcement, and mobile containment', async () => {
  const [action, css] = await Promise.all([
    source('../src/components/security/LogoutAllAction.jsx'),
    source('../src/styles/components/mpin-security.css'),
  ])
  assert.match(action, /role="dialog"/)
  assert.match(action, /aria-modal="true"/)
  assert.match(action, /aria-labelledby="logout-all-dialog-title"/)
  assert.match(action, /aria-describedby="logout-all-dialog-description"/)
  assert.match(action, /event\.key === 'Escape'/)
  assert.match(action, /event\.key !== 'Tab'/)
  assert.match(action, /role="alert"/)
  assert.match(action, /triggerRef\.current\?\.focus\(\)/)
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*\.logout-all-card \{ align-items: stretch; flex-direction: column/)
  assert.match(css, /\.logout-all-card > \.security-danger \{ width: 100%/)
})
