import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path) => readFileSync(new URL(`../../../frontend-react/${path}`, import.meta.url), 'utf8')
const futureSource = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('V2 Shopkeeper guard consumes shared auth verification without owning auth/me', () => {
  const shopkeeper = futureSource('src/components/shopkeeper/ShopkeeperGuard.jsx')
  assert.match(shopkeeper, /useAuthVerification\(\)/)
  assert.doesNotMatch(shopkeeper, /fetch\(['"]\/auth\/me/)
  assert.doesNotMatch(shopkeeper, /AuthVerificationProvider/)
})

test('V2 AI assistant waits for verified auth before protected assistant APIs', () => {
  const assistant = futureSource('src/components/ai/GlobalAiAssistant.jsx')
  assert.match(assistant, /const verified = authStatus === AUTH_STATUSES\.VERIFIED/)
  assert.match(assistant, /if \(!verified \|\| !assistantVisible \|\| aiBackendAvailableRef\.current !== true\) return/)
  assert.match(assistant, /if \(!verified \|\| !assistantVisible \|\| aiBackendAvailableRef\.current === false\) return/)
  assert.match(assistant, /if \(location\.pathname === AI_CHAT_ROUTE \|\| !verified\)/)
  assert.match(assistant, /\$\{AI_API_BASE\}\/preferences/)
  assert.match(assistant, /\$\{AI_API_BASE\}\/capabilities/)
})

test('V2 AI assistant quietly disables unavailable preference and capability endpoints', () => {
  const assistant = futureSource('src/components/ai/GlobalAiAssistant.jsx')
  const chat = futureSource('src/pages/shared/AiChat.jsx')
  for (const text of [assistant, chat]) {
    assert.match(text, /function isUnavailableAiEndpoint\(response\)/)
    assert.match(text, /response\?\.status === 404 \|\| response\?\.status === 405/)
    assert.match(text, /aiBackendAvailableRef\.current = false/)
  }
  assert.match(assistant, /aiBackendAvailableRef\.current = true[\s\S]*setCapabilities\(payload\.capabilities\)[\s\S]*await syncRemotePreferences\(\)/)
  assert.doesNotMatch(assistant, /console\.(error|warn|log)/)
  assert.doesNotMatch(chat, /console\.(error|warn|log)/)
  assert.ok(source('src/App.jsx'))
})
