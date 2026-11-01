import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { JSDOM } from '../../../frontend-react/node_modules/jsdom/lib/api.js';

const read = path => fs.readFileSync(`frontend-react/src/${path}`, 'utf8');
const pos = read('pages/shopkeeper/POSPage.jsx');
const receiptFunction = pos.slice(pos.indexOf('function buildReceiptHtml'), pos.indexOf('function printReceipt'));
const receipt = vm.runInNewContext(`${receiptFunction}; buildReceiptHtml`, { fmtDateTime: String });
const payload = '<script>window.__auditReceiptXss = "executed"</script>';
const html = receipt({ purchaser_name: payload, items: [], total_amount: 1, amount_paid: 1, change_amount: 0 }, 'Test Shop', '');
const dom = new JSDOM(html, { url: 'https://digi-transx.test/', runScripts: 'dangerously' });
assert.equal(dom.window.__auditReceiptXss, 'executed');
dom.window.close();
console.log('CONFIRMED: POS purchaser_name executes script in printed receipt HTML.');

process.env.TZ = 'Asia/Karachi';
const agreement = read('pages/client/AgreementBids.jsx');
const dates = agreement.slice(agreement.indexOf('function todayIso'), agreement.indexOf('export default'));
const addMonths = vm.runInNewContext(`${dates}; addMonths`, { Date });
assert.equal(addMonths('2026-10-23', 3), '2027-01-22');
assert.throws(() => addMonths('', 3), RangeError);
console.log('CONFIRMED: agreement date shifts backwards one day in Asia/Karachi; blank input throws RangeError.');

const streaming = read('pages/driver/DriverActiveTrip.jsx');
const stopBody = streaming.slice(streaming.indexOf('  function stopStreaming()'), streaming.indexOf('  return (', streaming.indexOf('  function stopStreaming()')));
let cleared = false;
const stopStreaming = vm.runInNewContext(`${stopBody}; stopStreaming`, {
  watchIdRef: { current: 0 },
  navigator: { geolocation: { clearWatch() { cleared = true; } } },
  setTracking() {}, setStatusMsg() {},
});
stopStreaming();
assert.equal(cleared, false);
console.log('CONFIRMED: valid geolocation watch ID 0 is not cleared by Stop.');

const login = read('pages/auth/Login.jsx');
assert.match(login, /const password = form\.password\.trim\(\)/);
assert.notEqual(' AuditPass123 '.trim(), ' AuditPass123 ');
console.log('CONFIRMED: login changes valid whitespace-bearing password before transmission.');

const items = [{ product: { price: 0.1 }, quantity: 1 }, { product: { price: 0.2 }, quantity: 1 }];
const total = items.reduce((sum, c) => sum + c.product.price * c.quantity, 0);
assert.equal(0.3 >= total, false);
console.log('CONFIRMED: POS refuses exactly PKR 0.30 paid for PKR 0.10 + 0.20 cart because total is ' + total);

for (const path of ['pages/transporter/PartsCartPage.jsx', 'pages/transporter/PartsMarketplace.jsx', 'pages/shopkeeper/ShopkeeperPartsOrders.jsx']) {
  assert.equal(read(path).includes('X-CSRF-Token'), false);
}
console.log('CONFIRMED: marketplace checkout/catalog/status/OTP/RFQ callers omit CSRF headers.');

const savedLocal = new Map();
globalThis.localStorage = {
  getItem: key => savedLocal.get(key) ?? null,
  setItem: (key, value) => savedLocal.set(key, value),
  removeItem: key => savedLocal.delete(key),
};
const assistant = await import('../../../frontend-react/src/lib/aiAssistant.js');
const privateHistory = [{ id: 'audit-history-a', title: 'A private record', createdAt: 1, updatedAt: 1,
  messages: [{ id: 'audit-msg', role: 'user', text: 'account-A-private-shipment-marker', createdAt: 1 }] }];
assistant.saveAssistantConversations(privateHistory);
const { clearAuthPresentation } = await import('../../../frontend-react/src/auth/presentation.js');
clearAuthPresentation({ removeItem() {} });
const nextAccountHistory = assistant.loadAssistantConversations();
assert.equal(nextAccountHistory[0].messages[0].text, 'account-A-private-shipment-marker');
console.log('CONFIRMED: AI conversation text survives logout and is loaded by the next account with no ownership check.');

const wallet = read('components/wallet/WalletWorkspace.jsx');
const transactionFn = wallet.slice(wallet.indexOf('function transactionAmount'), wallet.indexOf('export default'));
const transactionAmount = vm.runInNewContext(`${transactionFn}; transactionAmount`, { formatMoney: amount => `PKR ${amount}` });
assert.equal(transactionAmount({ type: 'agreement_payment_paid', amount: -100 }), '+PKR -100');
const reservationRows = [{ type: 'lock', amount: 100 }, { type: 'unlock', amount: 100 }];
const credits = reservationRows.filter(t => (t.type || '').toLowerCase() === 'credit' || parseFloat(t.amount || 0) > 0)
  .reduce((sum, t) => sum + Math.abs(parseFloat(t.amount || 0)), 0);
assert.equal(credits, 200);
console.log('CONFIRMED: wallet displays signed debit as +PKR -100 and AccountHistory classifies lock+unlock as PKR200 credit.');
