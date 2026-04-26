/**
 * Temperature conversion and formatting utilities.
 *
 * All internal values (MQTT data, heating logic) use Celsius.
 * Only call these functions at the display layer.
 */

/** Convert Celsius to Fahrenheit. */
export const toF = (c) => (c * 9) / 5 + 32

/**
 * Format a Celsius value for display in the given unit.
 *
 * Returns a ready-to-render string including the degree symbol:
 *   formatTemp(72,  'C') → '72°'
 *   formatTemp(72,  'F') → '162°F'
 *   formatTemp(210, 'C') → '210°'
 *
 * Callers should use this instead of duplicating the conversion inline.
 *
 * @param {number} celsius - Raw value in °C
 * @param {'C'|'F'} unit   - Target display unit from unitStore
 */
export function formatTemp(celsius, unit) {
  if (unit === 'F') return `${toF(celsius).toFixed(0)}°F`
  return `${celsius.toFixed(0)}°`
}
