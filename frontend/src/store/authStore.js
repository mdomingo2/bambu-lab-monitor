/**
 * authStore — scaffold for future account-based authentication.
 *
 * Currently unauthenticated: `isAuthenticated` is always true so all routes
 * are accessible without a login.  When auth is implemented, replace the
 * `login` and `logout` actions with real API calls and token management.
 *
 * Persisted to localStorage under "bambu-auth" so the session survives
 * page refreshes once login is wired up.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      /** The authenticated user object, or null when logged out. */
      user: null,

      /** Derived: true when a user session is active. */
      get isAuthenticated() {
        // TODO: return this.user !== null once login is implemented.
        return true
      },

      /**
       * Log in with username + password.
       * TODO: replace with a real POST /api/auth/login call that returns a
       * JWT or session token, then store the decoded user object here.
       */
      login: async (_username, _password) => {
        // Placeholder — auth not yet implemented.
        throw new Error('Authentication not yet implemented.')
      },

      /**
       * Clear the current session.
       * TODO: also call DELETE /api/auth/session (or clear the JWT cookie).
       */
      logout: () => set({ user: null }),
    }),
    {
      name: 'bambu-auth',
      // Only persist the user object, not action functions.
      partialize: (state) => ({ user: state.user }),
    }
  )
)
