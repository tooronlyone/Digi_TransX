import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiResponseError } from '../../auth/api'
import { finishFullLogout, requestLogoutAll } from '../../auth/logout'
import { useStepUp } from './StepUpProvider'

export default function LogoutAllAction() {
  const navigate = useNavigate()
  const { protectedFetch } = useStepUp()
  const [stage, setStage] = useState('closed')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const triggerRef = useRef(null)
  const dialogRef = useRef(null)
  const passwordRef = useRef(null)
  const errorRef = useRef(null)
  const generation = useRef(0)

  useEffect(() => () => {
    generation.current += 1
  }, [])

  useEffect(() => {
    if (stage === 'confirm') {
      window.requestAnimationFrame(() => dialogRef.current?.querySelector('button')?.focus())
    } else if (stage === 'password') {
      window.requestAnimationFrame(() => passwordRef.current?.focus())
    }
  }, [stage])

  useEffect(() => {
    if (error) window.requestAnimationFrame(() => errorRef.current?.focus())
  }, [error])

  function openConfirmation() {
    generation.current += 1
    setPassword('')
    setError('')
    setStage('confirm')
  }

  function closeDialog() {
    if (pending) return
    generation.current += 1
    setPassword('')
    setError('')
    setStage('closed')
    window.requestAnimationFrame(() => triggerRef.current?.focus())
  }

  async function performLogoutAll(passwordValue) {
    if (pending) return
    const operationGeneration = ++generation.current
    setPending(true)
    setError('')
    try {
      await requestLogoutAll(protectedFetch, passwordValue)
      if (operationGeneration !== generation.current) return
      setPassword('')
      generation.current += 1
      finishFullLogout(navigate)
    } catch (requestError) {
      if (operationGeneration !== generation.current) return
      setPassword('')
      if (
        requestError instanceof ApiResponseError
        && requestError.status === 428
        && requestError.code === 'current_password_required'
      ) {
        setStage('password')
        setError('')
      } else {
        setError(requestError.message || 'Unable to log out from all devices.')
      }
    } finally {
      if (operationGeneration === generation.current) setPending(false)
    }
  }

  function submitPassword(event) {
    event.preventDefault()
    if (!password || pending) return
    const passwordValue = password
    setPassword('')
    void performLogoutAll(passwordValue)
  }

  function trapFocus(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeDialog()
      return
    }
    if (event.key !== 'Tab') return
    const focusable = [...dialogRef.current.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), [tabindex="0"]',
    )]
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <section className="logout-all-card" aria-labelledby="logout-all-heading">
      <div>
        <p className="mpin-management__eyebrow">Session security</p>
        <h2 id="logout-all-heading">Log out from all devices</h2>
        <p>Your current access will end too. Every active session and trusted device for this account will be revoked.</p>
      </div>
      <button ref={triggerRef} type="button" className="security-danger" onClick={openConfirmation}>
        Log out from all devices
      </button>

      {stage !== 'closed' && (
        <div className="access-lock logout-all-overlay" role="presentation">
          <section
            ref={dialogRef}
            className="access-lock__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-all-dialog-title"
            aria-describedby="logout-all-dialog-description"
            onKeyDown={trapFocus}
          >
            <div className="access-lock__icon is-danger" aria-hidden="true">
              <i className="fas fa-right-from-bracket" />
            </div>
            <h2 id="logout-all-dialog-title">
              {stage === 'password' ? 'Verify your current password' : 'Log out everywhere?'}
            </h2>
            <p id="logout-all-dialog-description">
              {stage === 'password'
                ? 'Your current password is required. It stays only in memory for this request.'
                : 'This immediately ends this session and every other active session and trusted device.'}
            </p>

            {stage === 'confirm' ? (
              <div className="access-lock__form">
                {error && <p ref={errorRef} tabIndex="-1" className="security-message is-error" role="alert">{error}</p>}
                <button type="button" className="security-danger" disabled={pending} onClick={() => void performLogoutAll(undefined)}>
                  {pending ? 'Logging out…' : 'Continue'}
                </button>
                <button type="button" className="security-secondary" disabled={pending} onClick={closeDialog}>Cancel</button>
              </div>
            ) : (
              <form className="access-lock__form" onSubmit={submitPassword}>
                <label className="security-field">
                  <span>Current password</span>
                  <input
                    ref={passwordRef}
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={pending}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? 'logout-all-error' : undefined}
                  />
                </label>
                {error && <p id="logout-all-error" ref={errorRef} tabIndex="-1" className="security-message is-error" role="alert">{error}</p>}
                <button type="submit" className="security-danger" disabled={pending || !password}>
                  {pending ? 'Logging out…' : 'Log out from all devices'}
                </button>
                <button type="button" className="security-secondary" disabled={pending} onClick={closeDialog}>Cancel</button>
              </form>
            )}
          </section>
        </div>
      )}
    </section>
  )
}
