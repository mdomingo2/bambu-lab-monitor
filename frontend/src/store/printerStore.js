import { create } from 'zustand'

export const usePrinterStore = create((set, get) => ({
  printers:        [],
  statuses:        {},
  dismissedAlerts: {},   // { [printer_id]: string[] }
  connected:       false,
  farmName:        'Print Farm',

  setConnected: (connected) => set({ connected }),
  setFarmName:  (farmName)  => set({ farmName }),

  setPrinters: (printers) => set({ printers }),

  addPrinter: (printer) =>
    set((state) => ({ printers: [...state.printers, printer] })),

  updatePrinter: (printer) =>
    set((state) => ({
      printers: state.printers.map((p) => (p.id === printer.id ? printer : p)),
    })),

  removePrinter: (printerId) =>
    set((state) => ({
      printers:        state.printers.filter((p) => p.id !== printerId),
      statuses:        Object.fromEntries(Object.entries(state.statuses).filter(([k]) => k !== printerId)),
      dismissedAlerts: Object.fromEntries(Object.entries(state.dismissedAlerts).filter(([k]) => k !== printerId)),
    })),

  updateStatus: (status) =>
    set((state) => ({
      statuses: { ...state.statuses, [status.printer_id]: status },
    })),

  setAllStatuses: (statuses) => set({ statuses }),

  /** Replace the full dismissed-alerts map received in the init payload. */
  setAllDismissedAlerts: (dismissedAlerts) => set({ dismissedAlerts }),

  /** Apply a single-printer update broadcast after a dismiss/restore action. */
  updateDismissedAlerts: (printerId, codes) =>
    set((state) => ({
      dismissedAlerts: { ...state.dismissedAlerts, [printerId]: codes },
    })),

}))
