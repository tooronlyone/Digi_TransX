import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiResponseError, requestJson } from '../../auth/api'
import { logoutCurrentSession } from '../../auth/logout'

function ManagedRow({ item, kind, onRevoke, onLogout, navigate }) {
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
            {kind === 'session' && <button type="button" className="security-secondary" onClick={() => onLogout(navigate)}>Log out</button>}
          </>
        ) : (
          <button type="button" className="security-danger security-danger--small" onClick={() => onRevoke(item)}>
            Revoke
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

  async function load() {
    setState('loading')
    setError('')
    try {
      const result = await requestJson('/auth/security/sessions')
      setData({ sessions: result.sessions || [], trusted_devices: result.trusted_devices || [] })
      setState('ready')
    } catch (requestError) {
      setState('error')
      setError(requestError.message || 'Unable to load active sessions and devices.')
    }
  }

  useEffect(() => { void Promise.resolve().then(() => load()) }, [])

  async function revoke(item, kind) {
    const noun = kind === 'session' ? 'session' : 'trusted device'
    if (!window.confirm(`Revoke this ${noun}? This action cannot be undone.`)) return
    setNotice('')
    try {
      const endpoint = kind === 'session' ? 'sessions' : 'devices'
      await requestJson(`/auth/security/${endpoint}/${encodeURIComponent(item.management_ref)}`, { method: 'DELETE' })
      setNotice(`${noun[0].toUpperCase()}${noun.slice(1)} revoked.`)
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiResponseError && ['stale', 'not_found'].includes(requestError.code)) {
        setError('That item is no longer active. Refreshing the list.')
        await load()
      } else {
        setError(requestError.message || `Unable to revoke this ${noun}.`)
      }
    }
  }

  return (
    <section className="security-management" aria-labelledby="security-management-heading">
      <header>
        <p className="mpin-management__eyebrow">Account protection</p>
        <h2 id="security-management-heading">Active sessions and trusted devices</h2>
        <p>Review signed-in access using privacy-safe categories. Secrets and network details are never shown.</p>
      </header>
      {error && <p className="security-message is-error" role="alert">{error}</p>}
      {notice && <p className="security-message" role="status">{notice}</p>}
      {state === 'loading' && <p role="status">Loading active access…</p>}
      {state === 'ready' && (
        <div className="security-management__grid">
          <section aria-labelledby="active-sessions-heading">
            <h3 id="active-sessions-heading">Active Sessions</h3>
            {data.sessions.length ? <ul>{data.sessions.map((item) => <ManagedRow key={item.management_ref} item={item} kind="session" onRevoke={(row) => void revoke(row, 'session')} onLogout={logoutCurrentSession} navigate={navigate} />)}</ul> : <p>No active sessions.</p>}
          </section>
          <section aria-labelledby="trusted-devices-heading">
            <h3 id="trusted-devices-heading">Trusted Devices</h3>
            {data.trusted_devices.length ? <ul>{data.trusted_devices.map((item) => <ManagedRow key={item.management_ref} item={item} kind="device" onRevoke={(row) => void revoke(row, 'device')} navigate={navigate} />)}</ul> : <p>No active trusted devices.</p>}
          </section>
        </div>
      )}
      {state === 'error' && <button type="button" className="security-secondary" onClick={() => void load()}>Try again</button>}
    </section>
  )
}
