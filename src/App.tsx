import { useEffect, useState } from 'react'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { setApiToken } from './api/client'
import { useSessionStore } from './store/session'
import ImportScreen from './screens/ImportScreen'
import ReviewScreen from './screens/ReviewScreen'
import ExportScreen from './screens/ExportScreen'

// Augment window for the Electron contextBridge API
declare global {
  interface Window {
    electronAPI?: {
      openFileDialog(options: object): Promise<string[]>
      openFolderDialog(): Promise<string | null>
      openFolder(path: string): void
      openUrl(url: string): void
      submitFeedback(text: string): Promise<void>
      getApiBase(): Promise<string>
      getToken(): Promise<string>
      platform(): string
    }
  }
}

export default function App() {
  const setApiBase = useSessionStore((s) => s.setApiBase)
  const [ready, setReady] = useState(false)

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

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-muted text-sm">
        Starting…
      </div>
    )
  }

  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<ImportScreen />} />
        <Route path="/review/:sessionId" element={<ReviewScreen />} />
        <Route path="/export/:sessionId" element={<ExportScreen />} />
      </Routes>
    </HashRouter>
  )
}
