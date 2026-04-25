import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { FarmView } from './pages/FarmView'
import { PrinterDetail } from './pages/PrinterDetail'
import { Setup } from './pages/Setup'
import { History } from './pages/History'
import { useWebSocket } from './hooks/useWebSocket'
import { useTheme } from './hooks/useTheme'

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
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
