import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiResponseError, requestJson } from '../../auth/api'
import { logoutCurrentSession } from '../../auth/logout'

function ManagedRow({ item, kind, onRevoke, onLogout, navigate, pending }) {
  const title = kind === 'session' ? 'Session' : 'Device'
  return (
    <li className="security-management__row">
      <div>
        <strong>{item.category_label}</strong>
        <span>Created {item.created_at || 'Unknown'}</span>
        <span>Last activity {item.last_activity_at || 'Unknown'}</span>
      </div>
      <div className="security-management__actions">
        {item.is_current ? (
          <>
            <span className="security-management__current">Current {title.toLowerCase()}</span>
            <button type="button" className="security-secondary" disabled={pending} onClick={() => onLogout(navigate)}>Log out</button>
          </>
        ) : (
          <button type="button" className="security-danger security-danger--small" disabled={pending} onClick={(event) => onRevoke(item, event.currentTarget)}>
            {pending ? 'Revoking...' : 'Revoke'}
          </button>
        )}
      </div>
    </li>
  )
}

export default function SessionDeviceManagement() {
  const navigate = useNavigate()
  const [data, setData] = useState({ sessions: [], trusted_devices: [] })
  const [state, setState] = useState('loading')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pendingRef, setPendingRef] = useState('')
  const mounted = useRef(false)
  const activeLoad = useRef(null)
  const activeAction = useRef(null)
  const feedbackRef = useRef(null)

  async function load({ preserveError = false } = {}) {
    activeLoad.current?.abort()
    const controller = new AbortController()
    activeLoad.current = controller
    try {
      const result = await requestJson('/auth/security/sessions', { signal: controller.signal })
      if (!mounted.current || controller.signal.aborted) return
      setData({ sessions: result.sessions || [], trusted_devices: result.trusted_devices || [] })
      setState('ready')
    } catch (requestError) {
      if (!mounted.current || controller.signal.aborted) return
      setState('error')
      setNotice('')
      const message = requestError.message || 'Unable to load active sessions and devices.'
      setError((previous) => preserveError && previous ? `${previous} ${message}` : message)
    } finally {
      if (activeLoad.current === controller) activeLoad.current = null
    }
  }

  function reload({ preserveError = false, preserveNotice = false } = {}) {
    setState('loading')
    if (!preserveError) setError('')
    if (!preserveNotice) setNotice('')
    return load({ preserveError })
  }

  useEffect(() => {
    mounted.current = true
    let disposed = false
    queueMicrotask(() => { if (!disposed) void load() })
    return () => {
      disposed = true
      mounted.current = false
      activeLoad.current?.abort()
      activeAction.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!pendingRef && state !== 'loading' && (error || notice)) feedbackRef.current?.focus()
  }, [error, notice, pendingRef, state])

  async function revoke(item, kind, trigger) {
    if (activeAction.current || !mounted.current) return
    const noun = kind === 'session' ? 'session' : 'trusted device'
    if (!window.confirm(`Revoke this ${noun}? This action cannot be undone.`)) {
      trigger?.focus()
      return
    }
    const controller = new AbortController()
    activeAction.current = controller
    const actionRef = `${kind}:${item.management_ref}`
    setPendingRef(actionRef)
    setNotice('')
    setError('')
    try {
      const endpoint = kind === 'session' ? 'sessions' : 'devices'
      await requestJson(`/auth/security/${endpoint}/${encodeURIComponent(item.management_ref)}`, { method: 'DELETE', signal: controller.signal })
      if (!mounted.current || controller.signal.aborted) return
      setNotice(`${noun[0].toUpperCase()}${noun.slice(1)} revoked.`)
      await reload({ preserveNotice: true })
    } catch (requestError) {
      if (!mounted.current || controller.signal.aborted) return
      if (requestError instanceof ApiResponseError && ['stale', 'not_found'].includes(requestError.code)) {
        setError('That item is no longer active. Refreshing the list.')
        await reload({ preserveError: true })
      } else {
        setError(requestError.message || `Unable to revoke this ${noun}.`)
      }
    } finally {
      if (activeAction.current === controller) activeAction.current = null
      if (mounted.current && !controller.signal.aborted) setPendingRef('')
    }
  }

  return (
    <section className="security-management" aria-labelledby="security-management-heading">
      <header>
        <p className="mpin-management__eyebrow">Account protection</p>
        <h2 id="security-management-heading">Active sessions and trusted devices</h2>
        <p>Review signed-in access using privacy-safe categories. Secrets and network details are never shown.</p>
      </header>
      {error && <p ref={feedbackRef} tabIndex="-1" className="security-message is-error" role="alert">{error}</p>}
      {notice && <p ref={feedbackRef} tabIndex="-1" className="security-message" role="status">{notice}</p>}
      {state === 'loading' && <p role="status">Loading active access...</p>}
      {state === 'ready' && (
        <div className="security-management__grid">
          <section aria-labelledby="active-sessions-heading">
            <h3 id="active-sessions-heading">Active Sessions</h3>
            {data.sessions.length ? <ul>{data.sessions.map((item) => <ManagedRow key={item.management_ref} item={item} kind="session" pending={Boolean(pendingRef)} onRevoke={(row, trigger) => void revoke(row, 'session', trigger)} onLogout={logoutCurrentSession} navigate={navigate} />)}</ul> : <p>No active sessions.</p>}
          </section>
          <section aria-labelledby="trusted-devices-heading">
            <h3 id="trusted-devices-heading">Trusted Devices</h3>
            {data.trusted_devices.length ? <ul>{data.trusted_devices.map((item) => <ManagedRow key={item.management_ref} item={item} kind="device" pending={Boolean(pendingRef)} onRevoke={(row, trigger) => void revoke(row, 'device', trigger)} onLogout={logoutCurrentSession} navigate={navigate} />)}</ul> : <p>No active trusted devices.</p>}
          </section>
        </div>
      )}
      {state === 'error' && <button type="button" className="security-secondary" onClick={() => void reload()}>Try again</button>}
    </section>
  )
}
