import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import '../../styles/ai-assistant.css'
import {
  AI_API_BASE,
  AI_CHAT_ROUTE,
  DEFAULT_AI_CAPABILITIES,
  appendConversationTurn,
  applyMappedFields,
  buildAssistantContext,
  detectUserRole,
  dispatchTruckUpdate,
  loadAssistantMemory,
  loadAssistantPreferences,
  normalizeMode,
  roleLabel,
  saveAssistantMemory,
  saveAssistantPreferences,
  syncSessionRoleFromBackend,
} from '../../lib/aiAssistant'

export default function GlobalAiAssistant() {
  const location = useLocation()
  const navigate = useNavigate()
  const recognitionRef = useRef(null)
  const routePath = `${location.pathname}${location.search}${location.hash}`
  const [userRole, setUserRole] = useState(() => detectUserRole())
  const [memory, setMemory] = useState(() => loadAssistantMemory(location.pathname, detectUserRole()))
  const [preferences, setPreferences] = useState(() => loadAssistantPreferences())
  const [capabilities, setCapabilities] = useState(DEFAULT_AI_CAPABILITIES)
  const [preview, setPreview] = useState('')
  const [questionInput, setQuestionInput] = useState('')
  const [status, setStatus] = useState('Command assistant ready.')
  const [isListening, setIsListening] = useState(false)

  const pageContext = buildAssistantContext({
    pathname: location.pathname,
    userRole,
    memory,
    pageTitle: typeof document !== 'undefined' ? document.title : '',
  })

  useEffect(() => {
    setMemory((current) => loadAssistantMemory(location.pathname, userRole))
  }, [location.pathname, userRole])

  useEffect(() => {
    saveAssistantMemory(memory)
  }, [memory])

  useEffect(() => {
    saveAssistantPreferences(preferences)
    fetch(`${AI_API_BASE}/preferences`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        languagePreference: 'en',
        visibilityMode: preferences.mode,
        backgroundListening: preferences.backgroundListening,
      }),
    }).catch(() => {})
  }, [preferences])

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
          setCapabilities(payload.capabilities)
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
    function handleFocus(event) {
      const target = event.target
      if (!target) return
      setMemory((current) => ({
        ...current,
        activeField: target.id || target.name || null,
        activeForm: target.form?.id || null,
      }))
    }

    document.addEventListener('focusin', handleFocus)
    return () => document.removeEventListener('focusin', handleFocus)
  }, [])

  useEffect(() => {
    function handleHotkey(event) {
      if (event.ctrlKey && event.shiftKey && String(event.key || '').toLowerCase() === 'a') {
        event.preventDefault()
        cycleVisibilityMode()
      }
    }

    document.addEventListener('keydown', handleHotkey)
    return () => document.removeEventListener('keydown', handleHotkey)
  }, [])

  useEffect(() => {
    if (preferences.mode === 'hidden' && preferences.backgroundListening) {
      ensureBackgroundListening()
    }
    if (preferences.mode !== 'hidden' && !preferences.backgroundListening) {
      stopListening()
    }
  }, [preferences.mode, preferences.backgroundListening])

  useEffect(() => {
    return () => stopListening()
  }, [])

  if (location.pathname === AI_CHAT_ROUTE) {
    return null
  }

  function cycleVisibilityMode() {
    setPreferences((current) => {
      const mode = normalizeMode(current.mode)
      if (mode === 'visible') return { ...current, mode: 'minimized' }
      if (mode === 'minimized') return { ...current, mode: 'hidden' }
      return { ...current, mode: 'visible' }
    })
  }

  function stopListening() {
    try {
      recognitionRef.current?.stop()
    } catch {
      // no-op
    }
    setIsListening(false)
  }

  function ensureRecognition() {
    const Constructor = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Constructor) return null
    if (recognitionRef.current) return recognitionRef.current

    const recognition = new Constructor()
    recognition.lang = 'en-US'
    recognition.interimResults = false
    recognition.continuous = false
    recognition.maxAlternatives = 1
    recognition.onstart = () => {
      setIsListening(true)
      setStatus('Listening...')
    }
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || ''
      handleCapturedTranscript(transcript)
    }
    recognition.onerror = () => {
      setIsListening(false)
      setStatus('Speech recognition unavailable. Type and send request.')
    }
    recognition.onend = () => {
      setIsListening(false)
      if (preferences.mode === 'hidden' && preferences.backgroundListening) {
        ensureBackgroundListening()
      }
    }
    recognitionRef.current = recognition
    return recognition
  }

  function ensureBackgroundListening() {
    const recognition = ensureRecognition()
    if (!recognition || isListening) return
    try {
      recognition.start()
    } catch {
      // no-op
    }
  }

  function handleMicToggle() {
    const recognition = ensureRecognition()
    if (recognition) {
      if (isListening) {
        stopListening()
      } else {
        try {
          recognition.start()
        } catch {
          setStatus('Cannot start microphone. Type request and press Send.')
        }
      }
      return
    }

    if (preview.trim()) {
      processTranscript(preview)
      return
    }
    setStatus('Voice input unavailable. Type request and press Send.')
  }

  function handleCapturedTranscript(transcript) {
    const text = String(transcript || '').trim()
    if (!text) return

    if (memory.pendingQuestion) {
      setQuestionInput(text)
      submitPendingQuestion(text)
      return
    }

    setPreview(text)
    processTranscript(text)
  }

  function persistResponseState(payload, userText, assistantText) {
    setMemory((current) => {
      let next = {
        ...current,
        lastQuestion: userText,
        lastIntent: payload.intent || current.lastIntent,
        lastTopic: payload.topic || current.lastTopic,
        lastConcept: payload.concept || current.lastConcept,
        languagePreference: 'en',
        pendingData: payload.pendingData || current.pendingData,
        pendingActionId: payload.pendingActionId || null,
        confirmationStatus: payload.pendingActionId ? 'awaiting' : 'none',
        pendingQuestion: Boolean(payload.pendingQuestion),
        pendingQuestionPrompt: payload.pendingQuestion ? (payload.questionPrompt || assistantText) : '',
      }
      next = appendConversationTurn(next, 'user', userText, { pageName: pageContext.pageName })
      next = appendConversationTurn(next, 'assistant', assistantText, payload)
      return next
    })
  }

  async function processTranscript(transcript, options = {}) {
    const text = String(transcript || '').trim()
    if (!text) {
      setStatus('Enter or speak a request first.')
      return
    }

    setMemory((current) => ({ ...current, lastQuestion: text }))
    setStatus('Interpreting request...')

    try {
      const response = await fetch(`${AI_API_BASE}/interpret`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript: text,
          context: buildAssistantContext({
            pathname: location.pathname,
            userRole,
            memory: { ...memory, lastQuestion: text },
            pageTitle: typeof document !== 'undefined' ? document.title : '',
          }),
          history: (memory.conversationHistory || []).slice(-6),
        }),
      })

      const payload = await response.json()
      const responseText = String(payload?.confirmationPrompt || payload?.responseText || payload?.message || 'Request processed.')

      if (!response.ok || !payload?.success) {
        persistResponseState(payload || {}, text, responseText)
        setPreview(responseText)
        setStatus(responseText)
        if (!payload?.pendingQuestion) {
          setQuestionInput('')
        }
        return
      }

      persistResponseState(payload, text, responseText)
      setPreview(responseText)
      setStatus(responseText)
      if (options.fromPendingQuestion) {
        setQuestionInput('')
      }

      if (payload?.intent === 'add_truck' && payload?.result?.truck) {
        dispatchTruckUpdate(payload.result.truck)
      }

      const targetRoute = payload?.targetRoute || payload?.result?.targetRoute
      if (payload?.autoNavigated && targetRoute) {
        window.location.assign(targetRoute)
      }
    } catch {
      setStatus('Interpretation request failed.')
    }
  }

  async function confirmPendingAction() {
    if (!memory.pendingActionId) {
      setStatus('No pending action to confirm.')
      return
    }

    setStatus('Applying confirmed action...')
    try {
      const response = await fetch(`${AI_API_BASE}/confirm`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pendingActionId: memory.pendingActionId,
          confirmation: true,
          context: buildAssistantContext({
            pathname: location.pathname,
            userRole,
            memory,
            pageTitle: typeof document !== 'undefined' ? document.title : '',
          }),
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload?.success) {
        setStatus(payload?.message || 'Confirmation failed.')
        return
      }

      const mapped = Array.isArray(payload?.mappedFields)
        ? payload.mappedFields
        : payload?.result?.mappedFields || []
      if (mapped.length) {
        applyMappedFields(mapped)
      }

      const message = String(payload?.result?.message || payload?.message || 'Action completed.')
      setMemory((current) => ({
        ...current,
        pendingActionId: null,
        confirmationStatus: 'confirmed',
        pendingData: payload?.pendingData || {},
        pendingQuestion: Boolean(payload?.pendingQuestion),
        pendingQuestionPrompt: payload?.pendingQuestion ? (payload?.questionPrompt || message) : '',
      }))
      setPreview(message)
      setStatus(payload?.questionPrompt || message)

      if (payload?.result?.truck) {
        dispatchTruckUpdate(payload.result.truck)
      }

      const targetRoute = payload?.result?.targetRoute
      if (targetRoute) {
        window.location.assign(targetRoute)
      }
    } catch {
      setStatus('Confirmation request failed.')
    }
  }

  async function cancelPendingAction() {
    if (!memory.pendingActionId) {
      setStatus('No pending action to cancel.')
      return
    }

    try {
      await fetch(`${AI_API_BASE}/cancel`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pendingActionId: memory.pendingActionId }),
      })
    } catch {
      // no-op
    }

    setMemory((current) => ({
      ...current,
      pendingActionId: null,
      confirmationStatus: 'cancelled',
      pendingData: {},
      pendingQuestion: false,
      pendingQuestionPrompt: '',
    }))
    setQuestionInput('')
    setStatus('Pending action cancelled.')
  }

  function submitPendingQuestion(nextValue = questionInput) {
    const answer = String(nextValue || '').trim()
    if (!answer) {
      setStatus('Please enter or speak an answer first.')
      return
    }
    processTranscript(answer, { fromPendingQuestion: true })
  }

  function openFullChat() {
    navigate(capabilities.chat_page_route || AI_CHAT_ROUTE)
  }

  return (
    <section
      id="aiAssistantWidget"
      className={`ai-assistant-widget mode-${normalizeMode(preferences.mode)}`}
      aria-hidden={preferences.mode === 'hidden' ? 'true' : 'false'}
      data-ai-route={routePath}
    >
      <button
        type="button"
        className="ai-assistant-mini"
        aria-label="Open AI Assistant"
        onClick={() => setPreferences((current) => ({ ...current, mode: 'visible' }))}
      >
        AI
      </button>

      <div className="ai-assistant-shell">
        <div className="ai-assistant-header">
          <span>AI Assistant</span>
          <span className="ai-assistant-pill">{pageContext.pageLabel}</span>
          <div className="ai-assistant-controls">
            <button type="button" className="ai-assistant-btn ai-assistant-btn-ghost" onClick={openFullChat}>
              Chat
            </button>
            <select
              className="ai-assistant-select"
              title="Language"
              value="en"
              disabled
              onChange={() => {}}
            >
              <option value="en">EN</option>
            </select>
            <button type="button" className="ai-assistant-btn ai-assistant-btn-ghost" onClick={cycleVisibilityMode}>
              Mode
            </button>
          </div>
        </div>

        <div className="ai-assistant-body">
          <textarea
            className="ai-assistant-preview"
            placeholder="Speak or type your command for this page..."
            value={preview}
            onChange={(event) => setPreview(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                processTranscript(preview)
              }
            }}
          />

          <div className="ai-assistant-question" hidden={!memory.pendingQuestion}>
            <div className="ai-assistant-question-prompt">
              {memory.pendingQuestionPrompt || 'Please answer the assistant question.'}
            </div>
            <div className="ai-assistant-question-row">
              <input
                className="ai-assistant-question-input"
                type="text"
                placeholder="Type your answer..."
                value={questionInput}
                onChange={(event) => setQuestionInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    submitPendingQuestion()
                  }
                }}
              />
              <button type="button" className={`ai-assistant-btn ai-assistant-btn-mic${isListening ? ' is-recording' : ''}`} onClick={handleMicToggle}>
                {isListening ? 'Stop' : 'Mic'}
              </button>
              <button type="button" className="ai-assistant-btn ai-assistant-btn-send" onClick={() => submitPendingQuestion()}>
                Submit
              </button>
            </div>
          </div>

          <div className="ai-assistant-row">
            <button type="button" className={`ai-assistant-btn ai-assistant-btn-mic${isListening ? ' is-recording' : ''}`} onClick={handleMicToggle}>
              {isListening ? 'Stop' : 'Mic'}
            </button>
            <button type="button" className="ai-assistant-btn ai-assistant-btn-send" onClick={() => processTranscript(preview)}>
              Send
            </button>
            <button type="button" className="ai-assistant-btn ai-assistant-btn-confirm" disabled={!memory.pendingActionId} onClick={confirmPendingAction}>
              Confirm
            </button>
            <button type="button" className="ai-assistant-btn ai-assistant-btn-cancel" disabled={!memory.pendingActionId} onClick={cancelPendingAction}>
              Cancel
            </button>
          </div>

          <label className="ai-assistant-toggle">
            <input
              type="checkbox"
              checked={preferences.backgroundListening}
              onChange={(event) =>
                setPreferences((current) => ({
                  ...current,
                  backgroundListening: Boolean(event.target.checked),
                }))
              }
            />
            Background voice in hidden mode
          </label>

          <div className="ai-assistant-status">{status || `Signed in as ${roleLabel(userRole)}`}</div>
          <div className="ai-assistant-hint">Shortcut: Ctrl + Shift + A</div>
        </div>
      </div>
    </section>
  )
}
