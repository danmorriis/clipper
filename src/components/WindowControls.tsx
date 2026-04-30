/**
 * Custom window controls for Windows frameless mode.
 * Only rendered on Windows — Mac uses native hiddenInset controls.
 */
export default function WindowControls() {
  const isWin = window.electronAPI?.platform() === 'win32'
  if (!isWin) return null

  return (
    <div
      className="no-drag"
      style={{
        position:   'fixed',
        top:        10,
        left:       12,
        display:    'flex',
        gap:        6,
        zIndex:     9999,
      }}
    >
      <button
        onClick={() => window.electronAPI?.minimizeWindow()}
        title="Minimise"
        style={{
          width:           22,
          height:          22,
          borderRadius:    '50%',
          border:          'none',
          background:      'rgba(100,96,92,0.35)',
          color:           '#8a847e',
          fontSize:        14,
          lineHeight:      1,
          cursor:          'pointer',
          display:         'flex',
          alignItems:      'center',
          justifyContent:  'center',
          padding:         0,
          transition:      'background 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(100,96,92,0.6)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(100,96,92,0.35)')}
      >
        −
      </button>
      <button
        onClick={() => window.electronAPI?.closeWindow()}
        title="Close"
        style={{
          width:           22,
          height:          22,
          borderRadius:    '50%',
          border:          'none',
          background:      'rgba(100,96,92,0.35)',
          color:           '#8a847e',
          fontSize:        12,
          lineHeight:      1,
          cursor:          'pointer',
          display:         'flex',
          alignItems:      'center',
          justifyContent:  'center',
          padding:         0,
          transition:      'background 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(180,50,50,0.55)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(100,96,92,0.35)')}
      >
        ×
      </button>
    </div>
  )
}
