import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { ApiResponseError, requestJson } from '../../auth/api'
import { accessLockCoordinator } from '../../auth/accessLock'
import { useLocation } from 'react-router-dom'
import MpinInput from './MpinInput'
import '../../styles/components/mpin-security.css'

const StepUpContext = createContext(null)

export function StepUpProvider({ children }) {
  const location = useLocation()
  const [challenge, setChallenge] = useState(null)
  const [mpin, setMpin] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const resolver = useRef(null)
  const dialogRef = useRef(null)
  const mpinRef = useRef(null)
  const generation = useRef(0)

  const cancelChallenge = useCallback((message = 'Step-up authorization was cancelled.') => {
    generation.current += 1
    const current = resolver.current
    resolver.current = null
    setMpin('')
    setError('')
    setChallenge(null)
    setPending(false)
    current?.reject(new Error(message))
  }, [])

  useEffect(() => () => {
    cancelChallenge('Step-up authorization was cancelled because the page changed.')
  }, [location.key, cancelChallenge])

  useEffect(() => accessLockCoordinator.subscribe((event) => {
    if (event.type === 'access_locked' || event.type === 'full_login_required' || event.type === 'identity_context_changed') {
      cancelChallenge('Step-up authorization was cancelled because authentication changed.')
    }
  }), [cancelChallenge])

  useEffect(() => {
    if (challenge) window.requestAnimationFrame(() => mpinRef.current?.focus())
  }, [challenge])

  const requestProof = useCallback((action) => new Promise((resolve, reject) => {
    if (resolver.current) {
      reject(new Error('Another protected action is awaiting MPIN authorization.'))
      return
    }
    resolver.current = { resolve, reject }
    generation.current += 1
    setChallenge(action)
    setMpin('')
    setError('')
  }), [])

  const protectedFetch = useCallback(async (url, options = {}) => {
    const first = await fetch(url, options)
    const payload = await first.clone().json().catch(() => ({}))
    if (first.status !== 428 || payload?.code !== 'mpin_step_up_required' || !payload?.action) return first
    const authorized = await requestProof(payload.action)
    if (authorized.generation !== generation.current) {
      throw new Error('Step-up authorization was cancelled because authentication changed.')
    }
    const headers = new Headers(options.headers || {})
    headers.set('X-MPIN-Step-Up-Proof', authorized.proof)
    return fetch(url, { ...options, headers })
  }, [requestProof])

  async function authorize(event) {
    event.preventDefault()
    if (!/^[0-9]{4}$/.test(mpin) || pending || !challenge) return
    setPending(true)
    setError('')
    const operationGeneration = generation.current
    try {
      const result = await requestJson('/auth/mpin/step-up', {
        method: 'POST',
        body: { mpin, action: challenge },
      })
      if (operationGeneration !== generation.current) return
      const current = resolver.current
      resolver.current = null
      setMpin('')
      setChallenge(null)
      current?.resolve({
        proof: result.authorization_proof,
        generation: operationGeneration,
      })
    } catch (requestError) {
      if (operationGeneration !== generation.current) return
      setMpin('')
      setError(
        requestError instanceof ApiResponseError && requestError.status === 423
          ? 'MPIN is locked. Use Security settings for recovery.'
          : requestError.message || 'MPIN authorization failed. Try again.',
      )
    } finally {
      if (operationGeneration === generation.current) setPending(false)
    }
  }

  function cancel() {
    cancelChallenge()
  }

  function trapFocus(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      if (!pending) cancel()
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
    <StepUpContext.Provider value={{ protectedFetch }}>
      {children}
      {challenge && (
        <div className="access-lock step-up-overlay" role="presentation">
          <section ref={dialogRef} className="access-lock__dialog" role="dialog" aria-modal="true" aria-labelledby="step-up-title" onKeyDown={trapFocus}>
            <div className="access-lock__icon" aria-hidden="true"><i className="fas fa-shield-halved" /></div>
            <h2 id="step-up-title">Authorize protected action</h2>
            <p>Enter your four digit MPIN to continue. Authorization expires in three minutes and works only for this exact action.</p>
            <form onSubmit={authorize} className="access-lock__form">
              <MpinInput ref={mpinRef} value={mpin} onChange={setMpin} disabled={pending} errorId={error ? 'step-up-error' : undefined} />
              {error && <p id="step-up-error" className="security-message is-error" role="alert">{error}</p>}
              <button className="security-primary" type="submit" disabled={pending || mpin.length !== 4}>
                {pending ? 'Authorizing…' : 'Authorize'}
              </button>
              <button className="security-secondary" type="button" onClick={cancel} disabled={pending}>Cancel</button>
            </form>
          </section>
        </div>
      )}
    </StepUpContext.Provider>
  )
}

// The provider and its hook intentionally share this one security owner.
// eslint-disable-next-line react-refresh/only-export-components
export function useStepUp() {
  const value = useContext(StepUpContext)
  if (!value) throw new Error('useStepUp must be used within StepUpProvider.')
  return value
}
