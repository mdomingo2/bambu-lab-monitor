/**
 * unitStore — persists the user's preferred temperature unit across sessions.
 * Stored in localStorage under "bambu-unit-prefs".
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useUnitStore = create(
  persist(
    (set, get) => ({
      tempUnit: 'C',   // 'C' | 'F'
      toggleTempUnit: () =>
        set((s) => ({ tempUnit: s.tempUnit === 'C' ? 'F' : 'C' })),
    }),
    { name: 'bambu-unit-prefs' }
  )
)
