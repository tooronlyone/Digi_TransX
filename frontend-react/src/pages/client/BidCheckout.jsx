import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  PageTitle,
  SectionCard,
  StateMessage,
  formatMoney,
  getCsrfToken,
} from './clientUtils'
import '../../styles/pages/bid-checkout.css'

const EMPTY_CARD = {
  card_number: '',
  card_expiry: '',
  card_cvc: '',
  card_holder_name: '',
}

function formatCardNumber(value) {
  // Backend accepts 12–19 digits; group in fours for readability.
  const digits = String(value || '').replace(/\D/g, '').slice(0, 19)
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ')
}

function formatExpiry(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 4)
  if (digits.length <= 2) return digits
  return `${digits.slice(0, 2)}/${digits.slice(2)}`
}

function formatCvc(value) {
  return String(value || '').replace(/\D/g, '').slice(0, 4)
}

function formatCardholderName(value) {
  return String(value || '')
    .replace(/[^A-Za-z\s]/g, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/^\s+/g, '')
}

// One idempotency key per (order + bid + checkout attempt). Only this
// non-sensitive key is persisted so a reload or network retry reuses it; a
// different bid gets a different storage slot and therefore a different key.
function idemStorageKey(orderId, bidId) {
  return `bid_checkout_idem_${orderId}_${bidId}`
}

function newUuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Safe fallback: RFC4122-ish v4 from getRandomValues, or a last-resort mix.
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  return `idem-${Date.now()}-${Math.floor(Math.random() * 1e9)}`
}

function getOrCreateIdemKey(orderId, bidId) {
  const storeKey = idemStorageKey(orderId, bidId)
  try {
    const existing = sessionStorage.getItem(storeKey)
    if (existing) return existing
    const fresh = newUuid()
    sessionStorage.setItem(storeKey, fresh)
    return fresh
  } catch {
    // sessionStorage unavailable — fall back to an in-memory key.
    return newUuid()
  }
}

export default function BidCheckout() {
  const { orderId, bidId } = useParams()
  const navigate = useNavigate()

  const [bid, setBid] = useState(null)
  const [quote, setQuote] = useState(null)
  const [savedCards, setSavedCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Card data lives ONLY in component memory — never localStorage/sessionStorage.
  const [card, setCard] = useState(EMPTY_CARD)
  const [payMode, setPayMode] = useState('saved') // 'saved' | 'new'  (business shortfall)
  const [selectedMethodId, setSelectedMethodId] = useState(null)
  const [saveCard, setSaveCard] = useState(false)
  const [setDefault, setSetDefault] = useState(false)
  const [confirmCharge, setConfirmCharge] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [success, setSuccess] = useState(false)

  // One idempotency key per (orderId, bidId) pair, derived from the route
  // params: navigating to a different bid immediately uses that pair's own key,
  // while a reload or retry for the same pair reuses its persisted key.
  const idempotencyKey = useMemo(() => getOrCreateIdemKey(orderId, bidId), [orderId, bidId])

  // Post-success redirect timer, cleared on unmount so it never fires late.
  const redirectTimerRef = useRef(null)
  useEffect(() => () => {
    if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
  }, [])

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      setError('')
      try {
        const orderResp = await fetch(`/api/orders/${orderId}`, { credentials: 'same-origin' })
        const orderJson = await orderResp.json().catch(() => ({}))
        if (!orderResp.ok || orderJson.success === false) {
          throw new Error(orderJson.message || 'Unable to load order.')
        }
        const foundBid = (orderJson.bids || []).find((b) => String(b.id) === String(bidId))
        if (!active) return
        setBid(foundBid || null)

        const quoteResp = await fetch(`/api/orders/${orderId}/bids/${bidId}/payment-quote`, {
          credentials: 'same-origin',
        })
        const quoteJson = await quoteResp.json().catch(() => ({}))
        if (!quoteResp.ok || quoteJson.success === false) {
          throw new Error(quoteJson.message || 'Unable to load the payment quote.')
        }
        const q = quoteJson.quote
        if (!active) return
        setQuote(q)
        setConfirmCharge(false)

        // Business seekers may pay a shortfall with a saved card.
        if (q.client_kind === 'business' && q.requires_card) {
          let methods = []
          try {
            const methodsResp = await fetch('/api/payment-methods', { credentials: 'same-origin' })
            const methodsJson = await methodsResp.json().catch(() => ({}))
            if (methodsResp.ok && methodsJson.success !== false) {
              methods = methodsJson.methods || []
            }
          } catch {
            methods = []
          }
          if (!active) return
          setSavedCards(methods)
          if (methods.length > 0) {
            // Prefer the default card when it is one of the active methods,
            // otherwise fall back to the first active card. Saved-card mode is
            // never left with no selection.
            const defaultInList = q.default_card
              && methods.some((m) => String(m.id) === String(q.default_card.id))
            setSelectedMethodId(defaultInList ? q.default_card.id : methods[0].id)
            setPayMode('saved')
          } else {
            setSelectedMethodId(null)
            setPayMode('new')
          }
        } else {
          if (!active) return
          setSavedCards([])
          setSelectedMethodId(null)
        }
      } catch (loadError) {
        if (active) setError(loadError.message || 'Unable to load checkout.')
      } finally {
        if (active) setLoading(false)
      }
    }

    // load() guards every state update behind `active`, so it is safe to
    // invoke directly here and cancel via the cleanup below.
    load()
    return () => {
      active = false
    }
  }, [orderId, bidId])

  const clientKind = quote?.client_kind
  const requiresCard = !!quote?.requires_card
  const autoEnabled = !!quote?.auto_shortfall_charge_enabled

  // Overall seeker cost = wallet-funded + total card charge (fee included).
  const overallCost = useMemo(() => {
    if (!quote) return 0
    return Number(quote.wallet_funded_amount || 0) + Number(quote.total_card_charge || 0)
  }, [quote])

  function updateCard(field, formatter) {
    return (event) => {
      const raw = event.target.value
      const value = formatter ? formatter(raw) : raw
      setCard((prev) => ({ ...prev, [field]: value }))
    }
  }

  function buildPayload() {
    // Everyday users: one-time card funds the full bid; card is never saved.
    if (clientKind === 'everyday') {
      return {
        card: {
          card_number: card.card_number,
          card_expiry: card.card_expiry,
          card_cvc: card.card_cvc,
          card_holder_name: card.card_holder_name.trim(),
        },
      }
    }

    // Business seekers.
    if (!requiresCard) {
      return {} // wallet covers the full bid — no card needed.
    }

    if (payMode === 'new') {
      const payload = {
        card: {
          card_number: card.card_number,
          card_expiry: card.card_expiry,
          card_cvc: card.card_cvc,
          card_holder_name: card.card_holder_name.trim(),
        },
        save_card: !!saveCard,
      }
      if (saveCard) payload.set_default = !!setDefault
      return payload
    }

    // Saved card path.
    const payload = {}
    if (selectedMethodId != null) payload.saved_method_id = selectedMethodId
    // When automatic shortfall charging is disabled, the seeker must explicitly
    // authorize the card charge.
    if (!autoEnabled) payload.confirm_card_charge = !!confirmCharge
    return payload
  }

  function returnToComparison() {
    navigate(`/client/order/${orderId}`)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting || success) return

    // Saved-card mode must have a selected card and, when automatic charging
    // is disabled, explicit authorization (backend re-enforces both).
    if (clientKind === 'business' && requiresCard && payMode === 'saved') {
      if (selectedMethodId == null) {
        setSubmitError('Please select a saved card or enter a new card.')
        return
      }
      if (!autoEnabled && !confirmCharge) {
        setSubmitError('Please authorize the card charge to continue.')
        return
      }
    }

    setSubmitting(true)
    setSubmitError('')
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`/api/orders/${orderId}/bids/${bidId}/checkout`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify(buildPayload()),
      })
      const json = await response.json().catch(() => ({}))

      if (!response.ok || json.success === false) {
        const code = json.code
        // A no-longer-usable truck or a closed order: send the seeker back to a
        // freshly reloaded comparison / order view.
        if (code === 'bid_truck_unavailable' || code === 'order_not_open' || code === 'bid_not_pending') {
          clearIdemKey()
          returnToComparison()
          return
        }
        throw new Error(json.message || 'Checkout could not be completed.')
      }

      // Success — clear the raw card data and this pair's idempotency key.
      setCard(EMPTY_CARD)
      clearIdemKey()
      setSuccess(true)
      redirectTimerRef.current = setTimeout(returnToComparison, 1600)
    } catch (submitException) {
      setSubmitError(submitException.message || 'Checkout could not be completed.')
    } finally {
      setSubmitting(false)
    }
  }

  function clearIdemKey() {
    try {
      sessionStorage.removeItem(idemStorageKey(orderId, bidId))
    } catch {
      /* ignore */
    }
  }

  if (loading) {
    return (
      <div className="bid-checkout-page">
        <StateMessage type="loading">Loading checkout...</StateMessage>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bid-checkout-page">
        <StateMessage type="error">{error}</StateMessage>
        <Link to={`/client/order/${orderId}`} className="mt-4 inline-flex items-center gap-2 text-blue-600 hover:text-blue-700">
          <i className="fas fa-arrow-left"></i>
          Back to Order
        </Link>
      </div>
    )
  }

  if (success) {
    return (
      <div className="bid-checkout-page">
        <div className="checkout-success">
          <div className="checkout-success__icon"><i className="fas fa-circle-check" aria-hidden="true"></i></div>
          <h2>Payment Held</h2>
          <p>Your payment is securely held. The transporter can now start the trip once they are ready.</p>
          <button type="button" onClick={returnToComparison} className="checkout-primary-btn">
            View Order
          </button>
        </div>
      </div>
    )
  }

  const truck = bid?.truck
  const transporter = bid?.transporter

  return (
    <div className="bid-checkout-page">
      <PageTitle title="Checkout" subtitle={`Order #${orderId} · Bid #${bidId}`} />

      <div className="checkout-grid">
        <div className="checkout-main">
          {/* Selected transporter + truck */}
          <SectionCard title="Selected Transporter & Truck" icon="fa-truck">
            <div className="checkout-selected">
              <div className="checkout-selected__photo">
                {truck?.photo_url ? (
                  <img src={truck.photo_url} alt={truck?.truck_number || 'Truck'} loading="lazy" />
                ) : (
                  <div className="checkout-selected__fallback" aria-hidden="true"><i className="fas fa-truck"></i></div>
                )}
              </div>
              <div className="checkout-selected__meta">
                <div className="checkout-selected__name">
                  {transporter?.company_name || transporter?.display_name || 'Transporter'}
                </div>
                {truck && (
                  <div className="checkout-selected__truck">
                    {truck.type_name || 'Truck'}{truck.truck_number ? ` · ${truck.truck_number}` : ''}
                    {(truck.company || truck.model) ? ` · ${[truck.company, truck.model].filter(Boolean).join(' ')}` : ''}
                  </div>
                )}
                {truck && (
                  <div className="checkout-selected__specs">
                    {(truck.payload_max_tons ?? truck.capacity_tons) ? `${truck.payload_max_tons ?? truck.capacity_tons} t` : null}
                    {truck.volume_max_cbm ? ` · ${truck.volume_max_cbm} cbm` : ''}
                  </div>
                )}
              </div>
            </div>
          </SectionCard>

          {/* Payment method */}
          <form onSubmit={handleSubmit}>
            {clientKind === 'business' && !requiresCard && (
              <SectionCard title="Payment Method" icon="fa-wallet">
                <div className="checkout-note checkout-note--ok">
                  <i className="fas fa-circle-check" aria-hidden="true"></i>
                  <span>Your wallet balance covers this bid in full. No card is required.</span>
                </div>
              </SectionCard>
            )}

            {clientKind === 'business' && requiresCard && (
              <SectionCard title="Payment Method" icon="fa-credit-card">
                {savedCards.length > 0 && (
                  <div className="checkout-tabs">
                    <button type="button" className={`checkout-tab ${payMode === 'saved' ? 'is-active' : ''}`} onClick={() => setPayMode('saved')}>
                      Saved card
                    </button>
                    <button type="button" className={`checkout-tab ${payMode === 'new' ? 'is-active' : ''}`} onClick={() => setPayMode('new')}>
                      New card
                    </button>
                  </div>
                )}

                {payMode === 'saved' && savedCards.length > 0 && (
                  <div className="checkout-saved-list">
                    {savedCards.map((method) => (
                      <label key={method.id} className={`checkout-saved ${String(selectedMethodId) === String(method.id) ? 'is-selected' : ''}`}>
                        <input
                          type="radio"
                          name="saved_method"
                          checked={String(selectedMethodId) === String(method.id)}
                          onChange={() => setSelectedMethodId(method.id)}
                        />
                        <span className="checkout-saved__brand">{method.card_brand}</span>
                        <span className="checkout-saved__num">•••• {method.card_last_four}</span>
                        <span className="checkout-saved__exp">{String(method.expiry_month).padStart(2, '0')}/{method.expiry_year}</span>
                        {method.is_default && <span className="checkout-saved__default">Default</span>}
                      </label>
                    ))}
                    {!autoEnabled && (
                      <label className="checkout-confirm">
                        <input type="checkbox" checked={confirmCharge} onChange={(e) => setConfirmCharge(e.target.checked)} />
                        <span>I authorize charging the card-funded amount to this card.</span>
                      </label>
                    )}
                  </div>
                )}

                {payMode === 'new' && (
                  <>
                    <CardFields card={card} updateCard={updateCard} />
                    <label className="checkout-check">
                      <input type="checkbox" checked={saveCard} onChange={(e) => setSaveCard(e.target.checked)} />
                      <span>Save this card for future orders</span>
                    </label>
                    {saveCard && (
                      <label className="checkout-check">
                        <input type="checkbox" checked={setDefault} onChange={(e) => setSetDefault(e.target.checked)} />
                        <span>Set as my default card</span>
                      </label>
                    )}
                  </>
                )}
              </SectionCard>
            )}

            {clientKind === 'everyday' && (
              <SectionCard title="Card Details" icon="fa-credit-card">
                <div className="checkout-note">
                  <i className="fas fa-circle-info" aria-hidden="true"></i>
                  <span>Enter your card details to pay for this order. Your card details are used once and are never stored.</span>
                </div>
                <CardFields card={card} updateCard={updateCard} />
              </SectionCard>
            )}

            {submitError && (
              <div className="mb-4">
                <StateMessage type="error">{submitError}</StateMessage>
              </div>
            )}

            <div className="checkout-actions">
              <Link to={`/client/order/${orderId}`} className="checkout-secondary-btn">
                <i className="fas fa-arrow-left" aria-hidden="true"></i> Back
              </Link>
              <button type="submit" disabled={submitting} className="checkout-primary-btn">
                <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-lock'}`} aria-hidden="true"></i>
                {submitting ? 'Processing…' : `Pay ${formatMoney(overallCost)}`}
              </button>
            </div>
          </form>
        </div>

        {/* Server-calculated payment breakdown */}
        <div className="checkout-side">
          <SectionCard title="Payment Breakdown" icon="fa-receipt">
            <div className="breakdown">
              <Row label="Transport bid amount" value={formatMoney(quote.bid_amount)} />
              {clientKind === 'business' && (
                <Row label="Wallet available" value={formatMoney(quote.wallet_available)} muted />
              )}
              {clientKind === 'business' && (
                <Row label="Wallet-funded amount" value={formatMoney(quote.wallet_funded_amount)} />
              )}
              <Row label="Card-funded amount" value={formatMoney(quote.card_funded_amount)} />
              {Number(quote.card_funded_amount) > 0 && (
                <>
                  <Row label={`Card processing fee (${quote.processing_fee_percent}%)`} value={formatMoney(quote.processing_fee_amount)} />
                  <Row label="Total card charge" value={formatMoney(quote.total_card_charge)} />
                </>
              )}
              <div className="breakdown__divider" />
              <Row label="Overall seeker cost" value={formatMoney(overallCost)} strong />
            </div>

            <div className="breakdown-notes">
              <p><i className="fas fa-circle-info" aria-hidden="true"></i> The card processing fee is paid by you only on the card-funded amount.</p>
              <p><i className="fas fa-circle-info" aria-hidden="true"></i> Platform commission is deducted from the transporter’s payout — it is not added again to your charge.</p>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}

function CardFields({ card, updateCard }) {
  return (
    <div className="checkout-card-fields">
      <label className="checkout-field checkout-field--full">
        <span>Card number</span>
        <input
          type="text"
          inputMode="numeric"
          autoComplete="cc-number"
          placeholder="4242 4242 4242 4242"
          value={card.card_number}
          onChange={updateCard('card_number', formatCardNumber)}
        />
      </label>
      <label className="checkout-field">
        <span>Expiry (MM/YY)</span>
        <input
          type="text"
          inputMode="numeric"
          autoComplete="cc-exp"
          placeholder="12/30"
          value={card.card_expiry}
          onChange={updateCard('card_expiry', formatExpiry)}
        />
      </label>
      <label className="checkout-field">
        <span>Security code</span>
        <input
          type="text"
          inputMode="numeric"
          autoComplete="cc-csc"
          placeholder="123"
          value={card.card_cvc}
          onChange={updateCard('card_cvc', formatCvc)}
        />
      </label>
      <label className="checkout-field checkout-field--full">
        <span>Cardholder name</span>
        <input
          type="text"
          autoComplete="cc-name"
          placeholder="Name on card"
          value={card.card_holder_name}
          onChange={updateCard('card_holder_name', formatCardholderName)}
        />
      </label>
    </div>
  )
}

function Row({ label, value, muted, strong }) {
  return (
    <div className={`breakdown__row ${strong ? 'breakdown__row--strong' : ''} ${muted ? 'breakdown__row--muted' : ''}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}
