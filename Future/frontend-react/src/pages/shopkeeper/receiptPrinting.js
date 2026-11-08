import { fmtDateTime } from './posUtils.js'

function escapeReceiptText(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character])
}

export function buildReceiptHtml(sale, shopName, city) {
  const items = Array.isArray(sale.items) ? sale.items : []
  const receiptHeightMm = Math.max(125, 112 + items.length * 9)
  const rows = items.map(item => `
    <tr>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;">${escapeReceiptText(item.product_name)}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:center;">${escapeReceiptText(item.quantity)}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">PKR ${Number(item.unit_price).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</td>
      <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">PKR ${Number(item.subtotal).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</td>
    </tr>
  `).join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Receipt ${escapeReceiptText(sale.receipt_number)}</title>
<style>
  @page { size: 80mm ${receiptHeightMm}mm; margin: 0; }
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { width: 80mm; min-height: ${receiptHeightMm}mm; background: #fff; }
  body { font-family: 'Courier New', monospace; font-size: 10px; color: #111; padding: 5mm 4mm; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
  .logo { font-size: 16px; font-weight: 900; color: #111; letter-spacing: -0.5px; }
  .logo-sub { font-size: 8px; color: #4b5563; margin-top: 1px; }
  .shop-name { max-width: 38mm; text-align: right; font-weight: 700; font-size: 10px; }
  .shop-city { text-align: right; font-size: 8px; color: #6b7280; margin-top: 2px; }
  hr { border: none; border-top: 1px dashed #6b7280; margin: 7px 0; }
  .meta { font-size: 9px; color: #1f2937; line-height: 1.7; margin-bottom: 6px; }
  .meta span { font-weight: 700; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8px; margin-bottom: 7px; }
  thead tr { border-bottom: 2px solid #d1d5db; }
  th, td { overflow-wrap: anywhere; }
  th { padding: 3px 2px; text-align: left; font-weight: 700; color: #1f2937; }
  td { padding: 3px 2px !important; }
  th:first-child { width: 34%; }
  th:nth-child(2) { width: 10%; }
  th:nth-child(3), th:nth-child(4) { width: 28%; }
  th:nth-child(2) { text-align: center; }
  th:nth-child(3), th:nth-child(4) { text-align: right; }
  .totals { font-size: 9px; line-height: 1.8; }
  .totals .row { display: flex; justify-content: space-between; }
  .totals .grand { font-weight: 900; font-size: 11px; border-top: 2px solid #111; padding-top: 4px; margin-top: 3px; }
  .totals .change { font-weight: 900; }
  .footer { text-align: center; font-size: 8px; color: #4b5563; margin-top: 11px; line-height: 1.5; }
  @media print {
    html, body { width: 80mm !important; min-height: ${receiptHeightMm}mm !important; }
    body { padding: 5mm 4mm !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  }
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="logo">DigiTransX</div>
    <div class="logo-sub">Point of Sale</div>
  </div>
  <div>
    <div class="shop-name">${escapeReceiptText(shopName)}</div>
    ${city ? `<div class="shop-city">${escapeReceiptText(city)}</div>` : ''}
  </div>
</div>
<hr/>
<div class="meta">
  Receipt: <span>${escapeReceiptText(sale.receipt_number)}</span><br/>
  Date: <span>${escapeReceiptText(fmtDateTime(sale.created_at))}</span><br/>
  Purchaser: <span>${escapeReceiptText(sale.purchaser_name || '—')}</span>
</div>
<hr/>
<table>
  <thead>
    <tr>
      <th>Product</th>
      <th>Qty</th>
      <th>Unit Price</th>
      <th>Subtotal</th>
    </tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
<hr/>
<div class="totals">
  <div class="row grand"><span>Total</span><span>PKR ${Number(sale.total_amount).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
  <div class="row"><span>Amount Paid</span><span>PKR ${Number(sale.amount_paid).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
  <div class="row change"><span>Change</span><span>PKR ${Number(sale.change_amount).toLocaleString('en-PK', { minimumFractionDigits: 2 })}</span></div>
</div>
<div class="footer">
  — Thank you for your purchase! —<br/>
  Powered by DigiTransX
</div>
</body>
</html>`
}

export function printReceipt(sale, shopName, city) {
  const html = buildReceiptHtml(sale, shopName, city)
  const w = window.open('', '_blank', 'width=520,height=720')
  if (!w) return
  w.opener = null
  w.document.write(html)
  w.document.close()
  w.focus()
  setTimeout(() => { w.print() }, 400)
}

