/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from 'react'

export const AUTH_STATUSES = Object.freeze({
  CHECKING: 'checking',
  PRESENTED: 'presented',
  VERIFIED: 'verified',
  LOCKED: 'locked',
  TEMPORARILY_UNAVAILABLE: 'temporarily_unavailable',
  UNAUTHORIZED: 'unauthorized',
})

const AuthVerificationContext = createContext({
  status: AUTH_STATUSES.CHECKING,
  user: null,
})

export function AuthVerificationProvider({ value, children }) {
  return (
    <AuthVerificationContext.Provider value={value}>
      {children}
    </AuthVerificationContext.Provider>
  )
}

export function useAuthVerification() {
  return useContext(AuthVerificationContext)
}

export function ShellPageSkeleton() {
  return (
    <section className="shell-page-skeleton" aria-busy="true" aria-live="polite">
      <div className="shell-page-skeleton__header">
        <span />
        <strong />
      </div>
      <div className="shell-page-skeleton__grid">
        <span />
        <span />
        <span />
      </div>
    </section>
  )
}
