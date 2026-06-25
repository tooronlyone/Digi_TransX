import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function AdminLogin() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/auth/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ loginId: form.email, password: form.password }),
      })
      const json = await response.json().catch(() => ({}))
      if (!response.ok || json.success === false) throw new Error(json.message || 'Login failed.')
      if ((json.user?.role || '').trim().toLowerCase() !== 'platform_admin') {
        throw new Error('Not an admin account')
      }
      sessionStorage.setItem('user', JSON.stringify(json.user))
      sessionStorage.setItem('user_id', String(json.user.id))
      sessionStorage.setItem('user_role', json.user.role)
      if (json.csrf_token) sessionStorage.setItem('csrf_token', json.csrf_token)
      navigate('/admin/dashboard', { replace: true })
    } catch (loginError) {
      setError(loginError.message || 'Unable to login.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-950 px-4 text-slate-100">
      <form onSubmit={submit} className="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-6 shadow-xl">
        <h1 className="text-2xl font-bold text-white">Platform Admin</h1>
        <div className="mt-6 space-y-4">
          <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-cyan-400" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-cyan-400" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        {error && <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
        <button disabled={loading} className="mt-6 w-full rounded-lg bg-cyan-400 px-4 py-3 text-sm font-bold text-slate-950 hover:bg-cyan-300 disabled:opacity-60">
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}

