import { Link, useNavigate } from 'react-router-dom'
import '../../styles/pages/auth.css'

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
    value: 'fuel_station_manager',
    icon: 'fa-gas-pump',
    title: 'Fuel Station Manager',
    subtitle: 'I run a fuel pump or station',
    desc: 'Manage fuel stock, truck refuelling logs, payments and daily sales.',
  },
  {
    value: 'shopkeeper',
    icon: 'fa-store',
    title: 'Shop Owner / Vendor',
    subtitle: 'I run a shop or sell products',
    desc: 'Build product tables, track stock, analyse sales and export reports.',
  },
]

const ROLE_NEXT = {
  service_seeker: '/signup/details/service-seeker',
  logistics_provider: '/signup/details/logistics-provider',
  everyday_user: '/signup/details/everyday-user',
  fuel_station_manager: '/signup/details/fuel-station',
  shopkeeper: '/signup/details/shopkeeper',
}

export default function RoleSelect() {
  const navigate = useNavigate()

  function handleSelect(role) {
    const basic = sessionStorage.getItem('signup_basic')
    if (!basic) {
      navigate('/signup')
      return
    }
    sessionStorage.setItem('signup_role', role)
    navigate(ROLE_NEXT[role])
  }

  return (
    <main className="auth-role-page">
      <section className="auth-role-card">
        <div className="auth-role-header">
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

        <p className="auth-role-footer">
          Already have an account? <Link to="/login">Login here</Link>
        </p>
      </section>
    </main>
  )
}
