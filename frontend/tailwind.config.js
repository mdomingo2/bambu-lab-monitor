/** @type {import('tailwindcss').Config} */

// Justin's 3D Printing Lab — brand palette (see brand guide in Google Drive).
// Navy is the badge field, steel the machined neutral, orange the one accent.
const navy = {
  400: '#3E7590',
  500: '#2A5A73',
  600: '#1B4256',
  700: '#12303F',
  800: '#0B2231',
  900: '#071722',
  950: '#050F17',
}

const steel = {
  50:  '#F7F9FA',
  100: '#EEF2F4',
  200: '#DFE5E9',
  300: '#C3CED4',
  400: '#9FB0B9',
  500: '#7E939E',
  600: '#63808F',
  700: '#4A6272',
  800: '#33454F',
}

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy,
        steel,
        // Filament orange — the hot end, the extrusion, the one accent.
        brand: {
          50:  '#FEF5EC',
          100: '#FDEBD9',
          200: '#FCD3AF',
          300: '#FDBE85',
          400: '#FF9A4D',
          500: '#F0812B',
          600: '#C85F14',
          700: '#A44A0C',
          800: '#7C370A',
          900: '#5A2807',
          950: '#3B1A04',
        },
        // Remap the app-wide neutral scale: steel in light mode, navy in dark.
        zinc: {
          50:  steel[50],
          100: steel[100],
          200: steel[200],
          300: steel[300],
          400: steel[400],
          500: steel[500],
          600: steel[600],
          700: steel[800],
          800: navy[600],
          900: navy[800],
          950: navy[900],
        },
        // Brand status colors (guide: green/amber/red 500 + 100 tints)
        emerald: { 100: '#DFF0E6', 500: '#2E8B57', 600: '#27754A' },
        amber:   { 100: '#FBEFD3', 500: '#E0A21A' },
        red:     { 100: '#F8DFDC', 500: '#C0392B' },
      },
      fontFamily: {
        sans:    ['Barlow', 'system-ui', 'sans-serif'],
        display: ['"Saira Condensed"', '"Arial Narrow"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        eyebrow: '0.16em',
      },
      boxShadow: {
        'focus-brand': '0 0 0 3px rgba(240,129,43,.42)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
