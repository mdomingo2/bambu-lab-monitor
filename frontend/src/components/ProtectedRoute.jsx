import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

/**
 * Wraps any route that requires authentication.
 *
 * Renders a loading spinner while the auth check is in progress (the
 * very first render before /api/auth/me responds), then either renders
 * the children or redirects to /login.
 */
export function ProtectedRoute({ children }) {
  const user     = useAuthStore((s) => s.user)
  const checking = useAuthStore((s) => s.checking)

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <span className="w-8 h-8 border-2 border-brand-600/30 border-t-brand-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return children
}
