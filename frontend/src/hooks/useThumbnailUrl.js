/**
 * useThumbnailUrl — returns a thumbnail URL with an auto-refreshing cache-buster.
 *
 * The `?t=<timestamp>` query parameter changes every `intervalMs` milliseconds
 * (default 2 minutes), which causes the browser to re-fetch the image rather
 * than serve the stale cached version.  The timestamp is seeded to the current
 * time on mount so the first load is always fresh.
 *
 * @param {string}  printerId  - Printer UUID
 * @param {number}  [intervalMs=120000] - Refresh interval in milliseconds
 * @returns {string}  Full URL ready to use as an <img> src
 */
import { useState, useEffect } from 'react'

export function useThumbnailUrl(printerId, intervalMs = 2 * 60 * 1000) {
  const [tick, setTick] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])

  return `/api/printers/${printerId}/thumbnail?t=${tick}`
}
