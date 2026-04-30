import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

export type LicenseStatus =
  | { status: 'trial';         daysLeft: number }
  | { status: 'licensed';      tag: string | null; daysLeft: number | null }
  | { status: 'expired' }
  | { status: 'offline_locked' }
  | { status: 'loading' }

interface LicenseContextValue {
  licenseStatus: LicenseStatus
  activate:      (key: string) => Promise<{ success: boolean; error?: string }>
  showModal:     boolean
  setShowModal:  (v: boolean) => void
}

const LicenseContext = createContext<LicenseContextValue | null>(null)

export function LicenseProvider({ children }: { children: ReactNode }) {
  const [licenseStatus, setLicenseStatus] = useState<LicenseStatus>({ status: 'loading' })
  const [showModal,     setShowModal]     = useState(false)

  const refresh = async () => {
    if (!window.electronAPI) {
      // Browser / dev without Electron
      setLicenseStatus({ status: 'licensed', tag: 'DEV', daysLeft: null })
      return
    }
    const s = await window.electronAPI.getLicenseStatus()
    setLicenseStatus(s as LicenseStatus)
  }

  useEffect(() => { refresh() }, [])

  const activate = async (key: string) => {
    if (!window.electronAPI) return { success: false, error: 'Not in Electron' }
    const result = await window.electronAPI.activateLicense(key.trim())
    if (result.success) await refresh()
    return result
  }

  return (
    <LicenseContext.Provider value={{ licenseStatus, activate, showModal, setShowModal }}>
      {children}
    </LicenseContext.Provider>
  )
}

export function useLicense() {
  const ctx = useContext(LicenseContext)
  if (!ctx) throw new Error('useLicense must be used within LicenseProvider')
  return ctx
}
