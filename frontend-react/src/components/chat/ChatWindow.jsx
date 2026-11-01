import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'
import { formatDateTime, getCsrfToken, apiGet, apiSend } from '../../pages/client/clientUtils'
import '../../styles/components/chat-window.css'

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

const scrollPaneClass = '[scrollbar-width:thin] [scrollbar-color:#D1D5DB_transparent] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300'

export default function ChatWindow(props) {
  const { status, user } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <AccountChatWindow key={String(user.id)} {...props} currentUserId={user.id} />
}

function AccountChatWindow({ onUnreadChange, initialThreadId = null, heightClass = 'h-[calc(100vh-118px)]', currentUserId }) {
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [loadingThreads, setLoadingThreads] = useState(true)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const requestRef = useRef(0)
  const abortRef = useRef(null)
  const threadReadBusy = useRef(false)
  const ownerMounted = useRef(false), mutationsRef = useRef(new Set())
  useEffect(() => {
    ownerMounted.current = true
    const pending = mutationsRef.current
    return () => { ownerMounted.current = false; for (const controller of pending) controller.abort() }
  }, [])
  const fetchForOwner = useCallback(async (url, options) => {
    if (!ownerMounted.current) throw new DOMException('Sign-in changed.', 'AbortError')
    const controller = new AbortController()
    mutationsRef.current.add(controller)
    try { return await fetch(url, { ...options, signal: controller.signal }) }
    finally { mutationsRef.current.delete(controller) }
  }, [])
  const activeThread = useMemo(() => threads.find(thread => thread.id === activeThreadId) || null, [threads, activeThreadId])
  const visibleThreads = useMemo(() => {
    const query = searchTerm.trim().toLowerCase()
    return query ? threads.filter(thread => [thread.other_party_name, thread.order?.id, thread.order?.route_label,
      thread.order?.status, thread.last_message_preview].join(' ').toLowerCase().includes(query)) : threads
  }, [searchTerm, threads])
  const totalUnread = useMemo(() => threads.reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0), [threads])
  useEffect(() => { onUnreadChange?.(totalUnread) }, [onUnreadChange, totalUnread])

  const loadThreads = useCallback(async (preferredThreadId = null, { silent = false } = {}) => {
    if (silent && threadReadBusy.current) return
    threadReadBusy.current = true
    const requestId = ++requestRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const json = await apiGet('/api/chat/threads', { signal: controller.signal })
      if (requestId !== requestRef.current || controller.signal.aborted) return
      const nextThreads = Array.isArray(json.threads) ? json.threads : []
      setThreads(nextThreads)
      setError('')
      setActiveThreadId(current => {
        if (preferredThreadId && nextThreads.some(thread => thread.id === preferredThreadId)) return preferredThreadId
        if (current && nextThreads.some(thread => thread.id === current)) return current
        return nextThreads[0]?.id || null
      })
    } catch (loadError) {
      if (requestId === requestRef.current && !controller.signal.aborted && !silent) setError(loadError.message || 'Unable to load chats.')
    } finally {
      if (requestId === requestRef.current) threadReadBusy.current = false
      if (requestId === requestRef.current && !controller.signal.aborted) setLoadingThreads(false)
    }
  }, [])
  useEffect(() => {
    // Start an external request; state is committed only from its guarded response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadThreads(initialThreadId ? Number(initialThreadId) : null)
    return () => { abortRef.current?.abort() }
  }, [initialThreadId, loadThreads])
  useEffect(() => {
    if (loadingThreads) return undefined
    const timer = window.setInterval(() => { void loadThreads(null, { silent: true }) }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [loadingThreads, loadThreads])
  const refreshThreads = useCallback(() => loadThreads(null, { silent: true }), [loadThreads])
  const messagesLoaded = useCallback((threadId, incoming) => {
    setThreads(current => current.map(thread => thread.id === threadId ? {
      ...thread, unread_count: 0,
      last_message_at: incoming.length ? incoming[incoming.length - 1].created_at : thread.last_message_at,
    } : thread))
  }, [])
  return (
    <div className={`chat-window grid ${heightClass} min-h-0 overflow-hidden rounded-2xl bg-white shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.1)] lg:grid-cols-[34%_66%]`}>
      <section className="chat-sidebar flex min-h-0 flex-col border-gray-100 lg:border-r">
        <div className="chat-sidebar-header sticky top-0 z-10 flex-shrink-0 space-y-4 border-b border-gray-100 bg-white p-5">
          <div className="chat-title-row flex items-center justify-between gap-3">
            <h1 className="chat-title text-2xl font-bold text-[#111827]">Chats</h1>
            <span className="chat-count-pill rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
              {totalUnread || threads.length}
            </span>
          </div>
          <label className="chat-search flex min-h-11 items-center gap-3 rounded-lg border border-[#E5E7EB] bg-gray-50 px-3 text-[#6B7280]">
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

        {error && <p role="alert" className="px-5 py-2 text-sm text-red-700">{error}</p>}
        <div className={`chat-thread-list min-h-0 flex-1 overflow-y-auto ${scrollPaneClass}`}>
          {loadingThreads && <div className="chat-state-card m-5 rounded-lg bg-[#F3F4F6] px-4 py-5 text-sm text-[#6B7280]">Loading chats...</div>}
          {!loadingThreads && threads.length === 0 && (
            <div className="chat-state-card m-5 rounded-lg border border-dashed border-[#E5E7EB] bg-gray-50 px-4 py-8 text-center text-sm text-[#6B7280]">
              No chat threads yet. A thread is created automatically when a bid is placed.
            </div>
          )}
          {!loadingThreads && threads.length > 0 && visibleThreads.length === 0 && (
            <div className="chat-state-card m-5 rounded-lg bg-gray-50 px-4 py-8 text-center text-sm text-[#6B7280]">
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
                className={`chat-thread-item flex w-full items-start gap-3 border-b border-gray-100 px-5 py-4 text-left transition ${
                  active ? 'chat-thread-item--active bg-indigo-50/70' : 'bg-white hover:bg-gray-50'
                }`}
              >
                <span className="chat-avatar grid h-11 w-11 shrink-0 place-items-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                  {partyInitial(thread.other_party_name)}
                </span>
                <span className="chat-thread-content min-w-0 flex-1">
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="chat-thread-name block truncate text-sm font-semibold text-[#111827]">
                        {thread.other_party_name}
                        <span className="chat-order-id ml-2 font-medium text-[#6B7280]">#{thread.order.id}</span>
                      </span>
                      <span className="chat-route mt-1 block truncate text-sm text-[#6B7280]">{thread.order.route_label}</span>
                    </span>
                    <span className={`chat-order-status shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${orderStatusTone(status)}`}>
                      {status}
                    </span>
                  </span>
                  <span className="mt-2 flex items-center justify-between gap-3">
                    <span className="chat-preview truncate text-xs text-[#9CA3AF]">{thread.last_message_preview || 'No messages yet'}</span>
                    {thread.unread_count > 0 && (
                      <span className="chat-unread rounded-full bg-[#10B981] px-2 py-0.5 text-[11px] font-bold text-white">
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
      {activeThread ? <ThreadMessages key={activeThread.id} thread={activeThread} currentUserId={currentUserId}
        onMessagesLoaded={messagesLoaded} onRefreshThreads={refreshThreads} fetchForOwner={fetchForOwner} /> : (
        <section className="chat-main grid min-h-0 place-items-center bg-white px-6 py-10 text-center">
          <div><i className="far fa-comments text-6xl text-gray-300" aria-hidden="true"></i>
            <p className="mt-5 text-lg font-semibold text-gray-600">No messages yet.</p>
            <p className="mt-1 text-sm text-gray-400">Select a chat to start the conversation below.</p></div>
        </section>
      )}
    </div>
  )
}

function ThreadMessages({ thread, currentUserId, onMessagesLoaded, onRefreshThreads, fetchForOwner }) {
  const [messages, setMessages] = useState([])
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [sending, setSending] = useState(false)
  const [messageText, setMessageText] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [actingOnMessage, setActingOnMessage] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)
  const scopeRef = useRef(0)
  const mountedRef = useRef(false)
  const readRef = useRef(0)
  const abortRef = useRef(null)
  const messageReadBusy = useRef(false)
  const isCurrent = useCallback(scope => mountedRef.current && scope === scopeRef.current, [])

  const loadMessages = useCallback(async (threadId, afterId = null, { silent = false } = {}) => {
    if (threadId !== thread.id || !mountedRef.current) return
    if (silent && messageReadBusy.current) return
    messageReadBusy.current = true
    const scope = scopeRef.current, requestId = ++readRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    if (!silent) setLoadingMessages(true)
    try {
      const suffix = afterId ? `?after_id=${afterId}` : ''
      const json = await apiGet(`/api/chat/threads/${thread.id}/messages${suffix}`, { signal: controller.signal })
      if (!isCurrent(scope) || requestId !== readRef.current || controller.signal.aborted) return
      const incoming = Array.isArray(json.messages) ? json.messages : []
      setMessages(current => {
        if (!afterId) return incoming
        const known = new Set(current.map(item => item.id))
        const appended = incoming.filter(item => !known.has(item.id))
        return appended.length ? [...current, ...appended] : current
      })
      onMessagesLoaded(thread.id, incoming)
      setError('')
    } catch (loadError) {
      if (isCurrent(scope) && requestId === readRef.current && !controller.signal.aborted && !silent) setError(loadError.message || 'Unable to load messages.')
    } finally {
      if (requestId === readRef.current) messageReadBusy.current = false
      if (isCurrent(scope) && requestId === readRef.current && !controller.signal.aborted) setLoadingMessages(false)
    }
  }, [isCurrent, onMessagesLoaded, thread.id])
  useEffect(() => {
    mountedRef.current = true
    ++scopeRef.current
    // The keyed thread owns this request and ignores its result after cleanup.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMessages(thread.id)
    return () => {
      mountedRef.current = false; abortRef.current?.abort()
    }
  }, [thread.id, loadMessages])
  useEffect(() => {
    const timer = window.setInterval(() => {
      const hasPending = messages.some(message => message.message_type === 'media_request' && message.media_request_status === 'pending')
      void loadMessages(thread.id, hasPending ? null : messages[messages.length - 1]?.id || 0, { silent: true })
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [loadMessages, messages, thread.id])
  function appendMessage(message) {
    // A pre-mutation GET must not replace the newly confirmed response.
    ++readRef.current
    abortRef.current?.abort()
    messageReadBusy.current = false
    if (message) setMessages(current => current.some(item => item.id === message.id) ? current : [...current, message])
    setLoadingMessages(false)
  }
  async function sendTextMessage(event) {
    event.preventDefault()
    const content = messageText.trim(), scope = scopeRef.current
    if (!content || sending) return
    setSending(true); setNotice(''); setError('')
    try {
      const json = await apiSend(`/api/chat/threads/${thread.id}/messages`, { message_type: 'text', content }, 'POST',
        fetchForOwner)
      if (!isCurrent(scope)) return
      appendMessage(json.message); setMessageText('')
      await onRefreshThreads()
    } catch (sendError) {
      if (isCurrent(scope)) setError(sendError.message || 'Unable to send message.')
    } finally { if (isCurrent(scope)) setSending(false) }
  }
  async function sendMediaRequest() {
    const scope = scopeRef.current
    setActingOnMessage('request'); setNotice(''); setError('')
    try {
      const json = await apiSend(`/api/chat/threads/${thread.id}/messages`, { message_type: 'media_request', content: 'Can I send you a photo/video?' }, 'POST',
        fetchForOwner)
      if (!isCurrent(scope)) return
      appendMessage(json.message)
      await onRefreshThreads()
    } catch (requestError) {
      if (isCurrent(scope)) setError(requestError.message || 'Unable to request media permission.')
    } finally { if (isCurrent(scope)) setActingOnMessage('') }
  }
  async function respondToRequest(messageId, action) {
    const scope = scopeRef.current
    setActingOnMessage(`${action}:${messageId}`); setNotice(''); setError('')
    try {
      const json = await apiSend(`/api/chat/threads/${thread.id}/messages/${messageId}/respond-media-request`, { action }, 'POST',
        fetchForOwner)
      if (!isCurrent(scope)) return
      setNotice(json.message || 'Request updated.')
      await loadMessages(thread.id)
      if (isCurrent(scope)) await onRefreshThreads()
    } catch (actionError) {
      if (isCurrent(scope)) setError(actionError.message || 'Unable to update media request.')
    } finally { if (isCurrent(scope)) setActingOnMessage('') }
  }
  async function uploadMediaFile(event) {
    const input = event.target, file = input.files?.[0], scope = scopeRef.current
    if (!file) return
    setUploading(true); setNotice(''); setError('')
    try {
      const csrf = await getCsrfToken()
      const body = new FormData(); body.append('media', file)
      const response = await fetchForOwner(`/api/chat/threads/${thread.id}/messages/media`, {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf }, body,
      })
      const json = await response.json().catch(() => ({}))
      if (!isCurrent(scope)) return
      if (!response.ok || json.success === false) throw new Error(json.message || 'Unable to upload media.')
      appendMessage(json.message)
      await loadMessages(thread.id)
      if (isCurrent(scope)) await onRefreshThreads()
    } catch (uploadError) {
      if (isCurrent(scope)) setError(uploadError.message || 'Unable to upload media.')
    } finally { input.value = ''; if (isCurrent(scope)) setUploading(false) }
  }
  const approvedRequest = useMemo(() => messages.find(message => canSendMediaForApproval(message)), [messages])
  return <section className="chat-main flex min-h-0 flex-col bg-white">

            <div className="chat-main-header sticky top-0 z-10 flex-shrink-0 border-b border-gray-100 bg-white px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="chat-main-title text-lg font-bold text-[#111827]">{thread.other_party_name}</h2>
                  <p className="chat-main-subtitle mt-1 text-sm text-[#6B7280]">
                    Order #{thread.order.id} - {thread.order.route_label} - {thread.order.status}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    loadMessages(thread.id)
                    onRefreshThreads()
                  }}
                  className="chat-refresh-btn inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[#E5E7EB] bg-white text-[#6B7280] transition hover:bg-gray-50 hover:text-[#4F46E5]"
                  title="Refresh"
                >
                  <i className="fas fa-rotate-right text-sm" aria-hidden="true"></i>
                </button>
              </div>
            </div>

            <div className={`chat-messages min-h-0 flex-1 space-y-4 overflow-y-auto bg-[#F9FAFB] px-5 py-5 ${scrollPaneClass}`}>
              {loadingMessages && <div className="text-sm text-[#6B7280]">Loading conversation...</div>}
              {error && <div className="chat-alert chat-alert--error rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
              {notice && <div className="chat-alert chat-alert--success rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}
              {!loadingMessages && messages.length === 0 && (
                <div className="chat-empty grid min-h-full place-items-center text-center">
                  <div>
                    <i className="far fa-comments text-7xl text-gray-300" aria-hidden="true"></i>
                    <p className="mt-5 text-lg font-semibold text-gray-600">No messages yet.</p>
                    <p className="mt-1 text-sm text-gray-400">Start the conversation below.</p>
                  </div>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`chat-message-row flex ${message.is_own ? 'chat-message-row--own justify-end' : 'justify-start'}`}>
                  <div
                    className={`chat-bubble max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                      message.message_type === 'system'
                        ? 'chat-bubble--system bg-amber-50 text-amber-900'
                        : message.is_own
                          ? 'chat-bubble--own bg-[#4F46E5] text-white'
                          : 'chat-bubble--other bg-white text-[#111827]'
                    }`}
                  >
                    <div className="chat-bubble-sender mb-1 text-xs font-semibold opacity-80">
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

                    <div className={`chat-bubble-time mt-2 text-[11px] ${message.is_own && message.message_type !== 'system' ? 'text-indigo-100' : 'text-slate-400'}`}>
                      {formatDateTime(message.created_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="chat-composer-wrap flex-shrink-0 border-t border-gray-100 bg-white px-5 py-4">
              <input ref={fileInputRef} type="file" accept=".jpg,.jpeg,.png,.mp4,.mov" className="hidden" onChange={uploadMediaFile} />
              {approvedRequest && (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="chat-media-send mb-3 inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className={`fas ${uploading ? 'fa-spinner fa-spin' : 'fa-image'} mr-2`} aria-hidden="true"></i>
                  Send Photo/Video
                </button>
              )}
              <form className="chat-composer flex flex-col gap-3 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] p-2 sm:flex-row sm:items-center" onSubmit={sendTextMessage}>
                <button
                  type="button"
                  onClick={sendMediaRequest}
                  disabled={actingOnMessage === 'request'}
                  className="chat-request-btn inline-flex min-h-10 items-center justify-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-[#111827] transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
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
                  className="chat-input min-h-10 flex-1 border-0 bg-transparent px-3 py-2 text-sm text-[#111827] outline-none placeholder:text-[#6B7280]"
                />
                <button
                  type="submit"
                  disabled={sending || !messageText.trim()}
                  className="chat-send-btn inline-flex min-h-10 items-center justify-center rounded-lg bg-[#4F46E5] px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className={`fas ${sending ? 'fa-spinner fa-spin' : 'fa-paper-plane'} mr-2`} aria-hidden="true"></i>
                  Send
                </button>
              </form>
            </div>
  </section>
}
