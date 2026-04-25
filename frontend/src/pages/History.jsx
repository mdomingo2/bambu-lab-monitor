import { useEffect, useState } from 'react'
import { Clock, CheckCircle2, XCircle, Ban, Printer, Film } from 'lucide-react'

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

const STATUS_ICON = {
  completed: <CheckCircle2 size={15} className="text-emerald-500" />,
  failed:    <XCircle     size={15} className="text-red-500" />,
  cancelled: <Ban         size={15} className="text-zinc-400" />,
  running:   <Clock       size={15} className="text-brand-500 animate-pulse" />,
}

const STATUS_LABEL = {
  completed: 'text-emerald-600 dark:text-emerald-400',
  failed:    'text-red-600 dark:text-red-400',
  cancelled: 'text-zinc-400',
  running:   'text-brand-600 dark:text-brand-400',
}

export function History() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/history')
      .then(r => r.json())
      .then(data => { setJobs(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <Film size={20} className="text-zinc-400" />
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">Print History</h1>
        <span className="text-sm text-zinc-400 ml-auto">{jobs.length} jobs</span>
      </div>

      {loading && (
        <p className="text-zinc-400 text-sm">Loading…</p>
      )}

      {!loading && jobs.length === 0 && (
        <div className="card p-10 text-center text-zinc-400">
          <Printer size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No print history yet.</p>
          <p className="text-xs mt-1">Jobs are logged automatically when prints start.</p>
        </div>
      )}

      {!loading && jobs.length > 0 && (
        <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
          {jobs.map(job => (
            <div key={job.id} className="flex items-center gap-4 px-5 py-3.5">
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
          ))}
        </div>
      )}
    </div>
  )
}
