import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

function arrayBlock(text, name) {
  const match = text.match(new RegExp(`const ${name} = \\[([\\s\\S]*?)\\n\\]`))
  assert.ok(match, `${name} must exist`)
  return match[1]
}

test('mobile headers have no hamburger or visible standalone logout and avatars own account navigation', async () => {
  const [client, everyday, transporter, css] = await Promise.all([
    source('../src/components/client/ClientLayout.jsx'),
    source('../src/components/everyday/EverydayLayout.jsx'),
    source('../src/components/transporter/TransporterLayout.jsx'),
    source('../src/styles/global.css'),
  ])

  for (const layout of [client, everyday, transporter]) {
    assert.equal(/fa-bars|menuOpen|Toggle navigation/.test(layout), false)
    assert.match(layout, /header-account-link/)
    assert.match(layout, /aria-label="Open My (?:Account|Profile)"/)
    assert.match(layout, /header-logout/)
  }
  assert.match(client, /to="\/client\/account"/)
  assert.match(everyday, /to="\/everyday\/account"/)
  assert.match(transporter, /to="\/transporter\/profile"/)
  assert.match(css, /@media \(max-width: 768px\)[\s\S]*\.transporter-page \.header-logout \{ display: none; \}/)
})

test('service-seeker mobile navigation is exactly Dashboard, Post Order, Wallet and Messages', async () => {
  const client = await source('../src/components/client/ClientLayout.jsx')
  const mobile = arrayBlock(client, 'MOBILE_NAV_ITEMS')
  const labels = [...mobile.matchAll(/label: '([^']+)'/g)].map((match) => match[1])
  assert.deepEqual(labels, ['Dashboard', 'Post Order', 'Wallet', 'Messages'])
  for (const rejected of ['More', 'My Orders', 'Post Agreement', 'Your Account', 'Security', 'My Agreements']) {
    assert.equal(labels.includes(rejected), false)
  }
})

test('the removed More sheet has no component, state, handler, accessibility or CSS owner', async () => {
  const [navigation, css] = await Promise.all([
    source('../src/components/common/MobileBottomNavigation.jsx'),
    source('../src/styles/global.css'),
  ])
  assert.equal(/More destinations|mobile-more|moreOpen|aria-expanded|aria-modal/.test(navigation), false)
  assert.equal(/\.mobile-more|More destinations/.test(css), false)
  assert.match(navigation, /items\.map/)
  assert.match(css, /grid-template-columns: repeat\(auto-fit, minmax\(64px, 1fr\)\)/)
})

test('profile/account pages own Security Settings and one canonical Logout action', async () => {
  const [account, profile, app, logout] = await Promise.all([
    source('../src/pages/client/ClientAccount.jsx'),
    source('../src/pages/transporter/profile.jsx'),
    source('../src/App.jsx'),
    source('../src/auth/logout.js'),
  ])
  assert.match(account, /to=\{`\$\{base\}\/security`\}/)
  assert.match(account, />Security Settings</)
  assert.match(account, /logoutCurrentSession\(navigate\)/)
  assert.equal((profile.match(/logoutCurrentSession\(navigate\)/g) || []).length, 1)
  assert.match(profile, /to="\/transporter\/security"/)
  assert.match(app, /Route path="account" element=\{<ClientAccount \/>\}/)
  assert.match(logout, /getCsrfToken\(\)/)
  assert.match(logout, /fetch\('\/auth\/logout'/)
  assert.match(logout, /'X-CSRF-Token': csrf/)
  assert.match(logout, /clearAuthPresentation\(\)/)
})

test('Post Order exposes canonical order modes and contextual records without duplicate forms', async () => {
  const [navigation, postOrder, postAgreement] = await Promise.all([
    source('../src/components/client/OrderWorkspaceNavigation.jsx'),
    source('../src/pages/client/PostOrder.jsx'),
    source('../src/pages/client/PostAgreement.jsx'),
  ])
  assert.match(navigation, />One-Time Order</)
  assert.match(navigation, />Agreemental Order</)
  assert.match(navigation, /to="\/client\/post-order"/)
  assert.match(navigation, /to="\/client\/post-agreement"/)
  assert.match(navigation, /to="\/client\/orders"/)
  assert.match(navigation, /to="\/client\/my-agreements"/)
  assert.match(postOrder, /OrderWorkspaceNavigation mode="one-time"/)
  assert.match(postAgreement, /OrderWorkspaceNavigation mode="agreemental"/)
})

test('all secondary destinations moved out of mobile navigation remain reachable contextually', async () => {
  const [account, orderNav, bids, profile, everyday, app] = await Promise.all([
    source('../src/pages/client/ClientAccount.jsx'),
    source('../src/components/client/OrderWorkspaceNavigation.jsx'),
    source('../src/pages/transporter/MyBids.jsx'),
    source('../src/pages/transporter/profile.jsx'),
    source('../src/components/everyday/EverydayLayout.jsx'),
    source('../src/App.jsx'),
  ])
  for (const path of ['/client/orders', '/client/my-agreements', '/client/post-agreement']) assert.ok(orderNav.includes(path))
  assert.match(account, /\$\{base\}\/security/)
  for (const path of ['/transporter/available-bids', '/transporter/agreement-bids', '/transporter/my-agreements']) assert.ok(bids.includes(path))
  for (const path of ['/transporter/wallet', '/transporter/earnings', '/transporter/settings', '/transporter/security']) assert.ok(profile.includes(path))
  assert.match(everyday, /to="\/everyday\/account"/)
  assert.match(app, /path="security" element=\{<SecuritySettings \/>\}/)
})

test('MPIN visuals are compact while the single masked accessible input architecture is unchanged', async () => {
  const [css, input] = await Promise.all([
    source('../src/styles/components/mpin-security.css'),
    source('../src/components/security/MpinInput.jsx'),
  ])
  assert.match(css, /--mpin-slot-size: 48px/)
  assert.match(css, /--mpin-slot-size: 42px/)
  assert.match(css, /--mpin-slot-gap: 10px/)
  assert.match(css, /--mpin-slot-gap: 8px/)
  assert.match(css, /grid-template-columns: repeat\(4, var\(--mpin-slot-size\)\)/)
  assert.equal(/repeat\(4, minmax\([^)]*1fr/.test(css), false)
  assert.equal((input.match(/<input/g) || []).length, 1)
  assert.match(input, /type="password"/)
  assert.match(input, /inputMode="numeric"/)
  assert.match(input, /maxLength=\{4\}/)
  assert.match(input, /label = 'Four digit MPIN'/)
  assert.match(input, /<label className="mpin-control__label" htmlFor=\{inputId\}>/)
})

test('mobile and desktop typography resolve through distinct shared tokens', async () => {
  const [globalCss, clientCss, dashboardCss] = await Promise.all([
    source('../src/styles/global.css'),
    source('../src/styles/pages/client.css'),
    source('../src/styles/pages/transporter-dashboard.css'),
  ])
  assert.match(globalCss, /--type-page-title: clamp\(1\.9rem, 3vw, 2\.125rem\)/)
  assert.match(globalCss, /@media \(max-width: 768px\)[\s\S]*--type-page-title: clamp\(1\.375rem, 6vw, 1\.625rem\)/)
  assert.match(globalCss, /--type-body: \.9375rem/)
  assert.match(globalCss, /@media \(max-width: 768px\)[\s\S]*--type-body: \.875rem/)
  assert.match(clientCss, /\.everyday-hero h1 \{ font-size: var\(--type-page-title\); \}/)
  assert.match(dashboardCss, /\.dashboard-section-title \{ font-size: var\(--type-section-title\); \}/)
  assert.equal(/zoom\s*:/.test(globalCss + clientCss + dashboardCss), false)
  assert.equal(/(?:html|body)\s*\{[^}]*transform\s*:/s.test(globalCss), false)
})

test('transporter mobile navigation remains permission-filtered and contextual routes stay authorized', async () => {
  const [layout, bids] = await Promise.all([
    source('../src/components/transporter/TransporterLayout.jsx'),
    source('../src/pages/transporter/MyBids.jsx'),
  ])
  const mobile = arrayBlock(layout, 'MOBILE_NAV_ITEMS')
  const labels = [...mobile.matchAll(/label: '([^']+)'/g)].map((match) => match[1])
  assert.deepEqual(labels, ['Dashboard', 'Trucks', 'Bids', 'Messages'])
  assert.match(layout, /filter\(\(item\) => isTransporterPathAllowed\(user, item\.path\)\)/)
  assert.match(bids, /isTransporterPathAllowed\(presentedUser, '\/transporter\/agreement-bids'\)/)
  assert.match(bids, /isTransporterPathAllowed\(presentedUser, '\/transporter\/my-agreements'\)/)
})

test('shared shell keeps responsive width containment without concealing document overflow', async () => {
  const [globalCss, clientCss] = await Promise.all([
    source('../src/styles/global.css'),
    source('../src/styles/pages/client.css'),
  ])
  assert.match(globalCss, /@media \(max-width: 768px\)/)
  assert.match(globalCss, /\.transporter-page \.role-sidebar \{ display: none; \}/)
  assert.match(globalCss, /\.notification-center__panel[\s\S]*position: fixed;[\s\S]*right: 8px;[\s\S]*left: 8px;/)
  assert.match(clientCss, /\.everyday-order-form input,[\s\S]*min-width: 0;/)
  assert.equal(/(?:html|body|\*)[^{}]*\{[^}]*overflow-x\s*:\s*hidden/s.test(globalCss), false)
})
