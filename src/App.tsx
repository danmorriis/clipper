import { useEffect, useRef, useState } from 'react'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { setApiToken } from './api/client'
import { useSessionStore } from './store/session'
import ImportScreen from './screens/ImportScreen'
import ReviewScreen from './screens/ReviewScreen'
import ExportScreen from './screens/ExportScreen'
import { LicenseProvider, useLicense } from './contexts/LicenseContext'
import LicenseModal from './components/LicenseModal'
import ExpiredScreen from './components/ExpiredScreen'
import type { LicenseStatus } from './contexts/LicenseContext'

// Augment window for the Electron contextBridge API
declare global {
  interface Window {
    electronAPI?: {
      openFileDialog(options: object): Promise<string[]>
      openFolderDialog(): Promise<string | null>
      openFolder(path: string): void
      openUrl(url: string): void
      submitFeedback(text: string, machine: string): Promise<void>
      minimizeWindow(): void
      closeWindow(): void
      getApiBase(): Promise<string>
      getToken(): Promise<string>
      platform(): string
      getLicenseStatus(): Promise<LicenseStatus>
      activateLicense(key: string): Promise<{ success: boolean; error?: string }>
    }
  }
}

function AppInner() {
  const setApiBase = useSessionStore((s) => s.setApiBase)
  const [ready, setReady] = useState(false)
  const [visible, setVisible] = useState(false)
  const fadingOutRef = useRef(false)
  const { licenseStatus } = useLicense()

  useEffect(() => {
    const init = async () => {
      if (window.electronAPI) {
        const [base, token] = await Promise.all([
          window.electronAPI.getApiBase(),
          window.electronAPI.getToken(),
        ])
        setApiBase(base)
        setApiToken(token)
      } else {
        // Dev fallback: use env or default (no token — middleware skips check when unset)
        setApiBase(import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:9001')
      }
      setReady(true)
    }
    init()
  }, [setApiBase])

  const isLoading = !ready || licenseStatus.status === 'loading'

  // Fade the loading screen out, then fade the app in
  useEffect(() => {
    if (!isLoading && !fadingOutRef.current) {
      fadingOutRef.current = true
      setTimeout(() => setVisible(true), 1200)
    }
  }, [isLoading])

  if (isLoading || !visible) {
    return (
      <div
        className="flex h-full items-center justify-center text-muted text-sm transition-opacity duration-[1000ms]"
        style={{ opacity: isLoading ? 1 : 0 }}
      >
        Starting…
      </div>
    )
  }

  if (licenseStatus.status === 'expired' || licenseStatus.status === 'offline_locked') {
    return (
      <>
        <ExpiredScreen />
        <LicenseModal />
      </>
    )
  }

  return (
    <>
      <HashRouter>
        <Routes>
          <Route path="/"                  element={<ImportScreen />} />
          <Route path="/review/:sessionId" element={<ReviewScreen />} />
          <Route path="/export/:sessionId" element={<ExportScreen />} />
        </Routes>
      </HashRouter>
      <LicenseModal />
    </>
  )
}

export default function App() {
  return (
    <LicenseProvider>
      <AppInner />
    </LicenseProvider>
  )
}
