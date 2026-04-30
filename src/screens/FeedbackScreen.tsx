import { useState } from 'react'
import TitleBarSpacer from '../components/TitleBarSpacer'

type Status = 'idle' | 'sending' | 'sent' | 'error'

interface Props {
  onBack: () => void
}

export default function FeedbackScreen({ onBack }: Props) {
  const [text, setText] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [formVisible, setFormVisible] = useState(true)
  const [sentVisible, setSentVisible] = useState(false)

  const isMac = window.electronAPI?.platform() === 'darwin'
  const titleBarHeight = isMac ? 32 : 0
  const handleSubmit = async () => {
    if (!text.trim() || status === 'sending') return
    setStatus('sending')
    try {
      if (window.electronAPI?.submitFeedback) {
        await window.electronAPI.submitFeedback(text.trim())
      } else {
        await fetch(
          'https://docs.google.com/forms/d/e/1FAIpQLSfYHYJWEJm5kC0tC1Gf4LsK4TWz1LGt9vIDQ7BI-xlqwU_GwA/formResponse',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `entry.448791064=${encodeURIComponent(text.trim())}`,
            mode: 'no-cors',
          }
        )
      }
      setFormVisible(false)
      setTimeout(() => {
        setStatus('sent')
        setSentVisible(true)
      }, 500)
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="relative h-full bg-surface overflow-hidden">
      <TitleBarSpacer />

      {/* Back button — top left, always above the form div */}
      <button
        onClick={onBack}
        className="absolute left-8 text-[11px] font-light tracking-[0.15em] text-muted uppercase hover:text-foreground transition-colors"
        style={{ top: titleBarHeight + 16, zIndex: 10 }}
      >
        ← Back
      </button>

      {/* Title — pinned to window top, mirrors CLIP LAB position exactly */}
      <div
        className="absolute left-1/2 -translate-x-1/2 w-[512px] px-8 pt-6 transition-opacity duration-500"
        style={{ top: titleBarHeight, opacity: formVisible ? 1 : 0 }}
      >
        <div className="text-center">
          <h1 className="text-[48px] font-black tracking-[-0.03em] text-foreground leading-none">
            FEEDBACK
          </h1>
          <p className="text-[11px] font-light tracking-[0.15em] text-muted uppercase mt-6">
            Be brutally honest — from ID accuracy issues, to app colour palette,<br />to other features you'd like, or bits you don't like!
          </p>
        </div>
      </div>

      {/* Form — textarea + button centred in window */}
      <div
        className="absolute inset-0 flex items-center justify-center transition-opacity duration-500"
        style={{ opacity: formVisible ? 1 : 0, pointerEvents: formVisible ? 'auto' : 'none' }}
      >
        <div className="w-[512px] px-8 flex flex-col gap-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Your thoughts..."
            rows={6}
            disabled={status === 'sending'}
            className="w-full bg-surface-high border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted outline-none focus:border-foreground transition-colors resize-none font-light leading-relaxed"
          />

          {status === 'error' && (
            <p className="text-xs text-red-600 -mt-1">
              Something went wrong. Check your connection and try again.
            </p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!text.trim() || status === 'sending'}
            className="w-full py-3 rounded-lg bg-accent text-white text-sm font-bold hover:bg-accent/90 disabled:opacity-25 disabled:cursor-not-allowed transition-all"
          >
            {status === 'sending' ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>

      {/* Confirmation — fades in centred after submit */}
      {status === 'sent' && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center gap-5 transition-opacity duration-500"
          style={{ opacity: sentVisible ? 1 : 0 }}
        >
          <p className="text-[11px] font-light tracking-[0.15em] text-muted uppercase">
            thanks — received.
          </p>
          <button
            onClick={onBack}
            className="px-6 py-2 rounded-full text-[10px] font-medium tracking-[0.1em] uppercase text-muted border border-muted hover:text-foreground hover:border-foreground transition-colors"
          >
            Back
          </button>
        </div>
      )}
    </div>
  )
}
