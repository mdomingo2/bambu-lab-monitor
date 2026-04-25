import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws':     { target: 'ws://localhost:8000',  ws: true },
      // go2rtc WebSocket signaling — needed for camera modal in dev
      '/go2rtc': { target: 'http://localhost:1984', ws: true, rewrite: (p) => p.replace(/^\/go2rtc/, '') },
    },
  },
})
