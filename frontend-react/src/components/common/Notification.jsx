import { useEffect } from 'react'

export default function Notification({ type = 'info', message, onClose }) {
  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(onClose, type === 'success' ? 5000 : 8000)
    return () => clearTimeout(timer)
  }, [message, type, onClose])

  if (!message) return null

  const icons = {
    success: 'fa-circle-check',
    error: 'fa-circle-exclamation',
    info: 'fa-circle-info',
  }

  return (
    <div className={`app-notification app-notification--${type}`} role="status">
      <i className={`fas ${icons[type] || icons.info}`} aria-hidden="true"></i>
      <span>{message}</span>
      <button type="button" onClick={onClose} aria-label="Close notification">
        <i className="fas fa-xmark" aria-hidden="true"></i>
      </button>
    </div>
  )
}
