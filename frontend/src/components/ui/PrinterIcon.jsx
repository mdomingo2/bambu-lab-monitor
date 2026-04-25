/**
 * PrinterIcon — front-view silhouette icons for Bambu Lab printer models.
 *
 * Each icon uses a 40×40 viewBox and fill="currentColor" so it inherits
 * whatever text colour the parent sets (dark-mode compatible, Tailwind-friendly).
 *
 * Usage:
 *   <PrinterIcon model="P1S" size={48} className="text-brand-500" />
 *
 * Supported models: A1, P1S, P2S, H2D
 * Falls back to a generic box icon for unknown models.
 */

// ── A1 — open-frame bed-slinger ──────────────────────────────────────────────
//
//  ┌──────────────────────────┐  ← top cross-beam
//  │                          │  ← left/right rails (open interior)
//  ├──────────┬───┬───────────┤  ← X-axis gantry
//  │          │ ◉ │           │  ← toolhead carriage
//  │          └───┘           │
//  │           ▼              │  ← nozzle tip
//  ╘══════════════════════════╛  ← heated bed (wider than frame)
//
function A1Icon({ size }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="currentColor" aria-hidden="true">
      {/* Top cross-beam */}
      <rect x="7" y="3" width="26" height="3" rx="1.5" />
      {/* Left upright rail */}
      <rect x="7" y="3" width="3" height="23" rx="1.5" />
      {/* Right upright rail */}
      <rect x="30" y="3" width="3" height="23" rx="1.5" />
      {/* X-axis gantry bar */}
      <rect x="7" y="14.5" width="26" height="2.5" rx="1" />
      {/* Toolhead carriage body */}
      <rect x="16" y="17" width="8" height="7" rx="1.5" />
      {/* Nozzle tip (triangle) */}
      <path d="M17.5 24 L22.5 24 L20 27.5 Z" />
      {/* Heated bed — wider than the frame to show bed-slinger nature */}
      <rect x="2" y="30" width="36" height="5" rx="2.5" />
    </svg>
  )
}

// ── P1S — enclosed CoreXY ────────────────────────────────────────────────────
//
//  ╔══════════════════╗
//  ║  ┌────────────┐  ║  ← front window / door
//  ║  │            │  ╟─  ← door handle (right side)
//  ║  │            │  ║
//  ║  └────────────┘  ║
//  ║  ┌────────────┐  ║  ← bottom control panel strip
//  ╚══════════════════╝
//
function P1SIcon({ size }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="currentColor" aria-hidden="true">
      {/* Enclosure body — faint fill shows enclosed volume */}
      <rect x="4" y="2" width="32" height="36" rx="3" opacity="0.12" />
      {/* Thick walls drawn as filled rectangles */}
      <rect x="4"    y="2"    width="32" height="3.5" rx="2" />   {/* top wall */}
      <rect x="4"    y="34.5" width="32" height="3.5" rx="2" />   {/* bottom wall */}
      <rect x="4"    y="2"    width="3.5" height="36" rx="2" />   {/* left wall */}
      <rect x="32.5" y="2"    width="3.5" height="36" rx="2" />   {/* right wall */}
      {/* Front window border */}
      <rect x="10" y="7"  width="18" height="2"  rx="1" />        {/* window top */}
      <rect x="10" y="7"  width="2"  height="17" rx="1" />        {/* window left */}
      <rect x="26" y="7"  width="2"  height="17" rx="1" />        {/* window right */}
      <rect x="10" y="22" width="18" height="2"  rx="1" />        {/* window bottom */}
      {/* Window glass — subtle fill */}
      <rect x="12" y="9" width="14" height="13" rx="1" opacity="0.12" />
      {/* Door handle on right edge */}
      <rect x="29" y="13" width="2" height="8" rx="1" />
      {/* Bottom control panel strip */}
      <rect x="10" y="27" width="18" height="5" rx="1.5" opacity="0.35" />
    </svg>
  )
}

// ── P2S — larger enclosed CoreXY ─────────────────────────────────────────────
//
//  Distinguishable from P1S by:
//  • Slightly wider enclosure
//  • Taller, larger window
//  • Small raised sensor/hub bump on the top lid
//
function P2SIcon({ size }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="currentColor" aria-hidden="true">
      {/* Enclosure body */}
      <rect x="3" y="3" width="34" height="35" rx="3" opacity="0.12" />
      <rect x="3"    y="3"    width="34" height="3.5" rx="2" />   {/* top wall */}
      <rect x="3"    y="34.5" width="34" height="3.5" rx="2" />   {/* bottom wall */}
      <rect x="3"    y="3"    width="3.5" height="35" rx="2" />   {/* left wall */}
      <rect x="33.5" y="3"    width="3.5" height="35" rx="2" />   {/* right wall */}
      {/* Top sensor / filament hub bump — distinguishes P2S from P1S */}
      <rect x="14" y="1" width="12" height="3" rx="1.5" />
      {/* Larger window (taller than P1S) */}
      <rect x="9"  y="8"  width="20" height="2"  rx="1" />        {/* top */}
      <rect x="9"  y="8"  width="2"  height="19" rx="1" />        {/* left */}
      <rect x="27" y="8"  width="2"  height="19" rx="1" />        {/* right */}
      <rect x="9"  y="25" width="20" height="2"  rx="1" />        {/* bottom */}
      {/* Window glass */}
      <rect x="11" y="10" width="16" height="15" rx="1" opacity="0.12" />
      {/* Door handle */}
      <rect x="30" y="14" width="2" height="8" rx="1" />
      {/* Bottom control panel */}
      <rect x="9" y="29.5" width="20" height="4" rx="1.5" opacity="0.35" />
    </svg>
  )
}

// ── H2D — dual-extruder enclosed ─────────────────────────────────────────────
//
//  Same enclosure profile as P1S but inside the window you can see two
//  distinct toolhead bodies side-by-side — the H2D's signature feature.
//
function H2DIcon({ size }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="currentColor" aria-hidden="true">
      {/* Enclosure body */}
      <rect x="4" y="2" width="32" height="36" rx="3" opacity="0.12" />
      <rect x="4"    y="2"    width="32" height="3.5" rx="2" />
      <rect x="4"    y="34.5" width="32" height="3.5" rx="2" />
      <rect x="4"    y="2"    width="3.5" height="36" rx="2" />
      <rect x="32.5" y="2"    width="3.5" height="36" rx="2" />
      {/* Window border */}
      <rect x="10" y="7"  width="18" height="2"  rx="1" />
      <rect x="10" y="7"  width="2"  height="17" rx="1" />
      <rect x="26" y="7"  width="2"  height="17" rx="1" />
      <rect x="10" y="22" width="18" height="2"  rx="1" />
      {/* Window glass */}
      <rect x="12" y="9" width="14" height="13" rx="1" opacity="0.1" />
      {/* Left toolhead body */}
      <rect x="13" y="10" width="5.5" height="7" rx="1.5" opacity="0.8" />
      {/* Left nozzle tip */}
      <path d="M13.5 17 L18 17 L16 20 Z" opacity="0.8" />
      {/* Right toolhead body */}
      <rect x="20.5" y="10" width="5.5" height="7" rx="1.5" opacity="0.8" />
      {/* Right nozzle tip */}
      <path d="M21 17 L26 17 L24 20 Z" opacity="0.8" />
      {/* Door handle */}
      <rect x="29" y="13" width="2" height="8" rx="1" />
      {/* Bottom control panel */}
      <rect x="10" y="27" width="18" height="5" rx="1.5" opacity="0.35" />
    </svg>
  )
}

// ── Generic fallback ──────────────────────────────────────────────────────────
function GenericIcon({ size }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="currentColor" aria-hidden="true">
      <rect x="5" y="5" width="30" height="30" rx="4" opacity="0.15" />
      <rect x="5"  y="5"  width="30" height="3.5" rx="2" />
      <rect x="5"  y="31.5" width="30" height="3.5" rx="2" />
      <rect x="5"  y="5"  width="3.5" height="30" rx="2" />
      <rect x="31.5" y="5" width="3.5" height="30" rx="2" />
      <rect x="11" y="10" width="18" height="15" rx="2" opacity="0.2" />
    </svg>
  )
}

// ── Public component ──────────────────────────────────────────────────────────

const ICONS = { A1: A1Icon, P1S: P1SIcon, P2S: P2SIcon, H2D: H2DIcon }

/**
 * @param {string}  model      One of A1 | P1S | P2S | H2D
 * @param {number}  size       Width/height in px (default 40)
 * @param {string}  className  Tailwind classes applied to the wrapping <span>
 */
export function PrinterIcon({ model, size = 40, className = '' }) {
  const Icon = ICONS[model] ?? GenericIcon
  return (
    <span className={`inline-flex items-center justify-center shrink-0 ${className}`}>
      <Icon size={size} />
    </span>
  )
}
