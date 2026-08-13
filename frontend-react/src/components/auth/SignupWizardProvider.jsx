import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import {
  createSignupDraftStore,
  hasCompleteSignupBasic,
  subscribeSignupAuthReset,
} from '../../auth/signupDraft.js'
import { accessLockCoordinator } from '../../auth/accessLock.js'
import { SignupWizardContext, useSignupWizard } from '../../auth/signupWizardContext.js'

export function RequireSignupDraft({ role, children }) {
  const { draft } = useSignupWizard()
  if (!hasCompleteSignupBasic(draft.basic) || draft.role !== role) {
    return <Navigate to="/signup" replace />
  }
  return children
}

export function RequireSignupBasic({ children }) {
  const { draft } = useSignupWizard()
  if (!hasCompleteSignupBasic(draft.basic)) {
    return <Navigate to="/signup" replace />
  }
  return children
}

export default function SignupWizardProvider() {
  const [store] = useState(() => createSignupDraftStore())
  const [, setRevision] = useState(0)

  useEffect(() => {
    const unsubscribe = store.subscribe(() => setRevision((current) => current + 1))
    const unsubscribeAuthReset = subscribeSignupAuthReset(store, accessLockCoordinator)
    return () => {
      unsubscribeAuthReset()
      unsubscribe()
      store.clear()
    }
  }, [store])

  const value = { draft: store.read(), store }

  return (
    <SignupWizardContext.Provider value={value}>
      <Outlet />
    </SignupWizardContext.Provider>
  )
}
