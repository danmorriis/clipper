import { useRef, useState } from 'react'
import { useSessionStore } from '../store/session'

interface DropZoneProps {
  label: string
  sublabel?: string
  accept?: string[]
  value: string | null
  onChange: (path: string) => void
  error?: boolean
}

export default function DropZone({ label, sublabel, accept, value, onChange, error }: DropZoneProps) {
  const apiBase = useSessionStore((s) => s.apiBase)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    const path = (file as File & { path?: string }).path ?? file.name
    onChange(path)
  }

  const handleClick = async () => {
    if (window.electronAPI) {
      const filters = accept
        ? [{ name: 'Files', extensions: accept.map((a) => a.replace('.', '')) }]
        : []
      const paths = await window.electronAPI.openFileDialog({
        properties: ['openFile'],
        filters,
      })
      if (paths[0]) onChange(paths[0])
    } else {
      inputRef.current?.click()
    }
  }

  const filename = value ? value.split(/[/\\]/).pop() : null

  return (
    <div
      onClick={handleClick}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`
        relative flex flex-col items-center justify-center gap-1
        h-24 rounded-lg border-2 cursor-pointer
        transition-colors select-none
        ${dragging
          ? 'border-solid border-foreground bg-foreground/10'
          : error
          ? 'border-dashed border-red-600 bg-red-600/5'
          : filename
          ? 'border-solid border-foreground bg-surface-high'
          : 'border-dashed border-border hover:border-foreground/50 bg-surface-high'
        }
      `}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={accept?.join(',')}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onChange((f as File & { path?: string }).path ?? f.name)
        }}
      />
      {filename ? (
        <>
          <span className="text-xs text-foreground font-medium truncate max-w-[90%]">{filename}</span>
          <span className="text-[10px] text-muted">{label}</span>
        </>
      ) : (
        <>
          <span className="text-sm text-[#5a5550]">Drop {label.toLowerCase()} here</span>
          {sublabel && <span className="text-[11px] text-muted">{sublabel}</span>}
          <span className="text-[11px] text-muted/70 mt-1">or click to browse</span>
        </>
      )}
    </div>
  )
}
