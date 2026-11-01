import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
const backend = (path) => readFileSync(new URL(`../../backend/${path}`, import.meta.url), 'utf8')

test('Flask index injects auth-state bootstrap with no-store caching', () => {
  const app = backend('app.py')
  assert.match(app, /window\.__BOOTSTRAP__/)
  assert.match(app, /bootstrap\|tojson/)
  assert.match(app, /Cache-Control"\]\s*=\s*"no-store"/)
  assert.match(app, /"status": "unlocked" if unlocked else "locked"/)
  assert.match(app, /"status": "invalid"/)
  assert.match(app, /"verified_at": _iso_utc\(now\)/)
  assert.match(app, /BOOTSTRAP_FRESHNESS_MINUTES = 15/)
  assert.match(app, /"id": user\["id"\]/)
  assert.match(app, /"name": _display_name\(user\)/)
  assert.match(app, /"organization_default_route": role_redirect\(role\)/)
  assert.match(app, /session_event_reference/)
  assert.match(app, /trusted_device_reference/)
  assert.match(app, /access_proof_reference/)
  assert.doesNotMatch(app, /"csrf_token"/)
  assert.doesNotMatch(app, /"session_token"/)
  assert.doesNotMatch(app, /"device_token"/)
  assert.doesNotMatch(app, /"access_proof"/)
})

test('frontend auth presentation can hydrate display cache from bootstrap', () => {
  const presentation = source('src/auth/presentation.js')
  assert.match(presentation, /window\?\.__BOOTSTRAP__\?\.auth/)
  assert.match(presentation, /bootstrap\?\.auth\?\.user/)
  assert.match(presentation, /bootstrapAuth/)
  assert.match(presentation, /cacheBootstrapUser/)
  assert.match(presentation, /storage\.setItem\('user', JSON\.stringify\(user\)\)/)
  assert.match(presentation, /delete globalThis\.window\.__BOOTSTRAP__/)
})

test('secure access owner initializes from fresh bootstrap without blocking shell', () => {
  const provider = source('src/components/security/AccessLockProvider.jsx')
  assert.match(provider, /initialAuthorityFromBootstrap/)
  assert.match(provider, /bootstrapAuth\(\)/)
  assert.match(provider, /AUTH_FRESHNESS_MS = 15 \* 60 \* 1000/)
  assert.match(provider, /status === 'unlocked'/)
  assert.match(provider, /state: ACCESS_STATES\.UNLOCKED/)
  assert.match(provider, /status === 'locked'/)
  assert.match(provider, /state: ACCESS_STATES\.LOCKED_PASSWORD_REQUIRED/)
  assert.match(provider, /state: ACCESS_STATES\.FULL_LOGIN_REQUIRED/)
  assert.match(provider, /hasPresentation/)
  assert.match(provider, /AuthVerificationProvider/)
  assert.match(provider, /AUTH_STATUSES\.VERIFIED/)
  assert.match(provider, /setTimeout\(\(\) => setShowChecking\(true\), 400\)/)
  assert.match(provider, /state === ACCESS_STATES\.CHECKING && !hasPresentation && showChecking/)
  assert.doesNotMatch(provider, /ACCESS_STATES\.CHECKING,\s*\n\s*ACCESS_STATES\.LOCKED_MPIN_AVAILABLE/)
})

test('role guards consume shared auth verification without owning auth/me', () => {
  const guard = source('src/components/transporter/TransporterGuard.jsx')
  const clientHook = source('src/hooks/useClientAuth.js')
  const everydayHook = source('src/hooks/useEverydayAuth.js')
  const shopkeeper = source('src/components/shopkeeper/ShopkeeperGuard.jsx')
  for (const text of [guard, clientHook, everydayHook, shopkeeper]) {
    assert.match(text, /useAuthVerification\(\)/)
    assert.doesNotMatch(text, /fetch\(['"]\/auth\/me/)
    assert.doesNotMatch(text, /AuthVerificationProvider/)
  }
})

test('shell layouts render before verified but protected data and content wait', () => {
  const client = source('src/components/client/ClientLayout.jsx')
  const everyday = source('src/components/everyday/EverydayLayout.jsx')
  const layout = source('src/components/transporter/TransporterLayout.jsx')
  for (const text of [client, everyday, layout]) {
    assert.match(text, /const verified = status === AUTH_STATUSES\.VERIFIED/)
    assert.match(text, /\{verified \? children : <ShellPageSkeleton \/>\}/)
    assert.match(text, /\{verified && <NotificationBell/)
    assert.match(text, /verified && <TermsUpdateNotice/)
  }
  assert.match(layout, /if \(verified\) \{\s*apiGet\('\/api\/profile'\)/s)
  assert.match(layout, /if \(!verified\) return \(\) => \{ mounted = false \}/)
  assert.match(client, /if \(!verified\) return \(\) => \{ mounted = false \}/)
})

test('auth owner handles locked, 401, and transient failures distinctly', () => {
  const provider = source('src/components/security/AccessLockProvider.jsx')
  assert.match(provider, /if \(!auth\.access_locked\) \{/)
  assert.match(provider, /requestJson\('\/auth\/mpin\/status'/)
  assert.match(provider, /if \(error\?\.status === 401\) requireFullLogin\(\)/)
  assert.match(provider, /ACCESS_STATES\.TEMPORARILY_UNAVAILABLE/)
  assert.match(provider, /clearAuthPresentation\(\)/)
  assert.match(provider, /window\.addEventListener\('focus', refreshIfStale\)/)
  assert.match(provider, /document\.addEventListener\('visibilitychange', refreshIfStale\)/)
  assert.match(provider, /if \(refreshInFlight\.current\) return refreshInFlight\.current/)
})

test('AI assistant waits for verified auth before protected assistant APIs', () => {
  const assistant = source('src/components/ai/GlobalAiAssistant.jsx')
  assert.match(assistant, /const verified = authStatus === AUTH_STATUSES\.VERIFIED/)
  assert.match(assistant, /if \(!verified \|\| !assistantVisible \|\| aiBackendAvailableRef\.current !== true\) return/)
  assert.match(assistant, /if \(!verified \|\| !assistantVisible \|\| aiBackendAvailableRef\.current === false\) return/)
  assert.match(assistant, /if \(location\.pathname === AI_CHAT_ROUTE \|\| !verified\)/)
  assert.match(assistant, /\$\{AI_API_BASE\}\/preferences/)
  assert.match(assistant, /\$\{AI_API_BASE\}\/capabilities/)
})

test('AI assistant quietly disables unavailable preference and capability endpoints', () => {
  const assistant = source('src/components/ai/GlobalAiAssistant.jsx')
  const chat = source('src/pages/shared/AiChat.jsx')
  for (const text of [assistant, chat]) {
    assert.match(text, /function isUnavailableAiEndpoint\(response\)/)
    assert.match(text, /response\?\.status === 404 \|\| response\?\.status === 405/)
    assert.match(text, /aiBackendAvailableRef\.current = false/)
  }
  assert.match(assistant, /aiBackendAvailableRef\.current = true[\s\S]*setCapabilities\(payload\.capabilities\)[\s\S]*await syncRemotePreferences\(\)/)
  assert.doesNotMatch(assistant, /console\.(error|warn|log)/)
  assert.doesNotMatch(chat, /console\.(error|warn|log)/)
})

test('unlock route is not a dead login redirect', () => {
  const app = source('src/App.jsx')
  assert.match(app, /function UnlockRoute\(\)/)
  assert.match(app, /<Route path="\/unlock" element=\{<UnlockRoute \/>\} \/>/)
  assert.doesNotMatch(app, /<Route path="\/unlock" element=\{<Navigate to="\/login" replace \/>\} \/>/)
})
