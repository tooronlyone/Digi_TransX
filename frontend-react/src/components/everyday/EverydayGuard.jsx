import useEverydayAuth from '../../hooks/useEverydayAuth'

// Gates the /everyday/* surface: everyday users pass; business seekers are
// redirected to /client/*, and unauthenticated users to /login (handled inside
// useEverydayAuth). Mirrors ClientGuard's loading UX.
export default function EverydayGuard({ children }) {
  const { ready } = useEverydayAuth()

  if (!ready) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        <p className="text-sm text-slate-500">Checking session...</p>
      </div>
    )
  }

  return children
}
