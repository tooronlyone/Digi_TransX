import { createContext, useContext } from 'react'

export const SignupWizardContext = createContext(null)

export function useSignupWizard() {
  const value = useContext(SignupWizardContext)
  if (!value) throw new Error('Signup wizard is unavailable outside its route boundary.')
  return value
}
