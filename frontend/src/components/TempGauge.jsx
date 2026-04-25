import { clsx } from 'clsx'

export function TempGauge({ label, current, target, icon: Icon }) {
  const isHeating = target > 0 && current < target - 2
  const atTemp = target > 0 && current >= target - 2

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
          atTemp && 'text-emerald-500',
          !isHeating && !atTemp && 'text-zinc-700 dark:text-zinc-300'
        )}>
          {current.toFixed(0)}°
        </span>
        {target > 0 && (
          <span className="text-xs text-zinc-400 dark:text-zinc-600">/ {target.toFixed(0)}°</span>
        )}
      </div>
    </div>
  )
}
