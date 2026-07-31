/**
 * Shared constants used across multiple components.
 *
 * Centralising them here avoids silent drift when values need to change
 * (e.g. adjusting the chamber temperature noise floor).
 */

/**
 * Chamber temperatures below this threshold (°C) are considered noise —
 * printers without an enclosure or in cloud mode report 0–5 °C.
 * Suppress those readings so the UI doesn't show a meaningless "5°" cell.
 */
export const CHAMBER_TEMP_MIN = 15

/**
 * Top-border accent colour per printer model.
 * Used on PrinterCard tiles to give each model a distinct identity.
 */
export const MODEL_ACCENT = {
  A1:  'border-t-steel-400',
  P1S: 'border-t-brand-500',
  P2S: 'border-t-emerald-500',
  H2D: 'border-t-amber-500',
  H2S: 'border-t-navy-500',
}
