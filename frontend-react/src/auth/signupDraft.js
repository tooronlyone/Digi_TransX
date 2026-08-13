function cloneBasic(basic) {
  return basic && typeof basic === 'object' ? { ...basic } : null
}

function publicSnapshot(state) {
  return Object.freeze({
    basic: cloneBasic(state.basic),
    role: state.role,
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
        failure: '',
        generation: state.generation + 1,
        activeSubmission: null,
      })
      return true
    },
    selectRole(role) {
      if (!hasCompleteSignupBasic(state.basic) || state.activeSubmission) return false
      publish({ ...state, role: String(role || ''), failure: '' })
      return true
    },
    claimSubmission() {
      if (!hasCompleteSignupBasic(state.basic) || !state.role || state.activeSubmission) return null
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
