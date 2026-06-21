import { useEffect, useMemo, useRef, useState } from 'react'
import { formatDateTime, getCsrfToken, apiGet, apiSend } from '../../pages/client/clientUtils'

const POLL_INTERVAL_MS = 4000

function statusTone(status) {
  if (status === 'approved' || status === 'fulfilled') return 'text-emerald-700'
  if (status === 'denied') return 'text-red-700'
  return 'text-amber-700'
}

function canRespondToMediaRequest(message, currentUserId) {
  return message.message_type === 'media_request' && !message.is_own && message.media_request_status === 'pending' && message.sender_user_id !== currentUserId
}

function canSendMediaForApproval(message) {
  return message.message_type === 'media_request' && message.is_own && message.media_request_status === 'approved'
}

export default function ChatWindow({ role = 'client', onUnreadChange }) {
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
  const [currentUser, setCurrentUser] = useState(null)
  const fileInputRef = useRef(null)
  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) || null,
    [threads, activeThreadId],
  )

  useEffect(() => {
    const stored = sessionStorage.getItem('user')
    if (!stored) return
    try {
      setCurrentUser(JSON.parse(stored))
    } catch (_) {}
  }, [])

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
    loadThreads()
  }, [])

  useEffect(() => {
    if (!activeThreadId) {
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

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Chats</h2>
              <p className="mt-1 text-sm text-slate-500">Order-linked conversations for your {role} portal.</p>
            </div>
            {totalUnread > 0 && (
              <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">
                {totalUnread} unread
              </span>
            )}
          </div>
        </div>
        <div className="max-h-[70vh] overflow-y-auto p-3">
          {loadingThreads && <div className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-slate-500">Loading chats...</div>}
          {!loadingThreads && threads.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
              No chat threads yet. A thread is created automatically when a bid is placed.
            </div>
          )}
          {!loadingThreads && threads.map((thread) => {
            const active = thread.id === activeThreadId
            return (
              <button
                key={thread.id}
                type="button"
                onClick={() => setActiveThreadId(thread.id)}
                className={`mb-3 w-full rounded-2xl border px-4 py-4 text-left transition ${
                  active
                    ? 'border-blue-200 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-bold text-slate-900">{thread.other_party_name}</div>
                    <div className="mt-1 truncate text-xs text-slate-500">Order #{thread.order.id} - {thread.order.route_label}</div>
                  </div>
                  {thread.unread_count > 0 && (
                    <span className="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-bold text-emerald-700">
                      {thread.unread_count}
                    </span>
                  )}
                </div>
                <div className="mt-3 text-sm text-slate-600">{thread.last_message_preview}</div>
                <div className="mt-2 text-xs text-slate-400">{formatDateTime(thread.last_message_at)}</div>
              </button>
            )
          })}
        </div>
      </section>

      <section className="flex min-h-[70vh] flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
        {!activeThread && (
          <div className="grid flex-1 place-items-center px-6 py-10 text-center text-sm text-slate-500">
            Select a chat thread to start messaging.
          </div>
        )}

        {activeThread && (
          <>
            <div className="border-b border-slate-200 px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">{activeThread.other_party_name}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Order #{activeThread.order.id} - {activeThread.order.route_label} - {activeThread.order.status}
                  </p>
                </div>
                {approvedRequest && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <i className={`fas ${uploading ? 'fa-spinner fa-spin' : 'fa-image'} mr-2`} aria-hidden="true"></i>
                    Send Photo/Video
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 px-5 py-5">
              {loadingMessages && <div className="text-sm text-slate-500">Loading conversation...</div>}
              {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
              {notice && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}
              {!loadingMessages && messages.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
                  No messages yet. Start the conversation below.
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.is_own ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                      message.message_type === 'system'
                        ? 'bg-amber-50 text-amber-900'
                        : message.is_own
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-slate-900'
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

                    <div className={`mt-2 text-[11px] ${message.is_own && message.message_type !== 'system' ? 'text-blue-100' : 'text-slate-400'}`}>
                      {formatDateTime(message.created_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-200 px-5 py-4">
              <input ref={fileInputRef} type="file" accept=".jpg,.jpeg,.png,.mp4,.mov" className="hidden" onChange={uploadMediaFile} />
              <div className="mb-3 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={sendMediaRequest}
                  disabled={actingOnMessage === 'request'}
                  className="inline-flex min-h-10 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className={`fas ${actingOnMessage === 'request' ? 'fa-spinner fa-spin' : 'fa-camera'} mr-2`} aria-hidden="true"></i>
                  Request Photo/Video
                </button>
              </div>
              <form className="flex flex-col gap-3 sm:flex-row" onSubmit={sendTextMessage}>
                <textarea
                  value={messageText}
                  onChange={(event) => setMessageText(event.target.value)}
                  placeholder="Type your message..."
                  maxLength={2000}
                  rows={3}
                  className="min-h-[52px] flex-1 rounded-xl border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-blue-500"
                />
                <button
                  type="submit"
                  disabled={sending || !messageText.trim()}
                  className="inline-flex min-h-[52px] items-center justify-center rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
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
