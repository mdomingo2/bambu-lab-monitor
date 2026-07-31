/**
 * IdlePlaceholder — shown on cards when a printer is idle or has just finished.
 *
 * Renders a small inline SVG of a printer:
 *   FINISH state → printer with a checkmark and confetti dots
 *   IDLE state   → printer with a blank paper and sparkle dots
 */

export function IdlePlaceholder({ state }) {
  const finished = state === 'FINISH'
  return (
    <div className="w-full h-28 rounded bg-zinc-100 dark:bg-zinc-800 mb-3 flex flex-col items-center justify-center gap-2 select-none">
      {finished ? (
        /* ── Finished: printer + checkmark + confetti dots ── */
        <svg width="52" height="44" viewBox="0 0 52 44" fill="none">
          {/* body */}
          <rect x="8" y="18" width="34" height="20" rx="5" className="fill-zinc-300 dark:fill-zinc-600" />
          {/* feeder */}
          <rect x="14" y="7" width="22" height="14" rx="3" className="fill-zinc-200 dark:fill-zinc-700" />
          {/* slot */}
          <rect x="10" y="25" width="30" height="3" rx="1.5" className="fill-zinc-400 dark:fill-zinc-500" />
          {/* paper */}
          <rect x="16" y="9" width="16" height="17" rx="1.5" fill="white" />
          {/* checkmark */}
          <path d="M20 18.5 L23 21.5 L29 14.5" stroke="#2E8B57" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {/* confetti */}
          <circle cx="4"  cy="10" r="2"   fill="#F0812B" opacity="0.8" />
          <circle cx="48" cy="8"  r="1.5" fill="#F0812B" opacity="0.7" />
          <circle cx="46" cy="34" r="2"   fill="#9FB0B9" opacity="0.7" />
          <circle cx="6"  cy="34" r="1.5" fill="#2E8B57" opacity="0.7" />
          <circle cx="48" cy="22" r="1"   fill="#FF9A4D" opacity="0.8" />
          <circle cx="4"  cy="24" r="1"   fill="#9FB0B9" opacity="0.6" />
        </svg>
      ) : (
        /* ── Idle: printer + blank paper + sparkle dots ── */
        <svg width="52" height="44" viewBox="0 0 52 44" fill="none">
          {/* body */}
          <rect x="8" y="18" width="34" height="20" rx="5" className="fill-zinc-300 dark:fill-zinc-600" />
          {/* feeder */}
          <rect x="14" y="7" width="22" height="14" rx="3" className="fill-zinc-200 dark:fill-zinc-700" />
          {/* slot */}
          <rect x="10" y="25" width="30" height="3" rx="1.5" className="fill-zinc-400 dark:fill-zinc-500" />
          {/* blank paper */}
          <rect x="16" y="9" width="16" height="17" rx="1.5" fill="white" />
          {/* dashes suggesting empty page */}
          <line x1="19" y1="15" x2="29" y2="15" stroke="#C3CED4" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 2" />
          <line x1="19" y1="19" x2="27" y2="19" stroke="#C3CED4" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 2" />
          {/* sparkles */}
          <circle cx="4"  cy="10" r="2"   fill="#9FB0B9" opacity="0.7" />
          <circle cx="48" cy="12" r="1.5" fill="#F0812B" opacity="0.7" />
          <circle cx="46" cy="30" r="1"   fill="#9FB0B9" opacity="0.5" />
          <circle cx="5"  cy="28" r="1.5" fill="#F0812B" opacity="0.5" />
        </svg>
      )}
      <p className="text-[11px] font-medium text-zinc-400 dark:text-zinc-500 tracking-wide">
        {finished ? 'Print complete — ready for the next one!' : "Bed's free — what shall we print?"}
      </p>
    </div>
  )
}
