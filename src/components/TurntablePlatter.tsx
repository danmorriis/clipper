import { useEffect, useRef } from 'react'

interface Props {
  analysing?: boolean
  percent?: number
}

const NORMAL_VEL    = 360 / 70
const DECAY_CW      = 0.6
const DECAY_CCW     = 5.0
const CCW_DRAG_MULT = 0.55

const DISC_R  = 288   // SVG units
const RIM_OUT = 80    // extra px beyond disc edge

export default function TurntablePlatter({ analysing = false, percent = 0 }: Props) {
  const maxRadius = 288
  const radius = analysing ? Math.max(1, (percent / 100) * maxRadius) : 0

  const svgRef   = useRef<SVGSVGElement>(null)
  const outerRef = useRef<HTMLDivElement>(null)

  const rotation   = useRef(0)
  const velocity   = useRef(NORMAL_VEL)
  const lastTime   = useRef<number | null>(null)
  const rafId      = useRef(0)

  const dragging     = useRef(false)
  const lastAngle    = useRef(0)
  const lastDragTime = useRef(0)
  const dragVel      = useRef(0)

  // ── Geometry helpers ────────────────────────────────────────────────────────

  const screenMetrics = (clientX: number, clientY: number) => {
    const svg = svgRef.current!
    const ctm = svg.getScreenCTM()!
    const pt  = svg.createSVGPoint()
    pt.x = 300; pt.y = 300
    const { x: cx, y: cy } = pt.matrixTransform(ctm)
    const scale = Math.sqrt(ctm.a * ctm.a + ctm.b * ctm.b)
    const dx = clientX - cx
    const dy = clientY - cy
    return { dx, dy, dist: Math.sqrt(dx * dx + dy * dy), scale }
  }

  const isInDisc = (clientX: number, clientY: number) => {
    if (!svgRef.current) return false
    const { dist, scale } = screenMetrics(clientX, clientY)
    return dist <= (DISC_R + RIM_OUT) * scale
  }

  const pointerAngle = (clientX: number, clientY: number) => {
    const { dx, dy } = screenMetrics(clientX, clientY)
    return Math.atan2(dy, dx) * (180 / Math.PI)
  }

  const setCursor = (cursor: string) => {
    if (outerRef.current) outerRef.current.style.cursor = cursor
  }

  // ── Animation loop ──────────────────────────────────────────────────────────

  useEffect(() => {
    const tick = (time: number) => {
      if (lastTime.current === null) lastTime.current = time
      const dt = Math.min((time - lastTime.current) / 1000, 0.1)
      lastTime.current = time

      if (!dragging.current) {
        const excess = velocity.current - NORMAL_VEL
        const decay  = excess < 0 ? DECAY_CCW : DECAY_CW
        velocity.current = NORMAL_VEL + excess * Math.exp(-decay * dt)
        rotation.current += velocity.current * dt
      }

      if (svgRef.current) {
        svgRef.current.style.transform = `rotate(${rotation.current}deg)`
      }

      rafId.current = requestAnimationFrame(tick)
    }
    rafId.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId.current)
  }, [])

  // ── Window-level capture handlers ───────────────────────────────────────────
  // Capture phase fires before any element receives the event, so disc drags
  // work even when transparent container divs sit on top of the disc area.

  useEffect(() => {
    const el = outerRef.current
    if (!el) return

    const onDown = (e: PointerEvent) => {
      if (!isInDisc(e.clientX, e.clientY)) return
      dragging.current     = true
      lastAngle.current    = pointerAngle(e.clientX, e.clientY)
      lastDragTime.current = performance.now()
      dragVel.current      = velocity.current
      el.setPointerCapture(e.pointerId)
      setCursor('grabbing')
    }

    const onMove = (e: PointerEvent) => {
      if (!dragging.current) {
        setCursor(isInDisc(e.clientX, e.clientY) ? 'grab' : 'default')
        return
      }

      const angle = pointerAngle(e.clientX, e.clientY)
      const now   = performance.now()
      const dt    = (now - lastDragTime.current) / 1000

      if (dt > 0.001) {
        let delta = angle - lastAngle.current
        if (delta >  180) delta -= 360
        if (delta < -180) delta += 360

        const resistedDelta = delta < 0 ? delta * CCW_DRAG_MULT : delta
        rotation.current += resistedDelta

        const inst = resistedDelta / dt
        dragVel.current  = 0.6 * dragVel.current + 0.4 * inst
        velocity.current = dragVel.current
      }

      lastAngle.current    = angle
      lastDragTime.current = now
      e.preventDefault()
    }

    const onUp = (e: PointerEvent) => {
      if (!dragging.current) return
      dragging.current = false
      setCursor(isInDisc(e.clientX, e.clientY) ? 'grab' : 'default')
    }

    el.addEventListener('pointerdown',   onDown)
    el.addEventListener('pointermove',   onMove)
    el.addEventListener('pointerup',     onUp)
    el.addEventListener('pointercancel', onUp)

    return () => {
      el.removeEventListener('pointerdown',   onDown)
      el.removeEventListener('pointermove',   onMove)
      el.removeEventListener('pointerup',     onUp)
      el.removeEventListener('pointercancel', onUp)
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div
      ref={outerRef}
      className="absolute inset-0"
      style={{ zIndex: 0, cursor: 'default', userSelect: 'none', WebkitUserSelect: 'none' } as React.CSSProperties}
      aria-hidden="true"
    >
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{ transform: 'translateY(20px)', pointerEvents: 'none' }}
      >
        <svg
          ref={svgRef}
          viewBox="-130 0 860 600"
          width="802"
          height="560"
          style={{ overflow: 'visible', pointerEvents: 'none' }}
        >
          {/* Disc body */}
          <circle
            cx="300" cy="300" r="288"
            fill="#b3ada7" stroke="#9a9490" strokeWidth="2"
            opacity="0.5"
          />

          {/* Orange progress fill */}
          <circle
            cx="300" cy="300"
            fill="#d94e00"
            opacity="0.85"
            className="preserve-orange"
            style={{ r: `${radius}` as any, transition: 'r 0.8s ease' } as React.CSSProperties}
          />

          {/* Lines */}
          <g opacity="0.5">
            <line x1="300" y1="235" x2="300" y2="60"  stroke="#6e6a66" strokeWidth="0.9" opacity="0.65" />
            <line x1="300" y1="365" x2="300" y2="540" stroke="#6e6a66" strokeWidth="0.9" opacity="0.65" />
          </g>

          {/* Text labels */}
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
