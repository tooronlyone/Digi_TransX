export const AI_API_BASE = '/api/ai-assistant'
export const AI_CHAT_ROUTE = '/ai-chat'
export const AI_MEMORY_KEY = 'ai_assistant_memory_v2'
export const AI_PREFERENCES_KEY = 'ai_assistant_preferences_v2'
export const AI_CONVERSATIONS_KEY = 'ai_assistant_conversations_v1'

export const DEFAULT_AI_CAPABILITIES = {
  whisper_available: false,
  offline_chat_available: false,
  chat_page_route: AI_CHAT_ROUTE,
  browser_fallback_supported: true,
  english_only_input: true,
  intent_driven_only: true,
  supported_languages: ['en'],
  workflow_available: true,
}

const ROLE_ALIASES = {
  logistics_provider: 'transporter',
  service_seeker: 'client',
}

const EXACT_PAGE_MAP = {
  '/': {
    pageName: 'login',
    pageLabel: 'Login',
    pagePurpose: 'Authenticate securely to enter the system.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/login': {
    pageName: 'login',
    pageLabel: 'Login',
    pagePurpose: 'Authenticate securely to enter the system.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/signup': {
    pageName: 'signup',
    pageLabel: 'Sign Up',
    pagePurpose: 'Register a new account with role and contact details.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/signup/role': {
    pageName: 'signup_role',
    pageLabel: 'Role Select',
    pagePurpose: 'Choose the account type for registration.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/reset-password': {
    pageName: 'reset_password',
    pageLabel: 'Reset Password',
    pagePurpose: 'Recover account access and create a new password.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/unlock': {
    pageName: 'unlock',
    pageLabel: 'Unlock',
    pagePurpose: 'Unlock a protected account and verify ownership.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
  },
  '/ai-chat': {
    pageName: 'ai_chat',
    pageLabel: 'AI Chat',
    pagePurpose: 'Dedicated assistant chat page for questions and in-app actions.',
    availableActions: ['general_chat', 'assistant_actions', 'navigation'],
  },
  '/transporter/dashboard': {
    pageName: 'transporter_dashboard',
    pageLabel: 'Transporter Dashboard',
    pagePurpose: 'Manage trucks, availability, jobs, and earnings.',
    availableActions: ['add_truck', 'update_availability', 'earnings_query', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/personal-info': {
    pageName: 'transporter_personal_info',
    pageLabel: 'Personal Info',
    pagePurpose: 'Review fleet health, maintenance, fuel activity, account updates, earnings, and predictive insights from one hub.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/trucks': {
    pageName: 'my_truck',
    pageLabel: 'My Trucks',
    pagePurpose: 'Review fleet details, status, and truck-level actions.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/jobs': {
    pageName: 'transporter_available_jobs',
    pageLabel: 'Available Jobs',
    pagePurpose: 'Browse new jobs and apply to work that fits your fleet.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/jobs/active': {
    pageName: 'transporter_active_jobs',
    pageLabel: 'Active Jobs',
    pagePurpose: 'Track jobs that are currently in progress.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/jobs/history': {
    pageName: 'transporter_job_history',
    pageLabel: 'Job History',
    pagePurpose: 'Review completed, disputed, or cancelled job records.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/maintenance': {
    pageName: 'transporter_maintenance',
    pageLabel: 'Maintenance',
    pagePurpose: 'Track maintenance records, service reminders, and upcoming truck work.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/fuel': {
    pageName: 'transporter_fuel_management',
    pageLabel: 'Fuel Management',
    pagePurpose: 'Log fuel entries and review mileage, fuel cost, and consumption trends.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/analytics': {
    pageName: 'transporter_analytics',
    pageLabel: 'Analytics',
    pagePurpose: 'Review transporter analytics, performance charts, and operational trends.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/insights': {
    pageName: 'transporter_pred_insights',
    pageLabel: 'Predictive Insights',
    pagePurpose: 'Review demand, maintenance, and earnings forecasts for planning.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/earnings': {
    pageName: 'transporter_earnings',
    pageLabel: 'Earnings',
    pagePurpose: 'Track transporter earnings, withdrawals, and payout history.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/documents': {
    pageName: 'transporter_documents',
    pageLabel: 'Documents',
    pagePurpose: 'Review, print, and manage transporter-side documents.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/payments': {
    pageName: 'transporter_payments',
    pageLabel: 'Payments',
    pagePurpose: 'Manage incoming payments, released payouts, and due balances.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/profile': {
    pageName: 'transporter_profile',
    pageLabel: 'Profile',
    pagePurpose: 'Review transporter account details and profile information.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/settings': {
    pageName: 'transporter_settings',
    pageLabel: 'Settings',
    pagePurpose: 'Update preferences, notifications, and security settings.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/rating': {
    pageName: 'transporter_rating',
    pageLabel: 'Ratings',
    pagePurpose: 'Review customer ratings, comments, and rank trends.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/organization': {
    pageName: 'transporter_organization',
    pageLabel: 'Organization',
    pagePurpose: 'Create and manage restricted organization team accounts.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/leaderboard': {
    pageName: 'transporter_leaderboard',
    pageLabel: 'Leaderboard',
    pagePurpose: 'Compare your transporter performance with other transporters.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/help': {
    pageName: 'transporter_help',
    pageLabel: 'Help',
    pagePurpose: 'Read support content and guidance for transporter workflows.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/about': {
    pageName: 'transporter_about',
    pageLabel: 'About',
    pagePurpose: 'Learn about Digi_TransX and the transporter-side experience.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/contact': {
    pageName: 'transporter_contact',
    pageLabel: 'Contact',
    pagePurpose: 'Reach Digi_TransX support for operational help and account questions.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
  '/transporter/terms': {
    pageName: 'transporter_terms',
    pageLabel: 'Terms & Conditions',
    pagePurpose: 'Read transporter-side platform terms and operational commitments.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/privacy': {
    pageName: 'transporter_privacy',
    pageLabel: 'Privacy Policy',
    pagePurpose: 'Read transporter-side data collection, use, and protection details.',
    availableActions: ['page_explain', 'navigation', 'info_query'],
  },
  '/transporter/partner': {
    pageName: 'transporter_partner',
    pageLabel: 'Partner With Us',
    pagePurpose: 'Explore partnership options and onboarding requirements.',
    availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation', 'info_query'],
  },
}

function safeStorageGet(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // no-op
  }
}

function parseStoredJson(key, fallback) {
  const raw = safeStorageGet(key)
  if (!raw) return fallback
  try {
    const parsed = JSON.parse(raw)
    return parsed ?? fallback
  } catch {
    return fallback
  }
}

export function normalizeLanguage() {
  return 'en'
}

export function normalizeMode(mode) {
  const value = String(mode || '').toLowerCase()
  if (value === 'visible' || value === 'minimized' || value === 'hidden') return value
  return 'minimized'
}

export function normalizeRole(role) {
  const value = String(role || '').trim().toLowerCase()
  return ROLE_ALIASES[value] || value || 'guest'
}

export function detectUserRole() {
  try {
    if (sessionStorage.getItem('admin_id')) return 'admin'
    return normalizeRole(sessionStorage.getItem('user_role'))
  } catch {
    return 'guest'
  }
}

export function roleLabel(role) {
  const value = normalizeRole(role)
  if (!value) return 'Guest'
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export function titleize(text) {
  const cleaned = String(text || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return ''
  return cleaned
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function truncate(value, maxLength) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 1)}...`
}

export function buildAssistantId(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export function formatAssistantTime(timestamp) {
  try {
    return new Date(Number(timestamp || Date.now())).toLocaleString([], {
      hour: '2-digit',
      minute: '2-digit',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return ''
  }
}

export function humanMessageStatus(message) {
  if (message?.role === 'assistant') return message?.error ? 'Reply failed' : 'Seen'
  if (message?.pending) return 'Sending'
  if (String(message?.status || '').toLowerCase() === 'seen') return 'Seen'
  return 'Sent'
}

function normalizeMessage(source) {
  if (!source || typeof source !== 'object') return null
  const role = String(source.role || '').toLowerCase()
  if (role !== 'user' && role !== 'assistant') return null
  return {
    id: String(source.id || buildAssistantId('msg')),
    role,
    text: String(source.text || ''),
    createdAt: Number(source.createdAt || Date.now()),
    status: String(source.status || (role === 'assistant' ? 'seen' : 'sent')),
    pending: Boolean(source.pending),
    error: Boolean(source.error),
    model: String(source.model || ''),
  }
}

function normalizeConversation(source) {
  const messages = Array.isArray(source?.messages)
    ? source.messages.map(normalizeMessage).filter(Boolean)
    : []
  return {
    id: String(source?.id || buildAssistantId('conv')),
    title: String(source?.title || 'New chat'),
    createdAt: Number(source?.createdAt || Date.now()),
    updatedAt: Number(source?.updatedAt || Date.now()),
    language: normalizeLanguage(source?.language),
    messages,
  }
}

export function loadAssistantConversations() {
  const parsed = parseStoredJson(AI_CONVERSATIONS_KEY, [])
  if (!Array.isArray(parsed)) return []
  return parsed
    .filter((item) => item && typeof item === 'object')
    .map(normalizeConversation)
    .filter(Boolean)
}

export function saveAssistantConversations(conversations) {
  safeStorageSet(AI_CONVERSATIONS_KEY, JSON.stringify(conversations || []))
}

export function createAssistantConversation(language = 'en') {
  return {
    id: buildAssistantId('conv'),
    title: 'New chat',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    language: normalizeLanguage(language),
    messages: [],
  }
}

export function createAssistantMessage({
  role,
  text,
  status = 'sent',
  pending = false,
  error = false,
  model = '',
  createdAt = Date.now(),
}) {
  return {
    id: buildAssistantId('msg'),
    role,
    text: String(text || ''),
    createdAt,
    status,
    pending: Boolean(pending),
    error: Boolean(error),
    model: String(model || ''),
  }
}

export function loadAssistantPreferences() {
  const parsed = parseStoredJson(AI_PREFERENCES_KEY, {})
  return {
    mode: normalizeMode(parsed?.mode),
    backgroundListening: Boolean(parsed?.backgroundListening),
  }
}

export function saveAssistantPreferences(preferences) {
  safeStorageSet(
    AI_PREFERENCES_KEY,
    JSON.stringify({
      mode: normalizeMode(preferences?.mode),
      backgroundListening: Boolean(preferences?.backgroundListening),
    }),
  )
}

export function resolveAiPage(pathname) {
  const currentPath = String(pathname || '/').replace(/[?#].*$/, '')
  if (EXACT_PAGE_MAP[currentPath]) return EXACT_PAGE_MAP[currentPath]

  if (currentPath.startsWith('/transporter/trucks/add')) {
    return {
      pageName: 'add_truck',
      pageLabel: 'Add Truck',
      pagePurpose: 'Register truck number, capacity, and availability.',
      availableActions: ['field_entry', 'page_explain', 'navigation', 'add_truck'],
    }
  }
  if (currentPath.startsWith('/transporter/trucks/config/')) {
    return {
      pageName: 'truck_configuration',
      pageLabel: 'Truck Configuration',
      pagePurpose: 'Configure truck-specific regulatory and operating details.',
      availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
    }
  }
  if (currentPath.startsWith('/transporter/trucks/edit/')) {
    return {
      pageName: 'edit_truck',
      pageLabel: 'Edit Truck',
      pagePurpose: 'Update truck profile and activation details.',
      availableActions: ['field_entry', 'field_help', 'page_explain', 'navigation'],
    }
  }
  if (currentPath.endsWith('/track')) {
    return {
      pageName: 'track_truck',
      pageLabel: 'Track Truck',
      pagePurpose: 'Review truck movement and field tracking details.',
      availableActions: ['page_explain', 'navigation', 'info_query'],
    }
  }
  if (currentPath.endsWith('/service')) {
    return {
      pageName: 'service_history',
      pageLabel: 'Service History',
      pagePurpose: 'Inspect a truck service and maintenance timeline.',
      availableActions: ['page_explain', 'navigation', 'info_query'],
    }
  }
  if (currentPath.startsWith('/transporter/trucks/')) {
    return {
      pageName: 'my_truck',
      pageLabel: 'My Trucks',
      pagePurpose: 'Review fleet details, status, and truck-level actions.',
      availableActions: ['page_explain', 'navigation', 'info_query'],
    }
  }
  if (currentPath.startsWith('/transporter')) {
    const lastSegment = currentPath.split('/').filter(Boolean).at(-1) || 'page'
    return {
      pageName: `transporter_${lastSegment.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}`,
      pageLabel: titleize(lastSegment),
      pagePurpose: 'Transporter portal page for fleet operations and jobs.',
      availableActions: ['page_explain', 'navigation', 'info_query'],
    }
  }
  const lastSegment = currentPath.split('/').filter(Boolean).at(-1) || 'page'
  return {
    pageName: `page_${lastSegment.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}`,
    pageLabel: titleize(lastSegment),
    pagePurpose: 'General project page.',
    availableActions: ['field_help', 'navigation', 'info_query'],
  }
}

export function createDefaultMemory(pathname, userRole = detectUserRole()) {
  const page = resolveAiPage(pathname)
  return {
    currentPage: page.pageName,
    userRole: normalizeRole(userRole),
    activeForm: null,
    activeField: null,
    pendingData: {},
    confirmationStatus: 'none',
    pendingActionId: null,
    lastQuestion: '',
    lastPage: page.pageName,
    lastIntent: 'unknown',
    lastTopic: 'general',
    lastConcept: 'general_support_request',
    languagePreference: 'en',
    pendingQuestion: false,
    pendingQuestionPrompt: '',
    conversationHistory: [],
  }
}

export function loadAssistantMemory(pathname, userRole = detectUserRole()) {
  const fallback = createDefaultMemory(pathname, userRole)
  const parsed = parseStoredJson(AI_MEMORY_KEY, fallback)
  if (!parsed || typeof parsed !== 'object') return fallback
  return reconcileAssistantMemory({ ...fallback, ...parsed }, pathname, userRole)
}

export function reconcileAssistantMemory(memory, pathname, userRole = detectUserRole()) {
  const page = resolveAiPage(pathname)
  const next = {
    ...createDefaultMemory(pathname, userRole),
    ...(memory || {}),
    currentPage: page.pageName,
    userRole: normalizeRole(userRole),
    languagePreference: normalizeLanguage(memory?.languagePreference),
    conversationHistory: Array.isArray(memory?.conversationHistory) ? memory.conversationHistory.slice(-6) : [],
  }

  if (String(memory?.currentPage || '') !== page.pageName) {
    next.pendingData = {}
    next.pendingActionId = null
    next.confirmationStatus = 'none'
    next.pendingQuestion = false
    next.pendingQuestionPrompt = ''
    next.activeField = null
    next.activeForm = null
    next.conversationHistory = []
  }

  next.lastPage = page.pageName
  return next
}

export function saveAssistantMemory(memory) {
  safeStorageSet(AI_MEMORY_KEY, JSON.stringify(memory || {}))
}

export function appendConversationTurn(memory, role, content, extra = {}) {
  const text = String(content || '').trim()
  if (!text) return memory
  const item = {
    role: String(role || 'assistant'),
    content: text,
    pageName: extra.pageName || memory?.currentPage || 'other',
  }
  if (extra.intent) item.intent = String(extra.intent)
  if (extra.topic) item.topic = String(extra.topic)
  if (extra.concept) item.concept = String(extra.concept)

  return {
    ...memory,
    conversationHistory: [...(memory?.conversationHistory || []), item].slice(-6),
  }
}

export function serializeConversationHistory(messages) {
  return (messages || [])
    .filter((message) => !message.pending)
    .slice(-12)
    .map((message) => ({
      role: message.role,
      content: message.text,
    }))
}

export function buildAssistantContext({
  pathname,
  userRole,
  memory,
  pageTitle = '',
}) {
  const page = resolveAiPage(pathname)
  return {
    route: String(pathname || '/'),
    pageName: page.pageName,
    pageLabel: page.pageLabel,
    pageTitle: String(pageTitle || ''),
    currentPage: page.pageName,
    userRole: normalizeRole(userRole),
    visibleFields: collectVisibleFields(),
    availableActions: page.availableActions,
    pagePurpose: page.pagePurpose,
    activeForm: memory?.activeForm || null,
    activeField: memory?.activeField || null,
    pendingData: memory?.pendingData || {},
    confirmationStatus: memory?.confirmationStatus || 'none',
    pendingActionId: memory?.pendingActionId || null,
    pendingQuestion: Boolean(memory?.pendingQuestion),
    pendingQuestionPrompt: memory?.pendingQuestionPrompt || '',
    languagePreference: normalizeLanguage(memory?.languagePreference),
    lastQuestion: memory?.lastQuestion || '',
    lastIntent: memory?.lastIntent || 'unknown',
    lastTopic: memory?.lastTopic || 'general',
    lastConcept: memory?.lastConcept || 'general_support_request',
    history: (memory?.conversationHistory || []).slice(-6),
  }
}

function collectVisibleFields() {
  if (typeof document === 'undefined') return []
  const nodes = document.querySelectorAll('input, select, textarea')
  const fields = []
  nodes.forEach((node) => {
    if (!node) return
    if (node.closest?.('#aiAssistantWidget')) return
    if (!node.getClientRects || node.getClientRects().length === 0) return
    const style = window.getComputedStyle(node)
    if (style.visibility === 'hidden' || style.display === 'none') return
    const id = node.id || node.name
    if (!id || fields.includes(id)) return
    fields.push(id)
  })
  return fields
}

export function applyMappedFields(mappedFields) {
  ;(mappedFields || []).forEach((item) => {
    if (!item?.fieldId || typeof document === 'undefined') return

    let field =
      document.getElementById(item.fieldId) ||
      document.querySelector(`[name="${item.fieldId}"]`)

    if (!field && item.fieldId === 'role') {
      field = document.querySelector(`input[name="role"][value="${String(item.value)}"]`)
      if (field) {
        field.checked = true
        field.dispatchEvent(new Event('change', { bubbles: true }))
      }
      return
    }

    if (!field) return

    if (field.tagName === 'SELECT') {
      const match = [...field.options].find(
        (option) => String(option.value).toLowerCase() === String(item.value).toLowerCase(),
      )
      field.value = match ? match.value : item.value
    } else if (field.type === 'checkbox') {
      field.checked = Boolean(item.value)
    } else {
      field.value = item.value
    }

    field.dispatchEvent(new Event('input', { bubbles: true }))
    field.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

export function dispatchTruckUpdate(truck) {
  if (!truck || typeof window === 'undefined' || typeof window.CustomEvent !== 'function') return
  try {
    window.dispatchEvent(new CustomEvent('ai-truck-updated', { detail: truck }))
  } catch {
    // no-op
  }
}

export async function syncSessionRoleFromBackend() {
  try {
    const endpoint = sessionStorage.getItem('admin_id') ? '/api/admin/auth/me' : '/auth/me'
    const response = await fetch(endpoint, {
      method: 'GET',
      credentials: 'include',
    })
    if (!response.ok) return detectUserRole()
    const payload = await response.json()
    if (payload?.user) {
      sessionStorage.setItem('user_id', String(payload.user.id || ''))
      sessionStorage.setItem('user_role', normalizeRole(payload.user.role))
    } else if (payload?.admin) {
      sessionStorage.setItem('admin_id', String(payload.admin.id || ''))
      sessionStorage.setItem('admin_level', String(payload.admin.admin_level || '').toLowerCase())
      sessionStorage.setItem('user_role', 'admin')
    }
    return detectUserRole()
  } catch {
    return detectUserRole()
  }
}
