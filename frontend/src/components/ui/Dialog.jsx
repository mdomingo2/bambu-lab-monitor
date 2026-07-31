import { useEffect } from 'react'
import { X } from 'lucide-react'
import { clsx } from 'clsx'

export function Dialog({ open, onClose, title, children, size = 'md' }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    if (open) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  const sizes = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl', full: 'max-w-6xl' }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className={clsx('relative card w-full shadow-2xl flex flex-col max-h-[90vh]', sizes[size])}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 shrink-0">
          <h2 className="heading text-xl leading-tight">{title}</h2>
          <button onClick={onClose} className="btn-ghost p-1"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  )
}
