import { useState } from 'react'

interface Props {
  onClick: () => void
}

export default function FeedbackButton({ onClick }: Props) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'absolute',
        bottom: 16,
        right: 20,
        background: 'none',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 11,
        fontWeight: 300,
        letterSpacing: '0.15em',
        color: hovered ? '#1e1a18' : '#8a847e',
        transition: 'color 0.15s',
        zIndex: 1000,
      }}
    >
      FEEDBACK
    </button>
  )
}
