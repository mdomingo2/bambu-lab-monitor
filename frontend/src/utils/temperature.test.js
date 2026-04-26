import { describe, it, expect } from 'vitest'
import { toF, formatTemp } from './temperature'

describe('toF', () => {
  it('converts freezing point', () => expect(toF(0)).toBe(32))
  it('converts boiling point', () => expect(toF(100)).toBe(212))
  it('converts -40 (same in both scales)', () => expect(toF(-40)).toBe(-40))
  it('converts typical nozzle temp 210°C', () => expect(toF(210)).toBeCloseTo(410, 0))
  it('converts typical bed temp 60°C', () => expect(toF(60)).toBe(140))
  it('converts room temp 22°C', () => expect(toF(22)).toBeCloseTo(71.6, 1))
})

describe('formatTemp', () => {
  describe('Celsius display', () => {
    it('renders integer with degree symbol', () => expect(formatTemp(210, 'C')).toBe('210°'))
    it('rounds fractional values', () => expect(formatTemp(209.6, 'C')).toBe('210°'))
    it('renders zero', () => expect(formatTemp(0, 'C')).toBe('0°'))
    it('renders negative', () => expect(formatTemp(-5, 'C')).toBe('-5°'))
    it('renders typical bed temp', () => expect(formatTemp(60, 'C')).toBe('60°'))
  })

  describe('Fahrenheit display', () => {
    it('appends °F suffix', () => expect(formatTemp(100, 'F')).toBe('212°F'))
    it('renders freezing in °F', () => expect(formatTemp(0, 'F')).toBe('32°F'))
    it('rounds correctly', () => expect(formatTemp(22, 'F')).toBe('72°F'))
    it('renders typical nozzle temp', () => expect(formatTemp(210, 'F')).toBe('410°F'))
  })
})
