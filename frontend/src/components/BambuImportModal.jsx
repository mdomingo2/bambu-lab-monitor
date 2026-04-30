/**
 * BambuImportModal — Multi-step wizard to import printers from a Bambu Labs
 * cloud account.
 *
 * Steps:
 *   1. Login  — email + password → POST /api/bambu-cloud/login
 *   2. 2FA    — verification code (only shown when account has 2FA enabled)
 *   3. Select — choose which cloud printers to add; enter LAN IPs
 *   4. Done
 */
import { useState } from 'react'
import { AlertCircle, Check, ChevronRight, CloudDownload, Loader2, RefreshCw } from 'lucide-react'
import { Dialog } from './ui/Dialog'

const MODELS = ['A1', 'A1 Mini', 'P1P', 'P1S', 'P2S', 'X1C', 'X1E', 'H2D']

async function api(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`)
  return data
}

// ── Step 1: Login form ────────────────────────────────────────────────────────

function StepLogin({ onResult }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password) return
    setLoading(true); setError('')
    try {
      const data = await api('/api/bambu-cloud/login', { email: email.trim(), password })
      onResult(data, email.trim(), password)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Sign in with your Bambu Labs account to automatically discover your printers
        and fill in their serial numbers and access codes.
      </p>

      {error && <ErrorBox message={error} />}

      <div>
        <label className="label">Bambu Labs email</label>
        <input className="input" type="email" autoComplete="email"
               placeholder="you@example.com" value={email}
               onChange={(e) => setEmail(e.target.value)} disabled={loading} autoFocus />
      </div>
      <div>
        <label className="label">Password</label>
        <input className="input" type="password" autoComplete="current-password"
               placeholder="••••••••" value={password}
               onChange={(e) => setPassword(e.target.value)} disabled={loading} />
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button type="submit"
                disabled={loading || !email.trim() || !password}
                className="btn-primary flex items-center gap-2">
          {loading ? <Loader2 size={15} className="animate-spin" /> : <ChevronRight size={15} />}
          {loading ? 'Connecting…' : 'Continue'}
        </button>
      </div>
    </form>
  )
}

// ── Step 2: 2FA code ──────────────────────────────────────────────────────────

function Step2FA({ tfaKey, email, password, onResult, onNewTfaKey }) {
  const [code, setCode]       = useState('')
  const [error, setError]     = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [resent, setResent]   = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (code.length < 4) return
    setLoading(true); setError('')
    try {
      const data = await api('/api/bambu-cloud/verify', { tfa_key: tfaKey, code })
      onResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const resend = async () => {
    setResending(true); setError(''); setResent(false)
    try {
      const data = await api('/api/bambu-cloud/login', { email, password })
      if (data.tfa_key) {
        onNewTfaKey(data.tfa_key)
        setCode('')
        setResent(true)
        setTimeout(() => setResent(false), 4000)
      }
    } catch (err) {
      setError('Could not resend code: ' + err.message)
    } finally {
      setResending(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        A verification code was sent to your email. Enter it below.
      </p>
      {error && <ErrorBox message={error} />}
      {resent && (
        <div className="flex items-center gap-2 bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400 rounded-lg px-3 py-2 text-sm">
          <Check size={14} className="shrink-0" />
          New code sent — check your email.
        </div>
      )}
      <div>
        <label className="label">Verification code</label>
        <input className="input font-mono text-center tracking-widest text-lg"
               type="text" inputMode="numeric" maxLength={8} placeholder="123456"
               value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
               disabled={loading || resending} autoFocus />
      </div>
      <div className="flex items-center justify-between">
        <button type="button" onClick={resend}
                disabled={resending || loading}
                className="btn-ghost flex items-center gap-1.5 text-sm text-zinc-500">
          {resending
            ? <Loader2 size={13} className="animate-spin" />
            : <RefreshCw size={13} />}
          {resending ? 'Sending…' : 'Resend code'}
        </button>
        <button type="submit" disabled={loading || resending || code.length < 4}
                className="btn-primary flex items-center gap-2">
          {loading ? <Loader2 size={15} className="animate-spin" /> : <ChevronRight size={15} />}
          {loading ? 'Verifying…' : 'Verify'}
        </button>
      </div>
    </form>
  )
}

// ── Step 3: Device selection + IP entry ───────────────────────────────────────

function StepDevices({ token, onImport }) {
  const [devices, setDevices]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [ips, setIps]           = useState({})        // serial → ip string
  const [models, setModels]     = useState({})        // serial → model override
  const [selected, setSelected] = useState({})        // serial → boolean
  const [importing, setImporting] = useState(false)

  // Fetch device list immediately when this step mounts.
  const fetchDevices = async () => {
    setLoading(true); setError('')
    try {
      const data = await api('/api/bambu-cloud/devices', { token })
      const devs = data.devices || []
      setDevices(devs)
      const initSelected = {}
      const initModels   = {}
      devs.forEach((d) => {
        initSelected[d.serial] = true
        initModels[d.serial]   = d.model
      })
      setSelected(initSelected)
      setModels(initModels)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Run on mount (inside useEffect equivalent via component mounting)
  if (devices === null && !loading && !error) fetchDevices()
  // Kick off fetch once
  if (devices === null && !error) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    void (async () => { if (loading) await fetchDevices() })()
  }

  const anySelected = devices && devices.some((d) => selected[d.serial] && ips[d.serial]?.trim())

  const doImport = async () => {
    setImporting(true)
    const toAdd = devices.filter((d) => selected[d.serial] && ips[d.serial]?.trim())
    await onImport(toAdd.map((d) => ({
      name:        d.name,
      model:       models[d.serial] || d.model,
      serial:      d.serial,
      ip:          ips[d.serial].trim(),
      access_code: d.access_code,
      lan_mode:    d.lan_mode,
    })))
    setImporting(false)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-zinc-400">
        <Loader2 size={20} className="animate-spin" />
        <span className="text-sm">Fetching your printers…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <ErrorBox message={error} />
        <button onClick={fetchDevices} className="btn-secondary self-start">Retry</button>
      </div>
    )
  }

  if (!devices?.length) {
    return (
      <p className="text-sm text-zinc-500 py-6 text-center">
        No printers found in your Bambu account.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Select the printers to add and enter each one's local IP address.
        The serial number and access code are pre-filled from your account.
      </p>

      <div className="flex flex-col gap-3 max-h-72 overflow-y-auto pr-1">
        {devices.map((d) => (
          <label key={d.serial}
                 className={`flex flex-col gap-2 p-3 rounded-xl border cursor-pointer transition-colors
                   ${selected[d.serial]
                     ? 'border-brand-500 bg-brand-50/40 dark:bg-brand-900/20'
                     : 'border-zinc-200 dark:border-zinc-700 opacity-60'}`}>
            {/* Header row */}
            <div className="flex items-center gap-2">
              <input type="checkbox"
                     checked={!!selected[d.serial]}
                     onChange={(e) => setSelected((s) => ({ ...s, [d.serial]: e.target.checked }))}
                     className="accent-brand-600 w-4 h-4 shrink-0" />
              <span className="font-medium text-sm text-zinc-900 dark:text-zinc-100">{d.name}</span>
              {d.online && (
                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 font-medium">
                  Online
                </span>
              )}
            </div>

            {selected[d.serial] && (
              <div className="grid grid-cols-2 gap-2 pl-6">
                {/* Model selector */}
                <div>
                  <label className="label text-[10px]">Model</label>
                  <select className="input text-sm py-1"
                          value={models[d.serial] || d.model}
                          onChange={(e) => setModels((m) => ({ ...m, [d.serial]: e.target.value }))}>
                    {MODELS.map((m) => <option key={m}>{m}</option>)}
                  </select>
                </div>
                {/* IP address */}
                <div>
                  <label className="label text-[10px]">LAN IP address <span className="text-red-500">*</span></label>
                  <input className="input text-sm py-1 font-mono"
                         placeholder="192.168.1.x"
                         value={ips[d.serial] || ''}
                         onChange={(e) => setIps((i) => ({ ...i, [d.serial]: e.target.value }))} />
                </div>
                {/* Serial (read-only) */}
                <div>
                  <label className="label text-[10px]">Serial</label>
                  <input className="input text-sm py-1 font-mono bg-zinc-50 dark:bg-zinc-800"
                         value={d.serial} readOnly />
                </div>
                {/* Access code (read-only) */}
                <div>
                  <label className="label text-[10px]">Access code</label>
                  <input className="input text-sm py-1 font-mono bg-zinc-50 dark:bg-zinc-800"
                         value={d.access_code} readOnly />
                </div>
              </div>
            )}
          </label>
        ))}
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button onClick={doImport}
                disabled={importing || !anySelected}
                className="btn-primary flex items-center gap-2">
          {importing ? <Loader2 size={15} className="animate-spin" /> : <CloudDownload size={15} />}
          {importing ? 'Adding…' : 'Add selected printers'}
        </button>
      </div>
    </div>
  )
}

// ── Step 4: Done ─────────────────────────────────────────────────────────────

function StepDone({ count, onClose }) {
  return (
    <div className="flex flex-col items-center gap-4 py-6">
      <div className="w-14 h-14 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
        <Check size={28} className="text-emerald-600 dark:text-emerald-400" />
      </div>
      <div className="text-center">
        <p className="font-semibold text-zinc-900 dark:text-zinc-100">
          {count} printer{count !== 1 ? 's' : ''} added!
        </p>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          Your printers are now connecting via MQTT.
        </p>
      </div>
      <button onClick={onClose} className="btn-primary px-6">Done</button>
    </div>
  )
}

// ── Shared error box ──────────────────────────────────────────────────────────

function ErrorBox({ message }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-3 py-2 text-sm">
      <AlertCircle size={15} className="shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  )
}

// ── Main modal ────────────────────────────────────────────────────────────────

const STEP_TITLES = {
  login:   'Import from Bambu Account',
  tfa:     'Two-Factor Verification',
  devices: 'Select Printers',
  done:    'Import Complete',
}

export function BambuImportModal({ open, onClose, onPrintersAdded }) {
  const [step, setStep]         = useState('login')
  const [tfaKey, setTfaKey]     = useState('')
  const [token, setToken]       = useState('')
  const [addedCount, setAddedCount] = useState(0)
  // Kept only long enough to support "Resend code"; cleared on close.
  const [savedEmail, setSavedEmail]       = useState('')
  const [savedPassword, setSavedPassword] = useState('')

  const handleClose = () => {
    setStep('login')
    setTfaKey('')
    setToken('')
    setAddedCount(0)
    setSavedEmail('')
    setSavedPassword('')
    onClose()
  }

  const onLoginResult = (data, email, password) => {
    if (data.needs_2fa) {
      setTfaKey(data.tfa_key)
      setSavedEmail(email)
      setSavedPassword(password)
      setStep('tfa')
    } else {
      setToken(data.token)
      setStep('devices')
    }
  }

  const onVerifyResult = (data) => {
    setSavedEmail('')
    setSavedPassword('')
    setToken(data.token)
    setStep('devices')
  }

  const onImport = async (printers) => {
    let added = 0
    for (const p of printers) {
      try {
        const r = await fetch('/api/printers', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(p),
        })
        if (r.ok) added++
      } catch { /* ignore individual failures */ }
    }
    setAddedCount(added)
    setStep('done')
    if (added > 0) onPrintersAdded?.()
  }

  return (
    <Dialog open={open} onClose={step === 'done' ? handleClose : handleClose}
            title={STEP_TITLES[step]}>
      <div className="p-6 pt-2">
        {/* Step indicator (not shown for done) */}
        {step !== 'done' && (
          <div className="flex items-center gap-1 mb-5">
            {['login', 'tfa', 'devices'].map((s, i) => (
              <div key={s} className="flex items-center gap-1">
                <div className={`w-5 h-5 rounded-full text-[10px] flex items-center justify-center font-bold transition-colors
                  ${s === step
                    ? 'bg-brand-600 text-white'
                    : ['login', 'tfa', 'devices'].indexOf(step) > i
                      ? 'bg-emerald-500 text-white'
                      : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-400'
                  }`}>
                  {['login', 'tfa', 'devices'].indexOf(step) > i ? <Check size={11} /> : i + 1}
                </div>
                {i < 2 && <div className="w-6 h-px bg-zinc-200 dark:bg-zinc-700" />}
              </div>
            ))}
          </div>
        )}

        {step === 'login'   && <StepLogin onResult={onLoginResult} />}
        {step === 'tfa'     && <Step2FA tfaKey={tfaKey} email={savedEmail} password={savedPassword} onResult={onVerifyResult} onNewTfaKey={setTfaKey} />}
        {step === 'devices' && <StepDevices token={token} onImport={onImport} />}
        {step === 'done'    && <StepDone count={addedCount} onClose={handleClose} />}
      </div>
    </Dialog>
  )
}
