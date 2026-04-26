import { useState } from 'react'
import { PlusCircle, Pencil, Trash2, AlertCircle, Check, Video } from 'lucide-react'
import { usePrinterStore } from '../store/printerStore'
import { Dialog } from '../components/ui/Dialog'
import { StatusBadge } from '../components/StatusBadge'

const MODELS = ['A1', 'P1S', 'P2S', 'H2D']
// Models that default lan_mode=false:
//   A1  — cameras are cloud-only, RTSP on port 322 is not supported
//   P1S — LAN Mode must be explicitly enabled on the printer; off by default
const MODEL_LAN_DEFAULT = { A1: false, P1S: false, P2S: true, H2D: true }
const EMPTY_FORM = { name: '', model: 'P1S', ip: '', serial: '', access_code: '', lan_mode: false }

async function apiRequest(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.status === 204 ? null : res.json()
}

function ErrorBanner({ error }) {
  if (!error) return null
  return (
    <div className="mx-6 mt-4 flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
      <AlertCircle size={15} className="shrink-0 mt-0.5" />
      <span>{error}</span>
    </div>
  )
}

function PrinterForm({ initial = EMPTY_FORM, onSave, onCancel, saving, error }) {
  const [form, setForm] = useState(initial)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const valid = form.name.trim() && form.ip.trim() && form.serial.trim() && form.access_code.trim()

  // When model changes, reset lan_mode to the model's default.
  const handleModelChange = (e) => {
    const model = e.target.value
    setForm((f) => ({
      ...f,
      model,
      lan_mode: MODEL_LAN_DEFAULT[model] ?? true,
    }))
  }

  const isA1 = form.model === 'A1'

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner error={error} />
      <div className="p-6 pt-4 flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Printer name</label>
            <input className="input" placeholder="e.g. P1S Left" value={form.name} onChange={set('name')} />
          </div>
          <div>
            <label className="label">Model</label>
            <select className="input" value={form.model} onChange={handleModelChange}>
              {MODELS.map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="label">IP address</label>
          <input className="input font-mono" placeholder="192.168.1.100" value={form.ip} onChange={set('ip')} />
        </div>

        <div>
          <label className="label">Serial number</label>
          <input
            className="input font-mono uppercase"
            placeholder="01S00C123456789"
            value={form.serial}
            onChange={(e) => setForm((f) => ({ ...f, serial: e.target.value.toUpperCase() }))}
          />
        </div>

        <div>
          <label className="label">Access code</label>
          <input
            className="input font-mono"
            placeholder="8-digit code from printer screen"
            value={form.access_code}
            onChange={set('access_code')}
          />
          <p className="text-xs text-zinc-400 mt-1">
            Found on the printer touchscreen under Settings → Network
          </p>
        </div>

        {/* LAN Mode toggle */}
        <div className={`flex items-start gap-3 p-3 rounded-lg border ${
          isA1
            ? 'bg-zinc-50 dark:bg-zinc-800/30 border-zinc-200 dark:border-zinc-700 opacity-60'
            : form.lan_mode
              ? 'bg-emerald-50 dark:bg-emerald-900/10 border-emerald-200 dark:border-emerald-800'
              : 'bg-zinc-50 dark:bg-zinc-800/50 border-zinc-200 dark:border-zinc-700'
        }`}>
          <input
            type="checkbox"
            id="lan_mode"
            checked={form.lan_mode}
            disabled={isA1}
            onChange={(e) => setForm((f) => ({ ...f, lan_mode: e.target.checked }))}
            className="mt-0.5 w-4 h-4 accent-emerald-500 cursor-pointer disabled:cursor-not-allowed"
          />
          <div className="min-w-0 flex-1">
            <label
              htmlFor="lan_mode"
              className={`flex items-center gap-1.5 text-sm font-medium ${isA1 ? 'text-zinc-400 cursor-not-allowed' : 'text-zinc-800 dark:text-zinc-200 cursor-pointer'}`}
            >
              <Video size={13} />
              LAN Mode enabled
            </label>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-0.5 leading-relaxed">
              {isA1
                ? 'A1 / A1 mini cameras are cloud-only — live camera is not available regardless of LAN Mode.'
                : form.lan_mode
                  ? 'Live camera is enabled. Make sure LAN Mode is on under Settings → Network on the printer.'
                  : 'Live camera button is hidden. Enable LAN Mode on the printer first, then check this box.'}
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2 border-t border-zinc-200 dark:border-zinc-800">
          <button className="btn-ghost" onClick={onCancel} disabled={saving}>Cancel</button>
          <button className="btn-primary" disabled={!valid || saving} onClick={() => onSave(form)}>
            {saving ? 'Saving…' : 'Save printer'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Setup() {
  const printers = usePrinterStore((s) => s.printers)
  const statuses = usePrinterStore((s) => s.statuses)
  const farmName = usePrinterStore((s) => s.farmName)
  const setFarmName = usePrinterStore((s) => s.setFarmName)
  const [nameInput, setNameInput] = useState(farmName)
  const [nameSaved, setNameSaved] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [editPrinter, setEditPrinter] = useState(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)
  const [deleteId, setDeleteId] = useState(null)

  const saveFarmName = async () => {
    try {
      await apiRequest('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ farm_name: nameInput }),
      })
      setFarmName(nameInput)
      setNameSaved(true)
      setTimeout(() => setNameSaved(false), 2000)
    } catch (err) {
      console.error('Failed to save farm name:', err)
    }
  }

  const handleAdd = async (form) => {
    setSaving(true)
    setFormError(null)
    try {
      await apiRequest('/api/printers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      setAddOpen(false)
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = async (form) => {
    setSaving(true)
    setFormError(null)
    try {
      await apiRequest(`/api/printers/${editPrinter.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      setEditPrinter(null)
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    try {
      await apiRequest(`/api/printers/${deleteId}`, { method: 'DELETE' })
    } catch (err) {
      console.error('Delete failed:', err)
    } finally {
      setDeleteId(null)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-2xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">Setup</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Manage your print farm printers</p>
        </div>
        <button className="btn-primary flex items-center gap-2 text-sm" onClick={() => { setFormError(null); setAddOpen(true) }}>
          <PlusCircle size={16} />Add printer
        </button>
      </div>

      {/* Farm name */}
      <div className="card p-4 mb-6">
        <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-3 uppercase tracking-wide">Farm name</p>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="e.g. Domingo-True Print Farm"
          />
          <button
            className="btn-primary flex items-center gap-1.5 px-3"
            onClick={saveFarmName}
            disabled={!nameInput.trim() || nameInput === farmName}
          >
            {nameSaved ? <><Check size={14} /> Saved</> : 'Save'}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {printers.length === 0 && (
          <div className="card p-8 text-center text-zinc-400">
            <p className="text-4xl mb-3">🖨</p>
            <p>No printers yet. Add one to get started.</p>
          </div>
        )}
        {printers.map((p) => {
          const st = statuses[p.id]
          return (
            <div key={p.id} className="card p-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="font-semibold text-zinc-800 dark:text-zinc-100">{p.name}</span>
                  <span className="text-xs font-mono text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">{p.model}</span>
                  <StatusBadge state={st?.gcode_state ?? 'OFFLINE'} />
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-400 font-mono">
                  <span>{p.ip}</span><span>·</span><span>{p.serial}</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button className="btn-ghost p-2" onClick={() => { setFormError(null); setEditPrinter(p) }}><Pencil size={15} /></button>
                <button className="btn-ghost p-2 text-red-500 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20" onClick={() => setDeleteId(p.id)}><Trash2 size={15} /></button>
              </div>
            </div>
          )
        })}
      </div>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Add printer">
        <PrinterForm onSave={handleAdd} onCancel={() => setAddOpen(false)} saving={saving} error={formError} />
      </Dialog>

      <Dialog open={!!editPrinter} onClose={() => setEditPrinter(null)} title="Edit printer">
        {editPrinter && (() => {
          // Strip id so the form never accidentally submits it in the PATCH body.
          const { id: _id, ...editFields } = editPrinter
          return (
            <PrinterForm
              initial={editFields}
              onSave={handleEdit}
              onCancel={() => setEditPrinter(null)}
              saving={saving}
              error={formError}
            />
          )
        })()}
      </Dialog>

      <Dialog open={!!deleteId} onClose={() => setDeleteId(null)} title="Delete printer" size="sm">
        <div className="p-6">
          <p className="text-zinc-500 dark:text-zinc-400 mb-6">
            Remove <strong className="text-zinc-800 dark:text-zinc-200">{printers.find(p => p.id === deleteId)?.name}</strong>? This cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <button className="btn-ghost" onClick={() => setDeleteId(null)}>Cancel</button>
            <button className="btn-danger" onClick={handleDelete}>Delete</button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
