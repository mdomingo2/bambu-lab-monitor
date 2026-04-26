import { NavLink } from 'react-router-dom'
import { LayoutGrid, Settings, Wifi, WifiOff, Sun, Moon, History } from 'lucide-react'
import { usePrinterStore } from '../store/printerStore'
import { useUnitStore } from '../store/unitStore'
import { clsx } from 'clsx'

export function Sidebar({ onThemeToggle, theme }) {
  const connected      = usePrinterStore((s) => s.connected)
  const tempUnit       = useUnitStore((s) => s.tempUnit)
  const toggleTempUnit = useUnitStore((s) => s.toggleTempUnit)

  return (
    <aside className="w-16 shrink-0 bg-white border-r border-zinc-200 dark:bg-zinc-950 dark:border-zinc-800 flex flex-col items-center py-4 gap-2">
      {/* Logo */}
      <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center mb-4 shrink-0">
        <span className="text-lg">🖨</span>
      </div>

      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          clsx('btn-ghost flex flex-col items-center gap-0.5 py-2 px-2 text-[10px]',
            isActive && 'text-brand-600 bg-brand-50 dark:text-brand-400 dark:bg-brand-900/30')
        }
      >
        <LayoutGrid size={20} />
        <span>Farm</span>
      </NavLink>

      <NavLink
        to="/history"
        className={({ isActive }) =>
          clsx('btn-ghost flex flex-col items-center gap-0.5 py-2 px-2 text-[10px]',
            isActive && 'text-brand-600 bg-brand-50 dark:text-brand-400 dark:bg-brand-900/30')
        }
      >
        <History size={20} />
        <span>History</span>
      </NavLink>

      <NavLink
        to="/setup"
        className={({ isActive }) =>
          clsx('btn-ghost flex flex-col items-center gap-0.5 py-2 px-2 text-[10px]',
            isActive && 'text-brand-600 bg-brand-50 dark:text-brand-400 dark:bg-brand-900/30')
        }
      >
        <Settings size={20} />
        <span>Setup</span>
      </NavLink>

      <div className="mt-auto flex flex-col items-center gap-3">
        {/* °C / °F toggle */}
        <button
          onClick={toggleTempUnit}
          title={tempUnit === 'C' ? 'Switch to Fahrenheit' : 'Switch to Celsius'}
          className="btn-ghost p-1.5 text-[11px] font-semibold tabular-nums leading-none text-zinc-500 dark:text-zinc-400 hover:text-brand-600 dark:hover:text-brand-400"
        >
          °{tempUnit}
        </button>

        {/* Theme toggle */}
        <button
          onClick={onThemeToggle}
          className="btn-ghost p-2"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Connection indicator */}
        <div className="flex flex-col items-center gap-1">
          {connected
            ? <Wifi size={16} className="text-emerald-500" title="Connected" />
            : <WifiOff size={16} className="text-red-500 animate-pulse" title="Disconnected" />
          }
          <span className="text-[9px] text-zinc-400">{connected ? 'Live' : 'Off'}</span>
        </div>
      </div>
    </aside>
  )
}
