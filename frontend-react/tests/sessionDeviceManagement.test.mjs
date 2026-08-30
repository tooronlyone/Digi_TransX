import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('2C6 management is integrated into Security and uses safe bounded fields', async () => {
  const [page, component, css] = await Promise.all([
    source('../src/pages/shared/SecuritySettings.jsx'),
    source('../src/components/security/SessionDeviceManagement.jsx'),
    source('../src/styles/components/mpin-security.css'),
  ])
  assert.match(page, /<SessionDeviceManagement \/>/)
  assert.match(component, /Active Sessions/)
  assert.match(component, /Trusted Devices/)
  assert.match(component, /is_current/)
  assert.match(component, /category_label/)
  assert.match(component, /last_activity_at/)
  assert.match(component, /window\.confirm/)
  assert.match(component, /encodeURIComponent\(item\.management_ref\)/)
  assert.match(component, /logoutCurrentSession/)
  for (const forbidden of ['localStorage', 'sessionStorage', 'analytics', 'console.', 'token_digest', 'user_agent', 'ip_address']) {
    assert.equal(component.includes(forbidden), false, forbidden)
  }
  assert.match(css, /security-management__grid/)
  assert.match(css, /security-management__row/)
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*security-management__grid/)
})

test('2C6 mutations have no automatic retry and stale responses refresh safely', async () => {
  const component = await source('../src/components/security/SessionDeviceManagement.jsx')
  assert.equal(/retry|setTimeout|while\s*\(|for\s*\(/i.test(component), false)
  assert.match(component, /\['stale', 'not_found'\]/)
  assert.match(component, /await load\(\)/)
  assert.match(component, /role="alert"/)
  assert.match(component, /role="status"/)
})
