import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (relative) => readFile(new URL(relative, import.meta.url), 'utf8')

test('all authenticated role shells share the bottom navigation owner', async () => {
  const layouts = await Promise.all([
    source('../src/components/client/ClientLayout.jsx'),
    source('../src/components/everyday/EverydayLayout.jsx'),
    source('../src/components/transporter/TransporterLayout.jsx'),
  ])

  for (const layout of layouts) {
    assert.match(layout, /MobileBottomNavigation/)
    assert.match(layout, /className="sidebar role-sidebar"/)
    assert.equal(layout.includes('fa-bars'), false)
    assert.equal(layout.includes('menuOpen'), false)
    assert.equal(layout.includes('Toggle navigation'), false)
  }
})

test('mobile navigation exposes four primary destinations and a bounded accessible More sheet', async () => {
  const navigation = await source('../src/components/common/MobileBottomNavigation.jsx')
  assert.match(navigation, /PRIMARY_ITEM_COUNT = 4/)
  assert.match(navigation, /aria-expanded=/)
  assert.match(navigation, /aria-controls="mobile-more-destinations"/)
  assert.match(navigation, /role="dialog"/)
  assert.match(navigation, /aria-modal="true"/)
  assert.match(navigation, /event\.key === 'Escape'/)
  assert.match(navigation, /event\.key !== 'Tab'/)
  assert.match(navigation, /querySelectorAll\('a\[href\], button:not\(\[disabled\]\)'\)/)
  assert.match(navigation, /More destinations/)
  assert.equal(navigation.includes('fa-bars'), false)
})

test('shared shell CSS uses a bottom bar through tablet width without hiding page overflow', async () => {
  const css = await source('../src/styles/global.css')
  assert.match(css, /@media \(max-width: 768px\)/)
  assert.match(css, /\.transporter-page \.role-sidebar \{ display: none; \}/)
  assert.match(css, /\.mobile-bottom-nav[\s\S]*position: fixed;[\s\S]*grid-template-columns: repeat\(5, minmax\(0, 1fr\)\)/)
  assert.match(css, /\.transporter-page \.main-content,[\s\S]*margin-left: 0;/)
  assert.match(css, /\.notification-center__panel[\s\S]*position: fixed;[\s\S]*right: 8px;[\s\S]*left: 8px;/)
  assert.match(css, /100dvh/)
  assert.equal(/(?:html|body|\*)[^{}]*\{[^}]*overflow-x\s*:\s*hidden/s.test(css), false)
})

test('shared Post Order and MPIN surfaces explicitly collapse intrinsic mobile widths', async () => {
  const clientCss = await source('../src/styles/pages/client.css')
  const securityCss = await source('../src/styles/components/mpin-security.css')
  assert.match(clientCss, /\.everyday-order-form input,[\s\S]*\.everyday-order-form select,[\s\S]*min-width: 0;/)
  assert.match(clientCss, /@media \(max-width: 768px\)[\s\S]*\.client-form-grid[\s\S]*grid-template-columns: minmax\(0, 1fr\)/)
  assert.match(clientCss, /\.lp-map-btn[\s\S]*flex: 0 0 auto/)
  assert.match(securityCss, /@media \(max-width: 767px\)[\s\S]*\.security-settings-page \{ padding: 0; \}/)
  assert.match(securityCss, /max-height: 620px[\s\S]*orientation: landscape/)
})
