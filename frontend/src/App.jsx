import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { FarmView } from './pages/FarmView'
import { PrinterDetail } from './pages/PrinterDetail'
import { Setup } from './pages/Setup'
import { History } from './pages/History'
import { LoginPage } from './pages/LoginPage'
import { ProtectedRoute } from './components/ProtectedRoute'
import { useWebSocket } from './hooks/useWebSocket'
import { useTheme } from './hooks/useTheme'
import { useAuthStore } from './store/authStore'

function Layout({ children, onThemeToggle, theme }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar onThemeToggle={onThemeToggle} theme={theme} />
      <main className="flex-1 overflow-hidden flex flex-col bg-zinc-50 dark:bg-zinc-950">
        {children}
      </main>
    </div>
  )
}

function AppRoutes() {
  useWebSocket()
  const { theme, toggle } = useTheme()

  return (
    <Layout onThemeToggle={toggle} theme={theme}>
      <Routes>
        <Route path="/" element={<FarmView />} />
        <Route path="/printer/:id" element={<PrinterDetail />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="/history" element={<History />} />
        {/* Catch-all: redirect unknown paths to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  const checkAuth = useAuthStore((s) => s.checkAuth)

  // Check session validity once on startup.
  useEffect(() => { checkAuth() }, [checkAuth])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />

        {/* Everything else is protected */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppRoutes />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
