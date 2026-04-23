interface ProgressModalProps {
  title: string
  percent: number
  message: string
  onCancel?: () => void
  error?: string | null
}

export default function ProgressModal({ title, percent, message, onCancel, error }: ProgressModalProps) {
  return (
    <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50">
      <div className="bg-surface-raised border border-border rounded-xl p-6 w-[400px] flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>

        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <>
            <div className="w-full h-1.5 bg-surface-high rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-200"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="text-xs text-muted min-h-[16px]">{message}</p>
          </>
        )}

        {onCancel && (
          <button
            onClick={onCancel}
            className="self-end text-xs text-muted hover:text-foreground transition-colors"
          >
            {error ? 'Close' : 'Cancel'}
          </button>
        )}
      </div>
    </div>
  )
}
