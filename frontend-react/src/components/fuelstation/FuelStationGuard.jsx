import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'

export default function FuelStationGuard({ children }) {
  const navigate = useNavigate()
  const { status, user } = useAuthVerification()

  useEffect(() => {
    if (!user?.id) return
    if (String(user.role || '').trim().toLowerCase() !== 'fuel_station_manager') {
      navigate(user.redirect || user.organization_default_route || '/login', { replace: true })
    }
  }, [navigate, user])

  if (!user?.id && status === AUTH_STATUSES.CHECKING) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center flex-col gap-3">
        <div className="w-8 h-8 border-4 border-amber-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-400 text-sm">Checking fuel station session...</p>
      </div>
    )
  }

  if (status !== AUTH_STATUSES.VERIFIED) return <ShellPageSkeleton />

  return children
}
