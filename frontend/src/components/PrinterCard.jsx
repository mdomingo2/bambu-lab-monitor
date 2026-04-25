/**
 * PrinterCard — compact farm-view tile for a single printer.
 *
 * Clicking the card navigates to the printer detail page.
 * The light and camera buttons in the footer act in place without navigating.
 * The outer element is a <div role="button"> rather than <button> to allow
 * nested <button> elements without triggering an HTML validity violation.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Layers, Wind, AlertTriangle, Video, Lightbulb, ShieldAlert } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { Progress } from './ui/Progress'
import { AMSDisplay } from './AMSDisplay'
import { CameraModal } from './CameraModal'
import { WifiStrength } from './ui/WifiStrength'
import { PrinterIcon } from './ui/PrinterIcon'

// Chamber temps below this threshold are noise (no enclosure / cloud mode).
const CHAMBER_TEMP_MIN = 15

const MODEL_ACCENT = {
  A1:  'border-t-violet-500',
  P1S: 'border-t-brand-500',
  P2S: 'border-t-emerald-500',
  H2D: 'border-t-amber-500',
}

function formatTime(minutes) {
  if (!minutes) return '—'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

/** Compact temperature cell: "72° /210°" on one line. */
function TempCell({ label, current, target }) {
  const c = current ?? 0
  const t = target  ?? 0
  const isHeating = t > 0 && c < t - 2
  const atTemp    = t > 0 && c >= t - 2

  const valueClass = isHeating
    ? 'text-red-500'
    : atTemp
      ? 'text-emerald-500'
      : 'text-zinc-700 dark:text-zinc-300'

  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] text-zinc-400 leading-none">{label}</span>
      <span className={`text-sm font-semibold tabular-nums leading-tight ${valueClass}`}>
        {c.toFixed(0)}°
        {t > 0 && (
          <span className="text-[11px] font-normal text-zinc-400 ml-0.5">
            /{t.toFixed(0)}°
          </span>
        )}
      </span>
    </div>
  )
}

/** Dismiss a single HMS alert for a printer. State update arrives via WebSocket. */
async function dismissAlert(printerId, hmsCode) {
  await fetch(`/api/printers/${printerId}/dismissed-alerts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hms_code: hmsCode }),
  })
}

/** Send a light toggle command to the backend without any UI state change.
 *  The new state will arrive via MQTT → WebSocket shortly after. */
async function toggleLight(printerId, currentMode) {
  const next = currentMode === 'on' ? 'off' : 'on'
  await fetch(`/api/printers/${printerId}/light`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: next }),
  })
}

export function PrinterCard({ printer, status, dismissed = [] }) {
  const navigate   = useNavigate()
  const [showCamera, setShowCamera] = useState(false)

  const st        = status ?? {}
  const isRunning = st.gcode_state === 'RUNNING'
  const isFailed  = st.gcode_state === 'FAILED'
  const hasError  = (st.print_error && st.print_error !== 0) || isFailed
  // Only show alerts the user hasn't dismissed
  const hmsAlerts = (st.hms_alerts ?? []).filter((a) => !dismissed.includes(a.hms_code))
  const lightOn   = st.chamber_light === 'on'

  return (
    <>
      {showCamera && (
        <CameraModal printer={printer} onClose={() => setShowCamera(false)} />
      )}

      {/* Outer wrapper is a div-button to permit nested <button> elements. */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => navigate(`/printer/${printer.id}`)}
        onKeyDown={(e) => e.key === 'Enter' && navigate(`/printer/${printer.id}`)}
        className={`card text-left w-full border-t-2 ${MODEL_ACCENT[printer.model] ?? 'border-t-zinc-400'} p-5 hover:bg-zinc-50 dark:hover:bg-zinc-800/60 transition-colors group cursor-pointer`}
      >
        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5 min-w-0">
              {/* Model icon */}
              <PrinterIcon
                model={printer.model}
                size={22}
                className="text-zinc-400 dark:text-zinc-500 shrink-0"
              />
              <span className="font-semibold text-zinc-800 dark:text-zinc-100 group-hover:text-zinc-900 dark:group-hover:text-white transition-colors truncate">
                {printer.name}
              </span>
              <span className="text-xs text-zinc-400 font-mono bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded shrink-0">
                {printer.model}
              </span>
              {hasError && <AlertTriangle size={14} className="text-red-500 shrink-0" />}
            </div>
            {st.current_file && (
              <div className="flex items-center gap-1.5">
                <p className="text-xs text-zinc-400 truncate max-w-[180px]">{st.current_file}</p>
                {st.print_type && (
                  <span className="text-[9px] uppercase tracking-wide text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 rounded shrink-0">
                    {st.print_type}
                  </span>
                )}
              </div>
            )}
          </div>
          <StatusBadge state={st.gcode_state ?? 'OFFLINE'} />
        </div>

        {/* ── Stage sub-label ───────────────────────────────────────── */}
        {st.stage && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">{st.stage}</p>
        )}

        {/* ── HMS alerts ────────────────────────────────────────────── */}
        {hmsAlerts.length > 0 && (
          <div className="flex flex-col gap-1 mb-2">
            {hmsAlerts.map((alert) => (
              <div
                key={alert.hms_code}
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700"
              >
                <ShieldAlert size={13} className="text-amber-500 shrink-0" />
                <span className="text-xs text-amber-700 dark:text-amber-400 font-medium truncate flex-1">
                  {alert.hms_code}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); dismissAlert(printer.id, alert.hms_code) }}
                  title="Dismiss alert"
                  className="text-amber-400 hover:text-amber-600 dark:hover:text-amber-300 transition-colors shrink-0 ml-1 leading-none"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        {/* ── Progress bar ──────────────────────────────────────────── */}
        {isRunning && (
          <div className="mb-3">
            <div className="flex justify-between text-xs text-zinc-400 mb-1.5">
              <span className="flex items-center gap-1">
                <Layers size={11} />
                {st.layer_num}/{st.total_layers}
              </span>
              <span>{st.progress}%</span>
            </div>
            <Progress value={st.progress} />
          </div>
        )}

        {/* ── Temperatures ──────────────────────────────────────────── */}
        <div className="flex items-start gap-4 mb-3">
          <TempCell label="Nozzle"  current={st.nozzle_temp}  target={st.nozzle_target} />
          <TempCell label="Bed"     current={st.bed_temp}     target={st.bed_target} />
          {(st.chamber_temp ?? 0) >= CHAMBER_TEMP_MIN && (
            <TempCell label="Chamber" current={st.chamber_temp} target={0} />
          )}
        </div>

        {/* ── Print thumbnail ───────────────────────────────────────── */}
        {isRunning && (st.cover_file || st.gcode_file || st.current_file) && (
          <img
            src={`/api/printers/${printer.id}/thumbnail`}
            alt="Print preview"
            className="w-full h-28 object-contain rounded bg-zinc-100 dark:bg-zinc-800 mb-3"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        )}

        {/* ── AMS filament dots / external spool ───────────────────── */}
        {st.ams_trays?.length > 0 ? (
          <div className="mb-3">
            <AMSDisplay
              trays={st.ams_trays}
              units={st.ams_units ?? []}
              currentTray={st.ams_current_tray}
              compact
            />
          </div>
        ) : st.vt_tray?.tray_type ? (
          <div className="flex items-center gap-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            <div
              className="w-3 h-3 rounded-full border border-zinc-300 dark:border-zinc-600 shrink-0"
              style={{ backgroundColor: st.vt_tray.color }}
            />
            <span className="truncate">
              {st.vt_tray.sub_brand || st.vt_tray.tray_type} · {st.vt_tray.remain}%
            </span>
          </div>
        ) : null}

        {/* ── Footer ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span className="flex items-center gap-1">
            <Clock size={11} />
            {isRunning ? formatTime(st.remaining_time) : '—'}
          </span>
          <span className="flex items-center gap-1">
            <Wind size={11} />
            {st.fan_speed ?? 0}%
          </span>
          {st.wifi_signal && <WifiStrength value={st.wifi_signal} size="xs" />}
          {/* Light toggle — yellow when on, dim when off */}
          <button
            onClick={(e) => { e.stopPropagation(); toggleLight(printer.id, st.chamber_light) }}
            title={lightOn ? 'Turn light off' : 'Turn light on'}
            className={`p-0.5 rounded transition-colors ${
              lightOn
                ? 'text-yellow-400 hover:text-yellow-500'
                : 'text-zinc-400 hover:text-yellow-400'
            }`}
          >
            <Lightbulb size={12} className={lightOn ? '' : 'opacity-50'} />
          </button>
          {/* Camera — only shown when LAN Mode is enabled for this printer */}
          {printer.lan_mode !== false && (
            <button
              onClick={(e) => { e.stopPropagation(); setShowCamera(true) }}
              title="Live camera"
              className="p-0.5 rounded text-zinc-400 hover:text-brand-500 dark:hover:text-brand-400 transition-colors"
            >
              <Video size={12} />
            </button>
          )}
        </div>
      </div>
    </>
  )
}
