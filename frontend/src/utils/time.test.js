import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { formatTime, eta } from './time'

describe('formatTime', () => {
  it('returns em dash for 0', () => expect(formatTime(0)).toBe('—'))
  it('returns em dash for null', () => expect(formatTime(null)).toBe('—'))
  it('returns em dash for undefined', () => expect(formatTime(undefined)).toBe('—'))

  it('formats minutes under an hour', () => expect(formatTime(45)).toBe('45m'))
  it('formats exactly 1 minute', () => expect(formatTime(1)).toBe('1m'))
  it('formats exactly 60 minutes', () => expect(formatTime(60)).toBe('1h 0m'))
  it('formats 90 minutes', () => expect(formatTime(90)).toBe('1h 30m'))
  it('formats 120 minutes', () => expect(formatTime(120)).toBe('2h 0m'))
  it('formats 150 minutes', () => expect(formatTime(150)).toBe('2h 30m'))
  it('formats many hours', () => expect(formatTime(600)).toBe('10h 0m'))
})

describe('eta', () => {
  beforeEach(() => {
    // Pin Date.now() to a fixed timestamp so ETA is deterministic
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00'))
  })
  afterEach(() => vi.useRealTimers())

  it('returns null for 0 minutes', () => expect(eta(0)).toBeNull())
  it('returns null for null', () => expect(eta(null)).toBeNull())
  it('returns null for undefined', () => expect(eta(undefined)).toBeNull())

  it('returns a non-empty string for valid minutes', () => {
    const result = eta(60)
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('ETA 60 minutes from noon is 1:00 PM', () => {
    const result = eta(60)
    // toLocaleTimeString format varies by locale, but 1:00 PM should appear
    expect(result).toMatch(/1:00/)
  })

  it('ETA 90 minutes from noon is 1:30 PM', () => {
    expect(eta(90)).toMatch(/1:30/)
  })
})
