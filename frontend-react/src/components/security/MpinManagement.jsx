import { useEffect, useRef, useState } from 'react'
import { isMpinEligibleRole, isValidMpin } from '../../auth/accessLock'
import { ApiResponseError, requestJson } from '../../auth/api'
import { currentPresentedUser } from '../../auth/presentation'
import MpinInput from './MpinInput'
import '../../styles/components/mpin-security.css'

const EMPTY = Object.freeze({ current: '', disableCurrent: '', next: '', confirm: '', password: '' })

function boundedError(error, operation) {
  if (error instanceof ApiResponseError) {
    if (error.status === 401) return operation === 'change' || operation === 'disable' ? 'The current credential could not be verified.' : 'The password could not be verified.'
    if (error.status === 403) return 'MPIN is not available for this account role.'
    if (error.status === 409) return 'The requested MPIN change conflicts with the current state. Refresh and try again.'
    if (error.status === 423) return 'Unlock Digi_TransX with your password before resetting the MPIN.'
    if (error.status === 429) return 'Too many requests. Please wait and try again.'
    if (error.status === 503) return 'MPIN service is temporarily unavailable. Please try again.'
  }
  return 'The security change could not be completed. Please try again.'
}

export default function MpinManagement() {
  const user = currentPresentedUser()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState({ type: '', text: '' })
  const loadRevision = useRef(0)

  const eligible = isMpinEligibleRole(user?.role)

  async function loadStatus({ preserveMessage = false } = {}) {
    const revision = ++loadRevision.current
    setLoading(true)
    setStatus(null)
    if (!preserveMessage) setMessage({ type: '', text: '' })
    try {
      const payload = await requestJson('/auth/mpin/status')
      if (revision === loadRevision.current) setStatus(payload.mpin)
    } catch (error) {
      if (revision === loadRevision.current) setMessage({ type: 'error', text: boundedError(error, 'status') })
    } finally {
      if (revision === loadRevision.current) setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (eligible) loadStatus()
      else setLoading(false)
    }, 0)
    return () => {
      window.clearTimeout(timer)
      loadRevision.current += 1
    }
  }, [eligible])

  function update(field) {
    return (valueOrEvent) => {
      const value = typeof valueOrEvent === 'string' ? valueOrEvent : valueOrEvent.target.value
      setForm((current) => ({ ...current, [field]: value }))
    }
  }

  function validateNewMpin() {
    if (!isValidMpin(form.next)) return 'Enter exactly four ASCII digits.'
    if (form.next !== form.confirm) return 'The new MPIN values do not match.'
    return ''
  }

  async function mutate(operation, endpoint, body) {
    if (pending) return
    setPending(true)
    setMessage({ type: '', text: '' })
    try {
      await requestJson(endpoint, { method: 'POST', body })
      setMessage({ type: 'success', text: `MPIN ${operation} completed successfully.` })
      await loadStatus({ preserveMessage: true })
    } catch (error) {
      setMessage({ type: 'error', text: boundedError(error, operation) })
    } finally {
      setForm(EMPTY)
      setPending(false)
    }
  }

  async function enroll(event) {
    event.preventDefault()
    const validation = validateNewMpin()
    if (validation || !form.password) {
      setMessage({ type: 'error', text: validation || 'Enter your current password.' })
      return
    }
    await mutate('enrollment', '/auth/mpin/enroll', { mpin: form.next, password: form.password })
  }

  async function change(event) {
    event.preventDefault()
    const validation = validateNewMpin()
    if (validation || !isValidMpin(form.current)) {
      setMessage({ type: 'error', text: validation || 'Enter your current four digit MPIN.' })
      return
    }
    await mutate('change', '/auth/mpin/change', { current_mpin: form.current, new_mpin: form.next })
  }

  async function disable(event) {
    event.preventDefault()
    if (!isValidMpin(form.disableCurrent)) {
      setMessage({ type: 'error', text: 'Enter your current four digit MPIN.' })
      return
    }
    if (!window.confirm('Disable MPIN? Future software unlocks will require your password until MPIN is enrolled again.')) return
    await mutate('disable', '/auth/mpin/disable', { current_mpin: form.disableCurrent })
  }

  async function reset(event) {
    event.preventDefault()
    const validation = validateNewMpin()
    if (validation || !form.password) {
      setMessage({ type: 'error', text: validation || 'Enter your current password.' })
      return
    }
    await mutate('reset', '/auth/mpin/reset', { new_mpin: form.next, password: form.password })
  }

  if (!eligible) return null
  if (!loading && status && status.role_eligible !== true) return null

  return (
    <section className="mpin-management" aria-labelledby="mpin-management-title">
      <div className="mpin-management__header">
        <div>
          <p className="mpin-management__eyebrow">Software access security</p>
          <h2 id="mpin-management-title">MPIN</h2>
        </div>
        <button className="security-secondary" type="button" onClick={loadStatus} disabled={loading || pending}>Refresh status</button>
      </div>
      <p className="mpin-management__intro">Use a four digit MPIN to unlock an existing signed-in session on this trusted device. It cannot sign in on a new device.</p>

      {loading && <p className="security-message" role="status">Checking MPIN status…</p>}
      {message.text && <p className={`security-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</p>}

      {!loading && status && (
        <>
          {status.role_eligible !== true ? null : <div className={`mpin-status ${status.locked ? 'is-locked' : status.enrolled ? 'is-active' : 'is-empty'}`}>
            <i className={`fas ${status.locked ? 'fa-lock' : status.enrolled ? 'fa-shield-halved' : 'fa-circle-plus'}`} aria-hidden="true" />
            <div>
              <strong>{status.locked ? 'MPIN permanently locked' : status.enrolled ? 'MPIN active' : 'MPIN not configured'}</strong>
              <span>{status.locked ? 'Password verification is required to reset it.' : status.enrolled ? 'Available only for software unlock on this trusted session.' : 'Enroll an MPIN using your current password.'}</span>
            </div>
          </div>}

          {status.role_eligible === true && !status.enrolled && !status.locked && (
            <form className="mpin-management__form" onSubmit={enroll}>
              <h3>Enroll MPIN</h3>
              <div className="mpin-management__grid">
                <MpinInput id="enroll-mpin" label="New MPIN" value={form.next} onChange={update('next')} disabled={pending} />
                <MpinInput id="enroll-mpin-confirm" label="Confirm new MPIN" value={form.confirm} onChange={update('confirm')} disabled={pending} />
                <label className="security-field" htmlFor="enroll-password"><span>Current password</span><input id="enroll-password" type="password" autoComplete="current-password" value={form.password} onChange={update('password')} disabled={pending} /></label>
              </div>
              <button className="security-primary" type="submit" disabled={pending}>{pending ? 'Enrolling…' : 'Enroll MPIN'}</button>
            </form>
          )}

          {status.role_eligible === true && status.enrolled && !status.locked && (
            <div className="mpin-management__columns">
              <form className="mpin-management__form" onSubmit={change}>
                <h3>Change MPIN</h3>
                <MpinInput id="change-current-mpin" label="Current MPIN" value={form.current} onChange={update('current')} disabled={pending} />
                <MpinInput id="change-new-mpin" label="New MPIN" value={form.next} onChange={update('next')} disabled={pending} />
                <MpinInput id="change-confirm-mpin" label="Confirm new MPIN" value={form.confirm} onChange={update('confirm')} disabled={pending} />
                <button className="security-primary" type="submit" disabled={pending}>{pending ? 'Changing…' : 'Change MPIN'}</button>
              </form>
              <form className="mpin-management__form is-danger" onSubmit={disable}>
                <h3>Disable MPIN</h3>
                <p>Future software unlocks will require your password until you enroll again.</p>
                <MpinInput id="disable-current-mpin" label="Current MPIN" value={form.disableCurrent} onChange={update('disableCurrent')} disabled={pending} />
                <button className="security-danger" type="submit" disabled={pending}>{pending ? 'Disabling…' : 'Disable MPIN'}</button>
              </form>
            </div>
          )}

          {status.role_eligible === true && status.locked && (
            <form className="mpin-management__form" onSubmit={reset}>
              <h3>Reset locked MPIN</h3>
              <p>You have already unlocked the software with your password. Verify it again to authorize the credential reset.</p>
              <div className="mpin-management__grid">
                <MpinInput id="reset-mpin" label="New MPIN" value={form.next} onChange={update('next')} disabled={pending} />
                <MpinInput id="reset-mpin-confirm" label="Confirm new MPIN" value={form.confirm} onChange={update('confirm')} disabled={pending} />
                <label className="security-field" htmlFor="reset-password"><span>Current password</span><input id="reset-password" type="password" autoComplete="current-password" value={form.password} onChange={update('password')} disabled={pending} /></label>
              </div>
              <button className="security-primary" type="submit" disabled={pending}>{pending ? 'Resetting…' : 'Reset MPIN'}</button>
            </form>
          )}
        </>
      )}
    </section>
  )
}
