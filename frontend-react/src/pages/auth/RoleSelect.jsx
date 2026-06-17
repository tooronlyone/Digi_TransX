import { useNavigate } from 'react-router-dom'
import { Link } from 'react-router-dom'

const ROLES = [
  {
    value: 'service_seeker',
    icon: '📦',
    title: 'Service Seeker',
    subtitle: 'I need to move goods',
    desc: 'Post transport jobs, track shipments, manage invoices & documents.',
    color: 'border-emerald-400 bg-emerald-50',
    badge: 'bg-emerald-100 text-emerald-700',
    check: 'bg-emerald-500',
  },
  {
    value: 'logistics_provider',
    icon: '🚛',
    title: 'Logistics Provider',
    subtitle: 'I transport goods professionally',
    desc: 'Manage your fleet, accept jobs, track earnings and driver documents.',
    color: 'border-blue-400 bg-blue-50',
    badge: 'bg-blue-100 text-blue-700',
    check: 'bg-blue-500',
  },
  {
    value: 'everyday_user',
    icon: '🙋',
    title: 'Everyday User',
    subtitle: 'I occasionally need transport',
    desc: 'Simple booking for personal transport needs — no complex features.',
    color: 'border-violet-400 bg-violet-50',
    badge: 'bg-violet-100 text-violet-700',
    check: 'bg-violet-500',
  },
  {
    value: 'fuel_station_manager',
    icon: '⛽',
    title: 'Fuel Station Manager',
    subtitle: 'I run a fuel pump / station',
    desc: 'Manage fuel stock, truck refuelling logs, payments and daily sales.',
    color: 'border-amber-400 bg-amber-50',
    badge: 'bg-amber-100 text-amber-700',
    check: 'bg-amber-500',
  },
  {
    value: 'shopkeeper',
    icon: '🛒',
    title: 'Shop Owner / Vendor',
    subtitle: 'I run a shop or sell products',
    desc: 'Build your own product tables, track stock, analyse sales and export reports.',
    color: 'border-orange-400 bg-orange-50',
    badge: 'bg-orange-100 text-orange-700',
    check: 'bg-orange-500',
  },
]

const ROLE_NEXT = {
  service_seeker:       '/signup/details/service-seeker',
  logistics_provider:   '/signup/details/logistics-provider',
  everyday_user:        '/signup/details/everyday-user',
  fuel_station_manager: '/signup/details/fuel-station',
  shopkeeper:           '/signup/details/shopkeeper',
}

export default function RoleSelect() {
  const navigate = useNavigate()

  function handleSelect(role) {
    const basic = sessionStorage.getItem('signup_basic')
    if (!basic) { navigate('/signup'); return }
    sessionStorage.setItem('signup_role', role)
    navigate(ROLE_NEXT[role])
  }

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-white rounded-xl shadow-lg p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <Link to="/login">
            <span className="text-3xl font-bold text-blue-500">DigiTransX</span>
          </Link>
          <h1 className="text-2xl font-semibold text-gray-800 mt-3">What best describes you?</h1>
          <p className="text-gray-500 text-sm mt-1">Choose your role — you can always update it later</p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">✓</div>
            <span className="text-xs text-gray-400">Basic Info</span>
          </div>
          <div className="w-8 h-px bg-blue-300" />
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">2</div>
            <span className="text-xs font-semibold text-blue-600">Select Role</span>
          </div>
          <div className="w-8 h-px bg-gray-200" />
          <div className="flex items-center gap-1">
            <div className="w-6 h-6 rounded-full bg-gray-200 text-gray-400 text-xs flex items-center justify-center font-bold">3</div>
            <span className="text-xs text-gray-400">Details</span>
          </div>
        </div>

        {/* Role grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {ROLES.map(r => (
            <button key={r.value} onClick={() => handleSelect(r.value)}
              className={`text-left p-4 border-2 rounded-xl transition-all hover:scale-[1.02] hover:shadow-md ${r.color} cursor-pointer`}>
              <div className="flex items-start gap-3">
                <span className="text-3xl">{r.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="font-bold text-gray-800 text-sm">{r.title}</p>
                  </div>
                  <p className="text-xs font-medium text-gray-500 mb-1">{r.subtitle}</p>
                  <p className="text-xs text-gray-500 leading-relaxed">{r.desc}</p>
                </div>
              </div>
            </button>
          ))}
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-blue-500 hover:underline font-medium">Login here</Link>
        </p>
      </div>
    </div>
  )
}
