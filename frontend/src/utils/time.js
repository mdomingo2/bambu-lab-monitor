/**
 * Time formatting utilities shared across pages and components.
 */

/**
 * Format a duration in minutes as a human-readable string.
 * Returns '—' for falsy input (0, null, undefined).
 *
 * @example
 *   formatTime(90)  // '1h 30m'
 *   formatTime(45)  // '45m'
 *   formatTime(0)   // '—'
 */
export function formatTime(minutes) {
  if (!minutes) return '—'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

/**
 * Compute an ETA wall-clock time string from a remaining-minutes value.
 * Returns null for falsy input.
 *
 * @example
 *   eta(90)  // '3:45 PM'  (locale-formatted)
 */
export function eta(minutes) {
  if (!minutes) return null
  return new Date(Date.now() + minutes * 60_000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}
