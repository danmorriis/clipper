import { useState } from 'react'
import TitleBarSpacer from '../components/TitleBarSpacer'
import WindowControls from '../components/WindowControls'

type Status = 'idle' | 'sending' | 'sent' | 'error'

interface Props {
  onBack: () => void
}

export default function FeedbackScreen({ onBack }: Props) {
  const [text, setText] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [formVisible, setFormVisible] = useState(true)
  const [sentVisible, setSentVisible] = useState(false)

  const platform = window.electronAPI?.platform()
  const isMac = platform === 'darwin'
  const titleBarHeight = (isMac || platform === 'win32') ? 32 : 0
  const [machine, setMachine] = useState('')

  const handleSubmit = async () => {
    if (!text.trim() || status === 'sending') return
    setStatus('sending')
    try {
      if (window.electronAPI?.submitFeedback) {
        await window.electronAPI.submitFeedback(text.trim(), machine)
      } else {
        const MACHINE_ENTRY_ID = 'entry.467936750'
        const parts = [`entry.448791064=${encodeURIComponent(text.trim())}`]
        if (machine) parts.push(`${MACHINE_ENTRY_ID}=${encodeURIComponent(machine)}`)
        await fetch(
          'https://docs.google.com/forms/d/e/1FAIpQLSfYHYJWEJm5kC0tC1Gf4LsK4TWz1LGt9vIDQ7BI-xlqwU_GwA/formResponse',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: parts.join('&'),
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

          {/* Machine toggle */}
          <div className="flex flex-col items-center gap-2">
            <label className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted">
              Your Machine
            </label>
            <div className="flex items-center rounded-full bg-surface-high p-0.5">
              {[
                { value: 'Mac Silicon (M series macs)', label: 'Mac Silicon' },
                { value: 'Mac Intel (pre 2021)', label: 'Mac Intel (pre 2021)' },
                { value: 'Windows', label: 'Windows' },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setMachine(value)}
                  disabled={status === 'sending'}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-colors ${
                    machine === value
                      ? 'bg-foreground text-surface'
                      : 'text-muted hover:text-foreground'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {status === 'error' && (
            <p className="text-xs text-red-600 -mt-1">
              Something went wrong. Check your connection and try again.
            </p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!text.trim() || !machine || status === 'sending'}
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
