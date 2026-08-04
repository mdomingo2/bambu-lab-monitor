import { AlertCircle } from 'lucide-react'

/**
 * Inline error banner.
 *
 * Renders nothing when there is no message, so callers can pass their error
 * state straight through without guarding at every call site.
 *
 * `className` is for layout only (margins, width) — the surrounding pages
 * position this differently. Colours stay here so every error in the app
 * looks the same.
 */
export function ErrorMessage({ message, className = '' }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm ${className}`}
    >
      <AlertCircle size={14} className="shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  )
}
