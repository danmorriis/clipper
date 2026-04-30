interface Props {
  dark: boolean
  onToggle: () => void
}

export default function DarkModeToggle({ dark, onToggle }: Props) {
  return (
    <button
      onClick={onToggle}
      style={{
        background: 'none',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span
        style={{
          fontSize: 11,
          fontWeight: 300,
          letterSpacing: '0.15em',
          color: '#8a847e',
          fontFamily: 'inherit',
          userSelect: 'none',
        }}
      >
        DARK
      </span>

      {/* Pill track */}
      <div
        style={{
          width: 34,
          height: 18,
          borderRadius: 9,
          background: dark ? '#636060' : '#9a9490',
          padding: 2,
          display: 'flex',
          alignItems: 'center',
          transition: 'background 0.35s ease',
          flexShrink: 0,
        }}
      >
        {/* Sliding knob */}
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: '#c5bfb8',
            transform: dark ? 'translateX(16px)' : 'translateX(0)',
            transition: 'transform 0.35s ease',
          }}
        />
      </div>
    </button>
  )
}
