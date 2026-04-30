import { useEffect, useRef, useState } from 'react'
import { useLicense } from '../contexts/LicenseContext'

export default function LicenseModal() {
  const { showModal, setShowModal, activate } = useLicense()
  const [key,     setKey]     = useState('')
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fade in when shown
  useEffect(() => {
    if (showModal) {
      setKey('')
      setError('')
      setLoading(false)
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
      setTimeout(() => inputRef.current?.focus(), 150)
    } else {
      setVisible(false)
    }
  }, [showModal])

  const close = () => {
    setVisible(false)
    setTimeout(() => setShowModal(false), 200)
  }

  const handleActivate = async () => {
    if (!key.trim()) { setError('Please enter a key.'); return }
    setLoading(true)
    setError('')
    const result = await activate(key)
    setLoading(false)
    if (result.success) {
      close()
    } else {
      setError(result.error ?? 'Activation failed.')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter')  handleActivate()
    if (e.key === 'Escape') close()
  }

  if (!showModal) return null

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{
        background:  'rgba(0,0,0,0.45)',
        opacity:      visible ? 1 : 0,
        transition:  'opacity 0.2s ease',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) close() }}
    >
      <div
        className="bg-surface rounded-xl shadow-xl w-[400px] px-7 py-6 flex flex-col gap-4"
        style={{
          transform:  visible ? 'translateY(0)' : 'translateY(8px)',
          transition: 'transform 0.2s ease',
        }}
      >
        <div>
          <h2 className="text-sm font-semibold tracking-[0.08em] text-foreground uppercase">
            Enter License Key
          </h2>
          <p className="text-xs text-muted mt-1">
            Paste the key you were given below.
          </p>
        </div>

        <input
          ref={inputRef}
          value={key}
          onChange={(e) => { setKey(e.target.value); setError('') }}
          onKeyDown={handleKeyDown}
          placeholder="BISCUIT-XXXXXX-XXXXXX-XXXXXX"
          spellCheck={false}
          className="w-full bg-surface-high border border-border rounded-lg px-3 py-2.5 text-xs font-mono text-foreground placeholder:text-muted outline-none focus:border-foreground transition-colors"
        />

        {error && (
          <p className="text-xs text-red-600 -mt-2">{error}</p>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={close}
            className="px-4 py-1.5 rounded-lg text-xs text-muted hover:text-foreground transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleActivate}
            disabled={loading}
            className="px-4 py-1.5 rounded-lg bg-foreground text-surface text-xs font-medium hover:opacity-80 disabled:opacity-40 transition-all"
          >
            {loading ? 'Activating…' : 'Activate'}
          </button>
        </div>
      </div>
    </div>
  )
}
