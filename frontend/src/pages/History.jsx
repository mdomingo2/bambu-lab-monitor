/**
 * History — print job log with sort and group-by controls.
 *
 * Sorting options: newest · oldest · longest · shortest · by printer · by status
 * Grouping options: none · by printer model · by printer name · by status
 *
 * Model lookup is done client-side: printerStore already holds the full
 * printer list. Jobs for deleted printers fall back to "Unknown model".
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Clock, CheckCircle2, XCircle, Ban, Printer, Film,
  ChevronDown, ArrowUpDown,
} from 'lucide-react'
import { usePrinterStore } from '../store/printerStore'

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDuration(seconds) {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── Static maps ──────────────────────────────────────────────────────────────

const STATUS_ICON = {
  completed: <CheckCircle2 size={15} className="text-emerald-500" />,
  failed:    <XCircle      size={15} className="text-red-500" />,
  cancelled: <Ban          size={15} className="text-zinc-400" />,
  running:   <Clock        size={15} className="text-brand-500 animate-pulse" />,
}

const STATUS_LABEL = {
  completed: 'text-emerald-600 dark:text-emerald-400',
  failed:    'text-red-600 dark:text-red-400',
  cancelled: 'text-zinc-400',
  running:   'text-brand-600 dark:text-brand-400',
}

// Sort options — label + comparator
const SORT_OPTIONS = [
  { value: 'date-desc',     label: 'Newest first' },
  { value: 'date-asc',      label: 'Oldest first' },
  { value: 'duration-desc', label: 'Longest first' },
  { value: 'duration-asc',  label: 'Shortest first' },
  { value: 'printer',       label: 'Printer name' },
  { value: 'status',        label: 'Status' },
]

const SORT_FN = {
  'date-desc':     (a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''),
  'date-asc':      (a, b) => (a.started_at ?? '').localeCompare(b.started_at ?? ''),
  'duration-desc': (a, b) => (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0),
  'duration-asc':  (a, b) => (a.duration_seconds ?? 0) - (b.duration_seconds ?? 0),
  'printer':       (a, b) => (a.printer_name ?? '').localeCompare(b.printer_name ?? ''),
  'status':        (a, b) => (a.status ?? '').localeCompare(b.status ?? ''),
}

// Group options — label + key extractor
const GROUP_OPTIONS = [
  { value: 'none',    label: 'No grouping' },
  { value: 'model',   label: 'Printer type' },
  { value: 'printer', label: 'Printer name' },
  { value: 'status',  label: 'Status' },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function JobRow({ job }) {
  return (
    <div className="flex items-center gap-4 px-5 py-3.5">
      <div className="shrink-0">{STATUS_ICON[job.status] ?? STATUS_ICON.cancelled}</div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100 truncate">
          {job.file_name || 'Unknown file'}
        </p>
        <p className="text-xs text-zinc-400 flex items-center gap-1.5 mt-0.5">
          <Printer size={11} />
          {job.printer_name}
        </p>
      </div>

      <div className="text-right shrink-0">
        <p className={`text-xs font-medium capitalize ${STATUS_LABEL[job.status] ?? ''}`}>
          {job.status}
        </p>
        <p className="text-xs text-zinc-400 mt-0.5">{formatDuration(job.duration_seconds)}</p>
      </div>

      <div className="text-right shrink-0 hidden sm:block">
        <p className="text-xs text-zinc-500">{formatDate(job.started_at)}</p>
        {job.finished_at && (
          <p className="text-xs text-zinc-400">→ {formatDate(job.finished_at)}</p>
        )}
      </div>
    </div>
  )
}

/** Compact inline <select> with a label. */
function ControlSelect({ label, icon: Icon, value, onChange, options }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
      {Icon && <Icon size={13} />}
      <span className="hidden sm:inline">{label}</span>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="appearance-none pl-2 pr-6 py-1 text-xs rounded-md border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-400 cursor-pointer"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
      </div>
    </label>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function History() {
  const [jobs,    setJobs]    = useState([])
  const [loading, setLoading] = useState(true)
  const [sortBy,  setSortBy]  = useState('date-desc')
  const [groupBy, setGroupBy] = useState('none')

  // Build a printer-id → model lookup from the store
  const printers = usePrinterStore((s) => s.printers)
  const modelOf  = useMemo(() => {
    const map = {}
    printers.forEach((p) => { map[p.id] = p.model })
    return map
  }, [printers])

  useEffect(() => {
    fetch('/api/history')
      .then((r) => r.json())
      .then((data) => { setJobs(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // ── Sort ────────────────────────────────────────────────────────────────────
  const sorted = useMemo(() => {
    return [...jobs].sort(SORT_FN[sortBy] ?? SORT_FN['date-desc'])
  }, [jobs, sortBy])

  // ── Group ───────────────────────────────────────────────────────────────────
  const grouped = useMemo(() => {
    if (groupBy === 'none') return [{ key: null, jobs: sorted }]

    const keyOf = (job) => {
      if (groupBy === 'model')   return modelOf[job.printer_id] ?? 'Unknown model'
      if (groupBy === 'printer') return job.printer_name || 'Unknown printer'
      if (groupBy === 'status')  return job.status || 'unknown'
      return null
    }

    // Preserve sort order within each group; order groups by first occurrence
    const order  = []
    const groups = {}
    sorted.forEach((job) => {
      const key = keyOf(job)
      if (!groups[key]) { order.push(key); groups[key] = [] }
      groups[key].push(job)
    })
    return order.map((key) => ({ key, jobs: groups[key] }))
  }, [sorted, groupBy, modelOf])

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 overflow-y-auto p-6">

      {/* Header */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <Film size={20} className="text-zinc-400" />
        <h1 className="heading text-3xl leading-tight">Print History</h1>
        <span className="text-sm text-zinc-400 ml-auto">{jobs.length} jobs</span>
      </div>

      {/* Controls — only shown when there's something to sort/group */}
      {!loading && jobs.length > 0 && (
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <ControlSelect
            label="Sort"
            icon={ArrowUpDown}
            value={sortBy}
            onChange={setSortBy}
            options={SORT_OPTIONS}
          />
          <ControlSelect
            label="Group by"
            icon={ChevronDown}
            value={groupBy}
            onChange={setGroupBy}
            options={GROUP_OPTIONS}
          />
        </div>
      )}

      {/* Loading */}
      {loading && <p className="text-zinc-400 text-sm">Loading…</p>}

      {/* Empty */}
      {!loading && jobs.length === 0 && (
        <div className="card p-10 text-center text-zinc-400">
          <Printer size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No print history yet.</p>
          <p className="text-xs mt-1">Jobs are logged automatically when prints start.</p>
        </div>
      )}

      {/* Job list — optionally grouped */}
      {!loading && jobs.length > 0 && (
        <div className="flex flex-col gap-3">
          {grouped.map(({ key, jobs: groupJobs }) => (
            <div key={key ?? '__all__'}>
              {/* Group header */}
              {key !== null && (
                <div className="flex items-center gap-2 mb-1.5 px-1">
                  <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider capitalize">
                    {key}
                  </span>
                  <span className="text-xs text-zinc-400">({groupJobs.length})</span>
                  <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700 ml-1" />
                </div>
              )}
              <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
                {groupJobs.map((job) => (
                  <JobRow key={job.id} job={job} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
