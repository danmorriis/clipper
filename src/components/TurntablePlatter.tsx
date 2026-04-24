interface Props {
  analysing?: boolean
  percent?: number
}

export default function TurntablePlatter({ analysing = false, percent = 0 }: Props) {
  const maxRadius = 288
  const radius = analysing ? Math.max(1, (percent / 100) * maxRadius) : 0

  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: -1 }}
      aria-hidden="true"
    >
      <div className="absolute inset-0 flex items-center justify-center" style={{ transform: 'translateY(20px)' }}>
        <svg
          viewBox="0 0 600 600"
          width="560"
          height="560"
          style={{ animation: 'platter-spin 70s linear infinite', overflow: 'visible' }}
        >
          {/* Disc body */}
          <g opacity="0.5">
            <circle cx="300" cy="300" r="288" fill="#b3ada7" stroke="#9a9490" strokeWidth="2" />
          </g>

          {/* Orange progress circle — always present, r transitions smoothly */}
          <circle
            cx="300"
            cy="300"
            fill="#d94e00"
            opacity="0.85"
            style={{ r: `${radius}` as any, transition: 'r 0.8s ease' } as React.CSSProperties}
          />

          {/* Lines — rendered above the orange circle */}
          <g opacity="0.5">
            <line x1="300" y1="235" x2="300" y2="60"  stroke="#6e6a66" strokeWidth="0.9" opacity="0.65" />
            <line x1="300" y1="365" x2="300" y2="540" stroke="#6e6a66" strokeWidth="0.9" opacity="0.65" />
          </g>

          {/* Text labels — outside the circle, rotate with disc */}
          <text
            x="-18" y="300"
            textAnchor="end" dominantBaseline="middle"
            fontSize="11.8" fontFamily="Inter, sans-serif" fontWeight="300"
            letterSpacing="1.65" fill="#636060"
          >
            04/26
          </text>
          <text
            x="618" y="300"
            textAnchor="start" dominantBaseline="middle"
            fontSize="11.8" fontFamily="Inter, sans-serif" fontWeight="300"
            letterSpacing="1.65" fill="#636060"
          >
            BIG PERC ONLY
          </text>
        </svg>
      </div>
    </div>
  )
}
