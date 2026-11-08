import { Link, useNavigate } from 'react-router-dom'
import '../../styles/pages/auth.css'
import brandLogo from '../../assets/brand/digi-transx-logo.png'
import { hasCompleteSignupBasic } from '../../auth/signupDraft.js'
import { useSignupWizard } from '../../auth/signupWizardContext'

const ROLES = [
  {
    value: 'service_seeker',
    icon: 'fa-box',
    title: 'Service Seeker',
    subtitle: 'I need to move goods',
    desc: 'Post transport jobs, track shipments, manage invoices and documents.',
  },
  {
    value: 'logistics_provider',
    icon: 'fa-truck-fast',
    title: 'Logistics Provider',
    subtitle: 'I transport goods professionally',
    desc: 'Manage your fleet, accept jobs, track earnings and driver documents.',
  },
  {
    value: 'everyday_user',
    icon: 'fa-user',
    title: 'Everyday User',
    subtitle: 'I occasionally need transport',
    desc: 'Simple booking for personal transport needs with a lighter workflow.',
  },
  {
    value: 'driver',
    icon: 'fa-id-card',
    title: 'Truck Driver',
    subtitle: 'I drive commercial vehicles',
    desc: 'Receive trip dispatch requests, stream live GPS location, build reputation & earn in your wallet.',
  },
]

export default function RoleSelect() {
  const navigate = useNavigate()
  const { draft, store } = useSignupWizard()

  function handleSelect(role) {
    if (!hasCompleteSignupBasic(draft.basic)) {
      navigate('/signup')
      return
    }
    if (!store.selectRole(role)) return
    navigate('/signup/terms')
  }

  return (
    <main className="auth-role-page">
      <section className="auth-role-card">
        <div className="auth-role-header">
          <Link to="/login" className="auth-card-brand">
            <img className="auth-card-real-logo" src={brandLogo} alt="" aria-hidden="true" />
            <span className="auth-card-brand-text">
              Digi_Trans<span className="auth-card-brand-accent">X</span>
            </span>
          </Link>
          <h1>What best describes you?</h1>
          <p>Choose your role - you can always update it later.</p>
        </div>

        <div className="auth-steps" aria-label="Signup progress">
          <div className="auth-step auth-step--done">
            <span><i className="fas fa-check" aria-hidden="true"></i></span>
            <strong>Basic Info</strong>
          </div>
          <div className="auth-step-line" />
          <div className="auth-step auth-step--active">
            <span>2</span>
            <strong>Select Role</strong>
          </div>
          <div className="auth-step-line" />
          <div className="auth-step">
            <span>3</span>
            <strong>Terms</strong>
          </div>
          <div className="auth-step-line" />
          <div className="auth-step">
            <span>4</span>
            <strong>Details</strong>
          </div>
        </div>

        <div className="auth-role-grid">
          {ROLES.map((role) => (
            <button
              key={role.value}
              type="button"
              className={`auth-role-option auth-role-option--${role.value}`}
              onClick={() => handleSelect(role.value)}
            >
              <span className="auth-role-option__icon">
                <i className={`fas ${role.icon}`} aria-hidden="true"></i>
              </span>
              <span className="auth-role-option__body">
                <span className="auth-role-option__title">{role.title}</span>
                <span className="auth-role-option__subtitle">{role.subtitle}</span>
                <span className="auth-role-option__desc">{role.desc}</span>
              </span>
              <span className="auth-role-option__arrow">
                <i className="fas fa-arrow-right" aria-hidden="true"></i>
              </span>
            </button>
          ))}
        </div>

        <button
          type="button"
          className="auth-change-role-btn"
          onClick={() => navigate('/signup')}
        >
          <i className="fas fa-arrow-left" aria-hidden="true"></i>
          Back to basic information
        </button>

        <p className="auth-role-footer">
          Already have an account? <Link to="/login">Login here</Link>
        </p>
      </section>
    </main>
  )
}
