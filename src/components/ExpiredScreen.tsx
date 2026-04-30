import { useState } from 'react'
import { useLicense } from '../contexts/LicenseContext'

export default function ExpiredScreen() {
  const { licenseStatus, setShowModal, activate } = useLicense()
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState('')

  const isOffline = licenseStatus.status === 'offline_locked'

  const handleRetry = async () => {
    setRetrying(true)
    setRetryError('')
    // Trigger a fresh license check by calling getLicenseStatus via activate with empty key
    // Actually just reload — the LicenseProvider will re-run on mount
    if (window.electronAPI) {
      const result = await window.electronAPI.getLicenseStatus()
      if (result.status !== 'offline_locked' && result.status !== 'expired') {
        // Reconnected — reload the page to re-render with new status
        window.location.reload()
      } else {
        setRetryError('Still unable to connect. Check your internet connection.')
      }
    }
    setRetrying(false)
  }

  return (
    <div className="fixed inset-0 bg-surface flex flex-col items-center justify-center gap-4">
      <h1 className="text-[40px] font-black tracking-[-0.03em] text-foreground leading-none">
        CLIP LAB
      </h1>

      <p className="text-sm font-light text-muted text-center max-w-xs leading-relaxed mt-2">
        {isOffline
          ? 'Unable to verify your license.\nConnect to the internet to continue, or enter a license key.'
          : 'Your trial has expired - thank you for trying this out!'}
      </p>

      {retryError && (
        <p className="text-xs text-red-600">{retryError}</p>
      )}

      <div className="flex flex-col items-center gap-2 mt-2">
        {isOffline && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="px-6 py-2.5 rounded-lg bg-foreground text-surface text-xs font-semibold tracking-[0.08em] uppercase hover:opacity-80 disabled:opacity-40 transition-opacity"
          >
            {retrying ? 'Retrying…' : 'Retry Connection'}
          </button>
        )}
        <button
          onClick={() => setShowModal(true)}
          className="px-6 py-2.5 rounded-lg text-xs font-semibold tracking-[0.08em] uppercase text-muted hover:text-foreground transition-colors"
        >
          Enter License Key
        </button>
      </div>
    </div>
  )
}
