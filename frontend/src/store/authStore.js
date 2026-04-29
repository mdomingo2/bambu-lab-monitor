/**
 * Auth store — tracks whether the user is logged in and who they are.
 *
 * The session token lives in an httpOnly cookie managed by the server, so
 * JavaScript never sees it directly. Instead we call /api/auth/me on startup
 * to check if an existing session cookie is still valid.
 */
import { create } from 'zustand'

export const useAuthStore = create((set) => ({
  /**
   * null   = not yet checked (app just loaded)
   * false  = checked, no valid session
   * object = {username, role} — authenticated
   */
  user: null,
  checking: true,

  /** Called once on app startup to see if an existing session cookie is valid. */
  async checkAuth() {
    try {
      const r = await fetch('/api/auth/me', { credentials: 'include' })
      if (r.ok) {
        const user = await r.json()
        set({ user, checking: false })
      } else {
        set({ user: false, checking: false })
      }
    } catch {
      set({ user: false, checking: false })
    }
  },

  /** Log in with username + password. Returns null on success, error string on failure. */
  async login(username, password) {
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (r.ok) {
        const user = await r.json()
        set({ user, checking: false })
        return null
      }
      const body = await r.json().catch(() => ({}))
      return body.detail || 'Login failed'
    } catch {
      return 'Network error — check your connection'
    }
  },

  /** Log out and clear the session cookie. */
  async logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    set({ user: false, checking: false })
  },
}))
