import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../../styles/ai-chat.css'
import {
  AI_API_BASE,
  createAssistantConversation,
  createAssistantMessage,
  detectUserRole,
  dispatchTruckUpdate,
  formatAssistantTime,
  humanMessageStatus,
  loadAssistantConversations,
  normalizeLanguage,
  roleLabel,
  saveAssistantConversations,
  serializeConversationHistory,
  syncSessionRoleFromBackend,
  truncate,
} from '../../lib/aiAssistant'

function currentConversationPreview(conversation) {
  const last = conversation.messages.length ? conversation.messages[conversation.messages.length - 1] : null
  if (!last) return 'No messages yet.'
  return truncate(last.text, 72)
}

function chatContext(language, history, conversationId, userRole) {
  return {
    route: '/ai-chat',
    pageName: 'ai_chat',
    pageLabel: 'AI Chat',
    pageTitle: 'AI Chat',
    currentPage: 'ai_chat',
    userRole,
    availableActions: ['general_chat', 'assistant_actions', 'navigation'],
    pagePurpose: 'Dedicated assistant chat page for questions and in-app actions.',
    languagePreference: normalizeLanguage(language),
    history,
    conversationId: String(conversationId || ''),
  }
}

export default function AiChat() {
  const navigate = useNavigate()
  const messagesRef = useRef(null)
  const [conversations, setConversations] = useState(() => loadAssistantConversations())
  const [currentId, setCurrentId] = useState('')
  const [search, setSearch] = useState('')
  const [composer, setComposer] = useState('')
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState('Ready.')
  const [modelLabel, setModelLabel] = useState('Local model')
  const [userRole, setUserRole] = useState(() => detectUserRole())
  const homeRoute =
    userRole === 'transporter'
      ? '/transporter/dashboard'
      : userRole === 'admin'
        ? '/admin/dashboard'
        : '/login'

  const currentConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === currentId) || null,
    [conversations, currentId],
  )

  const filteredConversations = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return [...conversations]
      .sort((left, right) => right.updatedAt - left.updatedAt)
      .filter((conversation) => {
        if (!needle) return true
        const haystack = `${conversation.title} ${currentConversationPreview(conversation)}`.toLowerCase()
        return haystack.includes(needle)
      })
  }, [conversations, search])

  useEffect(() => {
    if (!conversations.length) {
      const initial = createAssistantConversation()
      setConversations([initial])
      setCurrentId(initial.id)
      return
    }
    if (!currentId || !conversations.some((conversation) => conversation.id === currentId)) {
      const latest = [...conversations].sort((left, right) => right.updatedAt - left.updatedAt)[0]
      setCurrentId(latest.id)
    }
  }, [conversations, currentId])

  useEffect(() => {
    saveAssistantConversations(conversations)
  }, [conversations])

  useEffect(() => {
    let active = true

    async function bootstrap() {
      const nextRole = await syncSessionRoleFromBackend()
      if (!active) return
      setUserRole(nextRole)
    }

    async function loadCapabilities() {
      try {
        const response = await fetch(`${AI_API_BASE}/capabilities`, {
          method: 'GET',
          credentials: 'include',
        })
        const payload = await response.json()
        if (!active) return
        if (response.ok && payload?.success && payload.capabilities) {
          if (payload.capabilities.offline_chat_available) {
            setModelLabel('Local Ollama ready')
          }
        }
      } catch {
        // no-op
      }
    }

    bootstrap()
    loadCapabilities()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!currentConversation) return
    document.title = `${currentConversation.title || 'AI Chat'} - Digi_TransX`
  }, [currentConversation])

  useEffect(() => {
    if (!messagesRef.current) return
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight
  }, [currentConversation?.messages])

  function updateCurrentConversation(updater) {
    setConversations((current) =>
      current.map((conversation) => {
        if (conversation.id !== currentId) return conversation
        return updater({ ...conversation, messages: [...conversation.messages] })
      }),
    )
  }

  function createAndSelectConversation() {
    const next = createAssistantConversation(currentConversation?.language || 'en')
    setConversations((current) => [next, ...current])
    setCurrentId(next.id)
    setComposer('')
    setStatus('Ready.')
  }

  function clearCurrentConversation() {
    if (!currentConversation) return
    updateCurrentConversation((conversation) => ({
      ...conversation,
      title: 'New chat',
      updatedAt: Date.now(),
      messages: [],
    }))
    setStatus('Current conversation cleared.')
  }

  async function sendMessage(event) {
    if (event) event.preventDefault()
    if (sending || !currentConversation) return

    const text = String(composer || '').trim()
    if (!text) {
      setStatus('Type a message first.')
      return
    }

    const language = normalizeLanguage(currentConversation.language)
    const userMessage = createAssistantMessage({ role: 'user', text, status: 'sent' })
    const placeholder = createAssistantMessage({
      role: 'assistant',
      text: 'Thinking with local AI...',
      status: 'Seen',
      pending: true,
    })
    const priorHistory = serializeConversationHistory(currentConversation.messages)

    setComposer('')
    setSending(true)
    setStatus('Sending to assistant...')

    updateCurrentConversation((conversation) => ({
      ...conversation,
      title: conversation.title === 'New chat' ? truncate(text, 42) || 'New chat' : conversation.title,
      language,
      updatedAt: Date.now(),
      messages: [...conversation.messages, userMessage, placeholder],
    }))

    try {
      const response = await fetch(`${AI_API_BASE}/interpret`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript: text,
          context: chatContext(language, priorHistory, currentConversation.id, userRole),
        }),
      })
      const payload = await response.json()
      const assistantText = String(payload?.responseText || payload?.message || 'Offline AI reply failed.')

      updateCurrentConversation((conversation) => {
        const messages = conversation.messages.filter((message) => message.id !== placeholder.id)
        messages.push(
          createAssistantMessage({
            role: 'assistant',
            text: assistantText,
            status: 'Seen',
            error: !response.ok || !payload?.success,
            model: String(payload?.llmModel || ''),
          }),
        )
        return {
          ...conversation,
          language: normalizeLanguage(payload?.language || language),
          updatedAt: Date.now(),
          messages,
        }
      })

      if (!response.ok || !payload?.success) {
        setStatus(assistantText)
        return
      }

      if (payload?.llmModel) {
        setModelLabel(`Local model: ${payload.llmModel}`)
      } else if (payload?.responseSource === 'assistant_action' || payload?.intent === 'add_truck') {
        setModelLabel('Assistant action')
      } else if (payload?.responseSource === 'ollama') {
        setModelLabel('Local Ollama reply')
      } else {
        setModelLabel('Assistant reply')
      }

      if (payload?.intent === 'add_truck' && payload?.result?.truck) {
        dispatchTruckUpdate(payload.result.truck)
      }

      setStatus('Reply received from assistant.')
    } catch {
      updateCurrentConversation((conversation) => {
        const messages = conversation.messages.filter((message) => message.id !== placeholder.id)
        messages.push(
          createAssistantMessage({
            role: 'assistant',
            text: 'Offline AI request failed. Please try again.',
            status: 'Seen',
            error: true,
          }),
        )
        return {
          ...conversation,
          updatedAt: Date.now(),
          messages,
        }
      })
      setStatus('Offline AI request failed.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="ai-chat-page">
      <div className="ai-chat-shell">
        <aside className="ai-chat-sidebar">
          <div className="ai-chat-sidebar-top">
            <div className="ai-chat-brand-block">
              <button type="button" className="ai-chat-brand ai-chat-brand-button" onClick={() => navigate(homeRoute)}>
                Digi_TransX AI
              </button>
              <p className="ai-chat-brand-copy">
                Local-first assistant for transport workflows, saved sessions, and quick app guidance.
              </p>
            </div>
            <button type="button" className="ai-chat-primary-btn" onClick={createAndSelectConversation}>
              New Chat
            </button>
          </div>

          <div className="ai-chat-sidebar-tools">
            <button type="button" className="ai-chat-link-btn" onClick={() => navigate(-1)}>
              Back
            </button>
            <span className="ai-chat-role-badge">{roleLabel(userRole)}</span>
          </div>

          <section className="ai-chat-sidebar-intro" aria-label="Saved chat context">
            <p className="ai-chat-sidebar-kicker">Conversation vault</p>
            <p className="ai-chat-sidebar-note">
              Keep recent chats close, reopen them fast, and continue from the last local reply.
            </p>
          </section>

          <label className="ai-chat-search-wrap">
            <span>Saved chats</span>
            <input
              type="search"
              placeholder="Search conversations"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <div className="ai-chat-list" aria-live="polite">
            {filteredConversations.length ? (
              filteredConversations.map((conversation) => (
                <button
                  type="button"
                  key={conversation.id}
                  className={`ai-chat-list-item${conversation.id === currentId ? ' is-active' : ''}`}
                  onClick={() => setCurrentId(conversation.id)}
                >
                  <div className="ai-chat-list-title">{conversation.title || 'New chat'}</div>
                  <div className="ai-chat-list-preview">{currentConversationPreview(conversation)}</div>
                  <div className="ai-chat-list-time">{formatAssistantTime(conversation.updatedAt)}</div>
                </button>
              ))
            ) : (
              <div className="ai-chat-list-empty">
                No saved chats yet. Start a new conversation and it will stay here.
              </div>
            )}
          </div>

          <div className="ai-chat-sidebar-footer">
            <span className="ai-chat-sidebar-signal" aria-hidden="true"></span>
            <p>History stays available in this browser so repeated operational questions are easy to reopen.</p>
          </div>
        </aside>

        <main className="ai-chat-main">
          <header className="ai-chat-header">
            <div className="ai-chat-header-copy">
              <p className="ai-chat-eyebrow">Offline assistant</p>
              <h1>{currentConversation?.title || 'New chat'}</h1>
              <p className="ai-chat-subtitle">
                General questions and app actions both work here. Truck add and similar requests go through the app assistant first.
              </p>
              <div className="ai-chat-header-highlights" aria-hidden="true">
                <span className="ai-chat-chip">Local replies</span>
                <span className="ai-chat-chip">Saved sessions</span>
                <span className="ai-chat-chip">App guidance</span>
              </div>
            </div>

            <div className="ai-chat-header-panel">
              <label className="ai-chat-control">
                <span className="ai-chat-control-label">Language</span>
                <select className="ai-chat-select" value="en" disabled onChange={() => {}}>
                  <option value="en">English</option>
                </select>
              </label>
              <div className="ai-chat-header-actions">
                <span className="ai-chat-model-badge">{modelLabel}</span>
                <button type="button" className="ai-chat-link-btn" onClick={clearCurrentConversation}>
                  Clear
                </button>
              </div>
            </div>
          </header>

          <section className="ai-chat-stage" aria-label="Conversation area">
            <div ref={messagesRef} className="ai-chat-messages" aria-live="polite">
              {!currentConversation?.messages.length ? (
                <div className="ai-chat-empty-state">
                  <p className="ai-chat-empty-eyebrow">Local workspace</p>
                  <h2>Ask anything or continue a saved task.</h2>
                  <p>
                    This page sends chat to the local assistant so general questions, app guidance, and follow-up transport help stay available even when you want an offline flow.
                  </p>
                  <div className="ai-chat-empty-suggestions">
                    <span>Explain this page</span>
                    <span>Help me add a truck</span>
                    <span>Show my recent conversation</span>
                  </div>
                </div>
              ) : (
                currentConversation.messages.map((message) => (
                  <article
                    key={message.id}
                    className={`ai-chat-message ${message.role === 'user' ? 'is-user' : 'is-assistant'}${message.pending ? ' is-pending' : ''}${message.error ? ' is-error' : ''}`}
                  >
                    <div className="ai-chat-avatar" aria-hidden="true">{message.role === 'user' ? 'YOU' : 'AI'}</div>
                    <div className="ai-chat-message-stack">
                      <div className="ai-chat-message-label">{message.role === 'user' ? 'You' : 'Offline AI'}</div>
                      <div className="ai-chat-bubble">{message.text}</div>
                      <div className="ai-chat-message-meta">
                        <span>{formatAssistantTime(message.createdAt)}</span>
                        <span>{humanMessageStatus(message)}</span>
                        {message.model ? <span>{message.model}</span> : null}
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          </section>

          <form className="ai-chat-composer" onSubmit={sendMessage}>
            <label className="ai-chat-compose-box">
              <textarea
                rows="3"
                placeholder="Type anything. The assistant can answer questions and perform supported app actions."
                value={composer}
                onChange={(event) => setComposer(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    sendMessage()
                  }
                }}
              />
            </label>
            <div className="ai-chat-compose-actions">
              <div className="ai-chat-status">{status}</div>
              <button type="submit" className="ai-chat-primary-btn" disabled={sending}>
                {sending ? 'Sending...' : 'Send'}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  )
}
