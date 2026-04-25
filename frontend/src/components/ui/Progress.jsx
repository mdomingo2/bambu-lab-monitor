/**
 * Progress — a thin horizontal progress bar.
 *
 * Props:
 *   value   0–100 (clamped)
 *   color   brand | emerald | amber | red  (default: brand)
 *   className  additional classes applied to the track
 */
import { clsx } from 'clsx'

const TRACK_COLORS = {
  brand:   'bg-brand-500',
  emerald: 'bg-emerald-500',
  amber:   'bg-amber-500',
  red:     'bg-red-500',
}

export function Progress({ value = 0, className, color = 'brand' }) {
  const fill = Math.min(100, Math.max(0, value))
  return (
    <div className={clsx(
      'w-full rounded-full h-2 overflow-hidden',
      'bg-zinc-200 dark:bg-zinc-800',   // visible in both light and dark mode
      className,
    )}>
      <div
        className={clsx('h-full rounded-full transition-all duration-500', TRACK_COLORS[color] ?? TRACK_COLORS.brand)}
        style={{ width: `${fill}%` }}
      />
    </div>
  )
}
