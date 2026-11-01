import { useEffect, useState } from 'react'
import { INSURANCE_REMINDER_EVENT } from '../../lib/insuranceReminder'
import '../../styles/components/insurance-reminder.css'

export default function InsuranceReminder() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    let timer
    function show() {
      clearTimeout(timer)
      setVisible(true)
      timer = setTimeout(() => setVisible(false), 10_000)
    }
    window.addEventListener(INSURANCE_REMINDER_EVENT, show)
    return () => {
      clearTimeout(timer)
      window.removeEventListener(INSURANCE_REMINDER_EVENT, show)
    }
  }, [])

  return visible ? <aside className="insurance-reminder" role="status" aria-live="polite">
    <i className="fas fa-shield-halved" aria-hidden="true" />
    <div><strong>Protect your shipment</strong><p>Consider goods insurance for added protection during transport.</p></div>
    <button type="button" aria-label="Dismiss insurance reminder" onClick={() => setVisible(false)}>×</button>
  </aside> : null
}
