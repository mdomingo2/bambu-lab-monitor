import { clsx } from 'clsx'
import { Droplets } from 'lucide-react'

const HUMIDITY_LABELS = ['—', 'Very wet', 'Wet', 'Moderate', 'Dry', 'Very dry']
const HUMIDITY_COLORS = [
  'text-zinc-400',
  'text-red-500',
  'text-orange-500',
  'text-yellow-500',
  'text-emerald-500',
  'text-emerald-600',
]

function HumidityBadge({ humidity, temp }) {
  const label = HUMIDITY_LABELS[humidity] ?? '—'
  const color = HUMIDITY_COLORS[humidity] ?? 'text-zinc-400'
  return (
    <span className={`flex items-center gap-1 text-[10px] font-medium ${color}`}>
      <Droplets size={10} />
      {label}
      {temp > 0 && <span className="text-zinc-400 font-normal ml-1">{temp.toFixed(1)}°C</span>}
    </span>
  )
}

export function AMSDisplay({ trays = [], units = [], currentTray = -1, compact = false }) {
  if (trays.length === 0) return null

  if (compact) {
    return (
      <div className="flex items-center gap-1 flex-wrap">
        {trays.map((t) => (
          <div
            key={t.slot}
            title={`${t.sub_brand || t.tray_type} — ${t.remain}%`}
            className={clsx(
              'w-3 h-3 rounded-full border',
              t.slot === currentTray
                ? 'border-brand-400 ring-1 ring-brand-400 scale-125'
                : 'border-zinc-300 dark:border-zinc-600'
            )}
            style={{ backgroundColor: t.color }}
          />
        ))}
      </div>
    )
  }

  // Group trays by AMS unit (4 slots per unit)
  const unitCount = Math.max(...trays.map((t) => Math.floor(t.slot / 4))) + 1
  const unitGroups = Array.from({ length: unitCount }, (_, i) =>
    trays.filter((t) => Math.floor(t.slot / 4) === i)
  ).filter((g) => g.length > 0)

  return (
    <div className="flex flex-col gap-4">
      {unitGroups.map((group, i) => {
        const unitInfo = units.find((u) => u.unit_id === i)
        return (
          <div key={i}>
            {(unitGroups.length > 1 || unitInfo) && (
              <div className="flex items-center gap-3 mb-2">
                {unitGroups.length > 1 && (
                  <span className="text-[10px] uppercase tracking-wide text-zinc-400 font-medium">
                    AMS {i + 1}
                  </span>
                )}
                {unitInfo && unitInfo.humidity > 0 && (
                  <HumidityBadge humidity={unitInfo.humidity} temp={unitInfo.temp} />
                )}
              </div>
            )}
            <div className="grid grid-cols-4 gap-2">
              {group.map((t) => (
                <div
                  key={t.slot}
                  className={clsx(
                    'rounded-lg p-2 flex flex-col gap-1 border',
                    t.slot === currentTray
                      ? 'border-brand-400 bg-brand-50 dark:bg-brand-900/20'
                      : 'border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50'
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <div
                      className="w-4 h-4 rounded-full border border-zinc-200 dark:border-zinc-600 shrink-0"
                      style={{ backgroundColor: t.color }}
                    />
                    <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300 truncate">
                      {t.tray_type}
                    </span>
                  </div>
                  {t.sub_brand && (
                    <p className="text-[10px] text-zinc-400 truncate">{t.sub_brand}</p>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-zinc-400">Slot {(t.slot % 4) + 1}</span>
                    <span className="text-[10px] text-zinc-500">{t.remain}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
