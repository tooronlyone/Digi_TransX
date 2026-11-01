import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import AuthCard from '../../components/common/AuthCard'
import { useSignupWizard } from '../../auth/signupWizardContext'
import { ROLE_NEXT } from '../../auth/signupRoles'

export default function SignupTerms() {
  const { draft, store } = useSignupWizard()
  const navigate = useNavigate()
  const [document, setDocument] = useState(null)
  const [error, setError] = useState('')
  const [accepted, setAccepted] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/auth/signup-terms?role=${encodeURIComponent(draft.role)}`, {
      credentials: 'same-origin', signal: controller.signal,
    }).then(async response => {
      const data = await response.json()
      if (!response.ok || !data.success) throw new Error(data.message || 'Unable to load terms.')
      if (!controller.signal.aborted) setDocument(data)
    }).catch(failure => {
      if (!controller.signal.aborted) setError(failure.message || 'Unable to load terms. Please try again.')
    })
    return () => controller.abort()
  }, [draft.role])

  if (!ROLE_NEXT[draft.role]) return <Navigate to="/signup/role" replace />

  function continueSignup(event) {
    event.preventDefault()
    if (!accepted || document?.role !== draft.role) return
    if (store.acceptTerms(document.version, document.role)) navigate(ROLE_NEXT[draft.role])
  }

  return <AuthCard title="Terms & Conditions" subtitle={`Review your agreement before completing your ${document?.role_label || 'selected role'} account.`}>
    {error ? <p role="alert">{error} <Link to="/signup/role">Return to role selection</Link></p> : !document ? <p role="status">Loading your agreement...</p> : <form onSubmit={continueSignup} className="auth-details-form">
      <div className="signup-terms-sections">
        {document.sections.map(section => <section key={section.title}>
          <h2>{section.title}</h2>
          <p>{section.text}</p>
        </section>)}
      </div>
      <p className="auth-help">Agreement version: {document.version}</p>
      <label className="signup-terms-acceptance">
        <input type="checkbox" required checked={accepted} onChange={event => setAccepted(event.target.checked)} />
        <span>I have read and agree to these Terms & Conditions for my {document.role_label} account, including the goods insurance notice.</span>
      </label>
      <button className="auth-submit" type="submit" disabled={!accepted}>Agree and continue</button>
      <Link to="/signup/role">Change role</Link>
    </form>}
  </AuthCard>
}
