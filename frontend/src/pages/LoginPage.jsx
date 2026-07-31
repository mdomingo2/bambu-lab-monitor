import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { AlertCircle, LogIn } from 'lucide-react'

export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const login    = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setLoading(true)
    setError('')
    const err = await login(username.trim(), password)
    setLoading(false)
    if (err) {
      setError(err)
    } else {
      navigate('/', { replace: true })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo / title */}
        <div className="flex flex-col items-center mb-8 gap-4">
          <img src="/logo-badge.png" alt="Justin's 3D Printing Lab" className="w-24 h-24 drop-shadow-lg" />
          <div className="flex flex-col items-center text-center gap-1.5">
            <div className="layer-rule" aria-hidden="true" />
            <h1 className="heading text-2xl leading-tight">Justin&rsquo;s 3D Printing Lab</h1>
            <p className="text-xs font-mono text-zinc-500 dark:text-zinc-400 tracking-wide uppercase">
              Farm monitor · Est. 2025 · Jamison, PA
            </p>
          </div>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 border-t-[3px] border-t-brand-500 rounded-lg shadow-sm p-6 flex flex-col gap-4"
        >
          {error && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={15} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="label">Username</label>
            <input
              className="input"
              type="text"
              autoComplete="username"
              placeholder="admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus
            />
          </div>

          <div>
            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            disabled={loading || !username.trim() || !password}
            className="btn-primary flex items-center justify-center gap-2 py-2.5 mt-1"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-navy-950/30 border-t-navy-950 rounded-full animate-spin" />
            ) : (
              <LogIn size={16} />
            )}
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-center text-xs text-zinc-400 dark:text-zinc-600 mt-6">
          First time? Check the backend container logs for your auto-generated password.
        </p>
      </div>
    </div>
  )
}
