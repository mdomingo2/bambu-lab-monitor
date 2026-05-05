/**
 * PrinterDetail — full-page view for a single printer.
 *
 * Shows live temperatures, progress, AMS, print controls, light toggle,
 * camera, HMS alerts, timelapse list, and printer info.
 *
 * NOTE: All hooks must appear before any conditional return to satisfy
 * React's Rules of Hooks.
 */
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Layers, Clock, Thermometer, Wind, Wifi, Zap, Activity,
  AlertTriangle, Gauge, Flame, Box, Video, Pause, Play, Square,
  Lightbulb, Film, Download, ShieldAlert,
} from 'lucide-react'
import { WifiStrength } from '../components/ui/WifiStrength'
import { PrinterIcon } from '../components/ui/PrinterIcon'
import { usePrinterStore } from '../store/printerStore'
import { StatusBadge } from '../components/StatusBadge'
import { Progress } from '../components/ui/Progress'
import { TempGauge } from '../components/TempGauge'
import { AMSDisplay } from '../components/AMSDisplay'
import { CameraModal } from '../components/CameraModal'
import { formatTime, eta } from '../utils/time'
import { CHAMBER_TEMP_MIN } from '../utils/constants'
import { useThumbnailUrl } from '../hooks/useThumbnailUrl'

const SPEED_LABELS = {
  1: 'Silent',
  2: 'Standard',
  3: 'Sport',
  4: 'Ludicrous',
}

const NOZZLE_TYPE_LABELS = {
  stainless_steel: 'Stainless',
  hardened_steel:  'Hardened',
  brass:           'Brass',
}

/**
 * TimelapseCard — thumbnail poster + filename + download link for one video.
 *
 * Tries to load the server-generated JPEG poster first. If the thumbnail
 * endpoint returns 404 (non-fast-start file or ffmpeg unavailable) the card
 * falls back gracefully to a Film icon placeholder so the layout stays intact.
 */
function TimelapseCard({ printerId, filename }) {
  const [thumbError, setThumbError] = useState(false)

  const thumbUrl    = `/api/printers/${printerId}/timelapses/${encodeURIComponent(filename)}/thumb`
  const downloadUrl = `/api/printers/${printerId}/timelapses/${encodeURIComponent(filename)}`

  // Strip the leading timestamp prefix that Bambu prepends (e.g. "20240401_") for display.
  const label = filename.replace(/^\d{8}_/, '').replace(/\.[^.]+$/, '')

  return (
    <a
      href={downloadUrl}
      target="_blank"
      rel="noreferrer"
      className="group relative block rounded-lg overflow-hidden bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 hover:border-brand-400 transition-colors"
    >
      {/* Poster image — falls back to icon placeholder on error */}
      <div className="relative aspect-video flex items-center justify-center">
        {thumbError ? (
          <div className="absolute inset-0 flex items-center justify-center text-zinc-400 dark:text-zinc-600">
            <Film size={28} />
          </div>
        ) : (
          <img
            src={thumbUrl}
            alt={label}
            className="w-full h-full object-cover"
            onError={() => setThumbError(true)}
          />
        )}
        {/* Download overlay on hover */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
          <Download
            size={20}
            className="text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow"
          />
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate px-2 py-1.5 leading-tight">
        {label || filename}
      </p>
    </a>
  )
}

/** A labelled stat block used in the stats grid. */
function StatBlock({ icon: Icon, label, value, sub, warn }) {
  return (
    <div className="card p-4 flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-zinc-400 mb-1">
        <Icon size={13} />{label}
      </div>
      <span className={`text-xl font-semibold tabular-nums ${warn ? 'text-red-500' : 'text-zinc-800 dark:text-zinc-100'}`}>
        {value}
      </span>
      {sub && <span className="text-xs text-zinc-400">{sub}</span>}
    </div>
  )
}

export function PrinterDetail() {
  const { id }     = useParams()
  const navigate   = useNavigate()

  // ── All hooks must come before any early return ──────────────────────────
  // Single store subscription — selects everything needed in one call to keep
  // the hook count fixed and avoid multiple Zustand subscriptions racing.
  const printer         = usePrinterStore((s) => s.printers.find((p) => p.id === id) ?? null)
  const status          = usePrinterStore((s) => s.statuses[id] ?? null)
  // NOTE: the ?? [] must be OUTSIDE the selector. If it were inside, Zustand's
  // useSyncExternalStore would receive a new [] reference on every snapshot call
  // when id has no dismissed alerts, causing an infinite re-render loop.
  const dismissed       = usePrinterStore((s) => s.dismissedAlerts[id]) ?? []

  const [showCamera,    setShowCamera]    = useState(false)
  const [controlling,   setControlling]   = useState(false)
  const [timelapses,    setTimelapses]    = useState([])
  const [showDismissed, setShowDismissed] = useState(false)

  // updateDismissedAlerts is a stable action — read once via getState(), no subscription needed.
  const updateDismissed = usePrinterStore.getState().updateDismissedAlerts

  // Auto-refreshing thumbnail URL — cache-busted every 2 minutes while the page is open.
  const thumbUrl = useThumbnailUrl(id)

  const TIMELAPSE_MODELS = ['H2D', 'P2S']
  useEffect(() => {
    if (!printer || !TIMELAPSE_MODELS.includes(printer.model)) return
    fetch(`/api/printers/${id}/timelapses`)
      .then((r) => r.json())
      .then((d) => setTimelapses(d.files ?? []))
      .catch(() => {})
  }, [id, printer?.model])
  // ────────────────────────────────────────────────────────────────────────

  if (!printer) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-400">
        <p>Printer not found.</p>
      </div>
    )
  }

  const st        = status ?? {}
  const isRunning = st.gcode_state === 'RUNNING'
  const isPaused  = st.gcode_state === 'PAUSE'
  const isFailed  = st.gcode_state === 'FAILED'
  const hasError  = (st.print_error && st.print_error !== 0) || isFailed
  // (hmsAlerts filtered below after dismissed is computed)
  const allAlerts    = st.hms_alerts ?? []
  const visibleAlerts = allAlerts.filter((a) => !dismissed.includes(a.hms_code))
  const hiddenAlerts  = allAlerts.filter((a) =>  dismissed.includes(a.hms_code))
  const etaTime      = isRunning ? eta(st.remaining_time) : null
  const lightOn      = st.chamber_light === 'on'

  const dismissAlert = async (hmsCode) => {
    const res = await fetch(`/api/printers/${id}/dismissed-alerts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hms_code: hmsCode }),
    })
    if (res.ok) {
      const { dismissed: next } = await res.json()
      updateDismissed(id, next)
    }
  }

  const restoreAlert = async (hmsCode) => {
    const res = await fetch(
      `/api/printers/${id}/dismissed-alerts/${encodeURIComponent(hmsCode)}`,
      { method: 'DELETE' }
    )
    if (res.ok) {
      const { dismissed: next } = await res.json()
      updateDismissed(id, next)
    }
  }

  const sendControl = async (action) => {
    setControlling(true)
    try {
      await fetch(`/api/printers/${id}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
    } finally {
      // Brief lockout to prevent double-sends; actual state arrives via MQTT.
      setTimeout(() => setControlling(false), 1500)
    }
  }

  const sendLight = async (mode) => {
    await fetch(`/api/printers/${id}/light`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {showCamera && (
        <CameraModal printer={printer} onClose={() => setShowCamera(false)} />
      )}

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/')} className="btn-ghost p-2">
          <ArrowLeft size={18} />
        </button>

        {/* Printer model icon */}
        <PrinterIcon
          model={printer.model}
          size={44}
          className="text-zinc-400 dark:text-zinc-500 shrink-0"
        />

        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{printer.name}</h1>
            <span className="text-xs text-zinc-400 font-mono bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded">
              {printer.model}
            </span>
            <StatusBadge state={st.gcode_state ?? 'OFFLINE'} />
            {hasError && (
              <span className="flex items-center gap-1 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-2 py-0.5 rounded-md border border-red-200 dark:border-red-800">
                <AlertTriangle size={12} /> Error {st.print_error}
              </span>
            )}
          </div>
          {st.stage && (
            <p className="text-sm text-amber-600 dark:text-amber-400 mt-0.5">{st.stage}</p>
          )}
          {st.current_file && (
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-sm text-zinc-400 truncate">{st.current_file}</p>
              {st.print_type && (
                <span className="text-[10px] uppercase tracking-wide font-medium text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded shrink-0">
                  {st.print_type}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Print failed banner ──────────────────────────────────────── */}
      {isFailed && (
        <div className="mb-5 flex items-start gap-3 bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-xl p-4">
          <AlertTriangle size={18} className="text-red-500 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-700 dark:text-red-400 text-sm">Print failed</p>
            {st.print_error ? (
              <p className="text-xs text-red-600 dark:text-red-500 mt-0.5">
                Error code 0x{st.print_error.toString(16).toUpperCase()}
              </p>
            ) : null}
          </div>
        </div>
      )}

      {/* ── HMS alerts ───────────────────────────────────────────────── */}
      {(visibleAlerts.length > 0 || hiddenAlerts.length > 0) && (
        <div className="mb-5 flex flex-col gap-2">
          {/* Active (non-dismissed) alerts */}
          {visibleAlerts.map((alert) => (
            <div
              key={alert.hms_code}
              className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 rounded-xl p-4"
            >
              <ShieldAlert size={18} className="text-amber-500 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-amber-700 dark:text-amber-400 text-sm font-mono">
                  {alert.hms_code}
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
                  Health Management System alert
                </p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <a href={alert.wiki_url} target="_blank" rel="noreferrer"
                  className="text-xs text-amber-600 dark:text-amber-400 hover:underline font-medium">
                  Direct page →
                </a>
                <a href="https://wiki.bambulab.com/en/x1/troubleshooting/hmscode"
                  target="_blank" rel="noreferrer"
                  className="text-xs text-amber-500/70 dark:text-amber-500/60 hover:underline">
                  HMS index →
                </a>
                <button
                  onClick={() => dismissAlert(alert.hms_code)}
                  title="Dismiss this alert"
                  className="mt-1 text-xs text-amber-400 hover:text-amber-600 dark:hover:text-amber-300 transition-colors"
                >
                  Dismiss ✕
                </button>
              </div>
            </div>
          ))}

          {/* Dismissed alerts — collapsed by default, expandable */}
          {hiddenAlerts.length > 0 && (
            <div>
              <button
                onClick={() => setShowDismissed((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors py-1"
              >
                <ShieldAlert size={12} />
                {hiddenAlerts.length} dismissed alert{hiddenAlerts.length > 1 ? 's' : ''}
                <span className="ml-1">{showDismissed ? '▲ Hide' : '▼ Show'}</span>
              </button>

              {showDismissed && (
                <div className="flex flex-col gap-2 mt-1">
                  {hiddenAlerts.map((alert) => (
                    <div
                      key={alert.hms_code}
                      className="flex items-start gap-3 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 opacity-60"
                    >
                      <ShieldAlert size={18} className="text-zinc-400 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-zinc-500 dark:text-zinc-400 text-sm font-mono">
                          {alert.hms_code}
                        </p>
                        <p className="text-xs text-zinc-400 mt-0.5">Dismissed</p>
                      </div>
                      <button
                        onClick={() => restoreAlert(alert.hms_code)}
                        className="text-xs text-zinc-400 hover:text-brand-500 dark:hover:text-brand-400 transition-colors shrink-0"
                      >
                        Restore
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Controls toolbar ─────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        {/* Print controls — only while printing or paused */}
        {(isRunning || isPaused) && (
          <>
            {isRunning ? (
              <button
                onClick={() => sendControl('pause')}
                disabled={controlling}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-700 hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              >
                <Pause size={14} /> Pause
              </button>
            ) : (
              <button
                onClick={() => sendControl('resume')}
                disabled={controlling}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-700 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 disabled:opacity-50 transition-colors"
              >
                <Play size={14} /> Resume
              </button>
            )}
            <button
              onClick={() => { if (window.confirm('Cancel this print?')) sendControl('stop') }}
              disabled={controlling}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-700 hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50 transition-colors"
            >
              <Square size={14} /> Cancel
            </button>
          </>
        )}

        {/* Failed state — offer to clear so the printer returns to IDLE */}
        {isFailed && (
          <button
            onClick={() => { if (window.confirm('Clear the failed print and return printer to idle?')) sendControl('stop') }}
            disabled={controlling}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-700 hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50 transition-colors"
          >
            <Square size={14} /> Clear failed print
          </button>
        )}

        {/* Light toggle + camera — always visible, pushed to the right */}
        <div className="flex items-center gap-1.5 ml-auto">
          <button
            onClick={() => sendLight(lightOn ? 'off' : 'on')}
            title={lightOn ? 'Turn light off' : 'Turn light on'}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              lightOn
                ? 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 border-yellow-300 dark:border-yellow-700 hover:bg-yellow-100 dark:hover:bg-yellow-900/40'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 border-zinc-200 dark:border-zinc-700 hover:bg-zinc-200 dark:hover:bg-zinc-700'
            }`}
          >
            <Lightbulb size={14} className={lightOn ? '' : 'opacity-40'} />
            {lightOn ? 'Light On' : 'Light Off'}
          </button>
          {/* Camera — only shown when LAN Mode is enabled for this printer */}
          {printer.lan_mode !== false && (
            <button
              onClick={() => setShowCamera(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-brand-50 hover:text-brand-600 dark:hover:bg-brand-900/20 dark:hover:text-brand-400 border border-zinc-200 dark:border-zinc-700 transition-colors"
            >
              <Video size={14} /> Camera
            </button>
          )}
        </div>
      </div>

      {/* ── Progress card ────────────────────────────────────────────── */}
      {isRunning && (
        <div className="card p-5 mb-5">
          <div className="flex gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex justify-between text-sm text-zinc-500 mb-2">
                <span className="flex items-center gap-1.5">
                  <Layers size={14} />
                  Layer {st.layer_num} of {st.total_layers}
                </span>
                <span className="font-semibold text-zinc-700 dark:text-zinc-200">
                  {st.progress}%
                </span>
              </div>
              <Progress value={st.progress} className="h-3 mb-2" />
              <div className="flex justify-between text-xs text-zinc-400">
                <span>{formatTime(st.remaining_time)} remaining</span>
                {etaTime && <span>ETA {etaTime}</span>}
              </div>
            </div>
            {(st.cover_file || st.gcode_file) && (
              <img
                src={thumbUrl}
                alt="Print preview"
                className="w-28 h-28 object-contain rounded bg-zinc-100 dark:bg-zinc-800 shrink-0"
                onError={(e) => { e.currentTarget.style.display = 'none' }}
              />
            )}
          </div>
        </div>
      )}

      {/* ── Temperatures + stats grid ─────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        <div className="card p-4 col-span-1">
          <p className="text-xs text-zinc-400 mb-3 flex items-center gap-1.5">
            <Thermometer size={13} />Temperatures
          </p>
          <div className="flex flex-col gap-4">
            <TempGauge label="Nozzle"  current={st.nozzle_temp ?? 0} target={st.nozzle_target ?? 0} />
            <TempGauge label="Bed"     current={st.bed_temp ?? 0}    target={st.bed_target ?? 0} />
            {(st.chamber_temp ?? 0) >= CHAMBER_TEMP_MIN && (
              <TempGauge label="Chamber" current={st.chamber_temp} target={0} />
            )}
          </div>
        </div>

        <div className="col-span-2 grid grid-cols-2 gap-4">
          <StatBlock icon={Clock}  label="Time remaining" value={formatTime(st.remaining_time)} sub={etaTime ? `ETA ${etaTime}` : undefined} />
          <StatBlock icon={Gauge}  label="Speed"          value={`${st.speed_pct ?? 100}%`}     sub={SPEED_LABELS[st.speed_level] ?? ''} />
          <StatBlock icon={Wind}   label="Part cooling"   value={`${st.fan_speed ?? 0}%`} />
          <StatBlock icon={Flame}  label="Hotend fan"     value={`${st.heatbreak_fan_speed ?? 0}%`} />
          <StatBlock icon={Wind}   label="Aux fan"        value={`${st.aux_fan_speed ?? 0}%`} />
          <StatBlock
            icon={Wifi}
            label="Wi-Fi"
            value={
              st.wifi_signal
                ? <span className="flex items-center gap-2">
                    <WifiStrength value={st.wifi_signal} size="sm" />
                    <span className="text-sm font-normal text-zinc-400 tabular-nums">{st.wifi_signal}</span>
                  </span>
                : '—'
            }
          />
        </div>
      </div>

      {/* ── AMS ─────────────────────────────────────────────────────── */}
      {st.ams_trays?.length > 0 && (
        <div className="card p-4 mb-5">
          <p className="text-xs text-zinc-400 mb-3 flex items-center gap-1.5">
            <Zap size={13} />AMS Filaments
          </p>
          <AMSDisplay
            trays={st.ams_trays}
            units={st.ams_units ?? []}
            currentTray={st.ams_current_tray}
            model={printer.model}
          />
        </div>
      )}

      {/* ── External spool (no AMS) ───────────────────────────────────── */}
      {!st.ams_trays?.length && st.vt_tray?.tray_type && (
        <div className="card p-4 mb-5 flex items-center gap-4">
          <Box size={16} className="text-zinc-400 shrink-0" />
          <div
            className="w-8 h-8 rounded-full border-2 border-zinc-200 dark:border-zinc-600 shrink-0"
            style={{ backgroundColor: st.vt_tray.color }}
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
              {st.vt_tray.sub_brand || st.vt_tray.tray_type}
            </p>
            <p className="text-xs text-zinc-400">
              {st.vt_tray.tray_type} · {st.vt_tray.remain}% remaining
            </p>
          </div>
          <span className="text-xs text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded">
            External
          </span>
        </div>
      )}

      {/* ── Timelapses ───────────────────────────────────────────────── */}
      {timelapses.length > 0 && (
        <div className="card p-4 mb-5">
          <p className="text-xs text-zinc-400 mb-3 flex items-center gap-1.5">
            <Film size={13} />Recent timelapses
          </p>
          <div className="grid grid-cols-3 gap-3">
            {timelapses.map((file) => (
              <TimelapseCard key={file} printerId={id} filename={file} />
            ))}
          </div>
        </div>
      )}

      {/* ── Printer info ─────────────────────────────────────────────── */}
      <div className="card p-4">
        <p className="text-xs text-zinc-400 mb-3 flex items-center gap-1.5">
          <Activity size={13} />Printer info
        </p>
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
          {[
            ['IP Address',          printer.ip],
            ['Serial',              printer.serial],
            ['Model',               printer.model],
            ['Nozzle',              st.nozzle_diameter
                                      ? `${st.nozzle_diameter}mm ${NOZZLE_TYPE_LABELS[st.nozzle_type] ?? st.nozzle_type ?? ''}`.trim()
                                      : '—'],
            ['Print source',        st.print_type || '—'],
            ['AI spaghetti detect', st.xcam_spaghetti_enabled ? 'Enabled' : 'Disabled'],
            ['AI halt on detect',   st.xcam_halt_enabled      ? 'Enabled' : 'Disabled'],
            ['First layer inspect', st.xcam_first_layer_enabled ? 'Enabled' : 'Disabled'],
            ['Last update',         st.last_update ? new Date(st.last_update).toLocaleTimeString() : '—'],
            ['Error code',          st.print_error ? `0x${st.print_error.toString(16).toUpperCase()}` : 'None'],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-zinc-400">{k}</span>
              <span className="text-zinc-700 dark:text-zinc-300 font-mono text-xs">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
