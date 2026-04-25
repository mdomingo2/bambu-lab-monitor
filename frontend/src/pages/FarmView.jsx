import { usePrinterStore } from '../store/printerStore'
import { PrinterCard } from '../components/PrinterCard'
import { Link } from 'react-router-dom'
import { PlusCircle } from 'lucide-react'

export function FarmView() {
  const printers        = usePrinterStore((s) => s.printers)
  const statuses        = usePrinterStore((s) => s.statuses)
  const farmName        = usePrinterStore((s) => s.farmName)
  const dismissedAlerts = usePrinterStore((s) => s.dismissedAlerts)

  const printing = printers.filter((p) => statuses[p.id]?.gcode_state === 'RUNNING').length
  const idle = printers.length - printing

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{farmName}</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            {printers.length} printer{printers.length !== 1 && 's'} ·{' '}
            <span className="text-emerald-600 dark:text-emerald-500">{printing} printing</span> ·{' '}
            <span className="text-zinc-400">{idle} idle</span>
          </p>
        </div>
        <Link to="/setup" className="btn-primary flex items-center gap-2 text-sm">
          <PlusCircle size={16} />
          Add Printer
        </Link>
      </div>

      {printers.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-zinc-400 gap-3">
          <span className="text-5xl">🖨</span>
          <p className="text-lg font-medium">No printers configured</p>
          <Link to="/setup" className="btn-primary text-sm">Add your first printer</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {printers.map((p) => (
            <PrinterCard key={p.id} printer={p} status={statuses[p.id]} dismissed={dismissedAlerts[p.id] ?? []} />
          ))}
        </div>
      )}
    </div>
  )
}
