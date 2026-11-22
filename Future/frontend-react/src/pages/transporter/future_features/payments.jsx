// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useState } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const CURRENCIES = { USD: '$', EUR: '€', GBP: '£', PKR: '₨' }

export default function Payments() {
  const api = useApi()
  const [mode, setMode] = useState('international')
  const [currency, setCurrency] = useState('USD')
  const [name, setName] = useState('')
  const [card, setCard] = useState('')
  const [expiry, setExpiry] = useState('')
  const [cvc, setCvc] = useState('')
  const [amount, setAmount] = useState('')
  const [slip, setSlip] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [toast, setToast] = useState(null)
  const [error, setError] = useState('')

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  function formatCard(val) {
    const digits = val.replace(/\D/g, '').slice(0, 16)
    return digits.replace(/(.{4})/g, '$1 ').trim()
  }

  function formatExpiry(val) {
    const digits = val.replace(/\D/g, '').slice(0, 4)
    if (digits.length >= 3) return digits.slice(0, 2) + '/' + digits.slice(2)
    return digits
  }

  const sym = CURRENCIES[currency] || ''
  const numAmount = parseFloat(amount) || 0
  const fee = numAmount * 0.025
  const total = numAmount + fee

  function validate() {
    if (!amount || numAmount <= 0) return 'Please enter a valid amount'
    if (mode === 'international') {
      if (!name.trim()) return 'Cardholder name is required'
      const rawCard = card.replace(/\s/g, '')
      if (rawCard.length !== 16) return 'Card number must be 16 digits'
      if (expiry.length !== 5) return 'Expiry must be MM/YY format'
      const [mm] = expiry.split('/')
      if (parseInt(mm) < 1 || parseInt(mm) > 12) return 'Invalid expiry month'
      if (!cvc || cvc.length < 3) return 'Invalid security code'
    } else {
      if (!slip) return 'Please upload a bank payment slip'
    }
    return ''
  }

  async function processPayment(e) {
    e.preventDefault()
    setError('')
    const err = validate()
    if (err) { setError(err); return }
    setProcessing(true)
    try {
      const body = mode === 'international'
        ? { mode, currency, name, card_last4: card.replace(/\s/g, '').slice(-4), amount: numAmount, fee, total }
        : { mode, currency, amount: numAmount, fee, total }
      await api.post('/api/payments', body)
      showToast(`Payment of ${sym}${total.toFixed(2)} processed successfully`)
      setAmount('')
      setCard('')
      setExpiry('')
      setCvc('')
      setName('')
      setSlip(null)
    } catch (err) {
      setError(err.message || 'Payment failed. Please try again.')
    } finally {
      setProcessing(false)
    }
  }

  return (
    <TransporterLayout>
      <div className="page-payments">
        <div className="top-bar">
          <div className="page-title">
            <h1>Payment Processing</h1>
            <p>Process transactions safely with our encrypted payment system</p>
          </div>
        </div>

        <div className="payment-card">
          <div className="card-header">
            <h2>Secure Payment Gateway</h2>
            <p>Process transactions safely with our encrypted payment system</p>
          </div>

          <div className="secure-note">
            <i className="fas fa-shield-alt"></i> All transactions are SSL encrypted and PCI compliant
          </div>

          {error && (
            <div className="error-message" style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#e74c3c', background: '#ffeaea', borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
              <i className="fas fa-exclamation-circle"></i> {error}
            </div>
          )}

          <form onSubmit={processPayment}>
            <div className="form-group payment-mode-group">
              <label htmlFor="mode">Payment Mode</label>
              <select id="mode" value={mode} onChange={e => setMode(e.target.value)} required>
                <option value="international">International Card Payment</option>
                <option value="local">Local Bank Transfer</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="currency">Currency</label>
              <select id="currency" value={currency} onChange={e => setCurrency(e.target.value)} required>
                {Object.keys(CURRENCIES).map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {mode === 'international' && (
              <>
                <div className="form-group">
                  <label htmlFor="name">Cardholder Name</label>
                  <div className="input-wrapper">
                    <input type="text" id="name" value={name} onChange={e => setName(e.target.value)}
                      placeholder="Full name as shown on card" autoComplete="cc-name" required />
                    <i className="fas fa-user input-icon"></i>
                  </div>
                </div>

                <div className="card-fields">
                  <div className="form-group">
                    <label htmlFor="card">Card Number</label>
                    <div className="input-wrapper">
                      <input type="text" id="card" value={card}
                        onChange={e => setCard(formatCard(e.target.value))}
                        maxLength={19} placeholder="1234 5678 9012 3456"
                        autoComplete="cc-number" required />
                      <i className="far fa-credit-card input-icon"></i>
                    </div>
                    <div className="card-icons">
                      <img src="https://img.icons8.com/color/48/000000/visa.png" alt="Visa" className="card-icon" style={{ opacity: card.startsWith('4') ? 1 : 0.35 }} />
                      <img src="https://img.icons8.com/color/48/000000/mastercard.png" alt="Mastercard" className="card-icon" style={{ opacity: card.replace(/\s/g, '').startsWith('5') ? 1 : 0.35 }} />
                      <img src="https://img.icons8.com/color/48/000000/amex.png" alt="Amex" className="card-icon" style={{ opacity: card.replace(/\s/g, '').startsWith('3') ? 1 : 0.35 }} />
                    </div>
                  </div>

                  <div className="row">
                    <div className="form-group">
                      <label htmlFor="expiry">Expiry Date</label>
                      <div className="input-wrapper">
                        <input type="text" id="expiry" value={expiry}
                          onChange={e => setExpiry(formatExpiry(e.target.value))}
                          maxLength={5} placeholder="MM/YY" autoComplete="cc-exp" required />
                        <i className="far fa-calendar-alt input-icon"></i>
                      </div>
                    </div>
                    <div className="form-group">
                      <label htmlFor="cvc">Security Code</label>
                      <div className="input-wrapper">
                        <input type="password" id="cvc" value={cvc}
                          onChange={e => setCvc(e.target.value.replace(/\D/g, '').slice(0, 4))}
                          maxLength={4} placeholder="CVC" autoComplete="cc-csc" required />
                        <i className="fas fa-lock input-icon"></i>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {mode === 'local' && (
              <>
                <div className="secure-note" style={{ marginBottom: 16 }}>
                  <i className="fas fa-university"></i>
                  <span style={{ marginLeft: 10 }}>Please transfer to our bank account and upload the payment slip below.</span>
                </div>
                <div className="form-group bank-slip-group">
                  <label htmlFor="slip">Upload Bank Payment Slip</label>
                  <div className="input-wrapper">
                    <input type="file" id="slip" accept=".pdf,.jpg,.jpeg,.png"
                      onChange={e => setSlip(e.target.files[0] || null)} />
                    <i className="fas fa-file-upload input-icon"></i>
                  </div>
                </div>
              </>
            )}

            <div className="form-group">
              <label htmlFor="amount">Payment Amount</label>
              <div className="input-wrapper">
                <input type="number" id="amount" value={amount}
                  onChange={e => setAmount(e.target.value)}
                  min="1" step="0.01" placeholder="0.00" required />
                <i className="fas fa-dollar-sign input-icon"></i>
              </div>
            </div>

            <div className="payment-summary">
              <h3>Payment Summary</h3>
              <div className="summary-row">
                <span>Subtotal:</span>
                <span>{sym}{numAmount.toFixed(2)}</span>
              </div>
              <div className="summary-row">
                <span>Processing Fee (2.5%):</span>
                <span>{sym}{fee.toFixed(2)}</span>
              </div>
              <div className="summary-row total">
                <span>Total Amount:</span>
                <span>{sym}{total.toFixed(2)}</span>
              </div>
            </div>

            <button type="submit" className="pay-btn" disabled={processing}>
              <i className="fas fa-lock"></i> {processing ? 'Processing...' : 'Process Payment'}
            </button>
          </form>
        </div>
      </div>

      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
          background: toast.type === 'error' ? '#e74c3c' : '#27ae60',
          color: '#fff', padding: '12px 20px', borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)', maxWidth: 360,
        }}>
          {toast.msg}
        </div>
      )}
    </TransporterLayout>
  )
}
