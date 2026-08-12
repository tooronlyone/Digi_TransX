import { createContext, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ACCESS_STATES,
  accessLockCoordinator,
  createLatestRequestGate,
  deriveAccessState,
  isPublicAuthPath,
  safeRelativePath,
} from '../../auth/accessLock'
import { ApiResponseError, requestJson } from '../../auth/api'
import { cacheAuthPresentation, clearAuthPresentation } from '../../auth/presentation'
import MpinInput from './MpinInput'
import '../../styles/components/mpin-security.css'

const AccessLockContext = createContext(null)

function genericUnlockMessage(error, kind) {
  if (error?.status === 503) return 'Unlock is temporarily unavailable. Please try again.'
  if (kind === 'mpin' && error?.status === 401) return 'The MPIN could not be verified.'
  if (kind === 'password' && error?.status === 401) return 'The password could not be verified.'
  return 'Unlock could not be completed. Please try again.'
}

function AccessLockScreen({ state, user, onRefresh }) {
  const navigate = useNavigate()
  const headingRef = useRef(null)
  const mpinRef = useRef(null)
  const dialogRef = useRef(null)
  const [mode, setMode] = useState(() => state === ACCESS_STATES.LOCKED_MPIN_AVAILABLE ? 'mpin' : 'password')
  const [mpin, setMpin] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  const permanent = state === ACCESS_STATES.MPIN_PERMANENTLY_LOCKED
  const mpinAvailable = state === ACCESS_STATES.LOCKED_MPIN_AVAILABLE && mode === 'mpin'
  const unavailable = state === ACCESS_STATES.TEMPORARILY_UNAVAILABLE

  useEffect(() => {
    window.requestAnimationFrame(() => {
      if (state === ACCESS_STATES.LOCKED_MPIN_AVAILABLE) mpinRef.current?.focus()
      else headingRef.current?.focus()
    })
  }, [state])

  function trapFocus(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      return
    }
    if (event.key !== 'Tab') return
    const focusable = [...dialogRef.current.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex="0"]',
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

  async function submitMpin(event) {
    event.preventDefault()
    if (!/^[0-9]{4}$/.test(mpin) || pending) {
      if (!pending) setError('Enter exactly four digits.')
      return
    }
    setPending(true)
    setError('')
    try {
      await requestJson('/auth/mpin/unlock', { method: 'POST', body: { mpin } })
      setMpin('')
      await onRefresh()
    } catch (requestError) {
      setMpin('')
      if (requestError instanceof ApiResponseError && requestError.status === 423 && requestError.code === 'mpin_locked') {
        await onRefresh()
      } else if (requestError instanceof ApiResponseError && requestError.status === 409) {
        await onRefresh()
      } else {
        setError(genericUnlockMessage(requestError, 'mpin'))
        window.requestAnimationFrame(() => mpinRef.current?.focus())
      }
    } finally {
      setPending(false)
    }
  }

  async function submitPassword(event) {
    event.preventDefault()
    if (!password || pending) return
    const identifier = user?.email || user?.cnic || ''
    if (!identifier) {
      setError('Password unlock is temporarily unavailable. Please sign in again.')
      return
    }
    setPending(true)
    setError('')
    try {
      await requestJson('/auth/access/unlock/password', {
        method: 'POST',
        body: { identifier, password },
      })
      setPassword('')
      await onRefresh()
    } catch (requestError) {
      setPassword('')
      if (requestError instanceof ApiResponseError && requestError.status === 409) {
        await onRefresh()
      } else {
        setError(genericUnlockMessage(requestError, 'password'))
      }
    } finally {
      setPending(false)
    }
  }

  async function logout() {
    setPending(true)
    try {
      await requestJson('/auth/logout', { method: 'POST' })
    } catch {
      // Local presentation cleanup is required even if logout persistence fails.
    } finally {
      clearAuthPresentation()
      accessLockCoordinator.notifyFullLoginRequired()
      navigate('/login', { replace: true })
      setPending(false)
    }
  }

  const title = permanent ? 'MPIN locked' : unavailable ? 'Unlock temporarily unavailable' : 'Digi_TransX is locked'
  const description = permanent
    ? 'Your MPIN is permanently locked. Verify your password to unlock, then reset the MPIN in Security settings.'
    : unavailable
      ? 'We could not confirm MPIN status. You can retry or unlock with your password.'
      : 'Your signed-in session is still valid. Unlock access to continue.'

  return (
    <div className="access-lock" role="presentation">
      <section
        ref={dialogRef}
        className="access-lock__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="access-lock-title"
        aria-describedby="access-lock-description"
        onKeyDown={trapFocus}
      >
        <div className="access-lock__icon" aria-hidden="true"><i className="fas fa-lock" /></div>
        <h1 id="access-lock-title" ref={headingRef} tabIndex={-1}>{title}</h1>
        <p id="access-lock-description">{description}</p>

        {mpinAvailable ? (
          <form onSubmit={submitMpin} className="access-lock__form">
            <MpinInput ref={mpinRef} value={mpin} onChange={setMpin} disabled={pending} errorId={error ? 'access-lock-error' : undefined} />
            {error && <p id="access-lock-error" className="security-message is-error" role="alert">{error}</p>}
            <button className="security-primary" type="submit" disabled={pending || mpin.length !== 4}>
              {pending ? 'Unlocking…' : 'Unlock'}
            </button>
            <button className="security-link" type="button" disabled={pending} onClick={() => { setMode('password'); setError(''); setMpin('') }}>
              Unlock with password
            </button>
          </form>
        ) : (
          <form onSubmit={submitPassword} className="access-lock__form">
            {!unavailable && <p className="access-lock__account">Unlocking the current signed-in account</p>}
            <label className="security-field" htmlFor="access-unlock-password">
              <span>Password</span>
              <input
                id="access-unlock-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={pending}
              />
            </label>
            {error && <p id="access-lock-error" className="security-message is-error" role="alert">{error}</p>}
            <button className="security-primary" type="submit" disabled={pending || !password}>
              {pending ? 'Verifying…' : 'Unlock with password'}
            </button>
            {state === ACCESS_STATES.LOCKED_PASSWORD_REQUIRED && !permanent && (
              <p className="access-lock__note">MPIN is not available for this account.</p>
            )}
            {state === ACCESS_STATES.LOCKED_MPIN_AVAILABLE && (
              <button className="security-link" type="button" disabled={pending} onClick={() => { setMode('mpin'); setError(''); setPassword('') }}>
                Use MPIN instead
              </button>
            )}
          </form>
        )}

        {unavailable && (
          <button className="security-secondary" type="button" disabled={pending} onClick={() => onRefresh()}>
            Retry status check
          </button>
        )}
        <button className="security-logout" type="button" disabled={pending} onClick={logout}>
          <i className="fas fa-sign-out-alt" aria-hidden="true" /> Log out
        </button>
      </section>
    </div>
  )
}

export default function AccessLockProvider({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [state, setState] = useState(ACCESS_STATES.CHECKING)
  const [user, setUser] = useState(null)
  const gate = useRef(createLatestRequestGate())
  const controller = useRef(null)

  const requireFullLogin = useCallback((returnPath = location.pathname) => {
    controller.current?.abort()
    gate.current.invalidate()
    setState(ACCESS_STATES.FULL_LOGIN_REQUIRED)
    setUser(null)
    clearAuthPresentation()
    const safePath = safeRelativePath(returnPath)
    if (!isPublicAuthPath(location.pathname)) {
      navigate('/login', { replace: true, state: { returnPath: safePath } })
    }
  }, [location.pathname, navigate])

  const refreshAuthority = useCallback(async () => {
    controller.current?.abort()
    const requestController = new AbortController()
    controller.current = requestController
    const revision = gate.current.begin()
    try {
      const auth = await requestJson('/auth/me', { signal: requestController.signal })
      if (!gate.current.isCurrent(revision)) return
      setUser(auth.user)
      cacheAuthPresentation(auth)
      if (!auth.access_locked) {
        setState(ACCESS_STATES.UNLOCKED)
        await accessLockCoordinator.markUnlocked()
        return
      }
      try {
        const status = await requestJson('/auth/mpin/status', { signal: requestController.signal })
        if (!gate.current.isCurrent(revision)) return
        setState(deriveAccessState({ authenticated: true, accessLocked: true, mpinStatus: status.mpin }))
      } catch (error) {
        if (!gate.current.isCurrent(revision) || error?.name === 'AbortError') return
        if (error?.status === 401) requireFullLogin()
        else setState(deriveAccessState({ authenticated: true, accessLocked: true, statusUnavailable: true }))
      }
    } catch (error) {
      if (!gate.current.isCurrent(revision) || error?.name === 'AbortError') return
      if (error?.status === 401) requireFullLogin()
      else if (isPublicAuthPath(location.pathname)) {
        setState(ACCESS_STATES.FULL_LOGIN_REQUIRED)
      } else {
        setState((current) => current === ACCESS_STATES.UNLOCKED ? current : ACCESS_STATES.TEMPORARILY_UNAVAILABLE)
      }
    }
  }, [location.pathname, requireFullLogin])

  useEffect(() => {
    const timer = window.setTimeout(refreshAuthority, 0)
    return () => {
      window.clearTimeout(timer)
      controller.current?.abort()
    }
  }, [refreshAuthority])

  useEffect(() => accessLockCoordinator.subscribe((event) => {
    if (event.type === 'access_locked') refreshAuthority()
    if (event.type === 'full_login_required') requireFullLogin(event.returnPath)
  }), [refreshAuthority, requireFullLogin])

  const blocked = [
    ACCESS_STATES.CHECKING,
    ACCESS_STATES.LOCKED_MPIN_AVAILABLE,
    ACCESS_STATES.LOCKED_PASSWORD_REQUIRED,
    ACCESS_STATES.MPIN_PERMANENTLY_LOCKED,
    ACCESS_STATES.TEMPORARILY_UNAVAILABLE,
  ].includes(state)

  const value = useMemo(() => ({ state, user, refreshAuthority }), [state, user, refreshAuthority])

  return (
    <AccessLockContext.Provider value={value}>
      <div className="access-lock__application" inert={blocked ? true : undefined} aria-hidden={blocked ? 'true' : undefined}>
        {children}
      </div>
      {state === ACCESS_STATES.CHECKING && (
        <div className="access-lock access-lock--checking" role="status" aria-live="polite">
          <div className="access-lock__checking-card">
            <span className="access-lock__spinner" aria-hidden="true" />
            <span>Checking secure access...</span>
          </div>
        </div>
      )}
      {blocked && state !== ACCESS_STATES.CHECKING && <AccessLockScreen key={state} state={state} user={user} onRefresh={refreshAuthority} />}
    </AccessLockContext.Provider>
  )
}
