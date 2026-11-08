import { useEffect, useRef, useState } from 'react'
import { requestJson } from '../../auth/api'

export default function DeliveryHandoffCode({ orderId }) {
  const [code, setCode] = useState(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const request = useRef(null)

  useEffect(() => () => request.current?.abort(), [])

  async function issueCode() {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setPending(true)
    setError('')
    setCode(null)
    try {
      const result = await requestJson(`/api/marketplace/orders/${orderId}/delivery-otp`, {
        method: 'POST', body: {}, signal: controller.signal,
      })
      if (!controller.signal.aborted) setCode(result)
    } catch (error) {
      if (!controller.signal.aborted) setError(error.message || 'The handoff code could not be issued.')
    } finally {
      if (request.current === controller) request.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return <section aria-label="Delivery handoff code">
    <p>Request a code when you have received and checked the parts.</p>
    <button type="button" className="store-secondary-link" disabled={pending} onClick={issueCode}>
      {pending ? 'Requesting code...' : 'Request handoff code'}
    </button>
    {error && <p role="alert">{error}</p>}
    {code && <p role="status">Handoff code: <strong>{code.delivery_otp}</strong>. Expires {new Date(code.expires_at).toLocaleTimeString('en-PK')}. Share it with the shop after receiving the parts.</p>}
  </section>
}
