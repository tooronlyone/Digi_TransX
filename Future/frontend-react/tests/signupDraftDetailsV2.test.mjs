import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('every V2 role details caller uses the canonical route-scoped store', async () => {
  const files = ['FuelStationDetails.jsx', 'ShopkeeperDetails.jsx']
  for (const file of files) {
    const content = source(`../src/pages/auth/roledetails/${file}`)
    assert.match(content, /useSignupWizard/)
    assert.match(content, /resolveRedirect, store, \{/)
    assert.match(content, /navigateTo: \(destination\) => navigate\(destination, \{ replace: true \}\)/)
    assert.doesNotMatch(content, /store\.clear/)
  }
})
