/**
 * HumidityLevel — five ascending bars for AMS desiccant/humidity level.
 *
 * Bambu AMS reports humidity on a 1–5 integer scale:
 *   5 = Very dry  (ideal — filament is well protected)
 *   4 = Dry
 *   3 = Moderate
 *   2 = Wet
 *   1 = Very wet  (filament at risk)
 *
 * Each level gets its own bar count AND colour for maximum separation:
 *   5 → 5 bars  orange-500   (very dry — warm/desert)
 *   4 → 4 bars  amber-400    (dry — warm/golden)
 *   3 → 3 bars  slate-400    (moderate — neutral)
 *   2 → 2 bars  sky-400      (wet — medium blue)
 *   1 → 1 bar   blue-700     (very wet — deep blue)
 *   0 → 0 bars  zinc-400     (no data — dim)
 *
 * Props:
 *   level      integer 0–5 from the AMS unit
 *   size       "xs" (card compact) | "sm" (default, detail view)
 *   showLabel  render the text label after the bars (e.g. "Dry")
 *   temp       optional °C value rendered to the right of the label
 */

import { Droplets } from 'lucide-react'
import { useUnitStore } from '../../store/unitStore'
import { formatTemp } from '../../utils/temperature'

const LABELS = ['—', 'Very wet', 'Wet', 'Moderate', 'Dry', 'Very dry']

// [barBgClass, iconTextClass] per level
const LEVEL_COLORS = [
  ['bg-zinc-400',   'text-zinc-400'],   // 0 — no data
  ['bg-blue-700',   'text-blue-700'],   // 1 — very wet
  ['bg-sky-400',    'text-sky-400'],    // 2 — wet
  ['bg-slate-400',  'text-slate-400'],  // 3 — moderate
  ['bg-amber-400',  'text-amber-400'],  // 4 — dry
  ['bg-orange-500', 'text-orange-500'], // 5 — very dry
]

export function HumidityLevel({ level, size = 'sm', showLabel = false, temp = null }) {
  const tempUnit              = useUnitStore((s) => s.tempUnit)
  const safeLevel             = Math.max(0, Math.min(5, level ?? 0))
  const [barColor, iconColor] = LEVEL_COLORS[safeLevel]
  const label                 = LABELS[safeLevel] ?? '—'

  // 5 bars with ascending heights; safeLevel bars are lit, the rest are dim
  const heights = size === 'xs'
    ? ['h-[3px]', 'h-[5px]', 'h-[7px]', 'h-[9px]', 'h-[11px]']
    : ['h-[4px]', 'h-[7px]', 'h-[10px]', 'h-[13px]', 'h-[16px]']
  const width    = size === 'xs' ? 'w-[2px]' : 'w-[3px]'
  const iconSize = size === 'xs' ? 9 : 11

  return (
    <span
      className="inline-flex items-center gap-[3px]"
      title={`Humidity: ${label}`}
      aria-label={`Humidity level: ${label}`}
    >
      <Droplets size={iconSize} className={`${iconColor} shrink-0`} />
      {/* bars — bottom-aligned so they step up like a signal meter */}
      <span className="inline-flex items-end gap-[2px]">
        {heights.map((h, i) => (
          <span
            key={i}
            className={`${width} ${h} rounded-sm ${
              i < safeLevel ? barColor : 'bg-zinc-300 dark:bg-zinc-600'
            }`}
          />
        ))}
      </span>
      {showLabel && (
        <span className={`text-[10px] font-medium ml-0.5 ${iconColor}`}>{label}</span>
      )}
      {temp != null && temp > 0 && (
        <span className="text-[10px] text-zinc-400 font-normal ml-1">
          {formatTemp(temp, tempUnit)}
        </span>
      )}
    </span>
  )
}
