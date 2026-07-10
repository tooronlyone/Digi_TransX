import { Link } from 'react-router-dom'

export default function AuthCard({ title, subtitle, children }) {
  return (
    <div className="auth-card-page min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="auth-card w-full max-w-md bg-white rounded-xl shadow-lg p-8">
        <div className="auth-card-header text-center mb-6">
          <Link to="/login" className="auth-card-brand inline-flex items-center justify-center gap-3 no-underline">
            <span className="auth-card-logo inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-500 shadow-lg shadow-blue-500/25">
              <svg viewBox="0 0 32 32" fill="none" width="28" height="28" aria-hidden="true">
                <g stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 9 L13 9 L19 23 L27 23"/>
                  <path d="M27 9 L19 9 L13 23 L5 23"/>
                </g>
              </svg>
            </span>
            <span className="auth-card-brand-text text-3xl font-bold text-slate-900">
              Digi_Trans
              <span
                style={{
                  background: 'linear-gradient(135deg,#2563eb,#3b82f6)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                X
              </span>
            </span>
          </Link>
          {title && <h1 className="auth-card-title text-2xl font-semibold text-gray-800 mt-3">{title}</h1>}
          {subtitle && <p className="auth-card-subtitle text-gray-500 text-sm mt-1">{subtitle}</p>}
        </div>
        {children}
      </div>
    </div>
  )
}
