import { clsx } from 'clsx'
import { useUnitStore } from '../store/unitStore'
import { formatTemp } from '../utils/temperature'

export function TempGauge({ label, current, target, icon: Icon }) {
  const tempUnit = useUnitStore((s) => s.tempUnit)

  // Heating/cooling logic stays in Celsius (raw values)
  const isHeating = target > 0 && current < target - 2
  const atTemp    = target > 0 && current >= target - 2
  const isCooling = target === 0 && current > 40

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-zinc-400 dark:text-zinc-500">
        {Icon && <Icon size={12} />}
        <span>{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={clsx(
          'text-lg font-semibold tabular-nums',
          isHeating && 'text-red-500 animate-pulse-slow',
          atTemp    && 'text-emerald-500',
          isCooling && 'text-blue-400',
          !isHeating && !atTemp && !isCooling && 'text-zinc-700 dark:text-zinc-300'
        )}>
          {formatTemp(current, tempUnit)}
        </span>
        {target > 0 && (
          <span className="text-xs text-zinc-400 dark:text-zinc-600">
            / {formatTemp(target, tempUnit)}
          </span>
        )}
      </div>
    </div>
  )
}
