/**
 * SVG-based clip trim bar. Mirrors the Python TrimBar widget exactly:
 * - Blue clip region when locked, orange when unlocked
 * - Draggable start/end handles, bar drag, click-to-seek
 * - Context timestamps top-left/right, handle timestamps below bar
 */

import { useCallback, useRef } from 'react'

const BAR_TOP = 14
const BAR_H = 34
const HANDLE_W = 14
const HIT_R = 20
const MIN_CLIP = 15

function fmtTs(t: number): string {
  const s = Math.floor(t)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

interface TrimBarProps {
  ctxStart: number
  ctxEnd: number
  trimStart: number
  trimEnd: number
  playhead: number
  unlocked: boolean
  maxClip?: number
  getFrameUrl?: (t: number) => string
  onTrimChange: (start: number, end: number) => void
  onCommit: (start: number, end: number) => void
  onSeek: (t: number) => void
}

export default function TrimBar({
  ctxStart,
  ctxEnd,
  trimStart,
  trimEnd,
  playhead,
  unlocked,
  maxClip = 60,
  getFrameUrl,
  onTrimChange,
  onCommit,
  onSeek,
}: TrimBarProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{
    type: 'start' | 'end' | 'bar' | null
    originT: number
    originStart: number
    originEnd: number
  }>({ type: null, originT: 0, originStart: 0, originEnd: 0 })

  // Internal mutable refs for drag math (avoid stale closures)
  const trimRef = useRef({ trimStart, trimEnd, ctxStart, ctxEnd })
  trimRef.current = { trimStart, trimEnd, ctxStart, ctxEnd }

  const width = svgRef.current?.clientWidth ?? 600

  const tToX = useCallback((t: number, w: number) => {
    const span = ctxEnd - ctxStart
    if (span <= 0) return HANDLE_W / 2
    return HANDLE_W / 2 + ((t - ctxStart) / span) * (w - HANDLE_W)
  }, [ctxEnd, ctxStart])

  const xToT = useCallback((x: number, w: number) => {
    const usable = w - HANDLE_W
    if (usable <= 0) return ctxStart
    const frac = (x - HANDLE_W / 2) / usable
    return Math.max(ctxStart, Math.min(ctxEnd, ctxStart + frac * (ctxEnd - ctxStart)))
  }, [ctxEnd, ctxStart])

  const getWidth = () => svgRef.current?.getBoundingClientRect().width ?? 600

  const onMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current!.getBoundingClientRect()
    const x = e.clientX - rect.left
    const w = rect.width
    const sx = tToX(trimStart, w)
    const ex = tToX(trimEnd, w)
    const ds = Math.abs(x - sx)
    const de = Math.abs(x - ex)

    if (ds < HIT_R && ds <= de) {
      dragRef.current = { type: 'start', originT: 0, originStart: 0, originEnd: 0 }
    } else if (de < HIT_R) {
      dragRef.current = { type: 'end', originT: 0, originStart: 0, originEnd: 0 }
    } else if (x >= sx && x <= ex) {
      dragRef.current = {
        type: 'bar',
        originT: xToT(x, w),
        originStart: trimStart,
        originEnd: trimEnd,
      }
    } else {
      onSeek(xToT(x, w))
    }

    e.preventDefault()
  }

  const onMouseMove = useCallback((e: MouseEvent) => {
    const drag = dragRef.current
    if (!drag.type) return
    const rect = svgRef.current!.getBoundingClientRect()
    const x = e.clientX - rect.left
    const w = rect.width
    const t = xToT(x, w)
    const { trimStart: ts, trimEnd: te, ctxStart: cs, ctxEnd: ce } = trimRef.current

    let newStart = ts
    let newEnd = te

    if (drag.type === 'start') {
      const minT = Math.max(cs, te - maxClip)
      const maxT = te - MIN_CLIP
      newStart = Math.max(minT, Math.min(maxT, t))
      newEnd = te
    } else if (drag.type === 'end') {
      const minT = ts + MIN_CLIP
      const maxT = Math.min(ce, ts + maxClip)
      newStart = ts
      newEnd = Math.max(minT, Math.min(maxT, t))
    } else if (drag.type === 'bar') {
      const duration = drag.originEnd - drag.originStart
      const delta = t - drag.originT
      newStart = Math.max(cs, Math.min(ce - duration, drag.originStart + delta))
      newEnd = newStart + duration
    }

    onTrimChange(newStart, newEnd)
  }, [xToT, maxClip, onTrimChange])

  const onMouseUp = useCallback(() => {
    if (dragRef.current.type) {
      onCommit(trimRef.current.trimStart, trimRef.current.trimEnd)
    }
    dragRef.current = { type: null, originT: 0, originStart: 0, originEnd: 0 }
  }, [onCommit])

  // Global mouse move/up during drag
  const startGlobalDrag = (e: React.MouseEvent<SVGSVGElement>) => {
    onMouseDown(e)
    if (dragRef.current.type) {
      window.addEventListener('mousemove', onMouseMove)
      window.addEventListener('mouseup', () => {
        onMouseUp()
        window.removeEventListener('mousemove', onMouseMove)
      }, { once: true })
    }
  }

  const w = width || 600
  const sx = tToX(trimStart, w)
  const ex = tToX(trimEnd, w)
  const phx = tToX(Math.max(ctxStart, Math.min(ctxEnd, playhead)), w)
  const midY = BAR_TOP + BAR_H / 2

  const fillColor = unlocked ? '#703a1e' : '#a8a29b'
  const borderColor = unlocked ? '#ff9a4a' : '#1e1a18'

  // Handle label positions
  const lblW = 64
  const lx = Math.max(0, Math.min(sx - lblW / 2, w - lblW))
  const rx = Math.max(lx + lblW + 4, Math.min(ex - lblW / 2, w - lblW))

  // Thumbnail frame timestamps every 30 s across the context window
  const THUMB_STEP = 30
  const thumbTimes: number[] = []
  for (let t = Math.floor(ctxStart / THUMB_STEP) * THUMB_STEP; t < ctxEnd; t += THUMB_STEP) {
    thumbTimes.push(t)
  }

  return (
    <svg
      ref={svgRef}
      width="100%"
      height="70"
      onMouseDown={startGlobalDrag}
      style={{ cursor: 'pointer', userSelect: 'none' }}
    >
      <defs>
        <clipPath id="trimbar-clip">
          <rect x={HANDLE_W / 2} y={BAR_TOP} width={Math.max(0, w - HANDLE_W)} height={BAR_H} rx={4} />
        </clipPath>
      </defs>

      {/* Context labels */}
      <text x={0} y={11} fontSize={9} fill="#555555" textAnchor="start">{fmtTs(ctxStart)}</text>
      <text x={w} y={11} fontSize={9} fill="#555555" textAnchor="end">{fmtTs(ctxEnd)}</text>

      {/* Background track — dark fallback while thumbnails load */}
      <rect x={HANDLE_W / 2} y={BAR_TOP} width={Math.max(0, w - HANDLE_W)} height={BAR_H} rx={4} fill="#1a1a1a" />

      {/* Thumbnail strip */}
      {getFrameUrl && (
        <g clipPath="url(#trimbar-clip)">
          {thumbTimes.map((t) => {
            const x0 = tToX(Math.max(t, ctxStart), w)
            const x1 = tToX(Math.min(t + THUMB_STEP, ctxEnd), w)
            return (
              <image
                key={t}
                href={getFrameUrl(t)}
                x={x0}
                y={BAR_TOP}
                width={Math.max(0, x1 - x0)}
                height={BAR_H}
                preserveAspectRatio="xMidYMid slice"
              />
            )
          })}
        </g>
      )}

      {/* Dim outside the clip region */}
      {sx > HANDLE_W / 2 && (
        <rect x={HANDLE_W / 2} y={BAR_TOP} width={sx - HANDLE_W / 2} height={BAR_H} fill="rgba(0,0,0,0.62)" clipPath="url(#trimbar-clip)" />
      )}
      {ex < w - HANDLE_W / 2 && (
        <rect x={ex} y={BAR_TOP} width={w - HANDLE_W / 2 - ex} height={BAR_H} fill="rgba(0,0,0,0.62)" clipPath="url(#trimbar-clip)" />
      )}

      {/* Tint the clip region when unlocked (orange hue) */}
      {unlocked && (
        <rect x={sx} y={BAR_TOP} width={Math.max(0, ex - sx)} height={BAR_H} fill="rgba(255,120,40,0.18)" />
      )}

      {/* Border around clip region */}
      <rect x={sx} y={BAR_TOP} width={Math.max(0, ex - sx)} height={BAR_H} fill="none" stroke={borderColor} strokeWidth={1} />

      {/* Start handle */}
      <rect x={sx - HANDLE_W / 2} y={BAR_TOP} width={HANDLE_W} height={BAR_H} rx={4} fill="#ffffff" />
      {/* End handle */}
      <rect x={ex - HANDLE_W / 2} y={BAR_TOP} width={HANDLE_W} height={BAR_H} rx={4} fill="#ffffff" />

      {/* Grip dots */}
      {[-5, 0, 5].map((dy) => (
        <g key={dy}>
          <ellipse cx={sx} cy={midY + dy} rx={2} ry={1.5} fill="#666" />
          <ellipse cx={ex} cy={midY + dy} rx={2} ry={1.5} fill="#666" />
        </g>
      ))}

      {/* Playhead */}
      {playhead >= ctxStart && playhead <= ctxEnd && (
        <>
          <polygon
            points={`${phx - 4},${BAR_TOP - 2} ${phx + 4},${BAR_TOP - 2} ${phx},${BAR_TOP + 6}`}
            fill="#ffffff"
          />
          <line
            x1={phx} y1={BAR_TOP + 6}
            x2={phx} y2={BAR_TOP + BAR_H}
            stroke="rgba(255,255,255,0.78)"
            strokeWidth={1}
          />
        </>
      )}

      {/* Handle timestamp labels */}
      <text x={lx + lblW / 2} y={BAR_TOP + BAR_H + 14} fontSize={8} fill="#555555" textAnchor="middle">
        {fmtTs(trimStart)}
      </text>
      <text x={rx + lblW / 2} y={BAR_TOP + BAR_H + 14} fontSize={8} fill="#555555" textAnchor="middle">
        {fmtTs(trimEnd)}
      </text>
    </svg>
  )
}
