import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useThumbnailUrl } from './useThumbnailUrl'

describe('useThumbnailUrl', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00'))
  })
  afterEach(() => vi.useRealTimers())

  it('returns a URL containing the printer ID', () => {
    const { result } = renderHook(() => useThumbnailUrl('printer-abc'))
    expect(result.current).toContain('/api/printers/printer-abc/thumbnail')
  })

  it('appends a ?t= cache-buster query parameter', () => {
    const { result } = renderHook(() => useThumbnailUrl('printer-abc'))
    expect(result.current).toMatch(/\?t=\d+/)
  })

  it('initial timestamp is seeded to current time', () => {
    const now = Date.now()
    const { result } = renderHook(() => useThumbnailUrl('printer-abc'))
    const ts = parseInt(result.current.split('?t=')[1], 10)
    expect(ts).toBe(now)
  })

  it('updates the timestamp after the interval elapses', () => {
    const { result } = renderHook(() => useThumbnailUrl('printer-abc', 120_000))
    const first = result.current

    act(() => { vi.advanceTimersByTime(120_000) })

    const second = result.current
    expect(second).not.toBe(first)
    // New timestamp should be 2 minutes ahead
    const ts1 = parseInt(first.split('?t=')[1], 10)
    const ts2 = parseInt(second.split('?t=')[1], 10)
    expect(ts2 - ts1).toBe(120_000)
  })

  it('does not update before the interval elapses', () => {
    const { result } = renderHook(() => useThumbnailUrl('printer-abc', 120_000))
    const first = result.current
    act(() => { vi.advanceTimersByTime(60_000) })
    expect(result.current).toBe(first)
  })

  it('clears the interval on unmount', () => {
    const { result, unmount } = renderHook(() => useThumbnailUrl('printer-abc', 120_000))
    const first = result.current
    unmount()
    act(() => { vi.advanceTimersByTime(300_000) })
    // After unmount the URL should be stable (the ref doesn't change)
    expect(result.current).toBe(first)
  })
})
