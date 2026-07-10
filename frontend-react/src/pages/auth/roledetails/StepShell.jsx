import { Link, useNavigate } from 'react-router-dom'
import '../../../styles/pages/auth.css'

const ICONS = {
  'Service Seeker': 'fa-box',
  'Logistics Provider': 'fa-truck-fast',
  'Everyday User': 'fa-user',
  'Fuel Station Manager': 'fa-gas-pump',
  'Shop Owner / Vendor': 'fa-store',
}

export default function StepShell({ title, subtitle, icon, children }) {
  const navigate = useNavigate()
  const iconClass = ICONS[title] || icon || 'fa-user'

  return (
    <main className="auth-details-page">
      <section className="auth-details-card">
        <div className="auth-details-logo">
          <Link to="/login" className="auth-card-brand">
            <span className="auth-card-logo">
              <svg viewBox="0 0 32 32" fill="none" width="28" height="28" aria-hidden="true">
                <g stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 9 L13 9 L19 23 L27 23"/>
                  <path d="M27 9 L19 9 L13 23 L5 23"/>
                </g>
              </svg>
            </span>
            <span className="auth-card-brand-text">
              Digi_Trans<span>X</span>
            </span>
          </Link>
        </div>

        <div className="auth-steps auth-steps--details" aria-label="Signup progress">
          <div className="auth-step auth-step--done">
            <span><i className="fas fa-check" aria-hidden="true"></i></span>
            <strong>Basic Info</strong>
          </div>
          <div className="auth-step-line" />
          <div className="auth-step auth-step--done">
            <span><i className="fas fa-check" aria-hidden="true"></i></span>
            <strong>Role</strong>
          </div>
          <div className="auth-step-line" />
          <div className="auth-step auth-step--active">
            <span>3</span>
            <strong>Details</strong>
          </div>
        </div>

        <div className="auth-details-heading">
          <span className="auth-details-icon">
            <i className={`fas ${iconClass}`} aria-hidden="true"></i>
          </span>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>

        <div className="auth-details-body">
          {children}
        </div>

        <button type="button" onClick={() => navigate('/signup/role')} className="auth-change-role-btn">
          <i className="fas fa-arrow-left" aria-hidden="true"></i>
          Change role
        </button>
      </section>
    </main>
  )
}
