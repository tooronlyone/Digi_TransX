import { useEffect, useMemo, useRef, useState } from 'react'
import { formatDateTime, getCsrfToken, apiGet, apiSend } from '../../pages/client/clientUtils'

const POLL_INTERVAL_MS = 4000

function statusTone(status) {
  if (status === 'approved' || status === 'fulfilled') return 'text-emerald-700'
  if (status === 'denied') return 'text-red-700'
  return 'text-amber-700'
}

function orderStatusTone(status = '') {
  const normalized = String(status).toLowerCase()
  if (normalized.includes('active') || normalized.includes('approved') || normalized.includes('assigned')) {
    return 'bg-emerald-50 text-emerald-700'
  }
  if (normalized.includes('cancel') || normalized.includes('reject') || normalized.includes('inactive')) {
    return 'bg-red-50 text-red-700'
  }
  return 'bg-gray-100 text-gray-500'
}

function partyInitial(name = '') {
  return String(name).trim().charAt(0).toUpperCase() || 'C'
}

function canRespondToMediaRequest(message, currentUserId) {
  return message.message_type === 'media_request' && !message.is_own && message.media_request_status === 'pending' && message.sender_user_id !== currentUserId
}

function canSendMediaForApproval(message) {
  return message.message_type === 'media_request' && message.is_own && message.media_request_status === 'approved'
}

export default function ChatWindow({ role = 'client', onUnreadChange, initialThreadId = null, heightClass = 'h-[calc(100vh-118px)]' }) {
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [messages, setMessages] = useState([])
  const [loadingThreads, setLoadingThreads] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [messageText, setMessageText] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [actingOnMessage, setActingOnMessage] = useState('')
  const [uploading, setUploading] = useState(false)
  const [currentUser] = useState(() => {
    const stored = sessionStorage.getItem('user')
    if (!stored) return null
    try {
      return JSON.parse(stored)
    } catch {
      return null
    }
  })
  const [searchTerm, setSearchTerm] = useState('')
  const fileInputRef = useRef(null)
  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) || null,
    [threads, activeThreadId],
  )
  const visibleThreads = useMemo(() => {
    const query = searchTerm.trim().toLowerCase()
    if (!query) return threads
    return threads.filter((thread) => {
      const haystack = [
        thread.other_party_name,
        thread.order?.id,
        thread.order?.route_label,
        thread.order?.status,
        thread.last_message_preview,
      ].join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }, [searchTerm, threads])

  const currentUserId = currentUser?.id ?? null
  const totalUnread = useMemo(
    () => threads.reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0),
    [threads],
  )

  useEffect(() => {
    onUnreadChange?.(totalUnread)
  }, [onUnreadChange, totalUnread])

  async function loadThreads(preferredThreadId = null, { silent = false } = {}) {
    if (!silent) setLoadingThreads(true)
    try {
      const json = await apiGet('/api/chat/threads')
      const nextThreads = json.threads || []
      setThreads(nextThreads)
      setError('')
      setActiveThreadId((current) => {
        if (preferredThreadId && nextThreads.some((thread) => thread.id === preferredThreadId)) return preferredThreadId
        if (current && nextThreads.some((thread) => thread.id === current)) return current
        return nextThreads[0]?.id || null
      })
    } catch (loadError) {
      setError(loadError.message || 'Unable to load chats.')
    } finally {
      if (!silent) setLoadingThreads(false)
    }
  }

  async function loadMessages(threadId, afterId = null, { silent = false } = {}) {
    if (!threadId) return
    if (!silent) setLoadingMessages(true)
    try {
      const suffix = afterId ? `?after_id=${afterId}` : ''
      const json = await apiGet(`/api/chat/threads/${threadId}/messages${suffix}`)
      const incoming = json.messages || []
      setMessages((current) => {
        if (!afterId) return incoming
        if (!incoming.length) return current
        const knownIds = new Set(current.map((item) => item.id))
        const appended = incoming.filter((item) => !knownIds.has(item.id))
        return appended.length ? [...current, ...appended] : current
      })
      setThreads((current) => current.map((thread) => (
        thread.id === threadId
          ? {
              ...thread,
              unread_count: 0,
              last_message_at: incoming.length ? incoming[incoming.length - 1].created_at : thread.last_message_at,
            }
          : thread
      )))
      setError('')
    } catch (loadError) {
      if (!silent) setError(loadError.message || 'Unable to load messages.')
    } finally {
      if (!silent) setLoadingMessages(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadThreads(initialThreadId ? Number(initialThreadId) : null)
  }, [initialThreadId])

  useEffect(() => {
    if (!activeThreadId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([])
      return
    }
    loadMessages(activeThreadId)
  }, [activeThreadId])

  useEffect(() => {
    if (!activeThreadId) return undefined
    const intervalId = window.setInterval(() => {
      const lastId = messages[messages.length - 1]?.id || 0
      loadMessages(activeThreadId, lastId, { silent: true })
      loadThreads(activeThreadId, { silent: true })
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(intervalId)
  }, [activeThreadId, messages, role])

  async function sendTextMessage(event) {
    event.preventDefault()
    const content = messageText.trim()
    if (!activeThreadId || !content) return

    setSending(true)
    setNotice('')
    try {
      const json = await apiSend(`/api/chat/threads/${activeThreadId}/messages`, {
        message_type: 'text',
        content,
      })
      setMessages((current) => [...current, json.message])
      setMessageText('')
      await loadThreads(activeThreadId, { silent: true })
    } catch (sendError) {
      setError(sendError.message || 'Unable to send message.')
    } finally {
      setSending(false)
    }
  }

  async function sendMediaRequest() {
    if (!activeThreadId) return
    setActingOnMessage('request')
    setNotice('')
    try {
      const json = await apiSend(`/api/chat/threads/${activeThreadId}/messages`, {
        message_type: 'media_request',
        content: 'Can I send you a photo/video?',
      })
      setMessages((current) => [...current, json.message])
      await loadThreads(activeThreadId, { silent: true })
    } catch (requestError) {
      setError(requestError.message || 'Unable to request media permission.')
    } finally {
      setActingOnMessage('')
    }
  }

  async function respondToRequest(messageId, action) {
    if (!activeThreadId) return
    setActingOnMessage(`${action}:${messageId}`)
    setNotice('')
    try {
      const json = await apiSend(`/api/chat/threads/${activeThreadId}/messages/${messageId}/respond-media-request`, { action })
      setNotice(json.message || 'Request updated.')
      await loadMessages(activeThreadId)
      await loadThreads(activeThreadId, { silent: true })
    } catch (actionError) {
      setError(actionError.message || 'Unable to update media request.')
    } finally {
      setActingOnMessage('')
    }
  }

  async function uploadMediaFile(event) {
    const file = event.target.files?.[0]
    if (!file || !activeThreadId) return

    setUploading(true)
    setNotice('')
    try {
      const csrf = await getCsrfToken()
      const formData = new FormData()
      formData.append('media', file)
      const response = await fetch(`/api/chat/threads/${activeThreadId}/messages/media`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf },
        body: formData,
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) {
        throw new Error(json.message || 'Unable to upload media.')
      }
      setMessages((current) => [...current, json.message])
      await loadThreads(activeThreadId, { silent: true })
      await loadMessages(activeThreadId)
    } catch (uploadError) {
      setError(uploadError.message || 'Unable to upload media.')
    } finally {
      event.target.value = ''
      setUploading(false)
    }
  }

  const approvedRequest = useMemo(
    () => messages.find((message) => canSendMediaForApproval(message)),
    [messages],
  )

  const scrollPaneClass = '[scrollbar-width:thin] [scrollbar-color:#D1D5DB_transparent] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300'

  return (
    <div className={`grid ${heightClass} min-h-0 overflow-hidden rounded-2xl bg-white shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)] lg:grid-cols-[34%_66%]`}>
      <section className="flex min-h-0 flex-col border-gray-100 lg:border-r">
        <div className="sticky top-0 z-10 flex-shrink-0 space-y-4 border-b border-gray-100 bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-2xl font-bold text-[#111827]">Chats</h1>
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
              {totalUnread || threads.length}
            </span>
          </div>
          <label className="flex min-h-11 items-center gap-3 rounded-lg border border-[#E5E7EB] bg-gray-50 px-3 text-[#6B7280]">
            <i className="fas fa-search text-sm" aria-hidden="true"></i>
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search chats..."
              className="h-full min-w-0 flex-1 border-0 bg-transparent text-sm text-[#111827] outline-none placeholder:text-[#6B7280]"
            />
          </label>
        </div>

        <div className={`min-h-0 flex-1 overflow-y-auto ${scrollPaneClass}`}>
          {loadingThreads && <div className="m-5 rounded-lg bg-[#F3F4F6] px-4 py-5 text-sm text-[#6B7280]">Loading chats...</div>}
          {!loadingThreads && threads.length === 0 && (
            <div className="m-5 rounded-lg border border-dashed border-[#E5E7EB] bg-gray-50 px-4 py-8 text-center text-sm text-[#6B7280]">
              No chat threads yet. A thread is created automatically when a bid is placed.
            </div>
          )}
          {!loadingThreads && threads.length > 0 && visibleThreads.length === 0 && (
            <div className="m-5 rounded-lg bg-gray-50 px-4 py-8 text-center text-sm text-[#6B7280]">
              No chats match your search.
            </div>
          )}
          {!loadingThreads && visibleThreads.map((thread) => {
            const active = thread.id === activeThreadId
            const status = thread.order?.status || 'Inactive'
            return (
              <button
                key={thread.id}
                type="button"
                onClick={() => setActiveThreadId(thread.id)}
                className={`flex w-full items-start gap-3 border-b border-gray-100 px-5 py-4 text-left transition ${
                  active ? 'bg-indigo-50/70' : 'bg-white hover:bg-gray-50'
                }`}
              >
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                  {partyInitial(thread.other_party_name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-[#111827]">
                        {thread.other_party_name}
                        <span className="ml-2 font-medium text-[#6B7280]">#{thread.order.id}</span>
                      </span>
                      <span className="mt-1 block truncate text-sm text-[#6B7280]">{thread.order.route_label}</span>
                    </span>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${orderStatusTone(status)}`}>
                      {status}
                    </span>
                  </span>
                  <span className="mt-2 flex items-center justify-between gap-3">
                    <span className="truncate text-xs text-[#9CA3AF]">{thread.last_message_preview || 'No messages yet'}</span>
                    {thread.unread_count > 0 && (
                      <span className="rounded-full bg-[#10B981] px-2 py-0.5 text-[11px] font-bold text-white">
                        {thread.unread_count}
                      </span>
                    )}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="flex min-h-0 flex-col bg-white">
        {!activeThread && (
          <div className="grid min-h-0 flex-1 place-items-center px-6 py-10 text-center">
            <div>
              <i className="far fa-comments text-6xl text-gray-300" aria-hidden="true"></i>
              <p className="mt-5 text-lg font-semibold text-gray-600">No messages yet.</p>
              <p className="mt-1 text-sm text-gray-400">Select a chat to start the conversation below.</p>
            </div>
          </div>
        )}

        {activeThread && (
          <>
            <div className="sticky top-0 z-10 flex-shrink-0 border-b border-gray-100 bg-white px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-[#111827]">{activeThread.other_party_name}</h2>
                  <p className="mt-1 text-sm text-[#6B7280]">
                    Order #{activeThread.order.id} - {activeThread.order.route_label} - {activeThread.order.status}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    loadMessages(activeThread.id)
                    loadThreads(activeThread.id, { silent: true })
                  }}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[#E5E7EB] bg-white text-[#6B7280] transition hover:bg-gray-50 hover:text-[#4F46E5]"
                  title="Refresh"
                >
                  <i className="fas fa-rotate-right text-sm" aria-hidden="true"></i>
                </button>
              </div>
            </div>

            <div className={`min-h-0 flex-1 space-y-4 overflow-y-auto bg-[#F9FAFB] px-5 py-5 ${scrollPaneClass}`}>
              {loadingMessages && <div className="text-sm text-[#6B7280]">Loading conversation...</div>}
              {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
              {notice && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}
              {!loadingMessages && messages.length === 0 && (
                <div className="grid min-h-full place-items-center text-center">
                  <div>
                    <i className="far fa-comments text-7xl text-gray-300" aria-hidden="true"></i>
                    <p className="mt-5 text-lg font-semibold text-gray-600">No messages yet.</p>
                    <p className="mt-1 text-sm text-gray-400">Start the conversation below.</p>
                  </div>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.is_own ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                      message.message_type === 'system'
                        ? 'bg-amber-50 text-amber-900'
                        : message.is_own
                          ? 'bg-[#4F46E5] text-white'
                          : 'bg-white text-[#111827]'
                    }`}
                  >
                    <div className="mb-1 text-xs font-semibold opacity-80">
                      {message.message_type === 'system' ? 'System' : message.sender_name}
                    </div>

                    {(message.message_type === 'text' || message.message_type === 'media_request' || message.message_type === 'system') && (
                      <div className="whitespace-pre-wrap break-words text-sm">{message.content || (message.message_type === 'media_request' ? 'Media request' : '')}</div>
                    )}

                    {message.message_type === 'media' && message.media_kind === 'image' && (
                      <img src={message.media_path} alt="Chat media" className="max-h-72 rounded-xl object-cover" />
                    )}
                    {message.message_type === 'media' && message.media_kind === 'video' && (
                      <video src={message.media_path} controls className="max-h-72 rounded-xl" />
                    )}

                    {message.message_type === 'media_request' && (
                      <div className={`mt-2 text-xs font-semibold ${message.is_own ? 'text-blue-100' : statusTone(message.media_request_status)}`}>
                        Status: {message.media_request_status || 'pending'}
                      </div>
                    )}

                    {canRespondToMediaRequest(message, currentUserId) && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => respondToRequest(message.id, 'approve')}
                          disabled={actingOnMessage === `approve:${message.id}` || actingOnMessage === `deny:${message.id}`}
                          className="inline-flex min-h-9 items-center justify-center rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => respondToRequest(message.id, 'deny')}
                          disabled={actingOnMessage === `approve:${message.id}` || actingOnMessage === `deny:${message.id}`}
                          className="inline-flex min-h-9 items-center justify-center rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Deny
                        </button>
                      </div>
                    )}

                    <div className={`mt-2 text-[11px] ${message.is_own && message.message_type !== 'system' ? 'text-indigo-100' : 'text-slate-400'}`}>
                      {formatDateTime(message.created_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex-shrink-0 border-t border-gray-100 bg-white px-5 py-4">
              <input ref={fileInputRef} type="file" accept=".jpg,.jpeg,.png,.mp4,.mov" className="hidden" onChange={uploadMediaFile} />
              {approvedRequest && (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="mb-3 inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className={`fas ${uploading ? 'fa-spinner fa-spin' : 'fa-image'} mr-2`} aria-hidden="true"></i>
                  Send Photo/Video
                </button>
              )}
              <form className="flex flex-col gap-3 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] p-2 sm:flex-row sm:items-center" onSubmit={sendTextMessage}>
                <button
                  type="button"
                  onClick={sendMediaRequest}
                  disabled={actingOnMessage === 'request'}
                  className="inline-flex min-h-10 items-center justify-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-[#111827] transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                  title="Request Photo/Video"
                >
                  <i className={`fas ${actingOnMessage === 'request' ? 'fa-spinner fa-spin' : 'fa-camera'} mr-2 text-[#6B7280]`} aria-hidden="true"></i>
                  Request Photo/Video
                </button>
                <input
                  value={messageText}
                  onChange={(event) => setMessageText(event.target.value)}
                  placeholder="Type your message..."
                  maxLength={2000}
                  className="min-h-10 flex-1 border-0 bg-transparent px-3 py-2 text-sm text-[#111827] outline-none placeholder:text-[#6B7280]"
                />
                <button
                  type="submit"
                  disabled={sending || !messageText.trim()}
                  className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[#4F46E5] px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className={`fas ${sending ? 'fa-spinner fa-spin' : 'fa-paper-plane'} mr-2`} aria-hidden="true"></i>
                  Send
                </button>
              </form>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
