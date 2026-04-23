import { useCallback, useRef, useState } from 'react'

const HANDLE_W = 14
const HIT_R = 20
const MIN_CLIP = 15
const MAX_CLIP_DEFAULT = 60

interface TrimState {
  ctxStart: number
  ctxEnd: number
  trimStart: number
  trimEnd: number
}

interface UseTrimBarOptions {
  onTrimChange?: (start: number, end: number) => void
  onSeek?: (t: number) => void
  onCommit?: (start: number, end: number) => void
}

export function useTrimBar(options: UseTrimBarOptions = {}) {
  const [trim, setTrim] = useState<TrimState>({
    ctxStart: 0,
    ctxEnd: 100,
    trimStart: 10,
    trimEnd: 55,
  })
  const [unlocked, setUnlocked] = useState(false)
  const [maxClip, setMaxClip] = useState(MAX_CLIP_DEFAULT)

  const dragRef = useRef<{
    type: 'start' | 'end' | 'bar' | null
    originT: number
    originStart: number
    originEnd: number
  }>({ type: null, originT: 0, originStart: 0, originEnd: 0 })

  const tToX = useCallback((t: number, width: number) => {
    const span = trim.ctxEnd - trim.ctxStart
    if (span <= 0) return HANDLE_W / 2
    const usable = width - HANDLE_W
    const frac = (t - trim.ctxStart) / span
    return HANDLE_W / 2 + frac * usable
  }, [trim.ctxEnd, trim.ctxStart])

  const xToT = useCallback((x: number, width: number) => {
    const usable = width - HANDLE_W
    if (usable <= 0) return trim.ctxStart
    const frac = (x - HANDLE_W / 2) / usable
    const t = trim.ctxStart + frac * (trim.ctxEnd - trim.ctxStart)
    return Math.max(trim.ctxStart, Math.min(trim.ctxEnd, t))
  }, [trim.ctxEnd, trim.ctxStart])

  const setup = useCallback((ctxStart: number, ctxEnd: number, trimStart: number, trimEnd: number) => {
    setTrim({ ctxStart, ctxEnd, trimStart, trimEnd })
    setUnlocked(false)
    setMaxClip(MAX_CLIP_DEFAULT)
  }, [])

  const setLockState = useCallback((locked: boolean) => {
    setUnlocked(!locked)
    setMaxClip(locked ? MAX_CLIP_DEFAULT : Infinity)
  }, [])

  const onMouseDown = useCallback((e: React.MouseEvent<SVGElement>, width: number) => {
    const x = e.nativeEvent.offsetX
    const sx = tToX(trim.trimStart, width)
    const ex = tToX(trim.trimEnd, width)
    const ds = Math.abs(x - sx)
    const de = Math.abs(x - ex)

    if (ds < HIT_R && ds <= de) {
      dragRef.current = { type: 'start', originT: 0, originStart: 0, originEnd: 0 }
    } else if (de < HIT_R) {
      dragRef.current = { type: 'end', originT: 0, originStart: 0, originEnd: 0 }
    } else if (x >= sx && x <= ex) {
      const t = xToT(x, width)
      dragRef.current = { type: 'bar', originT: t, originStart: trim.trimStart, originEnd: trim.trimEnd }
    } else {
      options.onSeek?.(xToT(x, width))
    }
  }, [tToX, xToT, trim, options])

  const onMouseMove = useCallback((e: React.MouseEvent<SVGElement>, width: number) => {
    const drag = dragRef.current
    if (!drag.type) return

    const t = xToT(e.nativeEvent.offsetX, width)

    setTrim((prev) => {
      let { trimStart, trimEnd } = prev

      if (drag.type === 'start') {
        const minT = Math.max(prev.ctxStart, prev.trimEnd - maxClip)
        const maxT = prev.trimEnd - MIN_CLIP
        trimStart = Math.max(minT, Math.min(maxT, t))
      } else if (drag.type === 'end') {
        const minT = prev.trimStart + MIN_CLIP
        const maxT = Math.min(prev.ctxEnd, prev.trimStart + maxClip)
        trimEnd = Math.max(minT, Math.min(maxT, t))
      } else if (drag.type === 'bar') {
        const duration = drag.originEnd - drag.originStart
        const delta = t - drag.originT
        trimStart = Math.max(prev.ctxStart, Math.min(prev.ctxEnd - duration, drag.originStart + delta))
        trimEnd = trimStart + duration
      }

      options.onTrimChange?.(trimStart, trimEnd)
      return { ...prev, trimStart, trimEnd }
    })
  }, [xToT, maxClip, options])

  const onMouseUp = useCallback(() => {
    if (dragRef.current.type) {
      setTrim((prev) => {
        options.onCommit?.(prev.trimStart, prev.trimEnd)
        return prev
      })
    }
    dragRef.current = { type: null, originT: 0, originStart: 0, originEnd: 0 }
  }, [options])

  return {
    trim,
    unlocked,
    tToX,
    xToT,
    setup,
    setLockState,
    onMouseDown,
    onMouseMove,
    onMouseUp,
  }
}
