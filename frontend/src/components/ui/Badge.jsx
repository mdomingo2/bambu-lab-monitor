import { clsx } from 'clsx'

const variants = {
  default: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300',
  success: 'bg-emerald-100 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/50 dark:text-emerald-400 dark:border-emerald-800',
  warning: 'bg-amber-100 text-amber-700 border border-amber-200 dark:bg-amber-900/50 dark:text-amber-400 dark:border-amber-800',
  danger:  'bg-red-100 text-red-600 border border-red-200 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  info:    'bg-brand-100 text-brand-700 border border-brand-200 dark:bg-brand-900/50 dark:text-brand-400 dark:border-brand-800',
  muted:   'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
}

export function Badge({ children, variant = 'default', className }) {
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-display font-bold uppercase tracking-wider', variants[variant], className)}>
      {children}
    </span>
  )
}
