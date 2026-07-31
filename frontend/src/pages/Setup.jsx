import { useState, useEffect, useCallback } from 'react'
import { PlusCircle, Pencil, Trash2, AlertCircle, Check, Video, CloudDownload, UserPlus, KeyRound, ShieldCheck, Eye, Cpu } from 'lucide-react'
import { usePrinterStore } from '../store/printerStore'
import { useAuthStore } from '../store/authStore'
import { Dialog } from '../components/ui/Dialog'
import { StatusBadge } from '../components/StatusBadge'
import { BambuImportModal } from '../components/BambuImportModal'

const EMPTY_FORM = { name: '', model: '', ip: '', serial: '', access_code: '', lan_mode: false }
const EMPTY_USER_FORM = { username: '', password: '', role: 'admin' }
const EMPTY_TYPE_FORM = { name: '', lan_mode_default: true, timelapse_support: false, camera_capable: true }

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

// ---------------------------------------------------------------------------
// Printer form
// ---------------------------------------------------------------------------

function PrinterForm({ initial = EMPTY_FORM, printerTypes = [], onSave, onCancel, saving, error }) {
  const firstType = printerTypes[0]?.name ?? ''
  const [form, setForm] = useState(() => ({
    ...initial,
    model: initial.model || firstType,
  }))
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const valid = form.name.trim() && form.model && form.ip.trim() && form.serial.trim() && form.access_code.trim()

  const handleModelChange = (e) => {
    const model = e.target.value
    const pt = printerTypes.find((t) => t.name === model)
    setForm((f) => ({ ...f, model, lan_mode: pt ? pt.lan_mode_default : true }))
  }

  const activePt = printerTypes.find((t) => t.name === form.model)
  const cameraCapable = activePt ? activePt.camera_capable : true
  const isA1 = !cameraCapable

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
              {printerTypes.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
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
          <p className="text-xs text-zinc-400 mt-1">Found on the printer touchscreen under Settings → Network</p>
        </div>

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
              {!cameraCapable
                ? `${form.model} cameras are cloud-only — live camera is not available regardless of LAN Mode.`
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

// ---------------------------------------------------------------------------
// Printer types section
// ---------------------------------------------------------------------------

function PrinterTypesSection({ types, onRefresh }) {
  const [addOpen, setAddOpen]   = useState(false)
  const [form, setForm]         = useState(EMPTY_TYPE_FORM)
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState(null)
  const [deleteType, setDeleteType] = useState(null)

  const setF = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const setFBool = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.checked }))
  const nameValid = form.name.trim().length > 0 && form.name.trim().length <= 20

  const handleAdd = async () => {
    setSaving(true)
    setError(null)
    try {
      await apiRequest('/api/printer-types', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, name: form.name.trim() }),
      })
      setAddOpen(false)
      setForm(EMPTY_TYPE_FORM)
      onRefresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setError(null)
    try {
      await apiRequest(`/api/printer-types/${encodeURIComponent(deleteType)}`, { method: 'DELETE' })
      setDeleteType(null)
      onRefresh()
    } catch (err) {
      setError(err.message)
      setDeleteType(null)
    }
  }

  return (
    <div className="card p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Printer types</p>
        <button
          className="btn-ghost flex items-center gap-1.5 text-xs px-2 py-1 border border-zinc-300 dark:border-zinc-700"
          onClick={() => { setError(null); setForm(EMPTY_TYPE_FORM); setAddOpen(true) }}
        >
          <PlusCircle size={13} />
          Add type
        </button>
      </div>

      {error && (
        <div className="mb-3 flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
          <AlertCircle size={14} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
        {types.map((t) => (
          <div key={t.name} className="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
            <div className="w-7 h-7 rounded-md bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center shrink-0">
              <Cpu size={14} className="text-zinc-500 dark:text-zinc-400" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{t.name}</span>
              <div className="flex gap-2 mt-0.5">
                {t.timelapse_support && (
                  <span className="text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-1.5 py-0.5 rounded">Timelapse</span>
                )}
                {t.camera_capable && (
                  <span className="text-xs text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/20 px-1.5 py-0.5 rounded">Camera</span>
                )}
                {t.lan_mode_default && (
                  <span className="text-xs text-navy-500 dark:text-steel-300 bg-steel-100 dark:bg-navy-700/40 px-1.5 py-0.5 rounded">LAN default</span>
                )}
              </div>
            </div>
            <button
              className="btn-ghost p-1.5 text-red-500 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
              title={`Delete ${t.name}`}
              onClick={() => { setError(null); setDeleteType(t.name) }}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>

      {/* Add type dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Add printer type">
        <div className="p-6 flex flex-col gap-4">
          <div>
            <label className="label">Model name</label>
            <input
              className="input font-mono uppercase"
              placeholder="e.g. X1C"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value.toUpperCase() }))}
              maxLength={20}
              autoComplete="off"
            />
            <p className="text-xs text-zinc-400 mt-1">Max 20 characters. Must be unique.</p>
          </div>

          <fieldset className="flex flex-col gap-2.5 p-3 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <legend className="text-xs font-medium text-zinc-500 dark:text-zinc-400 px-1">Capabilities</legend>

            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.camera_capable} onChange={setFBool('camera_capable')} className="w-4 h-4 accent-brand-500" />
              <span className="text-sm text-zinc-700 dark:text-zinc-300">Camera capable</span>
              <span className="text-xs text-zinc-400">(enables LAN Mode toggle)</span>
            </label>

            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.lan_mode_default} onChange={setFBool('lan_mode_default')} disabled={!form.camera_capable} className="w-4 h-4 accent-navy-500 disabled:opacity-40" />
              <span className={`text-sm ${!form.camera_capable ? 'text-zinc-400' : 'text-zinc-700 dark:text-zinc-300'}`}>LAN Mode on by default</span>
            </label>

            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.timelapse_support} onChange={setFBool('timelapse_support')} className="w-4 h-4 accent-emerald-500" />
              <span className="text-sm text-zinc-700 dark:text-zinc-300">Timelapse support (FTPS)</span>
            </label>
          </fieldset>

          {error && (
            <div className="flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2 border-t border-zinc-200 dark:border-zinc-800">
            <button className="btn-ghost" onClick={() => setAddOpen(false)} disabled={saving}>Cancel</button>
            <button className="btn-primary flex items-center gap-1.5" disabled={!nameValid || saving} onClick={handleAdd}>
              <PlusCircle size={14} />
              {saving ? 'Adding…' : 'Add type'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteType} onClose={() => setDeleteType(null)} title="Delete printer type" size="sm">
        <div className="p-6">
          <p className="text-zinc-500 dark:text-zinc-400 mb-6">
            Delete type <strong className="text-zinc-800 dark:text-zinc-200 font-mono">{deleteType}</strong>? This cannot be undone.
            If any printers use this type, deletion will be blocked.
          </p>
          <div className="flex justify-end gap-3">
            <button className="btn-ghost" onClick={() => setDeleteType(null)}>Cancel</button>
            <button className="btn-danger" onClick={handleDelete}>Delete type</button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Role badge
// ---------------------------------------------------------------------------

function RoleBadge({ role }) {
  if (role === 'admin') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-1.5 py-0.5 rounded bg-navy-800 text-white dark:bg-steel-200 dark:text-navy-900">
        <ShieldCheck size={11} />Admin
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400">
      <Eye size={11} />Viewer
    </span>
  )
}

// ---------------------------------------------------------------------------
// User management section
// ---------------------------------------------------------------------------

function UsersSection({ currentUsername }) {
  const [users, setUsers]           = useState([])
  const [loading, setLoading]       = useState(true)
  const [addOpen, setAddOpen]       = useState(false)
  const [resetUser, setResetUser]   = useState(null)  // username string
  const [deleteUser, setDeleteUser] = useState(null)  // username string
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState(null)

  // Own password change
  const [pwOpen, setPwOpen]   = useState(false)
  const [pwForm, setPwForm]   = useState({ current_password: '', new_password: '', confirm: '' })
  const [pwSaved, setPwSaved] = useState(false)

  const fetchUsers = useCallback(async () => {
    try {
      const data = await apiRequest('/api/users')
      setUsers(data)
    } catch (err) {
      console.error('Failed to load users:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  // ── Add user ──────────────────────────────────────────────────────────────

  const [addForm, setAddForm] = useState(EMPTY_USER_FORM)
  const setAdd = (k) => (e) => setAddForm((f) => ({ ...f, [k]: e.target.value }))
  const addValid = addForm.username.trim() && addForm.password.length >= 8

  const handleAdd = async () => {
    setSaving(true)
    setError(null)
    try {
      await apiRequest('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(addForm),
      })
      setAddOpen(false)
      setAddForm(EMPTY_USER_FORM)
      fetchUsers()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── Delete user ───────────────────────────────────────────────────────────

  const handleDelete = async () => {
    try {
      await apiRequest(`/api/users/${encodeURIComponent(deleteUser)}`, { method: 'DELETE' })
      setDeleteUser(null)
      fetchUsers()
    } catch (err) {
      setError(err.message)
      setDeleteUser(null)
    }
  }

  // ── Admin reset password ──────────────────────────────────────────────────

  const [resetPw, setResetPw] = useState('')
  const resetValid = resetPw.length >= 8

  const handleReset = async () => {
    setSaving(true)
    setError(null)
    try {
      await apiRequest(`/api/users/${encodeURIComponent(resetUser)}/password`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: resetPw }),
      })
      setResetUser(null)
      setResetPw('')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── Own password change ───────────────────────────────────────────────────

  const pwValid = pwForm.current_password && pwForm.new_password.length >= 8 && pwForm.new_password === pwForm.confirm
  const setPw = (k) => (e) => setPwForm((f) => ({ ...f, [k]: e.target.value }))

  const handleChangeOwnPassword = async () => {
    setSaving(true)
    setError(null)
    try {
      await apiRequest('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: pwForm.current_password, new_password: pwForm.new_password }),
      })
      setPwOpen(false)
      setPwForm({ current_password: '', new_password: '', confirm: '' })
      setPwSaved(true)
      setTimeout(() => setPwSaved(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Users</p>
        <button
          className="btn-ghost flex items-center gap-1.5 text-xs px-2 py-1 border border-zinc-300 dark:border-zinc-700"
          onClick={() => { setError(null); setAddForm(EMPTY_USER_FORM); setAddOpen(true) }}
        >
          <UserPlus size={13} />
          Add user
        </button>
      </div>

      {error && (
        <div className="mb-3 flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
          <AlertCircle size={14} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-400 py-2">Loading…</p>
      ) : (
        <div className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
          {users.map((u) => {
            const isSelf = u.username === currentUsername
            return (
              <div key={u.username} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                {/* Avatar initial */}
                <div className="w-7 h-7 rounded-full bg-steel-200 dark:bg-navy-600 flex items-center justify-center text-navy-700 dark:text-steel-200 text-xs font-semibold shrink-0 select-none">
                  {u.username[0].toUpperCase()}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{u.username}</span>
                    {isSelf && <span className="text-xs text-zinc-400">(you)</span>}
                    <RoleBadge role={u.role} />
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {isSelf ? (
                    /* Own account: change password with current-password verification */
                    <button
                      className="btn-ghost p-1.5 text-xs flex items-center gap-1"
                      title="Change my password"
                      onClick={() => { setError(null); setPwForm({ current_password: '', new_password: '', confirm: '' }); setPwOpen(true) }}
                    >
                      <KeyRound size={13} />
                      {pwSaved ? <Check size={12} className="text-emerald-500" /> : null}
                    </button>
                  ) : (
                    /* Other accounts: admin reset password */
                    <button
                      className="btn-ghost p-1.5"
                      title={`Reset ${u.username}'s password`}
                      onClick={() => { setError(null); setResetPw(''); setResetUser(u.username) }}
                    >
                      <KeyRound size={13} />
                    </button>
                  )}

                  {!isSelf && (
                    <button
                      className="btn-ghost p-1.5 text-red-500 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                      title={`Delete ${u.username}`}
                      onClick={() => { setError(null); setDeleteUser(u.username) }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Add user dialog ── */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Add user">
        <div className="p-6 flex flex-col gap-4">
          <div>
            <label className="label">Username</label>
            <input className="input" placeholder="e.g. justin" value={addForm.username} onChange={setAdd('username')} autoComplete="off" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" placeholder="8+ characters" value={addForm.password} onChange={setAdd('password')} autoComplete="new-password" />
          </div>
          <div>
            <label className="label">Role</label>
            <select className="input" value={addForm.role} onChange={setAdd('role')}>
              <option value="admin">Admin — full access</option>
              <option value="viewer">Viewer — read-only</option>
            </select>
          </div>
          {error && (
            <div className="flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
            </div>
          )}
          <div className="flex justify-end gap-3 pt-2 border-t border-zinc-200 dark:border-zinc-800">
            <button className="btn-ghost" onClick={() => setAddOpen(false)} disabled={saving}>Cancel</button>
            <button className="btn-primary flex items-center gap-1.5" disabled={!addValid || saving} onClick={handleAdd}>
              <UserPlus size={14} />
              {saving ? 'Creating…' : 'Create user'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* ── Admin reset password dialog ── */}
      <Dialog open={!!resetUser} onClose={() => setResetUser(null)} title={`Reset password — ${resetUser}`} size="sm">
        <div className="p-6 flex flex-col gap-4">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Set a new password for <strong className="text-zinc-800 dark:text-zinc-200">{resetUser}</strong>.</p>
          <div>
            <label className="label">New password</label>
            <input
              className="input"
              type="password"
              placeholder="8+ characters"
              value={resetPw}
              onChange={(e) => setResetPw(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <div className="flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
            </div>
          )}
          <div className="flex justify-end gap-3 pt-2 border-t border-zinc-200 dark:border-zinc-800">
            <button className="btn-ghost" onClick={() => setResetUser(null)} disabled={saving}>Cancel</button>
            <button className="btn-primary flex items-center gap-1.5" disabled={!resetValid || saving} onClick={handleReset}>
              <KeyRound size={14} />
              {saving ? 'Saving…' : 'Set password'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* ── Own change-password dialog ── */}
      <Dialog open={pwOpen} onClose={() => setPwOpen(false)} title="Change my password" size="sm">
        <div className="p-6 flex flex-col gap-4">
          <div>
            <label className="label">Current password</label>
            <input className="input" type="password" value={pwForm.current_password} onChange={setPw('current_password')} autoComplete="current-password" />
          </div>
          <div>
            <label className="label">New password</label>
            <input className="input" type="password" placeholder="8+ characters" value={pwForm.new_password} onChange={setPw('new_password')} autoComplete="new-password" />
          </div>
          <div>
            <label className="label">Confirm new password</label>
            <input className="input" type="password" placeholder="Repeat new password" value={pwForm.confirm} onChange={setPw('confirm')} autoComplete="new-password" />
            {pwForm.confirm && pwForm.new_password !== pwForm.confirm && (
              <p className="text-xs text-red-500 mt-1">Passwords don't match</p>
            )}
          </div>
          {error && (
            <div className="flex items-start gap-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
            </div>
          )}
          <div className="flex justify-end gap-3 pt-2 border-t border-zinc-200 dark:border-zinc-800">
            <button className="btn-ghost" onClick={() => setPwOpen(false)} disabled={saving}>Cancel</button>
            <button className="btn-primary flex items-center gap-1.5" disabled={!pwValid || saving} onClick={handleChangeOwnPassword}>
              <KeyRound size={14} />
              {saving ? 'Saving…' : 'Update password'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* ── Delete user confirmation ── */}
      <Dialog open={!!deleteUser} onClose={() => setDeleteUser(null)} title="Delete user" size="sm">
        <div className="p-6">
          <p className="text-zinc-500 dark:text-zinc-400 mb-6">
            Delete <strong className="text-zinc-800 dark:text-zinc-200">{deleteUser}</strong>? They will be immediately logged out and unable to sign in.
          </p>
          <div className="flex justify-end gap-3">
            <button className="btn-ghost" onClick={() => setDeleteUser(null)}>Cancel</button>
            <button className="btn-danger" onClick={handleDelete}>Delete user</button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Setup page
// ---------------------------------------------------------------------------

export function Setup() {
  const printers = usePrinterStore((s) => s.printers)
  const statuses = usePrinterStore((s) => s.statuses)
  const farmName = usePrinterStore((s) => s.farmName)
  const setFarmName = usePrinterStore((s) => s.setFarmName)
  const currentUser = useAuthStore((s) => s.user)

  const [nameInput, setNameInput] = useState(farmName)
  const [nameSaved, setNameSaved] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editPrinter, setEditPrinter] = useState(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)
  const [deleteId, setDeleteId] = useState(null)

  const [printerTypes, setPrinterTypes] = useState([])

  const fetchTypes = useCallback(async () => {
    try {
      const data = await apiRequest('/api/printer-types')
      setPrinterTypes(data)
    } catch (err) {
      console.error('Failed to load printer types:', err)
    }
  }, [])

  useEffect(() => { fetchTypes() }, [fetchTypes])

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
          <h1 className="heading text-3xl leading-tight">Setup</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Manage your print farm printers and account</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ghost flex items-center gap-1.5 text-sm border border-zinc-300 dark:border-zinc-700"
            onClick={() => setImportOpen(true)}
          >
            <CloudDownload size={15} />
            Import from Bambu Account
          </button>
          <button className="btn-primary flex items-center gap-2 text-sm" onClick={() => { setFormError(null); setAddOpen(true) }}>
            <PlusCircle size={16} />Add printer
          </button>
        </div>
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

      {/* Printer types */}
      <PrinterTypesSection types={printerTypes} onRefresh={fetchTypes} />

      {/* Users */}
      <UsersSection currentUsername={currentUser?.username} />

      {/* Printers list */}
      <div className="flex flex-col gap-3">
        {printers.length === 0 && (
          <div className="card p-8 text-center text-zinc-400">
            <img src="/logo-badge.png" alt="" className="w-16 h-16 mx-auto mb-3 opacity-60 saturate-0" />
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
        <PrinterForm printerTypes={printerTypes} onSave={handleAdd} onCancel={() => setAddOpen(false)} saving={saving} error={formError} />
      </Dialog>

      <Dialog open={!!editPrinter} onClose={() => setEditPrinter(null)} title="Edit printer">
        {editPrinter && (() => {
          const { id: _id, ...editFields } = editPrinter
          return (
            <PrinterForm
              initial={editFields}
              printerTypes={printerTypes}
              onSave={handleEdit}
              onCancel={() => setEditPrinter(null)}
              saving={saving}
              error={formError}
            />
          )
        })()}
      </Dialog>

      <BambuImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onPrintersAdded={() => setImportOpen(false)}
      />

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
