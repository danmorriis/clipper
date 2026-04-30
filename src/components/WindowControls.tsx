/**
 * Custom window controls for Windows frameless mode.
 * Only rendered on Windows — Mac uses native hiddenInset controls.
 */
export default function WindowControls() {
  const isWin = window.electronAPI?.platform() === 'win32'
  if (!isWin) return null

  const btnStyle: React.CSSProperties = {
    background:  'none',
    border:      'none',
    color:       '#3a3630',
    fontSize:    18,
    fontWeight:  600,
    lineHeight:  1,
    cursor:      'pointer',
    padding:     '0 3px',
    display:     'flex',
    alignItems:  'center',
    opacity:     0.7,
    transition:  'opacity 0.15s',
  }

  return (
    <div
      className="no-drag"
      style={{ position: 'fixed', top: 8, left: 12, display: 'flex', gap: 4, zIndex: 9999 }}
    >
      <button
        onClick={() => window.electronAPI?.closeWindow()}
        title="Close"
        style={btnStyle}
        onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
        onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.7')}
      >
        ×
      </button>
      <button
        onClick={() => window.electronAPI?.minimizeWindow()}
        title="Minimise"
        style={btnStyle}
        onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
        onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.7')}
      >
        −
      </button>
    </div>
  )
}
