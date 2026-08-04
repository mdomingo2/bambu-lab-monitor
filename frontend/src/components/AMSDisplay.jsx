import { clsx } from 'clsx'
import { HumidityLevel } from './ui/HumidityLevel'

const DEFAULT_SLOTS = 4  // fallback for units with no slot_count

/**
 * Per-model unit label overrides. Index = unit_id from firmware.
 * H2D has two single-slot AMS units (one per nozzle) plus an
 * optional high-temperature AMS (unit_id 2) labelled "AMS-HT".
 * All other printers fall back to generic "AMS {n}" labelling.
 *
 * The H2S is deliberately absent: it is the single-nozzle H2, so it has no
 * left/right nozzle pairing and its units are plain "AMS 1..n".
 */
const UNIT_LABELS = {
  H2D: ['Right AMS', 'Left AMS', 'AMS-HT'],
}

/**
 * Per-model display order of unit_ids.
 * H2D: show Left (unit 1), then Right (unit 0), then HT (unit 2).
 * Models without an entry here keep the firmware's natural order.
 */
const UNIT_ORDER = {
  H2D: [1, 0, 2],
}

function unitLabel(model, unitIdx, multiUnit) {
  const labels = UNIT_LABELS[model]
  if (labels?.[unitIdx]) return labels[unitIdx]
  return multiUnit ? `AMS ${unitIdx + 1}` : 'AMS'
}

/**
 * Build an ordered list of unit indices for display.
 * Uses UNIT_ORDER if defined for this model, otherwise natural order.
 */
function unitIndices(trays, units, model) {
  const raw = units.length > 0
    ? units.map((u) => u.unit_id)
    : trays.length === 0
      ? []
      : Array.from(
          { length: Math.max(...trays.map((t) => Math.floor(t.slot / DEFAULT_SLOTS))) + 1 },
          (_, i) => i
        )

  const order = UNIT_ORDER[model]
  if (!order) return raw
  // Show indices in the prescribed order, then append any extras not covered
  const ordered = order.filter((i) => raw.includes(i))
  const extras  = raw.filter((i) => !order.includes(i))
  return [...ordered, ...extras]
}

/**
 * Return all physical slots for a unit as [tray | null], filling gaps with null.
 * slotCount comes from AMSUnit.slot_count (1 for H2D, 4 for standard AMS).
 */
function slotsForUnit(trays, unitIdx, slotCount) {
  return Array.from({ length: slotCount }, (_, s) => {
    const globalSlot = unitIdx * DEFAULT_SLOTS + s
    return trays.find((t) => t.slot === globalSlot) ?? null
  })
}

export function AMSDisplay({ trays = [], units = [], currentTray = -1, compact = false, model = '' }) {
  const indices = unitIndices(trays, units, model)
  if (indices.length === 0) return null

  const multiUnit = indices.length > 1

  // ── Compact (card row) ────────────────────────────────────────────────────
  if (compact) {
    return (
      <div className="flex flex-col gap-1.5">
        {indices.map((unitIdx) => {
          const unitInfo  = units.find((u) => u.unit_id === unitIdx)
          const slotCount = unitInfo?.slot_count ?? DEFAULT_SLOTS
          const slots     = slotsForUnit(trays, unitIdx, slotCount)

          return (
            <div key={unitIdx} className="flex items-center gap-2">
              {multiUnit && (
                <span className="text-[9px] uppercase tracking-wide text-zinc-400 w-7 shrink-0">
                  {unitLabel(model, unitIdx, multiUnit)}
                </span>
              )}

              {/* 4 dots, filled or hollow-dashed for empty */}
              <div className="flex items-center gap-1 flex-1">
                {slots.map((t, s) =>
                  t ? (
                    <div
                      key={s}
                      title={`Slot ${s + 1} — ${t.sub_brand || t.tray_type} · ${t.remain}%`}
                      className={clsx(
                        'w-3 h-3 rounded-full border transition-transform',
                        t.slot === currentTray
                          ? 'border-brand-400 ring-1 ring-brand-400 scale-125'
                          : 'border-zinc-300 dark:border-zinc-600'
                      )}
                      style={{ backgroundColor: t.color }}
                    />
                  ) : (
                    <div
                      key={s}
                      title={`Slot ${s + 1} — empty`}
                      className="w-3 h-3 rounded-full border border-dashed border-zinc-300 dark:border-zinc-600 bg-transparent"
                    />
                  )
                )}
              </div>

              {unitInfo && unitInfo.humidity > 0 && (
                <HumidityLevel level={unitInfo.humidity} size="xs" />
              )}
            </div>
          )
        })}
      </div>
    )
  }

  // ── Full / detail view ────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-3">
      {indices.map((unitIdx) => {
        const unitInfo  = units.find((u) => u.unit_id === unitIdx)
        const slotCount = unitInfo?.slot_count ?? DEFAULT_SLOTS
        const slots     = slotsForUnit(trays, unitIdx, slotCount)

        return (
          <div
            key={unitIdx}
            className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/40 overflow-hidden"
          >
            {/* Unit header bar */}
            <div className="flex items-center gap-3 px-3 py-2 border-b border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
              <span className="text-[10px] uppercase tracking-wide text-zinc-400 font-semibold">
                {unitLabel(model, unitIdx, multiUnit)}
              </span>
              {unitInfo && unitInfo.humidity > 0 && (
                <HumidityLevel
                  level={unitInfo.humidity}
                  size="sm"
                  showLabel
                  temp={unitInfo.temp}
                />
              )}
            </div>

            {/* slot grid — columns match actual slot count */}
            <div className={clsx(
              'grid gap-2 p-3',
              slotCount === 1 ? 'grid-cols-1' :
              slotCount === 2 ? 'grid-cols-2' :
              slotCount === 3 ? 'grid-cols-3' :
                                'grid-cols-4'
            )}>
              {slots.map((t, s) => {
                const globalSlot = unitIdx * DEFAULT_SLOTS + s
                const isActive   = globalSlot === currentTray

                return t ? (
                  /* ── Loaded slot ── */
                  <div
                    key={s}
                    className={clsx(
                      'rounded-lg p-2 flex flex-col gap-1 border transition-colors',
                      isActive
                        ? 'border-brand-400 bg-brand-50 dark:bg-brand-900/20'
                        : 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/60'
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <div
                        className={clsx(
                          'w-4 h-4 rounded-full shrink-0 border',
                          isActive
                            ? 'border-brand-300 dark:border-brand-600'
                            : 'border-zinc-200 dark:border-zinc-600'
                        )}
                        style={{ backgroundColor: t.color }}
                      />
                      <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300 truncate">
                        {t.tray_type}
                      </span>
                    </div>
                    {t.sub_brand && (
                      <p className="text-[10px] text-zinc-400 truncate">{t.sub_brand}</p>
                    )}
                    <div className="flex items-center justify-between mt-auto">
                      <span className={clsx(
                        'text-[10px]',
                        isActive ? 'text-brand-500 font-medium' : 'text-zinc-400'
                      )}>
                        Slot {s + 1}
                      </span>
                      <span className="text-[10px] text-zinc-500">{t.remain}%</span>
                    </div>
                  </div>
                ) : (
                  /* ── Empty slot ── */
                  <div
                    key={s}
                    className="rounded-lg p-2 flex flex-col items-center justify-center gap-1.5 border border-dashed border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-900/20 min-h-[72px]"
                  >
                    <div className="w-4 h-4 rounded-full border-2 border-dashed border-zinc-300 dark:border-zinc-600" />
                    <span className="text-[10px] text-zinc-400">Slot {s + 1}</span>
                    <span className="text-[9px] text-zinc-300 dark:text-zinc-600 font-medium uppercase tracking-wide">
                      Empty
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
