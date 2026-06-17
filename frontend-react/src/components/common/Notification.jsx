import { useEffect } from 'react'

export default function Notification({ type, message, onClose }) {
  useEffect(() => {
    if (!message) return
    const timer = setTimeout(onClose, type === 'success' ? 5000 : 8000)
    return () => clearTimeout(timer)
  }, [message, type, onClose])

  if (!message) return null

  const colors = {
    success: 'border-green-500',
    error: 'border-red-500',
    info: 'border-blue-500'
  }

  const icons = { success: '✓', error: '✕', info: 'i' }

  return (
    <div className={`fixed top-5 right-5 z-50 bg-white rounded-lg shadow-xl border-l-4 ${colors[type] || colors.info} p-4 max-w-sm flex items-start gap-3`}>
      <span className="text-lg font-bold">{icons[type] || 'i'}</span>
      <span className="text-sm text-gray-700 flex-1">{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
    </div>
  )
}
