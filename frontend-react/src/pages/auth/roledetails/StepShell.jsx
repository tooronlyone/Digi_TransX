import { Link, useNavigate } from 'react-router-dom'

export default function StepShell({ title, subtitle, icon, children }) {
  const navigate = useNavigate()
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white rounded-xl shadow-lg p-8">
        {/* Logo */}
        <div className="text-center mb-6">
          <Link to="/login">
            <span className="text-3xl font-bold text-blue-500">DigiTransX</span>
          </Link>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">✓</div>
            <span className="text-xs text-gray-400">Basic Info</span>
          </div>
          <div className="w-8 h-px bg-blue-300" />
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">✓</div>
            <span className="text-xs text-gray-400">Role</span>
          </div>
          <div className="w-8 h-px bg-blue-300" />
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">3</div>
            <span className="text-xs font-semibold text-blue-600">Details</span>
          </div>
        </div>

        {/* Role header */}
        <div className="text-center mb-6">
          <span className="text-4xl">{icon}</span>
          <h1 className="text-xl font-bold text-gray-800 mt-2">{title}</h1>
          <p className="text-gray-500 text-sm mt-1">{subtitle}</p>
        </div>

        {children}

        <button onClick={() => navigate('/signup/role')}
          className="w-full mt-3 py-2.5 border border-gray-200 text-gray-500 text-sm rounded-lg hover:bg-gray-50 transition-colors">
          ← Change role
        </button>
      </div>
    </div>
  )
}
