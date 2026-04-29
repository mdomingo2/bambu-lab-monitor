/**
 * useWebSocket — maintains the persistent WebSocket connection to the backend.
 *
 * Dispatches incoming messages to the Zustand printer store and handles
 * automatic reconnection with a 3-second delay after any close/error.
 * Also requests browser notification permission on first mount.
 */
import { useEffect, useRef } from 'react'
import { usePrinterStore } from '../store/printerStore'
import { useAuthStore } from '../store/authStore'

// Derive the WebSocket URL from the current page protocol so the app works
// on both http (ws://) and https (wss://) origins.
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss' : 'ws'
const WS_URL = `${WS_PROTOCOL}://${window.location.host}/ws`

function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

function showNotification(title, body, icon = '/favicon.ico') {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, { body, icon })
  }
}

// WebSocket close codes that mean "you are not authenticated"
const AUTH_CLOSE_CODES = new Set([
  4001,  // our custom unauthorized code
  1008,  // Policy Violation (standard)
])

export function useWebSocket() {
  const ws             = useRef(null)
  const reconnectTimer = useRef(null)
  const logout         = useAuthStore.getState().logout

  const {
    setConnected, setPrinters, addPrinter, updatePrinter, removePrinter,
    updateStatus, setAllStatuses, setFarmName,
    setAllDismissedAlerts, updateDismissedAlerts,
  } = usePrinterStore()

  const connect = () => {
    ws.current = new WebSocket(WS_URL)

    ws.current.onopen = () => {
      setConnected(true)
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }

    ws.current.onclose = (event) => {
      setConnected(false)
      // Auth error — clear local session and let ProtectedRoute redirect to login.
      if (AUTH_CLOSE_CODES.has(event.code)) {
        logout()
        return
      }
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.current.onerror = () => {
      // Let onclose handle the reconnect — just close cleanly here.
      ws.current?.close()
    }

    ws.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        switch (msg.type) {
          case 'init':
            setPrinters(msg.data.printers)
            setAllStatuses(msg.data.statuses)
            if (msg.data.settings?.farm_name) setFarmName(msg.data.settings.farm_name)
            if (msg.data.dismissed_alerts)    setAllDismissedAlerts(msg.data.dismissed_alerts)
            break

          case 'status_update':
            updateStatus(msg.data)
            break

          case 'printers_update':
            if (msg.data.action === 'add')         addPrinter(msg.data.printer)
            else if (msg.data.action === 'update') updatePrinter(msg.data.printer)
            else if (msg.data.action === 'delete') removePrinter(msg.data.printer_id)
            break

          case 'settings_update':
            if (msg.data.farm_name) setFarmName(msg.data.farm_name)
            break

          case 'dismissed_alerts_update':
            updateDismissedAlerts(msg.data.printer_id, msg.data.dismissed)
            break

          case 'print_event': {
            const { event, printer_name, file_name } = msg.data
            if (event === 'completed') {
              showNotification(`✅ ${printer_name} — Print complete`, file_name || '')
            } else if (event === 'failed') {
              showNotification(`❌ ${printer_name} — Print failed`, file_name || '')
            }
            break
          }

          default:
            break
        }
      } catch (err) {
        console.error('[ws] parse error', err)
      }
    }
  }

  useEffect(() => {
    requestNotificationPermission()
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}
