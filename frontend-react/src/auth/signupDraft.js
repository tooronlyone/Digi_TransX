function cloneBasic(basic) {
  return basic && typeof basic === 'object' ? { ...basic } : null
}

function publicSnapshot(state) {
  return Object.freeze({
    basic: cloneBasic(state.basic),
    role: state.role,
    terms: state.terms ? { ...state.terms } : null,
    failure: state.failure,
    submitting: Boolean(state.activeSubmission),
  })
}

export function hasCompleteSignupBasic(basic) {
  return Boolean(basic && typeof basic.password === 'string' && basic.password.length > 0)
}

export function createSignupDraftStore() {
  let state = {
    basic: null,
    role: '',
    terms: null,
    failure: '',
    generation: 0,
    activeSubmission: null,
  }
  const listeners = new Set()

  function publish(next) {
    state = next
    const snapshot = publicSnapshot(state)
    for (const listener of listeners) listener(snapshot)
    return snapshot
  }

  function clearState({ preserveNonSensitive = false, failure = '' } = {}) {
    state.activeSubmission?.controller.abort()
    const basic = preserveNonSensitive && state.basic
      ? { ...state.basic, password: '' }
      : null
    return publish({
      basic,
      role: '',
      terms: null,
      failure: String(failure || ''),
      generation: state.generation + 1,
      activeSubmission: null,
    })
  }

  function isSubmissionActive(token) {
    return state.activeSubmission === token
      && token?.generation === state.generation
      && !token.controller.signal.aborted
  }

  return Object.freeze({
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    read() {
      return publicSnapshot(state)
    },
    begin(basic) {
      if (!hasCompleteSignupBasic(basic)) return false
      publish({
        basic: cloneBasic(basic),
        role: '',
        terms: null,
        failure: '',
        generation: state.generation + 1,
        activeSubmission: null,
      })
      return true
    },
    selectRole(role) {
      if (!hasCompleteSignupBasic(state.basic) || state.activeSubmission) return false
      publish({ ...state, role: String(role || ''), terms: null, failure: '' })
      return true
    },
    acceptTerms(version, role) {
      if (!version || role !== state.role || !hasCompleteSignupBasic(state.basic) || state.activeSubmission) return false
      publish({ ...state, terms: { version, role } })
      return true
    },
    claimSubmission() {
      if (!hasCompleteSignupBasic(state.basic) || !state.role || state.activeSubmission
          || state.terms?.role !== state.role) return null
      const token = Object.freeze({
        generation: state.generation,
        controller: new AbortController(),
      })
      state = { ...state, activeSubmission: token }
      const snapshot = publicSnapshot(state)
      for (const listener of listeners) listener(snapshot)
      return Object.freeze({
        token,
        signal: token.controller.signal,
        basic: cloneBasic(state.basic),
        role: state.role,
        terms: { ...state.terms },
      })
    },
    isSubmissionActive(token) {
      return isSubmissionActive(token)
    },
    failSubmission(token, message = 'Signup failed. Re-enter your password to try again.') {
      if (!isSubmissionActive(token)) return false
      clearState({ preserveNonSensitive: true, failure: message })
      return true
    },
    completeSubmission(token) {
      if (!isSubmissionActive(token)) return false
      clearState()
      return true
    },
    clear(options) {
      return clearState(options)
    },
  })
}

export function subscribeSignupAuthReset(store, coordinator) {
  return coordinator.subscribe((event) => {
    if (event.type === 'full_login_required') store.clear()
  })
}
