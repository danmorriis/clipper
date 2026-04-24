import { useCallback, useRef } from 'react'
import type { ProgressEvent } from '../types'

type SSECallback = (event: ProgressEvent) => void

export function useSSE() {
  const esRef = useRef<EventSource | null>(null)

  const connect = useCallback((
    url: string,
    onEvent: SSECallback,
    onClose?: () => void,
    isTerminal?: (event: ProgressEvent) => boolean,
  ) => {
    // Close any existing connection
    esRef.current?.close()

    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)
        onEvent(data)
        const terminal = isTerminal
          ? isTerminal(data)
          : (!!data.done || !!data.error || !!data.cancelled)
        if (terminal) {
          es.close()
          esRef.current = null
          onClose?.()
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
      onClose?.()
    }
  }, [])

  const close = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
  }, [])

  return { connect, close }
}
