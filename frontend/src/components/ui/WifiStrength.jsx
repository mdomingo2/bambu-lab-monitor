/**
 * WifiStrength — four ascending bars representing a WiFi dBm reading.
 *
 * Standard RSSI scale used by most wireless vendors:
 *   ≥ −50 dBm  → 4 bars  excellent
 *   −50..−60   → 3 bars  good
 *   −60..−70   → 2 bars  fair
 *   −70..−80   → 1 bar   poor
 *   < −80 dBm  → 0 bars  very poor
 *
 * Props:
 *   value   Raw wifi_signal string from MQTT, e.g. "-65dBm" or "-72dBm".
 *   size    "xs" (card footer) | "sm" (default, detail view)
 */

/** Extract the integer dBm value from strings like "-65dBm" or "-72". */
function parsedBm(raw) {
  if (!raw) return null
  const match = String(raw).match(/-?\d+/)
  return match ? parseInt(match[0], 10) : null
}

function barsFromdBm(dbm) {
  if (dbm === null) return 0
  if (dbm >= -50) return 4
  if (dbm >= -60) return 3
  if (dbm >= -70) return 2
  if (dbm >= -80) return 1
  return 0
}

/** Color for active bars — green when strong, amber when fair, red when poor. */
function activeColor(bars) {
  if (bars >= 3) return 'bg-emerald-500'
  if (bars === 2) return 'bg-amber-400'
  return 'bg-red-500'
}

export function WifiStrength({ value, size = 'sm' }) {
  const dbm  = parsedBm(value)
  const bars = barsFromdBm(dbm)
  const fill = activeColor(bars)

  // Four bars with ascending heights. xs = compact card footer.
  const heights = size === 'xs'
    ? ['h-[4px]', 'h-[6px]', 'h-[8px]', 'h-[10px]']
    : ['h-[6px]', 'h-[9px]', 'h-[12px]', 'h-[15px]']

  const width = size === 'xs' ? 'w-[3px]' : 'w-[4px]'

  return (
    <span
      className="inline-flex items-end gap-[2px]"
      title={dbm !== null ? `${dbm} dBm` : 'No signal data'}
      aria-label={`Wi-Fi signal: ${bars} of 4 bars`}
    >
      {heights.map((h, i) => (
        <span
          key={i}
          className={`${width} ${h} rounded-sm ${i < bars ? fill : 'bg-zinc-300 dark:bg-zinc-600'}`}
        />
      ))}
    </span>
  )
}
